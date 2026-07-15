"""GAZBOT V7 — the 5s→1-minute bar aggregator (shared).

Both the live strategy and the shadow desk decide on 1-minute bars (a 5-bar thrust
= a 5-MINUTE move; on 5s bars it was a 25s blip that fired constantly). They use
THIS one aggregator, so a shadow result can never drift from what the live desk
would do — the same guarantee the shared deciders give. Folds the 5s stream into
the forming minute; decisions read only the COMPLETED minutes. Clean-room.
"""

from __future__ import annotations

from collections import deque

from .deciders import Bar


class MinuteBars:
    """Rolling window of completed 1-minute bars, folded from a 5s bar stream."""

    def __init__(self, maxlen: int) -> None:
        self._bars: deque[Bar] = deque(maxlen=maxlen)
        self._cur: dict | None = None
        self.last_bar_ms = 0

    def fold(self, ts: int, o: float, h: float, l: float, c: float, v: float) -> None:
        self.last_bar_ms = ts * 1000
        m = (ts // 60) * 60
        cur = self._cur
        if cur is None or m > cur["min"]:
            if cur is not None:  # minute rolled over → finalise the completed 1m bar
                self._bars.append(Bar(cur["min"], cur["o"], cur["h"], cur["l"], cur["c"], cur["v"]))
            self._cur = {"min": m, "o": o, "h": h, "l": l, "c": c, "v": v}
        elif m == cur["min"]:
            cur["h"] = max(cur["h"], h)
            cur["l"] = min(cur["l"], l)
            cur["c"] = c
            cur["v"] += v
        # m < cur["min"]: an out-of-order/duplicate 5s bar — ignore

    def warm(self, cap_conn, symbol: str, lookback: int) -> None:
        rows = cap_conn.execute(
            "SELECT bar_ts, open, high, low, close, volume FROM bars "
            "WHERE symbol=? AND timeframe='5s' ORDER BY bar_ts DESC LIMIT ?",
            (symbol, lookback * 12 + 24),
        ).fetchall()
        for r in reversed(rows):
            self.fold(r["bar_ts"], r["open"], r["high"], r["low"], r["close"], r["volume"])

    def bars(self) -> list[Bar]:
        return list(self._bars)

    def fresh(self, now_ms: int, stale_ms: int) -> bool:
        return bool(self.last_bar_ms) and (now_ms - self.last_bar_ms) <= stale_ms
