#!/usr/bin/env python3
"""Land an EXTERNAL historical tape into the desk's parquet lake, in the lake's own shape.

★★★ THE TRAP THIS AVOIDS — and this desk has already fallen into it once. On 2026-08-18 the IBKR
backfill wrote to `data/backfill/`, which `gazbot7.lake` does not scan, so every bar pulled overnight
was invisible to the census and the walk-forward. `scripts/backfill_to_lake.py` fixed that by copying
into `data/tape/bars/<SYM>/backfill_<tf>.parquet`.

★ BUT THAT FIX IS ONLY HALF A FIX, AND IT ONLY WORKS BY ACCIDENT. Read `lake.connect()`:

        lake_days = _lake_days(stream, symbol)          # DAY-NAMED files only
        ...
        if lake_days:                                   # <-- THE GATE
            parts.append("... read_parquet('{base}/{stream}/{symbol}/*.parquet')")

`_lake_days()` counts only basenames that parse as a date. `backfill_1min.parquet` does not, so it
contributes NOTHING to `lake_days`. For MNQ/MGC the glob still fires because `tape_mirror.py` has
been laying down `YYYY-MM-DD.parquet` day partitions nightly for weeks — the backfill rides in on
their coat-tails. For a BRAND-NEW symbol with no nightly mirror (like NQ), `lake_days` is empty, the
gate is false, and the parquet is never read. The file would sit on disk, correct and complete, and
every query would return zero rows — the 08-18 failure exactly, one directory further along.

    → SO THIS LOADER WRITES DAY PARTITIONS (`YYYY-MM-DD.parquet`), NOT ONE BIG FILE.
      That is the shape the lake actually reads, the shape `coverage()` can count and gap-check,
      and the shape that needs no other job to have run first.

Schema written is the lake's `bars` schema exactly, per STREAMS['bars']:
    symbol, timeframe, bar_ts (BIGINT epoch seconds, UTC), open, high, low, close, volume

Sources supported:
    hf_nq1min  data/external/hf_nq1min/NQ_1min_*.parquet   -> symbol NQ, timeframe 1min
    yahoo_1d   data/external/yahoo/<X>_1d.csv              -> symbol per --symbol, timeframe 1day

Usage:
    PYTHONPATH=src .venv/bin/python scripts/external_to_lake.py --source hf_nq1min [--dry-run]
    PYTHONPATH=src .venv/bin/python scripts/external_to_lake.py --source yahoo_1d --file NQF_1d.csv --symbol NQ
    PYTHONPATH=src .venv/bin/python scripts/external_to_lake.py --verify --symbol NQ
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

GB = "/home/alphabot/gazbot7"
LAKE = f"{GB}/data/tape/bars"
EXT = f"{GB}/data/external"
COLS = "symbol, timeframe, bar_ts, open, high, low, close, volume"


def _con():
    import duckdb
    c = duckdb.connect()
    c.execute("SET memory_limit='%s'" % os.environ.get("GAZ_DUCKDB_MEM", "700MB"))
    c.execute("SET threads=2")
    os.makedirs(f"{GB}/data/duckdb_tmp", exist_ok=True)
    c.execute(f"SET temp_directory='{GB}/data/duckdb_tmp'")
    return c


def _write_days(con, select_sql: str, symbol: str, tf: str, dry: bool, force: bool = False,
                merge: bool = False) -> int:
    """Write one YYYY-MM-DD.parquet per UTC calendar day.

    ★ STAGE ONCE, THEN SLICE. The obvious loop — run `select_sql` filtered to one day, 3,287 times —
      re-reads all eleven source parquets and re-runs the dedupe window function on every iteration.
      Measured: ~13 s per day = 12 hours for a 48 MB dataset. Staging the projection into a single
      temp table first and slicing that is the same result in ~1 minute.
    ★ The staged table is ~3.7M x 8 narrow columns; DuckDB is capped at 700MB and spills to
      data/duckdb_tmp, so this never threatens the desk on a 7.5GB box.
    """
    out_dir = f"{LAKE}/{symbol}"
    os.makedirs(out_dir, exist_ok=True)
    con.execute("DROP TABLE IF EXISTS stage")
    con.execute(f"CREATE TEMP TABLE stage AS SELECT {COLS}, "
                f"strftime(to_timestamp(bar_ts),'%Y-%m-%d') AS d FROM ({select_sql})")
    con.execute("CREATE INDEX IF NOT EXISTS stage_d ON stage(d)")
    days = [r[0] for r in con.execute("SELECT DISTINCT d FROM stage ORDER BY d").fetchall()]
    if not days:
        print("  nothing to write")
        return 0
    print(f"  {symbol} {tf}: {len(days)} day partitions to write ({days[0]} .. {days[-1]})")
    if dry:
        return 0
    counts = dict(con.execute("SELECT d, count(*) FROM stage GROUP BY 1").fetchall())
    total = skipped = 0
    for i, d in enumerate(days):
        out = f"{out_dir}/{d}.parquet"
        # a day already mirrored from the LIVE desk is never overwritten by an external source —
        # our own capture is the record for any day we actually traded. --force overrides, which is
        # correct only for a symbol the desk does not itself capture (NQ is not traded here; MNQ is).
        if os.path.exists(out) and not (force or merge):
            skipped += 1
            continue
        n = counts[d]
        if os.path.exists(out) and merge:
            # ★ A DAY PARTITION IS PER (STREAM, SYMBOL) — NOT PER TIMEFRAME. tape_mirror puts every
            #   timeframe for a day in ONE file and distinguishes them by the `timeframe` column.
            #   So landing a 1day series for a symbol that already has 1min day files must UNION,
            #   never overwrite: a plain COPY would silently delete that day's 1-minute bars and
            #   leave a file that still reads fine. Dedupe on (timeframe, bar_ts), incumbent wins.
            src = (f"SELECT {COLS} FROM read_parquet('{out}') UNION ALL BY NAME "
                   f"SELECT {COLS} FROM stage WHERE d='{d}'")
            q = (f"SELECT {COLS} FROM ({src}) "
                 f"QUALIFY row_number() OVER (PARTITION BY timeframe, bar_ts ORDER BY 1) = 1 "
                 f"ORDER BY timeframe, bar_ts")
            n = con.execute(f"SELECT count(*) FROM ({q})").fetchone()[0]
            con.execute(f"CREATE OR REPLACE TEMP TABLE merged AS {q}")
            con.execute(f"COPY merged TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
        else:
            con.execute(f"COPY (SELECT {COLS} FROM stage WHERE d='{d}' ORDER BY bar_ts) "
                        f"TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
        # ⚠ VERIFY THE WRITE — a file that exists is not a file that landed (tape_mirror's rule).
        # This also repairs anything a previous interrupted run left half-written.
        try:
            back = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
        except Exception as e:
            print(f"    x UNREADABLE {d}: {e} — removing")
            os.remove(out)
            continue
        if back != n:
            print(f"    x MISMATCH {d} written={back:,} expected={n:,} — removing")
            os.remove(out)
            continue
        total += n
        if i % 500 == 0:
            print(f"    .. {i}/{len(days)} {d} ({total:,} rows)")
    if skipped:
        print(f"  skipped {skipped} day(s) already in the lake (use --force to overwrite)")
    con.execute("DROP TABLE IF EXISTS stage")
    return total


def audit_existing(con, symbol: str) -> None:
    """Every day file the lake holds for `symbol` must be READABLE and non-empty. An interrupted
    writer leaves a truncated parquet that `read_parquet('*.parquet')` fails the WHOLE glob on —
    one corrupt file makes the entire symbol unqueryable, which is the loudest possible version of
    this desk's quietest failure."""
    bad = 0
    files = sorted(glob.glob(f"{LAKE}/{symbol}/*.parquet"))
    for f in files:
        try:
            n = con.execute(f"SELECT count(*) FROM read_parquet('{f}')").fetchone()[0]
            if n == 0:
                raise ValueError("empty")
        except Exception as e:
            print(f"  x CORRUPT {os.path.basename(f)}: {e} — removing")
            os.remove(f)
            bad += 1
    print(f"  audited {len(files)} file(s) for {symbol}: {bad} removed")


