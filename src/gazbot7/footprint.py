"""GAZBOT V7 — the exhaustion-reversal footprint, SHADOW/observe-only.

The one genuinely new microstructure footprint from the L1/L2 hunt: fade heavy aggression
that can't move price into a resting wall. When one side dumps hard, price refuses to
follow, and there's a real wall on the side being hit → the next move is the FLIP.

Unlike the bar-based shadow slate, this is a TICK+BOOK gate, so it rides its own loop:
each cycle it reads the last 20s of aggressor ticks + the level-1 book, fires on the
tightened thresholds the 3-day backtest found were the consistent survivor (net≥400,
price-move≤2pt, hit-side wall≥1.5×), and manages one open position exited on the tick
path (8pt stop / 12pt target / 120s). It records to `shadow_trades` as `exhaustion_rev`
with entry_atr=8 / stop_atr_mult=1.0 / target_r=1.5 so the honest repricer replays the
exact 8pt/12pt exit on quotes. NEVER touches IBKR — research breadth only.

Verdict at build time (3 days): real direction, still SUB-COST and not yet significant
(t<2), but genuinely DIVERSIFIES rgv (−0.13 corr, two-sided, 70% non-overlapping). This
is INCUBATION — accumulate ~15-20 captured days before it's re-judged. Nothing arms.
"""
from __future__ import annotations

from dataclasses import dataclass

from .store import record_shadow_trade

# exit legs, in points (MNQ)
STOP_PT = 8.0
TARGET_PT = 12.0
HOLD_S = 120


@dataclass(frozen=True, slots=True)
class ExitLeg:
    """ONE exit policy hung off the shared exhaustion signal.

    ★★2026-08-16 (operator: "restart on 1.5 and shadow the 2.0"). The live gate moved to a wide
    ATR stop, and the open question is 1.5 vs 2.0 xATR. That could not be asked here before: the
    exit was two module constants in POINTS with no ATR anywhere in this loop.

    ★ WHY LEGS AND NOT THREE FootprintShadow INSTANCES. Detection is the expensive half (a tick
    scan plus a book read every cycle); the exit is arithmetic. Three instances would triple the
    scanning AND — the part that actually matters — let the arms drift onto DIFFERENT entries,
    because each would hold its own position and be busy at different moments. An exit comparison
    on non-identical entries is not a comparison. One signal, N legs, same fill.

    `mode="pt"`  — stop/target in POINTS (the legacy 8/12 that exhaustion_rev must keep)
    `mode="atr"` — stop/target as MULTIPLES OF ATR-14 at entry, which is how the live gate and the
                   report's grid both express it (report "stop 1.5xATR / target 2.0R" = 1.5 / 3.0).
    """

    name: str
    stop: float
    target: float
    mode: str = "pt"
    hold_s: int = HOLD_S
    # ★2026-08-16 (audit) GROUPS. Re-entry is gated per GROUP, not across all legs. Legs in one group
    # share every entry — that is what makes them an exit comparison. Legs in DIFFERENT groups are
    # independent, so a long-riding arm cannot starve a short-capped one.
    # Default "" means "my own group", i.e. fully independent, which is what the legacy control needs.
    group: str = ""

    @property
    def grp(self) -> str:
        return self.group or self.name


# The legacy single leg. exhaustion_rev is a PROTECTED control and the entry substrate for seven
# shipped scripts — it must stay bit-identical, so it is the default and its numbers are unchanged.
LEGACY_LEG = ExitLeg("exhaustion_rev", STOP_PT, TARGET_PT, "pt", HOLD_S)

