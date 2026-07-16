"""GAZBOT V7 — market-data capture (D5).

Ingests the live streams — aggressor ticks, L1 quotes, 5s time bars, L2 depth —
into a dedicated capture DB (kept separate from the trading store so high-volume
tick data never bloats the ledger; DuckDB reads across both at D9). Instrument-
parameterised: the LIVE desk trades MNQ only, but capture takes a symbol list, so
the shadow desk can watch MGC (or anything) without touching the live path.

``capture_health`` is the tested core: it classifies each stream and, crucially,
distinguishes a genuine **FEED_BREAK** (ticks live but 5s bars stale — the
``reqRealTimeBars`` farm dropped, the V5 scar whose fix is a gateway restart)
from ``NO_DATA`` (market closed / feed fully down). Clean-room: nothing copied.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

CAPTURE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    symbol TEXT NOT NULL, ts_ms INTEGER NOT NULL, price REAL NOT NULL,
    size REAL NOT NULL, aggressor TEXT NOT NULL          -- buy / sell / neutral
);
CREATE INDEX IF NOT EXISTS ix_ticks ON ticks(symbol, ts_ms);

CREATE TABLE IF NOT EXISTS quotes (
    symbol TEXT NOT NULL, ts_ms INTEGER NOT NULL,
    bid REAL, ask REAL, bid_sz REAL, ask_sz REAL
);
CREATE INDEX IF NOT EXISTS ix_quotes ON quotes(symbol, ts_ms);

CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL, bar_ts INTEGER NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, timeframe, bar_ts)
);

CREATE TABLE IF NOT EXISTS book (
    symbol TEXT NOT NULL, ts_ms INTEGER NOT NULL, side TEXT NOT NULL,  -- bid / ask
    level INTEGER NOT NULL, price REAL, size REAL
);
CREATE INDEX IF NOT EXISTS ix_book ON book(symbol, ts_ms);
"""


