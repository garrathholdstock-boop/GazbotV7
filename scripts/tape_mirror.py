#!/usr/bin/env python3
"""TAPE MIRROR — export completed days from SQLite to a local day-partitioned Parquet lake.

Operator, 2026-08-04: "1 week fully live and hot in sql. rest in parquet. and maybe we b2 after
2 months."

WHY. capture.db costs ~1.22 GB/day; the identical data as zstd Parquet costs ~0.044 GB/day — 28x less
for the same rows, same columns, same granularity, nothing decimated. So SQLite holds only what the LIVE
desk needs (footprint reads the latest book; gates warm up on recent bars) and the Parquet lake holds
the history the BACKTESTS need. Measured: 1 week hot + 2 months of lake = 11.2 GB, against 34.1 GB for
4 weeks of all-SQLite that did not fit at all.

★★ THE INTERLOCK IS THE POINT OF THIS FILE.
An archive that MIGHT have run, feeding a prune that deletes unconditionally, is a machine for losing
data quietly. So the contract is: **the prune may not delete a day this script has not VERIFIED.**
Verification is a row-count match per (table, symbol, day) between SQLite and the written Parquet, and
only a matching day is written to the manifest. prune_capture.py reads that manifest and clamps its
cutoff to the oldest UNMIRRORED day — so if this script stops running, the prune simply stops deleting
and capture.db grows. Growing is a nuisance you notice; silent gaps in the tape are not.

★ ONLY COMPLETE DAYS. A day is exported only once it is fully in the past (UTC), because a partial day
would verify against a partial count and then never be revisited — the row count would "match" while
half the session was missing.

★ IDEMPOTENT. Re-running re-exports nothing already verified. Safe on any schedule.

  PYTHONPATH=src .venv/bin/python scripts/tape_mirror.py [--dry-run] [--days N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import duckdb

GB = "/home/alphabot/gazbot7"
LAKE = os.environ.get("GAZBOT7_TAPE_LAKE", f"{GB}/data/tape")
MANIFEST = f"{LAKE}/_manifest.json"
LOG = f"{GB}/data/tape_mirror.log"

# (name, attached table, time column, seconds-per-unit) — `book` is the 41ms event stream and the
# finest data we own; it was missing from an earlier draft of the archive and that would have been a
# permanent loss, so it is first in the list deliberately.
SRC = [("book", "cap.book", "ts_ms", 1000),
       ("ticks", "cap.ticks", "ts_ms", 1000),
       ("quotes", "cap.quotes", "ts_ms", 1000),
       ("bars", "cap.bars", "bar_ts", 1),
       ("depth", "dep.depth_snap", "ts_ms", 1000)]


def log(m: str) -> None:
    line = f"{dt.datetime.now(dt.UTC):%FT%TZ} {m}"
    print(line)
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def load_manifest() -> dict:
    try:
        return json.load(open(MANIFEST))
    except Exception:
        return {"verified": {}}          # {"book|MNQ|2026-08-01": {"rows": N, "bytes": B, "at": iso}}


def save_manifest(m: dict) -> None:
    os.makedirs(LAKE, exist_ok=True)
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(m, fh, indent=1, sort_keys=True)
    os.replace(tmp, MANIFEST)            # atomic — a torn manifest would strand the prune


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=45, help="how far back to look for unmirrored days")
    a = ap.parse_args()

    os.makedirs(LAKE, exist_ok=True)
    man = load_manifest()
    con = duckdb.connect()
    con.execute(f"ATTACH '{GB}/data/capture.db' AS cap (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{GB}/data/depth.db' AS dep (TYPE sqlite, READ_ONLY)")

    today = dt.datetime.now(dt.UTC).date()
    floor = today - dt.timedelta(days=a.days)
    wrote = skipped = failed = 0
    total_bytes = 0

    for name, tbl, tcol, unit in SRC:
        try:
            days = con.execute(
                f"SELECT DISTINCT CAST({tcol}/{86400*unit} AS BIGINT) d, symbol FROM {tbl}").fetchall()
        except Exception as e:
            log(f"  {name}: unreadable ({e}) — skipped")
            continue
        for d, sym in sorted(days):
            day = dt.datetime.fromtimestamp(d * 86400, dt.UTC).date()
            # ★ only COMPLETE past days — a partial day would verify against a partial count
            if day >= today or day < floor:
                continue
            key = f"{name}|{sym}|{day:%Y-%m-%d}"
            out = f"{LAKE}/{name}/{sym}/{day:%Y-%m-%d}.parquet"
            if key in man["verified"] and os.path.exists(out):
                skipped += 1
                continue
            lo, hi = d * 86400 * unit, (d + 1) * 86400 * unit
            n_src = con.execute(
                f"SELECT count(*) FROM {tbl} WHERE symbol=? AND {tcol}>=? AND {tcol}<?",
                [sym, lo, hi]).fetchone()[0]
            if not n_src:
                continue
            if a.dry_run:
                log(f"  WOULD export {key}: {n_src:,} rows")
                wrote += 1
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            con.execute(f"COPY (SELECT * FROM {tbl} WHERE symbol='{sym}' AND {tcol}>={lo} "
                        f"AND {tcol}<{hi}) TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
            # ★ VERIFY before recording — a file that exists is not a file that is correct
            n_pq = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
            if n_pq != n_src:
                log(f"  ✗ {key}: MISMATCH src={n_src:,} parquet={n_pq:,} — NOT recorded, "
                    f"prune will refuse to delete this day")
                failed += 1
                continue
            b = os.path.getsize(out)
            total_bytes += b
            man["verified"][key] = {"rows": n_src, "bytes": b,
                                    "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
            wrote += 1
            log(f"  ✓ {key}: {n_src:,} rows -> {b/1e6:.1f} MB")
            # ★ save as we go. A full first run exports ~70 partitions over several minutes; saving
            # only at the end means an interruption discards the record of everything already written,
            # so the next run re-exports it all. The files would still be correct — this is about not
            # repeating minutes of work, and about the manifest reflecting reality at all times.
            if wrote % 5 == 0:
                save_manifest(man)

    if not a.dry_run and wrote:
        save_manifest(man)
    log(f"mirror: {wrote} exported, {skipped} already verified, {failed} FAILED, "
        f"{total_bytes/1e6:.1f} MB written, lake now {len(man['verified'])} verified partitions")
    if failed:
        log("★ failures leave those days UNMIRRORED — prune_capture will clamp and keep them on disk.")
    return 0


def mirrored_floor_ms() -> int | None:
    """Oldest day that HAS DATA in SQLite but is NOT verified in Parquet, as epoch ms.
    prune_capture clamps its cutoff to this, so it can never delete unarchived tape.

    ★ THE FIRST VERSION OF THIS WAS WRONG AND WOULD HAVE DISABLED THE PRUNE FOREVER.
    It walked the manifest's dates forward and stopped at the first CALENDAR gap — but 2026-07-18 is a
    Saturday. Markets are shut, no rows exist, no partition is written, and a weekend therefore looks
    identical to a missing archive. The clamp parked itself on 07-18 permanently and the prune reported
    "0 rows" every run while capture.db grew. It failed SAFE, which is why it would have gone unnoticed
    for weeks — the same shape as the router's full-roster pin logging "no change" for 411 ticks.

    The correct test is not calendar continuity but COVERAGE: for every (table, symbol, day) that
    actually holds rows in SQLite and is a complete past day, is it in the manifest? The earliest that
    is not is the floor. Weekends hold no rows, so they are never asked about."""
    man = load_manifest().get("verified", {})
    today = dt.datetime.now(dt.UTC).date()
    try:
        con = duckdb.connect()
        con.execute(f"ATTACH '{GB}/data/capture.db' AS cap (TYPE sqlite, READ_ONLY)")
        con.execute(f"ATTACH '{GB}/data/depth.db' AS dep (TYPE sqlite, READ_ONLY)")
        missing = []
        for name, tbl, tcol, unit in SRC:
            try:
                rows = con.execute(
                    f"SELECT DISTINCT CAST({tcol}/{86400*unit} AS BIGINT) d, symbol FROM {tbl}"
                ).fetchall()
            except Exception:
                continue
            for d, sym in rows:
                day = dt.datetime.fromtimestamp(d * 86400, dt.UTC).date()
                if day >= today:                      # today is still being written
                    continue
                if f"{name}|{sym}|{day:%Y-%m-%d}" in man:
                    continue
                # ★ CONFIRM IT ACTUALLY HAS ROWS BEFORE CALLING IT MISSING. The DISTINCT day-bucket
                # scan yields buckets that contain no rows under the same bounds (boundary rows, empty
                # weekend buckets), and the EXPORT loop skips those silently via `if not n_src`. If this
                # function counts them as unmirrored the two disagree permanently: the exporter will
                # never write them, so the clamp parks on the earliest one and the prune deletes
                # nothing, forever, while reporting success. Both sides must use the same rule.
                lo, hi = d * 86400 * unit, (d + 1) * 86400 * unit
                n = con.execute(
                    f"SELECT count(*) FROM {tbl} WHERE symbol=? AND {tcol}>=? AND {tcol}<?",
                    [sym, lo, hi]).fetchone()[0]
                if n:
                    missing.append(day)
        con.close()
    except Exception:
        return 0                                       # unreadable -> clamp everything -> delete nothing
    if not missing:
        # everything with rows is archived; nothing to protect, let retention decide
        return int(dt.datetime.combine(today, dt.time(), dt.UTC).timestamp() * 1000)
    return int(dt.datetime.combine(min(missing), dt.time(), dt.UTC).timestamp() * 1000)


if __name__ == "__main__":
    sys.exit(main())
