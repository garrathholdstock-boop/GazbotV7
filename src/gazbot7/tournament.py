"""GAZBOT V7 — the multi-slot paper-tournament runner.

Composes the three tournament modules into a runnable desk:
    md bars/tape → SlotStrategy.decide (per-slot intents) → MultiSlotCore (execution)
    venue fills  → MultiSlotCore.on_fill  ·  reconcile loop → drift halt

Per-gate P&L falls out for free: every slot's round-trip is recorded with its own
``gate`` tag, so summing ``trades`` by gate gives each gate's standalone P&L — the
ranking the tournament runs on.

TWO MODES:
- **dry-run** (``place_live=False``, the default): subscribes to the REAL md feed,
  runs the slot decisions, and LOGS what each slot would do — NO gateway, NO orders,
  zero account risk. This proves the wiring + shows grind-long vs grind-short live
  before any cutover.
- **live** (``place_live=True``): connects the gateway and trades the paper account.
  ⚠ GATED — the per-slot venue-audit hardening (naked-auditor / adopt / wedge over the
  netted book, PAPER_TOURNAMENT_SCOPE §4) is DEFERRED; do NOT run live until it lands
  AND the single-position desk is stopped (one account — they must not co-trade).

Clean-room. The ``step`` helper is pure/testable; ``run`` is the I/O shell.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import replace

from .agg import MinuteBars
from .capture import open_capture
from .config import RunConfig
from .deciders import (
    CONFIRM_GATES,
    CONFIRM_MAX_SECS,
    CONFIRM_SECS,
    ER_HOLD,
    EXH_ADVERSE_PT,
    EXH_CONFIRM_GATES,
    EXH_CONFIRM_MAX_SECS,
    EXH_CONFIRM_SECS,
    VETO_FLOW_MIN,
    VETO_GATES,
    VETO_MAX_SECS,
    VETO_SECS,
    Position,
    atr_blocks,
    compute_features,
    confirm_absorption,
    efficiency_ratio,
    er_blocks,
    er_hold_blocks,
    exit_absorption,
)
from .footprint import footprint_summary
from .ipc import MD_STREAM, T_BAR, T_TAPE, Subscriber
from .sdnotify import sd_notify
from .slot_strategy import SlotStrategy, grind_long_short_slots, scaleout_slots, tournament_slots

# The tournament REPLACES gazbot7-core as the desk, so it takes the master clientId 0
# (full order visibility/adoption) — core must be stopped first (one account, no co-trade).
TOURNAMENT_CLIENT_ID = 0
SWITCH_FILE = "gate_switches.env"   # data/<this> — intraday per-gate on/off, re-read LIVE (no restart)

log = logging.getLogger("tournament")


def parse_switches(text: str) -> set:
    """Parse the gate on/off file: ``gate=off`` lines. off/0/no/false/disable → disabled.
    Blank lines and ``#`` comments ignored. Absent gate = ON (default). The operator (or a
    Telegram command bot) edits this file; the tournament re-reads it live to stop a gate's
    NEW entries — an open position on a disabled gate still rides its normal managed exit."""
    off = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if v.strip().lower() in ("off", "0", "no", "false", "disable", "disabled"):
            off.add(k.strip())
    return off


def _base(slot: str) -> str:
    """Base gate name of a (possibly dual-slot) tag: 'exhaustion_short_A' → 'exhaustion_short'.
    So base-name benching / the 55s veto / the exhaustion-confirm apply to BOTH sub-slots, while a
    full '_A'/'_B' tag still matches itself for granular control. A non-dual tag is returned as-is.
    ★2026-08-01 (audit FIX): None/'' tolerated. step() now calls _base(i.get("slot")) UNDEFAULTED on
    the ER/ATR floor path, so a malformed intent without a "slot" key used to be a harmless
    ``None in ER_FLOOR`` and would now be an AttributeError that kills the decision loop.
    Revert: return slot[:-2] if (slot.endswith("_A") or slot.endswith("_B")) else slot."""
    slot = slot or ""
    return slot[:-2] if (slot.endswith("_A") or slot.endswith("_B")) else slot


def read_disabled(path: str, cache: dict) -> set:
    """The disabled-gate set from the switch file, cached on (mtime, size) so it's cheap to
    call each tick yet re-reads the instant the file changes. Missing file → nothing disabled.
    Never raises — a bad read must not break the loop."""
    try:
        st = os.stat(path)
        key = (st.st_mtime, st.st_size)
    except OSError:
        cache["key"], cache["off"] = None, set()
        return cache["off"]
    if cache.get("key") != key:
        cache["key"] = key
        try:
            with open(path) as f:
                cache["off"] = parse_switches(f.read())
        except OSError:
            cache["off"] = set()
    return cache.get("off", set())

_STALE_TAPE_MS = 10_000
_STALE_BAR_MS = 30_000


def step(strat: SlotStrategy, mb: MinuteBars, tape: dict, slotbook, now_ms: int,
         footprint: dict | None = None) -> list[dict]:
    """One decision cycle → per-slot intents (or []). Pure: freshness-gated, reads the
    rolling 1-min bars + the latest tape + the footprint summary (for the capitulation /
    exhaustion slots), defers to SlotStrategy. Then applies the per-gate ER (favourable-
    condition) gate: a momentum gate can't OPEN in chop, a reversion gate can't OPEN in a
    trend — the gate rides its normal managed exit if already open. No side effects."""
    tape_ts = tape.get("ts_ms", 0)
    if not tape_ts or now_ms - tape_ts > _STALE_TAPE_MS:
        return []
    if not mb.fresh(now_ms, _STALE_BAR_MS):
        return []
    bars = mb.bars()
    if len(bars) < 6:
        return []
    f = compute_features(bars)
    price = tape.get("last") or f.price
    # now_ms is the decision clock: NIPC needs it for its 13:00–15:00 UTC window, the 5s bar
    # folding, the 1-min trigger expiry, the 20-min cap and the 15:30 flat. Every other gate
    # ignores it (additive kwarg — no behaviour change).
    intents = strat.decide(f, price, bars, slotbook, tape.get("net_flow", 0.0), footprint, now_ms)
    er = efficiency_ratio(bars)
    kept = []
    for i in intents:
        slot = i.get("slot")
        if i.get("action") == "OPEN":
            # ★2026-08-01 FIX — pass _base(slot). ER_FLOOR/ATR_FLOOR are keyed on BASE gate names,
            # but under the dual-slot scale-out slate every tag carries an _A/_B suffix, so the raw
            # tag never matched and EVERY floor silently returned "don't block" from 07-29 16:20
            # onward (383 de-duped blocked episodes in the 8d before, zero after). _base() was already
            # applied at the benching / veto / confirm sites below — these two calls were missed.
            # Revert (kill switch for the floor values too): drop the two _base() calls.
            if er_blocks(_base(slot), er):        # wrong regime (chop for momentum / trend for reversion)
                log.info("ER gate: %s OPEN suppressed (er=%.2f, unfavourable condition)", slot, er)
                continue
            if atr_blocks(_base(slot), f.atr):    # trend too small to run (magnitude floor)
                log.info("ATR gate: %s OPEN suppressed (atr=%.1fpt below floor)", slot, f.atr)
                continue
            # SHADOW (observe-only, 2026-07-23): would the momentum ER-hold spike-filter block this
            # OPEN (ER not held ER_HOLD[slot] consecutive bars)? Recorded on the intent + logged; the
            # trade STILL opens — this does not gate live until forward-validated → promoted.
            # ★2026-08-01 (audit FIX) — SAME BUG CLASS as the two floor calls above, and MISSED by
            # that fix: ER_HOLD is keyed on BASE gate names, so under the scale-out slate
            # 'abs_veto_long_A' never matched and this shadow has recorded NOTHING since the 07-29
            # cutover. Observe-only, so no trading behaviour changes — but the measurement it exists
            # to collect was silently dead. Revert: drop the two _base() calls on this block.
            base = _base(slot)
            if base in ER_HOLD:
                meta = i.setdefault("meta", {})
                meta["shadow_er_hold_block"] = er_hold_blocks(base, bars)
                meta["er_now"], meta["er_prev"] = round(er, 3), round(efficiency_ratio(bars[:-1]), 3)
                if meta["shadow_er_hold_block"]:
                    log.info("SHADOW er-hold(N=%d): %s OPEN would block (er_now=%.2f er_prev=%.2f) "
                             "— observe-only, trade still opens", ER_HOLD[base], slot,
                             meta["er_now"], meta["er_prev"])
        kept.append(i)
    return kept


def _ensure_live_cfg(cfg: RunConfig, place_live: bool) -> RunConfig:
    """Keep the run switch and cfg coherent: a live run needs cfg.place_live too, else
    _build_live connects read-only and the core rejects every order ("place_live off") —
    a silent no-trade desk. Idempotent; only lifts False→True for a live run."""
    return replace(cfg, place_live=True) if place_live and not cfg.place_live else cfg


async def run(specs=None, cfg: RunConfig | None = None, *, place_live: bool = False,
              max_seconds: float | None = None) -> None:
    cfg = _ensure_live_cfg(cfg or RunConfig(), place_live)
    specs = specs or grind_long_short_slots()
    gates = [s.tag for s in specs]

    cap = open_capture(cfg.capture_path)              # kept OPEN for footprint reads each tick
    mb = MinuteBars(cfg.bar_lookback)
    mb.warm(cap, cfg.symbol, cfg.bar_lookback)
    needs_fp = any(s.kind in ("capitulation", "exhaustion") for s in specs)
    switch_path = os.path.join(os.path.dirname(cfg.store_path) or ".", SWITCH_FILE)
    switch_cache: dict = {}
    last_disabled: set = set()

    strat = SlotStrategy(specs, value_per_point=cfg.value_per_point)
    core = None
    gw = None
    audit_task = None
    if place_live:
        core, gw = await _build_live(cfg, gates)   # gateway + engine + per-slot safety + MultiSlotCore
        adopted = core.reconstruct()               # rebuild open slots + stops from OUR ledger (netted venue can't)
        if adopted:
            log.warning("tournament ADOPTED %d open slot(s) from store: %s", len(adopted), adopted)
        # ★★2026-08-07 ORPHAN SWEEP — runs AFTER reconstruct() so the live stop set is known.
        # Two restart defects made orphans both inevitable and uncancellable: the stop sequence
        # restarts at 0 (re-minting refs that are still resting at IBKR, so fills mis-attribute)
        # and the coid->Trade map is in-memory (so cancel() no-ops on anything placed before the
        # restart). GTC stops 1505/1506 sat ~2000pt away for DAYS as a result, and by 14:48 on
        # 08-07 had collided with the live stops of exhaustion_short_A/B. This adopts every
        # resting stp-* order, pushes the sequence past the highest, and cancels the ones no slot
        # owns. It cannot touch the day-rider's stop (orderRef '') or any manual order.
        try:
            sweep = core._broker.adopt_and_sweep(core.owned_stop_coids())
            if sweep.get("cancelled"):
                log.warning("tournament ORPHAN SWEEP: %s", sweep)
                _telegram_notifier(f"orphan sweep on startup: cancelled {sweep['cancelled']} "
                                   f"unowned stop(s), stop_seq now {sweep.get('stop_seq')}")
            else:
                log.info("tournament orphan sweep: %s", sweep)
        except Exception as e:                     # a failed sweep must never block the desk
            log.warning("tournament orphan sweep failed: %s", e)
        audit_task = asyncio.ensure_future(core.venue_audit_loop(gw))  # reconciles adopted state vs IBKR net
    else:
        from .slotbook import SlotBook
        slotbook = SlotBook(gates, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)

    md = Subscriber(MD_STREAM, topics=[T_BAR, T_TAPE])
    tape: dict = {}
    log.info("tournament %s — slots=%s", "LIVE" if place_live else "DRY-RUN", gates)
    start = time.monotonic()
    last_hb = 0.0
    audit_stale_paged = False
    pending_confirm: dict = {}   # ★ rgv 35s absorption-confirm buffer: slot → (armed_ms, intent)
    pending_veto: dict = {}      # ★ abs_veto 55s momentum-veto buffer: slot → (armed_ms, intent)
    pending_exh: dict = {}       # ★ exhaustion 5s confirm-veto buffer: slot → (armed_ms, intent)
    if place_live:
        sd_notify("READY=1")                       # Type=notify — tournament is up (no-op off systemd)
    try:
        while max_seconds is None or (time.monotonic() - start) < max_seconds:
            if place_live and gw is not None:      # own core_health.json/status.json (liveness)
                now_mono = time.monotonic()
                core.expire_pending_opens(now_mono)   # free a gate whose entry IOC never filled (+log nofill)
                if now_mono - last_hb >= 1.0:
                    core.write_heartbeat(conn=gw.state.value, healthy=gw.healthy)
                    # WATCHDOG is gated on the AUDIT loop's liveness, not just this loop's. If the
                    # safety spine (naked/drift/max-hold/stop-breach) has gone stale, WITHHOLD the
                    # ping → systemd (WatchdogSec=90) restarts the desk → it re-adopts open slots
                    # from the ledger and the revived loop fires any overdue exit. A dead auditor
                    # now SELF-HEALS in ~90s instead of riding a position all night (2026-07-22 −$216).
                    if core.audit_stale():
                        if not audit_stale_paged:
                            audit_stale_paged = True
                            _telegram_notifier("AUDIT LOOP STALE — safety spine not completing cycles; "
                                               "withholding the systemd watchdog so the desk AUTO-RESTARTS "
                                               "(~90s) to revive it. Any open slot is re-adopted from the ledger.")
                        log.error("audit loop stale → withholding WATCHDOG ping (systemd will restart)")
                    else:
                        audit_stale_paged = False
                        sd_notify("WATCHDOG=1")    # both loops live → prove it → systemd holds off
                    last_hb = now_mono
            msg = await md.poll(500)
            if msg is None:
                continue
            topic, body = msg
            if topic == T_BAR:
                # ★★2026-08-04 CRITICAL — FILTER BY SYMBOL. md publishes every captured symbol on one
                # stream and always tagged it, but this consumer folded them ALL into the MNQ deque.
                # Harmless while md captured one symbol; the moment MGC was added to capture (17:30
                # today) gold bars (~3,300) interleaved with MNQ bars (~29,800) and true range across
                # that jump is astronomic. ATR read 1848.16 against a true 15.11 — 122x — and the desk
                # opened two abs_veto_short lots at 22:02 with stops 1,848 points away instead of ~15,
                # i.e. ~$3,700 of risk per lot instead of ~$30. Every gate threshold is ATR-relative,
                # so this corrupted entries and exits simultaneously.
                # The bug was latent for the entire life of the desk and only a config change exposed
                # it. Anything consuming MD_STREAM must filter: the stream is multi-symbol by design.
                if body.get("symbol") != cfg.symbol:
                    continue
                mb.fold(body["ts"], body["o"], body["h"], body["l"], body["c"], body["v"])
            elif topic == T_TAPE:
                tape = body
                if core is not None:
                    core.note_price(tape.get("last"))   # feed the stop-breach guard
                now_ms = int(time.time() * 1000)
                book = core._sb if core is not None else slotbook
                fp = footprint_summary(cap, cfg.symbol, now_ms) if needs_fp else None
                disabled = read_disabled(switch_path, switch_cache)   # intraday per-gate off-switch (live)
                if disabled != last_disabled:
                    log.warning("gate switches changed → DISABLED (no new entries): %s", sorted(disabled) or "none")
                    last_disabled = set(disabled)
                intents = step(strat, mb, tape, book, now_ms, fp)
                if disabled:   # a disabled gate takes NO new entries; its open position still exits normally
                    kept = []
                    for i in intents:
                        if i.get("action") == "OPEN" and (i.get("slot") in disabled or _base(i.get("slot", "")) in disabled):
                            # SUPPRESSED-OPEN: record what the gate WOULD have traded — the exact
                            # counterfactual the filter used to drop SILENTLY. Greppable for a clean
                            # gated-vs-ungated ("everything left on") P&L, live, per day.
                            log.info("SUPPRESSED-OPEN: %s %s would open @%s (disabled by switch) t=%d",
                                     i.get("slot"), i.get("side", ""), i.get("price", ""), now_ms)
                        else:
                            kept.append(i)
                    intents = kept
                # ★ rgv 35s ABSORPTION-CONFIRM (LIVE 2026-07-24, operator): buffer an rgv OPEN, wait
                # CONFIRM_SECS, take the fade ONLY if the faded move ABSORBED in that window. The
                # strategy proposes OPEN only when flat, so the not-pending guard is enough. SAFETY:
                # any read error / not-yet-absorbed → DON'T enter (never a bad fill); stale → drop.
                out = []
                for i in intents:
                    # ★2026-08-01 (audit FIX) — _base(), same bug class as the ER/ATR floors and the
                    # ER_HOLD shadow. CONFIRM_GATES is empty today so this is INERT, but it is keyed
                    # on base names ({"rgv_long","rgv_short"} when populated), so re-arming the 35s
                    # absorption-confirm would have silently done nothing under the scale-out slate.
                    # Matches the VETO_GATES / EXH_CONFIRM_GATES sites below. Revert: drop _base().
                    if i.get("action") == "OPEN" and _base(i.get("slot", "")) in CONFIRM_GATES:
                        pending_confirm.setdefault(i["slot"], (now_ms, i))   # arm once; do NOT emit yet
                    else:
                        out.append(i)
                for slot in list(pending_confirm):
                    armed_ms, intent = pending_confirm[slot]
                    age = (now_ms - armed_ms) / 1000.0
                    if age < CONFIRM_SECS:
                        continue
                    ok = None
                    try:
                        rows = cap.execute(
                            "SELECT aggressor,size,price FROM ticks WHERE symbol=? AND ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
                            (cfg.symbol, armed_ms, now_ms)).fetchall()
                        if len(rows) >= 5:
                            flow = sum((s if a == "buy" else -s) for a, s, _ in rows)
                            ok = confirm_absorption(intent.get("side", ""), flow, rows[-1][2] - rows[0][2])
                    except Exception as e:
                        log.warning("rgv confirm read failed %s: %s — dropping", slot, e)
                        ok = False
                    if ok:
                        j = dict(intent)
                        j["price"] = tape.get("last") or intent.get("price")
                        out.append(j)
                        del pending_confirm[slot]
                        log.info("rgv CONFIRM: %s ABSORBED after %.0fs → OPEN @%s", slot, age, j["price"])
                    elif age > CONFIRM_MAX_SECS or ok is False:
                        del pending_confirm[slot]   # move not absorbed / turn gone → skip the fade
                        log.info("rgv confirm: %s NOT absorbed after %.0fs → skipped", slot, age)
                intents = out
                # ★ abs_veto 55s momentum VETO (LIVE 2026-07-25, operator): buffer an abs_veto thrust
                # OPEN, wait VETO_SECS, take it ONLY if the thrust STILL fires (re-emitted this tick,
                # slot flat) AND the burst was NOT absorbed over the window. Faithful promotion of the
                # shadow abs_veto_55s end-decision. SAFETY: any read error / <5 ticks / thrust gone →
                # VETO or skip (never a bad fill); a tape-gap past VETO_MAX_SECS drops the stale signal.
                fired_now = {i.get("slot") for i in intents if i.get("action") == "OPEN"}
                vout = []
                for i in intents:
                    if i.get("action") == "OPEN" and _base(i.get("slot", "")) in VETO_GATES:
                        pending_veto.setdefault(i["slot"], (now_ms, i))   # arm once; do NOT emit yet
                    else:
                        vout.append(i)
                for slot in list(pending_veto):
                    armed_ms, intent = pending_veto[slot]
                    age = (now_ms - armed_ms) / 1000.0
                    if age < VETO_SECS:
                        continue                          # still watching the burst
                    if age > VETO_MAX_SECS or slot not in fired_now:
                        del pending_veto[slot]            # tape gap / thrust no longer firing → skip
                        log.info("abs_veto: %s thrust gone/stale after %.0fs → skipped", slot, age)
                        continue
                    absorbed = True                       # default-VETO on any read failure / thin tape
                    try:
                        rows = cap.execute(
                            "SELECT aggressor,size,price FROM ticks WHERE symbol=? AND ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
                            (cfg.symbol, armed_ms, now_ms)).fetchall()
                        if len(rows) >= 5:
                            flow = sum((s if a == "buy" else -s) for a, s, _ in rows)
                            absorbed = exit_absorption(Position(intent.get("side", ""), 0.0, 0.0, 0.0),
                                                       tape_net=flow, window_price_delta=rows[-1][2] - rows[0][2],
                                                       flow_min=VETO_FLOW_MIN) is not None
                    except Exception as e:
                        log.warning("abs_veto read failed %s: %s — vetoing", slot, e)
                    if absorbed:
                        del pending_veto[slot]
                        log.info("abs_veto: %s ABSORBED (fakeout) after %.0fs → vetoed", slot, age)
                    else:
                        j = dict(intent)
                        j["price"] = tape.get("last") or intent.get("price")
                        vout.append(j)
                        del pending_veto[slot]
                        log.info("abs_veto: %s clean thrust after %.0fs → OPEN @%s", slot, age, j["price"])
                intents = vout
                # ★ exhaustion 5s CONFIRM-VETO (LIVE 2026-07-29, operator): buffer an exhaustion_short
                # OPEN, wait EXH_CONFIRM_SECS, take it ONLY if the fade has NOT gone adverse by more
                # than EXH_ADVERSE_PT over the window (buyers still pushing = absorption failed → skip).
                # Backtest: cuts fast-failing shorts, 0 winners cut, +$9→+$236 / 89 faithful shadow fires.
                # SAFETY: any read error / <3 ticks → default-SKIP (never a bad fill); stale → drop.
                eout = []
                for i in intents:
                    if i.get("action") == "OPEN" and _base(i.get("slot", "")) in EXH_CONFIRM_GATES:
                        pending_exh.setdefault(i["slot"], (now_ms, i))   # arm once; do NOT emit yet
                    else:
                        eout.append(i)
                for slot in list(pending_exh):
                    armed_ms, intent = pending_exh[slot]
                    age = (now_ms - armed_ms) / 1000.0
                    if age < EXH_CONFIRM_SECS:
                        continue                          # still watching the confirm window
                    adverse = True                        # default-SKIP on any read failure / thin tape
                    try:
                        rows = cap.execute(
                            "SELECT price FROM ticks WHERE symbol=? AND ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
                            (cfg.symbol, armed_ms, now_ms)).fetchall()
                        if len(rows) >= 3:
                            sig_px = intent.get("price")
                            if intent.get("side") == "SHORT":
                                adverse = (max(r[0] for r in rows) - sig_px) > EXH_ADVERSE_PT
                            else:                          # LONG fade: adverse = price fell
                                adverse = (sig_px - min(r[0] for r in rows)) > EXH_ADVERSE_PT
                    except Exception as e:
                        log.warning("exh confirm read failed %s: %s — skipping", slot, e)
                    if adverse or age > EXH_CONFIRM_MAX_SECS:
                        del pending_exh[slot]
                        log.info("exh confirm: %s adverse/stale after %.0fs → vetoed", slot, age)
                    else:
                        j = dict(intent)
                        j["price"] = tape.get("last") or intent.get("price")
                        eout.append(j)
                        del pending_exh[slot]
                        log.info("exh confirm: %s held after %.0fs → OPEN @%s", slot, age, j["price"])
                intents = eout
                if not intents:
                    continue
                if place_live:
                    await core.on_intents(intents)
                else:
                    for i in intents:
                        log.info("[DRY] %s %s side=%s qty=%s @%s", i["action"], i["slot"],
                                 i.get("side", ""), i.get("qty", ""), i.get("price", ""))
    finally:
        if audit_task is not None:
            audit_task.cancel()
        md.close()
        cap.close()
        if gw is not None:
            await gw.stop()


def _telegram_notifier(msg: str) -> None:
    """Per-slot safety alarms (naked / drift-halt / wedge / unverified / flatten) MUST page —
    a silent live desk is the 2026-07-17 naked-bleed class. All tournament alerts are safety."""
    from .notify import notify
    notify(f"[V7-tournament] {msg}", critical=True)


async def _build_live(cfg: RunConfig, gates):
    """Live execution wiring (paper account). The per-slot venue-audit loop (naked/adopt/wedge/
    time-exit) is started by the caller; here we build the gateway + engine + per-slot safety +
    MultiSlotCore, with the operator notifier wired through so every safety alarm pages."""
    from ib_async import ContFuture, Future

    from .broker_adapter import IBBrokerAdapter
    from .engine import OrderEngine
    from .ib_gateway import IBGateway
    from .multislot_core import MultiSlotCore
    from .safety import SafetyManager
    from .slotbook import SlotBook
    from .store import open_store

    store = open_store(cfg.store_path)
    gw = IBGateway(cfg.host, cfg.port, client_id=cfg.client_id, readonly=not cfg.place_live)
    ref: dict = {}
    await gw.start()
    (contract,) = await gw._ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))
    # Protective stops must REST on the concrete front-month Future, NOT the ContFuture: IBKR
    # intermittently never fires a resting stop's trigger on a continuous contract (stuck
    # PreSubmitted/whyHeld='trigger' → the stop-breach guard market-flattens = STOP_UNFILLED). The
    # ContFuture already resolved the front month, so its conId IS the concrete contract — qualify a
    # Future off that conId. Same conId → positions/naked-audit reconcile at the venue.
    (stop_contract,) = await gw._ib.qualifyContractsAsync(Future(conId=contract.conId, exchange=cfg.exchange))
    broker = IBBrokerAdapter(gw._ib, contract, cfg.symbol,
                             on_fill=lambda f: ref["core"].on_fill(f),
                             on_stop_event=lambda coid, status: None,
                             stop_contract=stop_contract)
    engine = OrderEngine(broker, store)
    slotbook = SlotBook(gates, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
    safeties = {g: SafetyManager(broker, notifier=_telegram_notifier) for g in gates}
    core = MultiSlotCore(cfg, engine, slotbook, safeties, publisher=None, store=store,
                         notifier=_telegram_notifier)
    ref["core"] = core
    core._broker = broker          # ★2026-08-07 handle for the startup orphan sweep (see below)
    return core, gw


_SLATES = {"tournament": tournament_slots, "grind2": grind_long_short_slots,
           "scaleout": scaleout_slots}   # ★2026-07-29 dual-slot scale-out (A@R scalp + B chandelier)


def main() -> None:  # `python -m gazbot7.tournament`  (GAZBOT7_TOURNAMENT_LIVE=1 to trade)
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    live = os.environ.get("GAZBOT7_TOURNAMENT_LIVE") == "1"
    slate = _SLATES.get(os.environ.get("GAZBOT7_TOURNAMENT_SLATE", "tournament"), tournament_slots)
    cfg = RunConfig(place_live=live, client_id=TOURNAMENT_CLIENT_ID)
    specs = slate()
    # ★2026-08-04: journal the RESOLVED exit ladder before trading. Tracking exit_overrides.json in git
    # makes the config visible; this makes it HISTORICAL, so "what was live at 14:00 last Thursday?" is
    # answerable without reading git log and guessing. See config_journal's docstring for the study that
    # failed for want of it. Wrapped: a journal failure must never stop the desk from starting.
    try:
        from .config_journal import record as _journal_config
        _journal_config(specs, slate=os.environ.get("GAZBOT7_TOURNAMENT_SLATE", "tournament"),
                        place_live=live)
    except Exception as e:                                  # pragma: no cover - defensive only
        logging.getLogger("tournament").warning("config journal skipped: %s", e)
    asyncio.run(run(specs, cfg, place_live=live))


if __name__ == "__main__":
    raise SystemExit(main())
