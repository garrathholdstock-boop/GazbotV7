"""Read the L2 book out of `depth.db` for a live shadow sim. Read-only, fail-closed.

★★2026-08-15. The MGC gold gates need the order book, and there is NO FREE IBKR DEPTH SUBSCRIPTION —
all three are in use (`gazbot7-depth-capture` = MNQ + MGC at 10 levels / 250ms, `md` = MNQ at 5
levels / 41ms). So the shadow service READS what depth-capture already writes; it must not subscribe.

⚠ AND `capture.db.book` HAS NO MGC AT ALL — gold's depth only ever lands in `depth.db`. A reader
pointed at capture.db would return nothing for MGC, forever, with no error. That is the shape of
mistake this module exists to make impossible.

★ THE CAUSALITY RULE, and it is the whole reason this is not three lines inline: the snapshot used
must be the last one AT OR BEFORE the entry stamp — NEVER the next one. Reaching forward by even one
250ms sample would let the gate see the book AFTER price arrived at the level, which is precisely
the thing it is trying to predict. That look-ahead would flatter the exact feature under test.
"""

from __future__ import annotations

import sqlite3

DEPTH_DB = "/home/alphabot/gazbot7/data/depth.db"
MAX_STALE_MS = 5_000        # a snapshot older than this is not "the book now"
MAX_SPREAD_PT = 5.0         # sanity: a wider quote is a crossed/torn book, not a market


class DepthFeed:
    """Last-known book at or before a timestamp, for one symbol."""

    def __init__(self, symbol: str, path: str = DEPTH_DB, max_stale_ms: int = MAX_STALE_MS):
        self._symbol = symbol
        self._path = path
        self._max_stale = max_stale_ms
        self._cols = ", ".join(f"bid{k}p, bid{k}s, ask{k}p, ask{k}s" for k in range(1, 11))
        self._conn: sqlite3.Connection | None = None

    def _c(self) -> sqlite3.Connection | None:
        """Open lazily and READ-ONLY. depth-capture is writing to this file continuously; a reader
        that took a write lock could stall the capture that every gold study depends on."""
        if self._conn is None:
            try:
                self._conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True, timeout=2.0)
                self._conn.row_factory = sqlite3.Row
            except Exception:
                return None
        return self._conn

    def book_at(self, ts_ms: int) -> dict | None:
        """The last snapshot at or before `ts_ms`, or None.

        Returns None — never a guess — when: the file is unreadable, there is no snapshot at or
        before the stamp, the newest one is older than `max_stale_ms`, or the quote is nonsense
        (non-positive prices, crossed, or a spread beyond MAX_SPREAD_PT). Every caller treats None
        as "do not trade", so a gap in the feed costs a missed trade and never a wrong one.
        """
        c = self._c()
        if c is None:
            return None
        try:
            row = c.execute(
                f"SELECT ts_ms, {self._cols} FROM depth_snap "
                f"WHERE symbol=? AND ts_ms<=? ORDER BY ts_ms DESC LIMIT 1",
                (self._symbol, int(ts_ms)),
            ).fetchone()
        except Exception:
            return None
        if row is None:
            return None
        if int(ts_ms) - int(row["ts_ms"]) > self._max_stale:
            return None                      # stale: the venue is shut, or capture has stopped
        b1, a1 = row["bid1p"], row["ask1p"]
        if not b1 or not a1 or b1 <= 0 or a1 <= 0:
            return None
        if not (0.0 <= a1 - b1 <= MAX_SPREAD_PT):
            return None                      # crossed or torn — not a market
        return {k: row[k] for k in row.keys()}

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
