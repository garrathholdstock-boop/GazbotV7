---
name: duckdb-pandas-for-analytics
description: "RULE — always use DuckDB + pandas (vectorized) for V7 analytics/backtests, never raw sqlite row-loops"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9162c01b-c354-41a1-9fc3-162d48ae4678
---

Operator RULE (2026-07-21): **always use DuckDB + pandas (vectorized) for any V7 analytics / backtest / tape-crunching work — never a raw `sqlite3` Python row-loop.**

DuckDB 1.5.4 + pandas 3.0.3 are installed in the gazbot7 venv, and `gazbot7/analytics.py` is the pattern: `con = duckdb.connect()` → `ATTACH '<path>' AS x (TYPE sqlite, READ_ONLY)` (it reads the operational sqlite DBs directly — gazbot7.db / capture.db / the V5 archive ticks.db/depth.db/alphabot.db), then do the heavy lifting in **SQL (bucketing, window functions, ASOF joins)** and pull results to a pandas `.df()`.

**Why:** the desk's store is SQLite (operational, WAL) but **DuckDB is the analytics layer over it** (store.py: "DuckDB is the analytics layer, added at D9"). DuckDB is columnar + vectorized (SIMD batches) — it crunches the 15M-row tick tables / 30-day bar history in seconds, where a Python `sqlite3` loop over 200k cadence points each range-scanning the tick table takes minutes (the footprint backtest 2026-07-21 was the lesson: I wrote it as a sqlite loop, it ground for minutes; the DuckDB rewrite `scripts/footprint_backtest_duck.py` bucketed the ticks once + rolled windows in-engine).

**How to apply:** any time I'm about to iterate rows in Python to aggregate/scan tape or trades — STOP, do it as a DuckDB query (5s buckets → window funcs → ASOF-join L2 → boolean gate columns → `.df()`), only loop in Python for the irreducibly-sequential bit (e.g. per-fire exit lookups, a few hundred). Ties to [[edge-spectrum-pipeline]] / [[analytics-capture-roadmap]] (DuckDB courtroom). Backtest tools: `scripts/gate_backtest.py` (Features gates, bars), `scripts/footprint_backtest_duck.py` (footprint gates, ticks+L2, vectorized).
