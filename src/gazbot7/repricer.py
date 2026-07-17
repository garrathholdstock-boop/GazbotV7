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

from .deciders import Position as _Pos
from .deciders import exit_chandelier as _exit_chandelier
from .store import record_shadow_real


class Quote(NamedTuple):
    ts_ms: int
    bid: float
    ask: float


def reprice(trade, quotes: list[Quote], *, value_per_point: float, fee_rt: float,
            chand: tuple[float, float, float] | None = None):
    """Return (real_pnl, fill_status). ``trade`` is a shadow_trades row/dict with
    side, entry_atr, target_r, stop_atr_mult, qty. ``quotes`` span entry→exit.
    ``chand`` = (start_k, min_k, tighten) for the chandelier leg — each variant's own
    trail; None → the live default (3.5, 0.5, 0.75). Non-chandelier trades ignore it."""
    if not quotes:
        return None, "no_data"
    side = trade["side"]
    atr = trade["entry_atr"]
    tr = trade["target_r"]
    sm = trade["stop_atr_mult"]
    qty = trade["qty"]

    entry = quotes[0].ask if side == "LONG" else quotes[0].bid  # far-touch entry
    if entry <= 0 or atr <= 0:  # belt-and-braces: never score off a junk price/ATR
        return None, "no_data"
    r = sm * atr
    stop = entry - r if side == "LONG" else entry + r
    chandelier = tr <= 0  # target_r=0 sentinel → ride the tightening chandelier, not a fixed target
    target = None if chandelier else (entry + tr * r if side == "LONG" else entry - tr * r)
    sk, mk, tt = chand if chand is not None else (3.5, 0.5, 0.75)

    peak = 0.0
    exit_px = None
    for q in quotes[1:]:
        mid = (q.bid + q.ask) / 2.0
        fav = (mid - entry) if side == "LONG" else (entry - mid)
        peak = max(peak, fav)
        hit_stop = (mid <= stop) if side == "LONG" else (mid >= stop)
        if hit_stop:
            exit_px = q.bid if side == "LONG" else q.ask
            break
        if chandelier:
            if _exit_chandelier(_Pos(side, entry, atr, peak), mid, start_k=sk, min_k=mk, tighten=tt):
                exit_px = q.bid if side == "LONG" else q.ask
                break
        else:
            hit_tgt = (mid >= target) if side == "LONG" else (mid <= target)
            if hit_tgt:
                exit_px = q.bid if side == "LONG" else q.ask
                break
    if exit_px is None:  # ran to the end of the window → fill at the last touch
        exit_px = quotes[-1].bid if side == "LONG" else quotes[-1].ask

    if side == "LONG":
        gross = (exit_px - entry) * value_per_point * qty
    else:
        gross = (entry - exit_px) * value_per_point * qty
    return gross - fee_rt, "filled"


def _quotes_for(cap_conn, symbol: str, lo_ms: int, hi_ms: int) -> list[Quote]:
    # ``bid > 0 AND ask > 0`` rejects IBKR's no-quote SENTINEL (-1.0), which is NOT
    # NULL so an ``IS NOT NULL`` filter lets it through — a −1 fill priced a +$70
    # winner as −$58,350 ((−1 − 29175)·2), and once written it froze (2026-07-17).
    rows = cap_conn.execute(
        "SELECT ts_ms, bid, ask FROM quotes WHERE symbol=? AND ts_ms>=? AND ts_ms<=? "
        "AND bid > 0 AND ask > 0 ORDER BY ts_ms",
        (symbol, lo_ms, hi_ms),
    ).fetchall()
    return [Quote(r["ts_ms"], r["bid"], r["ask"]) for r in rows]


def reprice_pending(store, cap_conn, *, value_per_point: float, fee_rt: float,
                    tail_ms: int = 120_000, bar_s: int = 60,
                    chand_params: dict[str, tuple[float, float, float]] | None = None) -> int:
    """Reprice every shadow_trade not yet in shadow_real, using captured quotes.
    Returns how many were newly repriced.

    ``chand_params`` maps strategy → (start_k, min_k, tighten) so each chandelier
    variant is replayed on its OWN trail; None → derive it from the live slate (so a
    tighter variant is never silently scored at the 3.5 default, whoever calls this).

    UNITS: shadow ``entry_ts``/``exit_ts`` are minute-aligned bar starts in
    SECONDS (from MinuteBars); captured ``quotes.ts_ms`` are MILLISECONDS — so the
    bar ts must be ×1000. The signal only fires once the 1-minute bar CLOSES
    (ts + ``bar_s``), so the honest entry is the first quote AFTER the close —
    filling at the minute start would be a pre-signal (lookahead) fill and would
    overstate the edge."""
    if chand_params is None:
        from .shadow import chandelier_params  # lazy: avoid an import cycle at module load
        chand_params = chandelier_params()
    done = {r[0] for r in store.execute("SELECT trade_id FROM shadow_real")}
    now = datetime.now(UTC).isoformat()
    # latest CLEAN captured quote per symbol. A trade whose window extends past this
    # is DEFERRED (re-tried next pass once capture catches up), never scored — and
    # frozen — on a truncated window. The −$58k poison came from repricing a
    # session-close hold at 22:01 whose window ran to 22:03 (2026-07-17).
    cap_max = {r[0]: r[1] for r in cap_conn.execute(
        "SELECT symbol, max(ts_ms) FROM quotes WHERE bid > 0 AND ask > 0 GROUP BY symbol")}
    n = 0
    for t in store.execute("SELECT * FROM shadow_trades ORDER BY id").fetchall():
        if t["id"] in done:
            continue
        lo_ms = (t["entry_ts"] + bar_s) * 1000       # first tick after the bar closed
        hi_ms = (t["exit_ts"] + bar_s) * 1000 + tail_ms
        if cap_max.get(t["symbol"], 0) < hi_ms:
            continue  # window not fully captured yet — defer, don't freeze a partial score
        quotes = _quotes_for(cap_conn, t["symbol"], lo_ms, hi_ms)
        pnl, status = reprice(t, quotes, value_per_point=value_per_point, fee_rt=fee_rt,
                              chand=chand_params.get(t["strategy"]))
        record_shadow_real(
            store, trade_id=t["id"], strategy=t["strategy"], symbol=t["symbol"],
            real_pnl=pnl, fill_status=status, repriced_at=now,
        )
        n += 1
    return n