def load_hf_nq1min(con, dry: bool, force: bool = False, merge: bool = False) -> int:
    files = sorted(glob.glob(f"{EXT}/hf_nq1min/NQ_1min_*.parquet"))
    if not files:
        print("no hf_nq1min files"); return 0
    lst = "[" + ",".join(f"'{f}'" for f in files) + "]"
    # dedupe: 224 duplicated timestamps exist in the raw set (0.006%); keep the higher-volume print
    sel = f"""
        SELECT 'NQ' AS symbol, '1min' AS timeframe,
               CAST(epoch(timestamp) AS BIGINT) AS bar_ts,
               open, high, low, close, CAST(volume AS BIGINT) AS volume
        FROM read_parquet({lst})
        QUALIFY row_number() OVER (PARTITION BY timestamp ORDER BY volume DESC) = 1"""
    return _write_days(con, sel, "NQ", "1min", dry, force, merge)


def load_yahoo_1d(con, fname: str, symbol: str, dry: bool, force: bool = False,
                  merge: bool = False) -> int:
    path = f"{EXT}/yahoo/{fname}"
    if not os.path.exists(path):
        print(f"missing {path}"); return 0
    sel = f"""
        SELECT '{symbol}' AS symbol, '1day' AS timeframe, CAST(ts AS BIGINT) AS bar_ts,
               open, high, low, close, CAST(coalesce(volume,0) AS BIGINT) AS volume
        FROM read_csv('{path}') WHERE close IS NOT NULL"""
    return _write_days(con, sel, symbol, "1day", dry, force, merge)


