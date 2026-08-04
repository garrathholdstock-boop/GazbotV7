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
    # ★ 2026-07-31 (operator): ROLLING 4-WEEK retention for all streams (was book 3d/quotes 5d/ticks 7d,
    # which capped the data below the 4wk needed for Friday backtesting). Grows the DB — watch disk.
    #
    # ★★ 2026-08-04 (operator: "do the book retention change, 5 days") — BOOK ALONE back to 5d.
    # MEASURED: book + its index grows 0.80 GB/DAY, against 0.14 GB/day for ticks+quotes+bars COMBINED.
    # It is 81% of capture.db. At 28 days x the two symbols now captured it projects to ~45 GB live plus
    # ~90 GB of local backups, on a 75 GB disk with 15 GB free — it fills the disk in roughly two weeks,
    # and the 07-31 move to 28d is what created that.
    # WHY BOOK SPECIFICALLY AND NOTHING ELSE:
    #   * it is the WEAKER COPY. data/depth.db holds 10 levels at ~0.045 GB/day/symbol because it dedups
    #     an unchanged book; this table holds levels 0..4 at 13.9M rows/day — ~35x the rows for half the
    #     depth. Anything wanting real book history should read depth.db.
    #   * the only live reader is footprint.py: `SELECT ... FROM book WHERE ... level=1 AND ts_ms<=?`.
    #     It wants the LATEST book, never history, so 5 days is already far more than it can use.
    #   * ticks/quotes/bars KEEP the full 4 weeks — they are what Friday backtesting actually consumes
    #     and together cost 0.14 GB/day, affordable for both symbols.
    # Deleting CAPS growth immediately (freed pages get reused) but does NOT shrink the file — run
    # gazbot7-capture-vacuum in a market-closed window to reclaim it.
    # Revert: set back to 28 and make sure the disk can take ~45 GB.
    ("book", "ts_ms", True, 5),
    ("quotes", "ts_ms", True, 28),
    ("ticks", "ts_ms", True, 28),
    ("bars", "bar_ts", False, 60),   # bars are tiny (189K rows) → keep 60d of free extra history
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
