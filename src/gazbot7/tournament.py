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
from .deciders import ER_HOLD, atr_blocks, compute_features, efficiency_ratio, er_blocks, er_hold_blocks
from .footprint import footprint_summary
from .ipc import MD_STREAM, T_BAR, T_TAPE, Subscriber
from .sdnotify import sd_notify
from .slot_strategy import SlotStrategy, grind_long_short_slots, tournament_slots

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
    intents = strat.decide(f, price, bars, slotbook, tape.get("net_flow", 0.0), footprint)
    er = efficiency_ratio(bars)
    kept = []
    for i in intents:
        slot = i.get("slot")
        if i.get("action") == "OPEN":
            if er_blocks(slot, er):        # wrong regime (chop for momentum / trend for reversion)
                log.info("ER gate: %s OPEN suppressed (er=%.2f, unfavourable condition)", slot, er)
                continue
            if atr_blocks(slot, f.atr):    # trend too small to run (magnitude floor)
                log.info("ATR gate: %s OPEN suppressed (atr=%.1fpt below floor)", slot, f.atr)
                continue
            # SHADOW (observe-only, 2026-07-23): would the momentum ER-hold spike-filter block this
            # OPEN (ER not held ER_HOLD[slot] consecutive bars)? Recorded on the intent + logged; the
            # trade STILL opens — this does not gate live until forward-validated → promoted.
            if slot in ER_HOLD:
                meta = i.setdefault("meta", {})
                meta["shadow_er_hold_block"] = er_hold_blocks(slot, bars)
                meta["er_now"], meta["er_prev"] = round(er, 3), round(efficiency_ratio(bars[:-1]), 3)
                if meta["shadow_er_hold_block"]:
                    log.info("SHADOW er-hold(N=%d): %s OPEN would block (er_now=%.2f er_prev=%.2f) "
                             "— observe-only, trade still opens", ER_HOLD[slot], slot,
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
                    intents = [i for i in intents if not (i.get("action") == "OPEN" and i.get("slot") in disabled)]
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
    from ib_async import ContFuture

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
    broker = IBBrokerAdapter(gw._ib, contract, cfg.symbol,
                             on_fill=lambda f: ref["core"].on_fill(f),
                             on_stop_event=lambda coid, status: None)
    engine = OrderEngine(broker, store)
    slotbook = SlotBook(gates, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
    safeties = {g: SafetyManager(broker, notifier=_telegram_notifier) for g in gates}
    core = MultiSlotCore(cfg, engine, slotbook, safeties, publisher=None, store=store,
                         notifier=_telegram_notifier)
    ref["core"] = core
    return core, gw


_SLATES = {"tournament": tournament_slots, "grind2": grind_long_short_slots}


def main() -> None:  # `python -m gazbot7.tournament`  (GAZBOT7_TOURNAMENT_LIVE=1 to trade)
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    live = os.environ.get("GAZBOT7_TOURNAMENT_LIVE") == "1"
    slate = _SLATES.get(os.environ.get("GAZBOT7_TOURNAMENT_SLATE", "tournament"), tournament_slots)
    cfg = RunConfig(place_live=live, client_id=TOURNAMENT_CLIENT_ID)
    asyncio.run(run(slate(), cfg, place_live=live))


if __name__ == "__main__":
    raise SystemExit(main())