def verify(con, symbol: str) -> None:
    """Prove the lake can SEE it — the only check that matters. Uses the real lake API."""
    sys.path.insert(0, f"{GB}/src")
    from gazbot7.lake import connect, coverage
    print(f"\n── gazbot7.lake.coverage() for {symbol} ──")
    for r in coverage(symbols=(symbol,)):
        if r["days"]:
            print(f"  {r['stream']:<7} days={r['days']:<6} weeks={r['weeks']:<7} "
                  f"lake={r['lake']} span={r['span']} gaps={len(r['gaps'])}")
    print(f"\n── gazbot7.lake.connect(symbol='{symbol}') sees ──")
    lc = connect(symbol=symbol, include_v5=False, include_hot=False)
    print(lc.execute(
        "SELECT timeframe, count(*) n, min(bar_ts) lo, max(bar_ts) hi FROM bars GROUP BY 1").df()
        .to_string(index=False))
    print(lc.execute(
        "SELECT strftime(to_timestamp(min(bar_ts)),'%Y-%m-%d') first_day, "
        "strftime(to_timestamp(max(bar_ts)),'%Y-%m-%d') last_day FROM bars").df().to_string(index=False))
    lc.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["hf_nq1min", "yahoo_1d"])
    ap.add_argument("--file", default="NQF_1d.csv")
    ap.add_argument("--symbol", default="NQ")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing day partitions (only for a symbol the desk does not capture)")
    ap.add_argument("--audit", action="store_true", help="drop corrupt/empty day files")
    ap.add_argument("--merge", action="store_true",
                    help="UNION into an existing day partition instead of replacing it — "
                         "required whenever the symbol already holds another timeframe")
    a = ap.parse_args()
    con = _con()
    n = 0
    if a.audit:
        audit_existing(con, a.symbol)
    if a.source == "hf_nq1min":
        n = load_hf_nq1min(con, a.dry_run, a.force, a.merge)
    elif a.source == "yahoo_1d":
        n = load_yahoo_1d(con, a.file, a.symbol, a.dry_run, a.force, a.merge)
    if a.source:
        print(f"{'would publish' if a.dry_run else 'published'} {n:,} rows into {LAKE}/{a.symbol}")
    con.close()
    if a.verify:
        verify(_con(), a.symbol)
    return 0


if __name__ == "__main__":
    sys.exit(main())