# ★ The 1.5-vs-2.0 question, both arms in ONE harness. Comparing the live 1.5 against a shadow 2.0
# would confound stop width with the harness (the shadow book leaks past its own stops on 44% of
# trades), which is exactly the bias that makes the wide-stop grid suspect in the first place.
# Target is held CONSTANT at 3.0xATR so only the stop varies — the live config's target distance.
# ⚠⚠ hold_s IS NOT 0. The first version used 0 ("the graded cell was 'no cap'") and an audit found
# two consequences, both bad:
#   1. THE PROTECTED CONTROL LOST 56% OF ITS ENTRIES. on_cycle takes a new signal only when EVERY leg
#      is flat, so an uncapped leg riding for hours blocks exhaustion_rev — whose own cap is 120s.
#      Replayed on 171 real signals: 95 of them BLOCKED, and exh_w20 held up to 360 minutes without
#      resolving. The control's 664-row history would have been joined by a differently-sampled
#      population with nothing marking the change.
#   2. UNBOUNDED TICK SCAN. _try_close re-reads ticks from entry to now on every cycle with no LIMIT,
#      against a 5.6GB capture.db on a 7.5GB box with three prior OOM kills. An uncapped leg grows
#      that range forever, and once the entry falls out of capture's 5-day window it can never close.
# 7200s (2h) matches the desk's own global max_hold_minutes=120 — the outer backstop every live
# position already has — so the legs cannot outlive what the real desk would allow anyway, and the
# "no cap" the grid tested is preserved in practice for all but the extreme tail.
_LEG_CAP_S = 7200

# group="wide": these two share every entry with EACH OTHER (the 1.5-vs-2.0 comparison) but are
# independent of exhaustion_rev, so the 120s control keeps its own sampling and its 664-row history
# stays comparable to itself.
WIDE_LEGS = [
    ExitLeg("exh_w15", 1.5, 3.0, "atr", _LEG_CAP_S, group="wide"),   # mirrors what went live 08-16
    ExitLeg("exh_w20", 2.0, 3.0, "atr", _LEG_CAP_S, group="wide"),   # better on the grid, but
]                                                                    # monotonic to its edge


@dataclass(frozen=True, slots=True)
class FootprintCfg:
    net_min: float = 400.0     # |20s net signed aggressor volume| floor (contracts)
    move_max: float = 2.0      # price may have moved at most this many points over the window
    wall_ratio: float = 1.5    # near-touch resting size on the HIT side ≥ this × the far side
    window_s: int = 20


def exhaustion_signal(net_signed: float, price_move_pt: float,
                      bid1_size: float, ask1_size: float,
                      bid1_price: float, ask1_price: float,
                      cfg: FootprintCfg = FootprintCfg()) -> tuple[str, float] | None:
    """The pure gate. net_signed = 20s (buy_vol − sell_vol); price_move_pt = signed price
    change over the window. Returns (side, entry_price) to FADE, or None.

    Buy-heavy tape absorbed into an ask wall → SHORT; sell-heavy into a bid wall → LONG.
    """
    if abs(net_signed) < cfg.net_min:
        return None
    if abs(price_move_pt) > cfg.move_max:          # the aggression DID move price → not absorption
        return None
    if bid1_size <= 0 or ask1_size <= 0:
        return None
    mid = (bid1_price + ask1_price) / 2.0
    if net_signed > 0:                              # buyers lifting; hit side = ASK
        if ask1_size >= cfg.wall_ratio * bid1_size:
            return ("SHORT", mid)
    else:                                           # sellers hitting; hit side = BID
        if bid1_size >= cfg.wall_ratio * ask1_size:
            return ("LONG", mid)
    return None


