#!/usr/bin/env python3
"""One-time capture.db VACUUM — reclaim disk after the retention prune.

Deletes free pages but don't shrink the file; VACUUM rewrites it compacted. Run at the CME halt
(market closed → capture connections idle, no live book write to contend with). In-place VACUUM:
open connections (md/tournament) adapt to the rebuilt file, no restart needed. GUARDED: aborts if
disk is too tight (VACUUM needs temp space ~= the final size), and is harmless on SQLITE_BUSY
(DB unchanged). Re-asserts WAL after.

  python scripts/vacuum_capture.py
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys

DB = "/home/alphabot/gazbot7/data/capture.db"
MIN_FREE_GB = 4.0   # need headroom for the temp compacted copy


def gb(n: float) -> float:
    return round(n / 1e9, 2)


def run() -> int:
    before = os.path.getsize(DB)
    free = shutil.disk_usage(os.path.dirname(DB)).free
    print(f"capture.db {gb(before)}GB · disk free {gb(free)}GB")
    if free < MIN_FREE_GB * 1e9:
        print(f"ABORT: only {gb(free)}GB free (< {MIN_FREE_GB}GB) — VACUUM needs temp space, skipping")
        return 1
    con = sqlite3.connect(DB, timeout=300, isolation_level=None)   # autocommit — VACUUM can't be in a txn
    con.execute("PRAGMA busy_timeout=300000")
    try:
        con.execute("VACUUM")
        con.execute("PRAGMA journal_mode=WAL")                     # re-assert WAL (VACUUM can reset it)
    except sqlite3.OperationalError as e:
        print(f"VACUUM busy/failed ({e}) — DB UNCHANGED, no harm; retry another window")
        con.close()
        return 0
    con.close()
    after = os.path.getsize(DB)
    print(f"VACUUM done: {gb(before)}GB → {gb(after)}GB (reclaimed {gb(before - after)}GB)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
