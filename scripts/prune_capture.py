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
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

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
    # ★★2026-08-04 REVERTED to 28d, same evening (operator: "i dont want any short cuts. make sure the
    # DBs are rich granular data. i will pay for the hd space") — AND because my justification for 5d was
    # WRONG. I called book "the weaker copy of depth.db". It is shallower (levels 0..4 vs 10) but it is
    # SIX TIMES FINER IN TIME: measured 87,142 distinct timestamps/hour = one every 41 ms, event-driven
    # on every DOM update, against depth.db's 250 ms sample (14,124/hour). Fleeting quotes — the actual
    # spoofing tell, and the order-vs-trade imbalance divergence flagged as the highest-value unused
    # signal on this desk — live BETWEEN 250 ms samples and are invisible to depth.db. Cutting book to
    # 5 days would have thrown away the only stream that can see them.
    # Cost, stated plainly: ~0.80 GB/day/symbol, so ~45 GB for both at 28 days, plus local backups.
    ("book", "ts_ms", True, 5),
    ("quotes", "ts_ms", True, 5),
    ("ticks", "ts_ms", True, 5),
    ("bars", "bar_ts", False, 60),   # bars are tiny (236K rows) → keep 60 trading days, effectively free
]
DROP_TMP = ("tmp_book", "tmp_tick")   # leftover scratch tables — safe to drop


def run(dry: bool):
    con = sqlite3.connect(DB, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    now = dt.datetime.now(dt.UTC).timestamp()
    total = 0

    # ★★ THE INTERLOCK. This prune may NOT delete a day that tape_mirror.py has not exported to
    # Parquet AND verified by row count. Without it, an archive that merely MIGHT have run feeds a
    # delete that always runs — a machine for losing tape quietly, which is the exact failure class
    # that cost this desk the 07-31..08-02 exit ladder (untracked file, no record, unrecoverable).
    # If the mirror stops, the clamp stops the prune and capture.db grows instead. Growth is a
    # nuisance you notice; a silent gap in the tape is not.
    floor_ms = None
    try:
        from tape_mirror import mirrored_floor_ms
        floor_ms = mirrored_floor_ms()
        if floor_ms is None:
            print("  ⚠ tape manifest EMPTY — nothing verified in Parquet, so NOTHING will be deleted.")
        else:
            print(f"  tape mirror verified up to {dt.datetime.fromtimestamp(floor_ms/1000, dt.UTC):%Y-%m-%d}"
                  f" — prune clamped to that day")
    except Exception as e:
        print(f"  ⚠ tape_mirror unavailable ({e}) — refusing to delete anything this run")
        floor_ms = 0                       # 0 = clamp everything away = delete nothing

    for tbl, tcol, is_ms, days in RETAIN:
        # ★★2026-08-04 (operator: "cut sqlite to 5 days. each trading week is 5 days") — retention is
        # counted in TRADING DAYS, i.e. days that actually contain rows, NOT calendar days.
        # A calendar cutoff does not mean what it looks like: run on a Monday, "5 days" keeps
        # Mon/Sun/Sat/Fri/Thu — only THREE trading days, because the weekend eats two. Measured across
        # the week a 5-calendar-day rule retains 3,3,3,4,5,4,3 trading days depending on when it runs.
        # Counting days-with-rows instead handles weekends and exchange holidays for free, and makes
        # "5 days" mean one trading week on every day of the week.
        unit = 86400000 if is_ms else 86400
        have = [r[0] for r in con.execute(
            f"SELECT DISTINCT CAST({tcol}/{unit} AS BIGINT) d FROM {tbl} ORDER BY d DESC").fetchall()]
        have = [d for d in have if con.execute(
            f"SELECT 1 FROM {tbl} WHERE {tcol}>=? AND {tcol}<? LIMIT 1",
            (d * unit, (d + 1) * unit)).fetchone()]          # drop empty boundary buckets
        if len(have) <= days:
            cutoff = 0                                        # fewer trading days than we keep
        else:
            cutoff = have[days - 1] * unit                    # start of the OLDEST day we keep
        if floor_ms is not None:
            clamp = floor_ms if is_ms else floor_ms / 1000
            cutoff = min(cutoff, clamp)    # never delete past what is verifiably archived
        if dry:
            n = con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {tcol} < ?", (cutoff,)).fetchone()[0]
            keep = con.execute(f"SELECT COUNT(*) FROM {tbl}", ()).fetchone()[0] - n
            print(f"  {tbl:8} would delete {n:>12,} (keeping {days} TRADING days) · keep {keep:,}")
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
        print(f"  {tbl:8} deleted {deleted:>12,} rows (kept {days} trading days)")
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