def footprint_summary(cap, symbol: str, now_ms: int, *, window_s: int = 20) -> dict:
    """One aggressor-tape + L1-book roll-up feeding BOTH footprint gates, computed from
    the capture DB — the tournament calls this each tape tick (the shadow loop does the
    same). Reuses ``capitulation_tape`` (the climax cap_* inputs) and the exhaustion
    inputs (20s signed net + price move + the level-1 book). Read-only; a bad/empty read
    returns zeros so the gates simply don't fire."""
    from .capture import capitulation_tape

    c = capitulation_tape(cap, symbol, now_ms)
    ticks = _recent_ticks(cap, symbol, now_ms - window_s * 1000, now_ms)
    net = sum((t[2] if t[3] == "buy" else -t[2]) for t in ticks if t[3] in ("buy", "sell"))
    move = (ticks[-1][1] - ticks[0][1]) if len(ticks) >= 2 else 0.0
    bp, bs, ap, as_ = _book_l1(cap, symbol, now_ms)
    return {
        "cap_sell": c["sell"], "cap_buy": c["buy"], "cap_base": c["base"],
        "cap_dpx": c["dpx"], "cap_flip": c["flip"],
        "net_signed": net, "price_move_pt": move,
        "bid1_size": bs or 0.0, "ask1_size": as_ or 0.0,
        "bid1_price": bp or 0.0, "ask1_price": ap or 0.0,
    }


def _recent_ticks(cap, symbol: str, lo_ms: int, hi_ms: int):
    return cap.execute(
        "SELECT ts_ms, price, size, aggressor FROM ticks "
        "WHERE symbol=? AND ts_ms>=? AND ts_ms<=? ORDER BY ts_ms",
        (symbol, lo_ms, hi_ms),
    ).fetchall()