def open_capture(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(CAPTURE_SCHEMA)
    conn.commit()
    return conn


def record_tick(conn, symbol, ts_ms, price, size, aggressor) -> None:
    conn.execute(
        "INSERT INTO ticks (symbol, ts_ms, price, size, aggressor) VALUES (?,?,?,?,?)",
        (symbol, ts_ms, price, size, aggressor),
    )


def record_quote(conn, symbol, ts_ms, bid, ask, bid_sz, ask_sz) -> None:
    conn.execute(
        "INSERT INTO quotes (symbol, ts_ms, bid, ask, bid_sz, ask_sz) VALUES (?,?,?,?,?,?)",
        (symbol, ts_ms, bid, ask, bid_sz, ask_sz),
    )


def record_bar(conn, symbol, timeframe, bar_ts, o, h, low, c, volume) -> None:
    """Upsert a bar (a re-delivered in-progress bar updates in place)."""
    conn.execute(
        "INSERT INTO bars (symbol, timeframe, bar_ts, open, high, low, close, volume) "
        "VALUES (?,?,?,?,?,?,?,?) "
        "ON CONFLICT(symbol, timeframe, bar_ts) DO UPDATE SET "
        "high=excluded.high, low=excluded.low, close=excluded.close, volume=excluded.volume",
        (symbol, timeframe, bar_ts, o, h, low, c, volume),
    )


def record_book(conn, symbol, ts_ms, levels) -> None:
    """levels: iterable of (side, level, price, size). One snapshot at ts_ms."""
    conn.executemany(
        "INSERT INTO book (symbol, ts_ms, side, level, price, size) VALUES (?,?,?,?,?,?)",
        [(symbol, ts_ms, side, lvl, px, sz) for (side, lvl, px, sz) in levels],
    )


# ── health ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class StreamHealth:
    symbol: str
    tick_age_s: float | None
    bar5s_age_s: float | None
    status: str  # OK / FEED_BREAK / STALE / NO_DATA


def capture_health(
    conn,
    symbols,
    now_ms: int,
    *,
    tick_fresh_s: float = 15.0,
    bar_fresh_s: float = 30.0,
) -> list[StreamHealth]:
    out: list[StreamHealth] = []
    for sym in symbols:
        lt = conn.execute("SELECT MAX(ts_ms) FROM ticks WHERE symbol=?", (sym,)).fetchone()[0]
        lb = conn.execute(
            "SELECT MAX(bar_ts) FROM bars WHERE symbol=? AND timeframe='5s'", (sym,)
        ).fetchone()[0]
        tick_age = (now_ms - lt) / 1000.0 if lt is not None else None
        bar_age = (now_ms - lb * 1000) / 1000.0 if lb is not None else None
        ticks_live = tick_age is not None and tick_age <= tick_fresh_s
        bars_live = bar_age is not None and bar_age <= bar_fresh_s
        if ticks_live and bars_live:
            status = "OK"
        elif ticks_live and not bars_live:
            status = "FEED_BREAK"  # reqRealTimeBars farm dropped — fix is a gateway restart
        elif not ticks_live and not bars_live:
            status = "NO_DATA"  # market closed or feed fully down
        else:
            status = "STALE"  # bars live, ticks stale (unusual)
        out.append(StreamHealth(sym, tick_age, bar_age, status))
    return out


def recent_tape(conn, symbol: str, now_ms: int, *, window_s: int = 60) -> tuple[float, float, float | None]:
    """Aggressor summary over the trailing window: (net_flow buy−sell, price
    delta first→last, last price). The md service publishes this so strategy
    decides off the live stream, not a DB poll. Empty window → (0, 0, None)."""
    rows = conn.execute(
        "SELECT price, size, aggressor FROM ticks WHERE symbol=? AND ts_ms>=? ORDER BY ts_ms",
        (symbol, now_ms - window_s * 1000),
    ).fetchall()
    if not rows:
        return 0.0, 0.0, None
    buy = sum(r["size"] for r in rows if r["aggressor"] == "buy")
    sell = sum(r["size"] for r in rows if r["aggressor"] == "sell")
    return buy - sell, rows[-1]["price"] - rows[0]["price"], rows[-1]["price"]


def capitulation_tape(conn, symbol: str, now_ms: int, *, short_s: int = 20, base_s: int = 180) -> dict:
    """Aggressor-tape footprint for the capitulation gate (2026-07-16). Returns the
    last ``short_s`` seconds' sell/buy volume, a per-``short_s`` baseline (the mean
    over the trailing ``base_s`` window BEFORE the short window — for the climax
    ratio), and ``flip`` = are buyers taking over in the most recent half. The
    footprint of a flush bottom is a one-sided volume climax that then flips."""
    lo = now_ms - base_s * 1000
    short_cut = now_ms - short_s * 1000
    half_cut = now_ms - (short_s * 1000) // 2
    rows = conn.execute(
        "SELECT ts_ms, price, size, aggressor FROM ticks WHERE symbol=? AND ts_ms>=? AND ts_ms<=? ORDER BY ts_ms",
        (symbol, lo, now_ms),  # upper-bounded: only the trailing base_s up to now
    ).fetchall()
    if not rows:
        return {"sell": 0.0, "buy": 0.0, "base": 0.0, "dpx": 0.0, "flip": False}
    sell = buy = base_tot = half_sell = half_buy = 0.0
    first_px = last_px = None
    for r in rows:
        ts, px, sz, a = r["ts_ms"], r["price"], r["size"], r["aggressor"]
        if ts < short_cut:
            base_tot += sz  # baseline = everything before the short window
            continue
        if first_px is None:
            first_px = px
        last_px = px
        if a == "sell":
            sell += sz
        elif a == "buy":
            buy += sz
        if ts >= half_cut:
            if a == "sell":
                half_sell += sz
            elif a == "buy":
                half_buy += sz
    windows = max(1.0, (base_s - short_s) / short_s)  # how many short-windows in the baseline
    dpx = (last_px - first_px) if (first_px is not None and last_px is not None) else 0.0
    return {"sell": sell, "buy": buy, "base": base_tot / windows, "dpx": dpx, "flip": half_buy > half_sell}


# ── live ingest ───────────────────────────────────────────────────────────
def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _aggressor(last: float, bid: float | None, ask: float | None) -> str:
    if ask is not None and last >= ask:
        return "buy"
    if bid is not None and last <= bid:
        return "sell"
    return "neutral"


class CaptureManager:
    """Subscribes MNQ (+ any extra symbols) to 5s bars / L1 quotes / aggressor
    ticks / L2 depth via the gateway's IB, and writes to the capture store."""

    def __init__(self, gateway, cap_store, symbols, *, exchange: str = "CME",
                 depth_rows: int = 5, publisher=None) -> None:
        self._gw = gateway
        self._store = cap_store
        self._symbols = list(symbols)
        self._exchange = exchange
        self._depth_rows = depth_rows
        self._contracts: dict[str, object] = {}
        self._pub = publisher  # optional ipc.Publisher → live MD_STREAM (bars)

    async def start(self) -> None:
        from ib_async import ContFuture

        ib = self._gw._ib
        for sym in self._symbols:
            (qc,) = await ib.qualifyContractsAsync(ContFuture(sym, self._exchange))
            self._contracts[sym] = qc
            bars = ib.reqRealTimeBars(qc, 5, "TRADES", False)
            bars.updateEvent += self._bar_handler(sym)
            tkr = ib.reqMktData(qc, "", False, False)
            tkr.updateEvent += self._quote_handler(sym)
            tbt = ib.reqTickByTickData(qc, "AllLast", 0, False)
            tbt.updateEvent += self._tick_handler(sym)
            dom = ib.reqMktDepth(qc, self._depth_rows, False)
            dom.updateEvent += self._depth_handler(sym)

    def _bar_handler(self, sym):
        def h(bars, has_new_bar):
            b = bars[-1]
            ts = int(b.time.timestamp())
            record_bar(self._store, sym, "5s", ts, b.open_, b.high, b.low, b.close, b.volume)
            self._store.commit()
            if self._pub is not None:  # publish the closed bar to the live stream
                import asyncio

                from .ipc import T_BAR
                asyncio.ensure_future(self._pub.send(T_BAR, {
                    "symbol": sym, "tf": "5s", "ts": ts, "o": b.open_, "h": b.high,
                    "l": b.low, "c": b.close, "v": b.volume, "closed": True,
                }))

        return h

    def _quote_handler(self, sym):
        def h(tkr):
            record_quote(self._store, sym, _now_ms(), tkr.bid, tkr.ask, tkr.bidSize, tkr.askSize)
            self._store.commit()

        return h

    def _tick_handler(self, sym):
        def h(tkr):
            for t in tkr.tickByTicks:
                record_tick(self._store, sym, _now_ms(), t.price, t.size,
                            _aggressor(t.price, tkr.bid, tkr.ask))
            self._store.commit()

        return h

    def _depth_handler(self, sym):
        def h(tkr):
            ts = _now_ms()
            levels = [("bid", i, d.price, d.size) for i, d in enumerate(tkr.domBids)]
            levels += [("ask", i, d.price, d.size) for i, d in enumerate(tkr.domAsks)]
            if levels:
                record_book(self._store, sym, ts, levels)
                self._store.commit()

        return h
