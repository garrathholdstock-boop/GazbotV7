#!/usr/bin/env python3
"""Publish the backfilled bars INTO the lake, so research can actually see them.

★★★2026-08-18 THE GAP THIS CLOSES. backfill_history.py writes to data/backfill/, which is NOT one of
the paths gazbot7.lake scans (data/tape, data/v5_parquet, capture.db). So every bar pulled overnight
was invisible to the census and the walk-forward: the research would have run on the OLD dataset and
reported normally. Pulling data nobody can query is the same as not pulling it.

Two shape problems are fixed here, not papered over:
  1. the backfill files carry only (ts,o,h,l,c,v) — symbol and timeframe live in the FILENAME, so
     they are projected into real columns to match the lake's bars schema exactly;
  2. the lake's bars stream is 5s and the backfill's finest is 1min. They are written under their
     TRUE timeframe label ('1min','5mins','1hour','1day') rather than being mislabelled as 5s —
     a wrong label would be worse than absence, because a study would silently mix resolutions.

Contracts overlap by design (each covers its own quarter and they chain), so rows are deduped on
(symbol,timeframe,bar_ts) keeping the FIRST — the front-month print for any instant.

  PYTHONPATH=src python scripts/backfill_to_lake.py [--dry-run]
"""
from __future__ import annotations
import argparse
import glob
import os
import re
import sys

GB = "/home/alphabot/gazbot7"
SRC = f"{GB}/data/backfill"
LAKE = f"{GB}/data/tape/bars"
PAT = re.compile(r"^(?P<sym>[A-Z0-9]+)_(?P<con>[A-Z0-9]+)_(?P<tf>1day|1hour|5mins|1min)\.parquet$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    import duckdb
    files = sorted(glob.glob(f"{SRC}/*.parquet"))
    if not files:
        print("no backfill files")
        return 0
    groups: dict[tuple[str, str], list[str]] = {}
    for f in files:
        m = PAT.match(os.path.basename(f))
        if not m:
            print(f"  skip (unparsed name): {os.path.basename(f)}")
            continue
        groups.setdefault((m["sym"], m["tf"]), []).append(f)

    con = duckdb.connect()
    total = 0
    for (sym, tf), fs in sorted(groups.items()):
        out_dir = f"{LAKE}/{sym}"
        os.makedirs(out_dir, exist_ok=True)
        out = f"{out_dir}/backfill_{tf}.parquet"
        lst = "[" + ",".join(f"'{x}'" for x in fs) + "]"
        q = f"""
            SELECT '{sym}' AS symbol, '{tf}' AS timeframe,
                   CAST(ts AS BIGINT) AS bar_ts, open, high, low, close, volume
            FROM read_parquet({lst})
            QUALIFY row_number() OVER (PARTITION BY bar_ts ORDER BY ts) = 1
            ORDER BY bar_ts"""
        n, lo, hi = con.execute(
            f"SELECT COUNT(*), MIN(bar_ts), MAX(bar_ts) FROM ({q})").fetchone()
        span = con.execute(
            f"SELECT strftime(to_timestamp(MIN(bar_ts)),'%Y-%m-%d'), "
            f"strftime(to_timestamp(MAX(bar_ts)),'%Y-%m-%d') FROM ({q})").fetchone()
        print(f"  {sym} {tf:<6} {n:8,d} rows  {span[0]} .. {span[1]}  <- {len(fs)} contract files")
        if not a.dry_run:
            con.execute(f"COPY ({q}) TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
            # ⚠ VERIFY THE WRITE, as tape_mirror does — a file that exists is not a file that landed
            back = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out}')").fetchone()[0]
            if back != n:
                print(f"    ✗ MISMATCH written={back:,} expected={n:,} — removing")
                os.remove(out)
                continue
            total += n
    con.close()
    print(f"{'would publish' if a.dry_run else 'published'} {total:,} rows into {LAKE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
