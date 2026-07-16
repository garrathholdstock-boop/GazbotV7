"""GAZBOT V7 — the honest tick repricer (D8).

Scores every shadow trade on the real tick path, not the optimistic bar price.
The entry fills at the far touch (cross the spread), the 1-ATR stop and the
R-target are replayed on tick mids, and the exit fills at the far touch — so the
spread and the true stop/target ordering are baked in. This is the ONLY number
the shadow desk is judged on (``shadow_real.real_pnl``).

Critically, the R-target scalp leg is priced natively here — the V5 repricer
couldn't see the ``rtarget`` leg and left such strategies' honest P&L blank
(dip_loose_absorption). That class is impossible in V7: reprice replays the
target the same as the stop. Clean-room: nothing copied.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

from .store import record_shadow_real


class Quote(NamedTuple):
    ts_ms: int
    bid: float
    ask: float


def reprice(trade, quotes: list[Quote], *, value_per_point: float, fee_rt: float):
    """Return (real_pnl, fill_status). ``trade`` is a shadow_trades row/dict with
    side, entry_atr, target_r, stop_atr_mult, qty. ``quotes`` span entry→exit."""
    if not quotes:
        return None, "no_data"
    side = trade["side"]
    atr = trade["entry_atr"]
    tr = trade["target_r"]
    sm = trade["stop_atr_mult"]
    qty = trade["qty"]

    entry = quotes[0].ask if side == "LONG" else quotes[0].bid  # far-touch entry
    r = sm * atr
    if side == "LONG":
        stop, target = entry - r, entry + tr * r
    else:
        stop, target = entry + r, entry - tr * r

    exit_px = None
    for q in quotes[1:]:
        mid = (q.bid + q.ask) / 2.0
        if side == "LONG":
            if mid <= stop:
                exit_px = q.bid
                break
            if mid >= target:
                exit_px = q.bid
                break
        else:
            if mid >= stop:
                exit_px = q.ask
                break
            if mid <= target:
                exit_px = q.ask
                break
    if exit_px is None:  # ran to the end of the window → fill at the last touch
        exit_px = quotes[-1].bid if side == "LONG" else quotes[-1].ask

    if side == "LONG":
        gross = (exit_px - entry) * value_per_point * qty
    else:
        gross = (entry - exit_px) * value_per_point * qty
    return gross - fee_rt, "filled"


def _quotes_for(cap_conn, symbol: str, lo_ms: int, hi_ms: int) -> list[Quote]:
    rows = cap_conn.execute(
        "SELECT ts_ms, bid, ask FROM quotes WHERE symbol=? AND ts_ms>=? AND ts_ms<=? "
        "AND bid IS NOT NULL AND ask IS NOT NULL ORDER BY ts_ms",
        (symbol, lo_ms, hi_ms),
    ).fetchall()
    return [Quote(r["ts_ms"], r["bid"], r["ask"]) for r in rows]


def reprice_pending(store, cap_conn, *, value_per_point: float, fee_rt: float,
                    tail_ms: int = 120_000, bar_s: int = 60) -> int:
    """Reprice every shadow_trade not yet in shadow_real, using captured quotes.
    Returns how many were newly repriced.

    UNITS: shadow ``entry_ts``/``exit_ts`` are minute-aligned bar starts in
    SECONDS (from MinuteBars); captured ``quotes.ts_ms`` are MILLISECONDS — so the
    bar ts must be ×1000. The signal only fires once the 1-minute bar CLOSES
    (ts + ``bar_s``), so the honest entry is the first quote AFTER the close —
    filling at the minute start would be a pre-signal (lookahead) fill and would
    overstate the edge."""
    done = {r[0] for r in store.execute("SELECT trade_id FROM shadow_real")}
    now = datetime.now(UTC).isoformat()
    n = 0
    for t in store.execute("SELECT * FROM shadow_trades ORDER BY id").fetchall():
        if t["id"] in done:
            continue
        lo_ms = (t["entry_ts"] + bar_s) * 1000       # first tick after the bar closed
        hi_ms = (t["exit_ts"] + bar_s) * 1000 + tail_ms
        quotes = _quotes_for(cap_conn, t["symbol"], lo_ms, hi_ms)
        pnl, status = reprice(t, quotes, value_per_point=value_per_point, fee_rt=fee_rt)
        record_shadow_real(
            store, trade_id=t["id"], strategy=t["strategy"], symbol=t["symbol"],
            real_pnl=pnl, fill_status=status, repriced_at=now,
        )
        n += 1
    return n
