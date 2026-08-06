#!/usr/bin/env python3
"""Mirror the auto-memory into the repo so it is version-controlled.

★ WHY (operator, 2026-08-06). /root/.claude/projects/-root/memory/ sits outside any repo and had no
snapshot convention, while CLAUDE.md did (docs/CLAUDE_snapshot_*.md). Those files are load-bearing —
they are what a fresh session reads to decide how the desk is routed — and they lived on one disk with
no history.

★ WHY A MIRROR AND NOT A DATED COPY. CLAUDE.md uses dated snapshots, but for 144 files that is the wrong
shape: dated copies give you 144 new paths per snapshot and no way to see what actually changed. Mirroring
into ONE tracked directory lets git do the dating, so `git log -p docs/memory/<name>.md` shows a real
per-memory diff over time. That matters here specifically: on 2026-08-06 a memory whose TITLE contradicted
its own conclusion (shadow-board-as-regime-router) mis-steered a whole session, and the fix was a
frontmatter edit. Catching that class of drift needs diffs, not archives.

Deletions are mirrored too — a memory that was deleted because it turned out to be WRONG is exactly the
event worth having in history.

Usage:  python3 scripts/snapshot_memory.py [--dry-run]
"""
from __future__ import annotations

import argparse
import filecmp
import pathlib
import shutil
import sys

SRC = pathlib.Path("/root/.claude/projects/-root/memory")
DST = pathlib.Path("/home/alphabot/gazbot7/docs/memory")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not SRC.is_dir():
        print(f"source missing: {SRC}", file=sys.stderr)
        return 1
    DST.mkdir(parents=True, exist_ok=True)

    src_files = {p.name: p for p in SRC.glob("*.md")}
    dst_files = {p.name: p for p in DST.glob("*.md")}
    added = updated = removed = 0

    for name, sp in sorted(src_files.items()):
        dp = DST / name
        if not dp.exists():
            added += 1
            print(f"  + {name}")
            if not a.dry_run:
                shutil.copy2(sp, dp)
        elif not filecmp.cmp(sp, dp, shallow=False):
            updated += 1
            print(f"  ~ {name}")
            if not a.dry_run:
                shutil.copy2(sp, dp)

    for name in sorted(dst_files):
        if name not in src_files:
            removed += 1
            print(f"  - {name}  (deleted upstream — kept in git history)")
            if not a.dry_run:
                (DST / name).unlink()

    print(f"{len(src_files)} memories | +{added} added, ~{updated} updated, -{removed} removed"
          + ("  [dry-run]" if a.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
