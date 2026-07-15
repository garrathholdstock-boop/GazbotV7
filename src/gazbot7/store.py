"""GAZBOT V7 — the persistence store (D0).

The one source of truth for *what executed* is the ``fills`` table, keyed by
IBKR's ``exec_id`` (the primary key). Applying the same fill twice is a no-op —
idempotency is enforced at the schema level, so no caller, on any path, can
double-count a fill. This is the bedrock the order/fill state machine (D3) is
built on: because a fill can be safely re-applied, both the fast per-order path
and any account-wide path may deliver it, and the second delivery is absorbed
rather than racing (the exact fragility that produced V5's partial-fill
backfill class).

Clean-room: nothing here is copied from V5. SQLite (WAL) is the operational
store; DuckDB is the analytics layer over it (added at D9). No legacy cached
columns (e.g. V5's lying ``positions.stop_*``) exist here.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

# ── schema ────────────────────────────────────────────────────────────────
# Core operational tables. Shadow/research tables (shadow_trades, shadow_real)
# arrive at D8; the monitor's verdicts already have a home here (exec_health).
SCHEMA = """
CREATE TABLE IF NOT EXISTS fills (
    exec_id     TEXT PRIMARY KEY,                 -- IBKR execId; THE idempotency key
    order_id    TEXT NOT NULL,                    -- our client order id
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    qty         REAL NOT NULL CHECK (qty > 0),
    price       REAL NOT NULL CHECK (price > 0),  -- no synthetic px=0 executions, ever (V5 VCORR scar)
    commission  REAL NOT NULL DEFAULT 0,
    exec_time   TEXT NOT NULL,                    -- ISO8601 UTC (venue time)
    kind        TEXT NOT NULL DEFAULT 'fill',
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fills_order ON fills(order_id);
CREATE INDEX IF NOT EXISTS ix_fills_time  ON fills(exec_time);

CREATE TABLE IF NOT EXISTS orders (
    client_order_id TEXT PRIMARY KEY,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    qty         REAL NOT NULL CHECK (qty > 0),
    order_type  TEXT NOT NULL,                    -- LMT / MKT / STP / …
    limit_price REAL,
    status      TEXT NOT NULL,                    -- PENDING/WORKING/PARTIAL/FILLED/CANCELLED/REJECTED
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    side          TEXT NOT NULL CHECK (side IN ('LONG','SHORT')),
    qty           REAL NOT NULL CHECK (qty > 0),
    entry_price   REAL NOT NULL,
    exit_price    REAL NOT NULL,
    entry_exec_id TEXT,
    exit_exec_id  TEXT,                           -- idempotency handle for the close (D3)
    opened_at     TEXT NOT NULL,
    closed_at     TEXT NOT NULL,
    pnl_usd       REAL NOT NULL,                  -- net of fees, venue truth
    fees_usd      REAL NOT NULL DEFAULT 0,
    exit_reason   TEXT NOT NULL,                  -- a REAL reason, never a backfill placeholder
    gate          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_trades_exit_exec
    ON trades(exit_exec_id) WHERE exit_exec_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS positions (
    symbol     TEXT PRIMARY KEY,
    net_qty    REAL NOT NULL,                     -- signed: + long, - short (venue truth)
    avg_price  REAL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    gate           TEXT NOT NULL,
    side           TEXT,
    outcome        TEXT NOT NULL,                 -- submitted / blocked
    block_reason   TEXT,
    intended_price REAL
);

CREATE TABLE IF NOT EXISTS shadow_trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy      TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    side          TEXT NOT NULL CHECK (side IN ('LONG','SHORT')),
    qty           REAL NOT NULL,
    entry_ts      INTEGER NOT NULL,
    entry_price   REAL NOT NULL,
    entry_atr     REAL NOT NULL,          -- carried so the repricer can replay stop/target
    target_r      REAL NOT NULL,
    stop_atr_mult REAL NOT NULL,
    exit_ts       INTEGER NOT NULL,
    exit_price    REAL NOT NULL,
    exit_reason   TEXT NOT NULL,
    ceiling_pnl   REAL NOT NULL           -- optimistic bar-price pnl; NEVER scored on
);

CREATE TABLE IF NOT EXISTS shadow_real (
    trade_id    INTEGER PRIMARY KEY,      -- FK -> shadow_trades.id
    strategy    TEXT,
    symbol      TEXT,
    real_pnl    REAL,                     -- honest tick-repriced pnl (the ONLY score)
    fill_status TEXT,
    repriced_at TEXT
);

CREATE TABLE IF NOT EXISTS exec_health (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    kind       TEXT NOT NULL,                     -- PIPELINE / INTEGRITY / <symbol>
    status     TEXT NOT NULL,                     -- OK / WARN / CRIT
    detail     TEXT
);
"""


# ── types ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Fill:
    """An immutable venue execution. ``exec_id`` is the idempotency key."""

    exec_id: str
    order_id: str
    symbol: str
    side: str  # 'BUY' | 'SELL'
    qty: float
    price: float
    exec_time: str  # ISO8601 UTC
    commission: float = 0.0
    kind: str = "fill"


# ── helpers ───────────────────────────────────────────────────────────────
def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def open_store(path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the V7 store: WAL, FK on, schema applied."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def record_fill(conn: sqlite3.Connection, fill: Fill) -> bool:
    """Idempotently record a venue fill.

    Returns ``True`` if this fill was newly inserted, ``False`` if its
    ``exec_id`` was already present (a no-op — the second observer of the same
    execution). Never raises on a duplicate; that is the whole point.
    """
    row = asdict(fill)
    row["ingested_at"] = _utcnow_iso()
    cur = conn.execute(
        "INSERT INTO fills "
        "(exec_id, order_id, symbol, side, qty, price, commission, exec_time, kind, ingested_at) "
        "VALUES "
        "(:exec_id, :order_id, :symbol, :side, :qty, :price, :commission, :exec_time, :kind, :ingested_at) "
        "ON CONFLICT(exec_id) DO NOTHING",
        row,
    )
    conn.commit()
    return cur.rowcount == 1


def upsert_order(
    conn: sqlite3.Connection,
    *,
    client_order_id: str,
    symbol: str,
    side: str,
    qty: float,
    order_type: str,
    status: str,
    limit_price: float | None = None,
) -> None:
    """Insert or update an order by its client_order_id (we own the id)."""
    now = _utcnow_iso()
    conn.execute(
        "INSERT INTO orders "
        "(client_order_id, symbol, side, qty, order_type, limit_price, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(client_order_id) DO UPDATE SET "
        "status=excluded.status, limit_price=excluded.limit_price, updated_at=excluded.updated_at",
        (client_order_id, symbol, side, qty, order_type, limit_price, status, now, now),
    )
    conn.commit()


def get_order(conn: sqlite3.Connection, client_order_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
    ).fetchone()


def record_trade(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    side: str,  # LONG / SHORT
    qty: float,
    entry_price: float,
    exit_price: float,
    opened_at: str,
    closed_at: str,
    pnl_usd: float,
    fees_usd: float,
    exit_reason: str,
    entry_exec_id: str | None = None,
    exit_exec_id: str | None = None,
    gate: str | None = None,
) -> bool:
    """Record a closed round-trip. Idempotent on ``exit_exec_id`` (the fill that
    brought the position flat) — completing the same close twice is a no-op.
    Returns True if newly written, False if it was already recorded."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO trades "
        "(symbol, side, qty, entry_price, exit_price, entry_exec_id, exit_exec_id, "
        " opened_at, closed_at, pnl_usd, fees_usd, exit_reason, gate) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (symbol, side, qty, entry_price, exit_price, entry_exec_id, exit_exec_id,
         opened_at, closed_at, pnl_usd, fees_usd, exit_reason, gate),
    )
    conn.commit()
    return cur.rowcount == 1


