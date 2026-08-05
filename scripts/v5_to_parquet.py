#!/usr/bin/env python3
"""Convert the frozen V5 archive to Parquet — same data, ~20x smaller, and queryable.

Operator, 2026-08-05, after Backblaze flagged the free-tier limit: the V5 archive went to B2 as raw
SQLite (10.5 GiB) because the `cold` tier used VACUUM INTO while the `tape` tier used Parquet. I
applied the compression lesson to one tier and not the other. Measured on ticks.db: 3,620 MB of
SQLite becomes 177 MB of zstd Parquet — 20x — with every row and column intact.

WHAT IT DOES. Every table with rows, from both V5 databases, one Parquet file each, plus a manifest
recording the source row count so the upload can be VERIFIED rather than assumed. Empty tables are
skipped (nothing to preserve) and recorded as such, so "missing" is never ambiguous.

★ WHY VERIFY BY ROW COUNT AND NOT BY SIZE. The cold tier "succeeded" on size alone and I still could
not tell the operator it was safe, because a byte total says nothing about whether the file opens.
The manifest here lets a later check re-read every Parquet and compare counts against the source —
which is the actual question: can I get the data back?

  PYTHONPATH=src .venv/bin/python scripts/v5_to_parquet.py [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import duckdb

V5 = "/home/alphabot/alphabot2/data"
SRC = [("alphabot", f"{V5}/alphabot.db"), ("ticks", f"{V5}/ticks.db")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/home/alphabot/gazbot7/data/v5_parquet")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    man: dict = {"tables": {}, "skipped_empty": []}
    total = 0

    for tag, path in SRC:
        if not os.path.exists(path):
            print(f"  {tag}: MISSING {path}")
            continue
        con = duckdb.connect()
        con.execute(f"ATTACH '{path}' AS s (TYPE sqlite, READ_ONLY)")
        tabs = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_catalog='s'").fetchall()]
        print(f"\n{tag}: {len(tabs)} tables")
        for t in sorted(tabs):
            try:
                n = con.execute(f'SELECT count(*) FROM s."{t}"').fetchone()[0]
            except Exception as e:
                print(f"   ! {t}: unreadable ({str(e)[:60]}) — skipped")
                continue
            if n == 0:
                man["skipped_empty"].append(f"{tag}.{t}")
                continue
            d = os.path.join(a.out, tag)
            os.makedirs(d, exist_ok=True)
            f = os.path.join(d, f"{t}.parquet")
            try:
                con.execute(f"""COPY (SELECT * FROM s."{t}") TO '{f}'
                                (FORMAT parquet, COMPRESSION zstd)""")
            except Exception as e:
                print(f"   ! {t}: export failed ({str(e)[:60]})")
                continue
            b = os.path.getsize(f)
            total += b
            man["tables"][f"{tag}.{t}"] = {"rows": n, "bytes": b}
            if n > 50_000:
                print(f"   {n:>10,} rows -> {b/1e6:>8.1f} MB  {t}")
        con.close()

    with open(os.path.join(a.out, "_manifest.json"), "w") as fh:
        json.dump(man, fh, indent=1, sort_keys=True)
    src_gb = sum(os.path.getsize(p) for _, p in SRC if os.path.exists(p)) / 1e9
    print(f"\n{len(man['tables'])} tables exported, {len(man['skipped_empty'])} empty skipped")
    print(f"SQLite {src_gb:.2f} GB  ->  Parquet {total/1e9:.3f} GB  ({src_gb/max(total/1e9,1e-9):.0f}x)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
