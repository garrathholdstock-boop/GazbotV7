#!/usr/bin/env python3
"""Cap capture.db growth — retention prune of the big time-series tables.

The L2 `book` (79M rows) drives the growth; the live desk only ever reads the LATEST book
(footprint), so book history is very prunable. Deletes are BATCHED with a WAL checkpoint after
each batch so the -wal file can't balloon and spike a tight disk (2026-07-22: 9.3G free). Deleting
CAPS growth (freed pages get reused) but does NOT shrink the file — run VACUUM in a market-closed
window to reclaim disk.

  python scripts/prune_capture.py --dry-run     # count what WOULD be deleted
  python scripts/prune_capture.py               # prune
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3

DB = "/home/alphabot/gazbot7/data/capture.db"
BATCH = 50_000
# (table, time_col, ms?, retain_days) — book is the bulk → tightest; bars are tiny → keep long
RETAIN = [
    ("book", "ts_ms", True, 3),
    ("quotes", "ts_ms", True, 5),
    ("ticks", "ts_ms", True, 7),
    ("bars", "bar_ts", False, 60),
]
DROP_TMP = ("tmp_book", "tmp_tick")   # leftover scratch tables — safe to drop


def run(dry: bool):
    con = sqlite3.connect(DB, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    now = dt.datetime.now(dt.UTC).timestamp()
    total = 0
    for tbl, tcol, is_ms, days in RETAIN:
        cutoff = (now - days * 86400) * (1000 if is_ms else 1)
        if dry:
            n = con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {tcol} < ?", (cutoff,)).fetchone()[0]
            keep = con.execute(f"SELECT COUNT(*) FROM {tbl}", ()).fetchone()[0] - n
            print(f"  {tbl:8} would delete {n:>12,} (older than {days}d) · keep {keep:,}")
            total += n
            continue
        deleted = 0
        while True:
            cur = con.execute(
                f"DELETE FROM {tbl} WHERE rowid IN "
                f"(SELECT rowid FROM {tbl} WHERE {tcol} < ? LIMIT ?)", (cutoff, BATCH))
            con.commit()
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")   # flush + truncate WAL each batch → no disk spike
            deleted += cur.rowcount
            if cur.rowcount < BATCH:
                break
        print(f"  {tbl:8} deleted {deleted:>12,} rows older than {days}d")
        total += deleted
    if not dry:
        for t in DROP_TMP:
            con.execute(f"DROP TABLE IF EXISTS {t}")
            con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        print(f"  dropped leftover {', '.join(DROP_TMP)}")
    con.close()
    verb = "would prune" if dry else "pruned"
    print(f"{verb} {total:,} rows total — growth capped (freed pages reused). "
          f"File won't shrink without VACUUM (market-closed window; disk is tight).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    run(ap.parse_args().dry_run)