def record_shadow_trade(
    conn: sqlite3.Connection,
    *,
    strategy: str,
    symbol: str,
    side: str,
    qty: float,
    entry_ts: int,
    entry_price: float,
    entry_atr: float,
    target_r: float,
    stop_atr_mult: float,
    exit_ts: int,
    exit_price: float,
    exit_reason: str,
    ceiling_pnl: float,
) -> int:
    cur = conn.execute(
        "INSERT INTO shadow_trades "
        "(strategy, symbol, side, qty, entry_ts, entry_price, entry_atr, target_r, "
        " stop_atr_mult, exit_ts, exit_price, exit_reason, ceiling_pnl) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (strategy, symbol, side, qty, entry_ts, entry_price, entry_atr, target_r,
         stop_atr_mult, exit_ts, exit_price, exit_reason, ceiling_pnl),
    )
    conn.commit()
    return cur.lastrowid


def record_shadow_real(
    conn: sqlite3.Connection, *, trade_id: int, strategy: str, symbol: str,
    real_pnl: float, fill_status: str, repriced_at: str,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO shadow_real "
        "(trade_id, strategy, symbol, real_pnl, fill_status, repriced_at) VALUES (?,?,?,?,?,?)",
        (trade_id, strategy, symbol, real_pnl, fill_status, repriced_at),
    )
    conn.commit()


def get_shadow_trades(conn: sqlite3.Connection, strategy: str | None = None) -> list[sqlite3.Row]:
    if strategy is None:
        return conn.execute("SELECT * FROM shadow_trades ORDER BY id").fetchall()
    return conn.execute(
        "SELECT * FROM shadow_trades WHERE strategy = ? ORDER BY id", (strategy,)
    ).fetchall()


def get_trades(conn: sqlite3.Connection, symbol: str | None = None) -> list[sqlite3.Row]:
    if symbol is None:
        return conn.execute("SELECT * FROM trades ORDER BY id").fetchall()
    return conn.execute(
        "SELECT * FROM trades WHERE symbol = ? ORDER BY id", (symbol,)
    ).fetchall()


def get_fill(conn: sqlite3.Connection, exec_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM fills WHERE exec_id = ?", (exec_id,)).fetchone()


def count_fills(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
