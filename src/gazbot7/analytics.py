"""GAZBOT V7 — the DuckDB analytics layer (D9).

Opens a DuckDB session with the V7 store attached (and, optionally, the frozen V5
archive), so research/reports query the present and the past in ONE place. This
is where the sweeps / edge analysis / Friday reports live — re-derived on this
stack (DuckDB + numpy + pandas), never copied from V5. Offline and read-only over
data; it never touches the trading path.
"""

from __future__ import annotations

from pathlib import Path

import duckdb


def open_analytics(v7_path: str | Path, *, v5_archive: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with ``v7`` (and optionally ``v5``) sqlite DBs attached.
    Cross-boundary history 'just works' — one query spans V7 present + V5 past."""
    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")
    # ATTACH takes a literal path, not a bind parameter; paths are internal (not
    # user input) — escape single quotes defensively.
    v7 = str(v7_path).replace("'", "''")
    con.execute(f"ATTACH '{v7}' AS v7 (TYPE sqlite)")
    if v5_archive is not None:
        v5 = str(v5_archive).replace("'", "''")
        con.execute(f"ATTACH '{v5}' AS v5 (TYPE sqlite, READ_ONLY)")
    return con


def shadow_summary(con: duckdb.DuckDBPyConnection):
    """Per-strategy honest shadow performance (scored ONLY on real_pnl)."""
    return con.execute(
        """
        SELECT s.strategy,
               COUNT(*)                                                    AS n,
               ROUND(SUM(r.real_pnl), 2)                                   AS real_pnl,
               ROUND(AVG(r.real_pnl), 2)                                   AS avg_pnl,
               ROUND(100.0 * SUM(CASE WHEN r.real_pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct
        FROM v7.shadow_trades s
        JOIN v7.shadow_real  r ON r.trade_id = s.id
        WHERE r.fill_status = 'filled'
        GROUP BY s.strategy
        ORDER BY real_pnl DESC
        """
    ).fetchall()


def desk_pnl_by_day(con: duckdb.DuckDBPyConnection):
    """Live-desk net P&L per UTC day (net of fees, on closed_at)."""
    return con.execute(
        """
        SELECT substr(closed_at, 1, 10) AS day,
               COUNT(*)                 AS trades,
               ROUND(SUM(pnl_usd), 2)   AS net_pnl
        FROM v7.trades
        GROUP BY day
        ORDER BY day
        """
    ).fetchall()
