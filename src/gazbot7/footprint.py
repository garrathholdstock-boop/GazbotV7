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


def _recent_ticks(cap, symbol: str, lo_ms: int, hi_ms: int):
    return cap.execute(
        "SELECT ts_ms, price, size, aggressor FROM ticks "
        "WHERE symbol=? AND ts_ms>=? AND ts_ms<=? ORDER BY ts_ms",
        (symbol, lo_ms, hi_ms),
    ).fetchall()


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
                 cfg: FootprintCfg = FootprintCfg(), name: str = "exhaustion_rev"):
        self._store = store
        self._sym = symbol
        self._vpp = value_per_point
        self._fee = fee_rt
        self._cfg = cfg
        self._name = name
        self._open: dict | None = None

    def on_cycle(self, cap, now_ms: int) -> None:
        if self._open is not None:
            self._try_close(cap, now_ms)
        if self._open is None:
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
        if sig is not None:
            side, entry = sig
            self._open = {"side": side, "entry_ts": now_ms // 1000, "entry_price": entry}

    # ── exit: first 8pt stop / 12pt target on the tick path, else 120s time ──────
    def _try_close(self, cap, now_ms: int) -> None:
        op = self._open
        entry_ms = op["entry_ts"] * 1000
        ticks = _recent_ticks(cap, self._sym, entry_ms + 1, now_ms)
        e = op["entry_price"]
        if op["side"] == "SHORT":
            stop, tgt = e + STOP_PT, e - TARGET_PT
        else:
            stop, tgt = e - STOP_PT, e + TARGET_PT
        exit_px = exit_ts = reason = None
        for ts, px, _sz, _agg in ticks:
            hit_stop = (px >= stop) if op["side"] == "SHORT" else (px <= stop)
            hit_tgt = (px <= tgt) if op["side"] == "SHORT" else (px >= tgt)
            if hit_stop:
                exit_px, exit_ts, reason = stop, ts // 1000, "STOP"; break
            if hit_tgt:
                exit_px, exit_ts, reason = tgt, ts // 1000, "TARGET"; break
            if ts // 1000 - op["entry_ts"] >= HOLD_S:
                exit_px, exit_ts, reason = px, ts // 1000, "TIME"; break
        if exit_px is None:
            if now_ms // 1000 - op["entry_ts"] >= HOLD_S and ticks:
                exit_px, exit_ts, reason = ticks[-1][1], ticks[-1][0] // 1000, "TIME"
            else:
                return  # still open, no touch yet
        self._record(op, exit_px, exit_ts, reason)
        self._open = None

    def _record(self, op, exit_price, exit_ts, reason) -> None:
        if op["side"] == "LONG":
            gross = (exit_price - op["entry_price"]) * self._vpp
        else:
            gross = (op["entry_price"] - exit_price) * self._vpp
        record_shadow_trade(
            self._store,
            strategy=self._name, symbol=self._sym, side=op["side"], qty=1.0,
            entry_ts=op["entry_ts"], entry_price=op["entry_price"],
            entry_atr=STOP_PT,           # 8 → repricer: stop = 1.0×8 = 8pt, target = 1.5×8 = 12pt
            target_r=TARGET_PT / STOP_PT, stop_atr_mult=1.0,
            exit_ts=exit_ts, exit_price=exit_price, exit_reason=reason,
            ceiling_pnl=gross - self._fee,
        )