def _atr14(cap, symbol: str, at_ms: int):
    """ATR-14 over 1-minute bars ending at `at_ms`, or None.

    ★2026-08-16 — this loop is tick+book driven and had NO bar context at all, which is why its exit
    could only ever be expressed in fixed points. An ATR leg needs one number, once per signal, so
    this is a single small query at entry (fires are 33-100/day) rather than anything continuous.

    ⚠ Returns None rather than a guess when the window is short. Callers stand the ATR legs down on
    None — an ATR arm that quietly fell back to points would report a "2.0xATR" result that was
    never measured at 2.0xATR, which is worse than not recording.

    ⚠ capture.db carries 5 TRADING days and MULTIPLE SYMBOLS — hence the explicit symbol filter and
    the 1-minute fold from the 5s bars (`bar_ts - bar_ts % 60`); reading 5s bars as minutes is a trap
    this desk has already paid for.
    """
    try:
        rows = cap.execute(
            "SELECT (bar_ts - bar_ts % 60) m, MAX(high) hi, MIN(low) lo "
            "FROM bars WHERE symbol=? AND timeframe='5s' AND bar_ts>=? AND bar_ts<=? "
            "GROUP BY 1 ORDER BY 1", (symbol, at_ms // 1000 - 20 * 60, at_ms // 1000)).fetchall()
    except Exception:
        return None
    if len(rows) < 14:
        return None
    rng = [r[1] - r[2] for r in rows[-14:]]
    atr = sum(rng) / len(rng)
    return atr if atr > 0 else None


def _book_l1(cap, symbol: str, at_ms: int):
    """Most-recent level-1 (bid_price, bid_size, ask_price, ask_size) at or before at_ms."""
    def latest(side):
        r = cap.execute(
            "SELECT price, size FROM book WHERE symbol=? AND side=? AND level=1 AND ts_ms<=? "
            "ORDER BY ts_ms DESC LIMIT 1", (symbol, side, at_ms),
        ).fetchone()
        return (r[0], r[1]) if r else (None, None)
    bp, bs = latest("bid")
    ap, as_ = latest("ask")
    return bp, bs, ap, as_


class FootprintShadow:
    """Observe-only exhaustion-reversal evaluator. Call on_cycle() each shadow tick with
    the capture connection + current ms. Maintains one open position, records closed
    trades to shadow_trades. Fail-safe: the caller must guard it so it can never break
    the shadow loop."""

    def __init__(self, store, symbol: str, *, value_per_point: float, fee_rt: float,
                 cfg: FootprintCfg = FootprintCfg(), name: str = "exhaustion_rev",
                 legs: list | None = None):
        self._store = store
        self._sym = symbol
        self._vpp = value_per_point
        self._fee = fee_rt
        self._cfg = cfg
        self._name = name
        # ★2026-08-16 ONE SIGNAL, N EXIT LEGS. `legs=None` reproduces the pre-existing single 8/12pt
        # arm under `name`, so exhaustion_rev — a protected control and the entry substrate for seven
        # shipped scripts — is untouched by default.
        self._legs = list(legs) if legs else [ExitLeg(name, STOP_PT, TARGET_PT, "pt", HOLD_S)]
        # per-leg open positions. Was a single dict; now keyed by leg name so the legs can exit at
        # different moments while still having entered on the SAME fill.
        self._open: dict[str, dict] = {}
        # ★2026-07-28 (operator): net-flow instrumentation — log the entry net_signed with every
        # fire so the net_min threshold (400 vs 450 vs 500) can be tuned from real data. Own table,
        # additive, best-effort (never breaks the shadow loop). Join to shadow_trades on trade_id.
        try:
            self._store.execute(
                "CREATE TABLE IF NOT EXISTS footprint_signal_net ("
                "trade_id INTEGER, strategy TEXT, side TEXT, entry_ts INTEGER, "
                "net_signed REAL, price_move REAL, bid1 REAL, ask1 REAL)")
            self._store.commit()
        except Exception:
            pass

    def on_cycle(self, cap, now_ms: int) -> None:
        if self._open:
            self._try_close(cap, now_ms)
        # ★ Re-entry is per GROUP (audit fix). Within a group every leg enters on the same fill, so
        # the comparison is of the exit alone. Across groups they are independent — otherwise an
        # uncapped 2h arm starves the 120s control, which measurement showed it did: 95 of 171 real
        # signals blocked. Any group with no open leg is offered the signal.
        if len(self._open) < len(self._legs):
            self._try_open(cap, now_ms)

    # ── entry ────────────────────────────────────────────────────────────────
    def _try_open(self, cap, now_ms: int) -> None:
        ticks = _recent_ticks(cap, self._sym, now_ms - self._cfg.window_s * 1000, now_ms)
        if len(ticks) < 3:
            return
        net = sum((t[2] if t[3] == "buy" else -t[2]) for t in ticks if t[3] in ("buy", "sell"))
        move = ticks[-1][1] - ticks[0][1]
        bp, bs, ap, as_ = _book_l1(cap, self._sym, now_ms)
        if bp is None or ap is None:
            return
        sig = exhaustion_signal(net, move, bs or 0, as_ or 0, bp, ap, self._cfg)
        if sig is None:
            return
        side, entry = sig
        # ATR-14 is only needed when a leg asks for it, and it costs a bar query — so compute it
        # ONCE per signal, and only if some leg is in atr mode. None -> those legs stand down rather
        # than silently falling back to points, which would report a 2.0xATR arm that was never one.
        atr = _atr14(cap, self._sym, now_ms) if any(l.mode == "atr" for l in self._legs) else None
        base = {"side": side, "entry_ts": now_ms // 1000, "entry_price": entry,
                "net_signed": net, "price_move": move,
                "bid1": bs or 0.0, "ask1": as_ or 0.0, "atr": atr}
        busy = {self._open[n]["leg"].grp for n in self._open}
        for leg in self._legs:
            if leg.name in self._open or leg.grp in busy:
                continue      # this group is mid-trade; it does not see this signal
            if leg.mode == "atr" and not (atr and atr > 0):
                continue      # no ATR -> no ATR-based arm. Fails CLOSED, and visibly (no row).
            self._open[leg.name] = dict(base, leg=leg)

    # ── exit: first 8pt stop / 12pt target on the tick path, else 120s time ──────
    def _try_close(self, cap, now_ms: int) -> None:
        # One tick read serves every open leg — they entered on the same fill, so they walk the same
        # tape. Reading it per leg would be N identical scans of capture.db every cycle.
        entry_ms = min(op["entry_ts"] for op in self._open.values()) * 1000
        ticks = _recent_ticks(cap, self._sym, entry_ms + 1, now_ms)
        for name in list(self._open):
            op = self._open[name]
            leg = op["leg"]
            e = op["entry_price"]
            if leg.mode == "atr":
                stop_d, tgt_d = leg.stop * op["atr"], leg.target * op["atr"]
            else:
                stop_d, tgt_d = leg.stop, leg.target
            if op["side"] == "SHORT":
                stop, tgt = e + stop_d, e - tgt_d
            else:
                stop, tgt = e - stop_d, e + tgt_d
            exit_px = exit_ts = reason = None
            for ts, px, _sz, _agg in ticks:
                if ts <= op["entry_ts"] * 1000:
                    continue
                hit_stop = (px >= stop) if op["side"] == "SHORT" else (px <= stop)
                hit_tgt = (px <= tgt) if op["side"] == "SHORT" else (px >= tgt)
                if hit_stop:
                    exit_px, exit_ts, reason = stop, ts // 1000, "STOP"; break
                if hit_tgt:
                    exit_px, exit_ts, reason = tgt, ts // 1000, "TARGET"; break
                # hold_s = 0 means NO time cap — the report's graded cell was "no cap", and a hidden
                # 120s cap would silently make it a different policy.
                if leg.hold_s and ts // 1000 - op["entry_ts"] >= leg.hold_s:
                    exit_px, exit_ts, reason = px, ts // 1000, "TIME"; break
            if exit_px is None:
                if leg.hold_s and now_ms // 1000 - op["entry_ts"] >= leg.hold_s and ticks:
                    exit_px, exit_ts, reason = ticks[-1][1], ticks[-1][0] // 1000, "TIME"
                else:
                    continue  # this leg is still open; others may not be
            self._record(op, exit_px, exit_ts, reason, name=name, leg=leg)
            del self._open[name]

    def _record(self, op, exit_price, exit_ts, reason, *, name=None, leg=None) -> None:
        if op["side"] == "LONG":
            gross = (exit_price - op["entry_price"]) * self._vpp
        else:
            gross = (op["entry_price"] - exit_price) * self._vpp
        leg = leg or LEGACY_LEG
        # ★ THE REPRICER MUST REPLAY THE LEG'S OWN GEOMETRY, NOT THE LEGACY 8/12.
        # It reconstructs the exit from (entry_atr, stop_atr_mult, target_r): stop distance is
        # stop_atr_mult x entry_atr, target is target_r x that. The legacy trick was to store
        # entry_atr=8 with mult 1.0 so 1.5R replayed as 12pt. For an ATR leg we store the REAL ATR
        # and the real multiples, so 1.5xATR / 3.0xATR replays as target_r = 3.0/1.5 = 2.0 — which
        # is exactly how the live slot is configured. Getting this wrong would silently reprice
        # every arm at the legacy 8/12 and the whole comparison would be of one policy with itself.
        if leg.mode == "atr":
            entry_atr, stop_mult = float(op["atr"]), leg.stop
            target_r = leg.target / leg.stop
        else:
            entry_atr, stop_mult = leg.stop, 1.0
            target_r = leg.target / leg.stop
        tid = record_shadow_trade(
            self._store,
            strategy=(name or self._name), symbol=self._sym, side=op["side"], qty=1.0,
            entry_ts=op["entry_ts"], entry_price=op["entry_price"],
            entry_atr=entry_atr, target_r=target_r, stop_atr_mult=stop_mult,
            exit_ts=exit_ts, exit_price=exit_price, exit_reason=reason,
            ceiling_pnl=gross - self._fee,
        )
        # net-flow log (best-effort, observe-only — never break recording)
        try:
            self._store.execute(
                "INSERT INTO footprint_signal_net "
                "(trade_id, strategy, side, entry_ts, net_signed, price_move, bid1, ask1) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (tid, self._name, op["side"], op["entry_ts"], op.get("net_signed"),
                 op.get("price_move"), op.get("bid1"), op.get("ask1")))
            self._store.commit()
        except Exception:
            pass
