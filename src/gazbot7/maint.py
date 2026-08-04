"""GAZBOT V7 — DB hygiene (S10): WAL checkpoint + VACUUM-INTO backup.

Two operations, run from a daily timer:

* **checkpoint** — ``PRAGMA wal_checkpoint(TRUNCATE)`` so the WAL can't run away
  (V5 hit 4.7 GB when a long reader pinned the read-mark).
* **backup** — ``VACUUM INTO`` a timestamped copy: one consistent MVCC snapshot,
  no writer lock, single forward pass that does NOT restart on a concurrent write
  (V5's ``.backup`` thrashed for 90+ min on a 4.6 GB DB and left multi-GB orphans).
  A failed backup leaves NO file, never a 0-byte masquerade, then prunes to the
  newest ``keep``.

V7 needs no schema-version guard (the schema is declarative ``CREATE TABLE IF NOT
EXISTS`` — no migration runner to drift) and no agent_audit table (there is no
automated DB-mutating janitor; core writes are the normal path). Clean-room.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path


def checkpoint(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def wal_bytes(db_path: str) -> int:
    w = Path(str(db_path) + "-wal")
    return w.stat().st_size if w.exists() else 0


def _prune(backup_dir: str, name: str, keep: int) -> None:
    if keep <= 0:
        return
    files = sorted(Path(backup_dir).glob(f"{name}.*.db"))
    for f in files[:-keep]:
        f.unlink()


def backup(db_path: str, backup_dir: str, *, keep: int = 7, stamp: str | None = None) -> str:
    """VACUUM INTO a timestamped copy; refuse a 0-byte result; prune to ``keep``."""
    os.makedirs(backup_dir, exist_ok=True)
    stamp = stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    name = Path(db_path).stem
    out = os.path.join(backup_dir, f"{name}.{stamp}.db")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM INTO ?", (out,))
    finally:
        conn.close()
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        if os.path.exists(out):
            os.remove(out)  # a failed backup leaves NO file, not an empty one
        raise RuntimeError(f"backup produced no/empty file for {db_path}")
    _prune(backup_dir, name, keep)
    return out


def main() -> int:  # `python -m gazbot7.maint` — the daily hygiene sweep
    store = os.environ.get("GAZBOT7_STORE", "data/gazbot7.db")
    cap = os.environ.get("GAZBOT7_CAPTURE", "data/capture.db")
    bdir = os.environ.get("GAZBOT7_BACKUP_DIR", "/home/alphabot/gazbot7/backups")
    # Per-DB retention (2026-07-23): a flat keep=7 let the ~3.5GB/night CAPTURE copies pile to 18GB
    # and 86% disk. Capture is ephemeral market data (regenerated live + pruned nightly) → keep few;
    # the gazbot7 STATE DB is <1MB → keep many. Env-overridable.
    keep_store = int(os.environ.get("GAZBOT7_BACKUP_KEEP_STORE", "14"))
    keep_cap = int(os.environ.get("GAZBOT7_BACKUP_KEEP_CAPTURE", "2"))
    for db, keep in ((store, keep_store), (cap, keep_cap)):
        if not os.path.exists(db):
            continue
        checkpoint(db)
        try:
            out = backup(db, bdir, keep=keep)
            print(f"maint: {db} -> {out} ({os.path.getsize(out)} bytes, keep={keep})")
        except Exception as e:
            print(f"maint: BACKUP FAILED {db}: {e}")
            from .notify import notify
            notify(f"Garrath — V7 DB backup FAILED: {db} ({e})", critical=True)
    backup_plain_files(bdir)
    return 0  # a hygiene sweep must never fail its host


# ★2026-08-04: NON-DB files that are IRREPLACEABLE HISTORY.
# `backup()` only handles SQLite (VACUUM INTO), so these were covered by nothing. That is fine for
# regenerable state and fatal for a history log: data/config_journal.jsonl exists precisely so the
# resolved exit ladder is recoverable after the fact, and a history that lives on exactly one disk is
# one failure from being as unrecoverable as the untracked exit_overrides.json it was built to replace.
# gate_switches.env is here for the same reason — the router rewrites it constantly and it is gitignored.
_PLAIN_FILES = ("data/config_journal.jsonl", "data/exit_overrides.json", "data/gate_switches.env")


def backup_plain_files(backup_dir: str, *, keep: int = 14, root: str = "/home/alphabot/gazbot7",
                       stamp: str | None = None) -> list[str]:
    """Timestamped copies of small append-only/config files. Never raises — hygiene, not the order path."""
    import shutil
    out: list[str] = []
    stamp = stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest_dir = os.path.join(backup_dir, "config")
    for rel in _PLAIN_FILES:
        src = os.path.join(root, rel)
        if not os.path.exists(src):
            continue
        try:
            os.makedirs(dest_dir, exist_ok=True)
            base = Path(rel).name
            dst = os.path.join(dest_dir, f"{base}.{stamp}")
            shutil.copy2(src, dst)
            out.append(dst)
            keepers = sorted(Path(dest_dir).glob(f"{base}.*"))
            for f in keepers[:-keep]:
                f.unlink()
            print(f"maint: {rel} -> {dst} ({os.path.getsize(dst)} bytes)")
        except Exception as e:
            print(f"maint: plain-file backup FAILED {rel}: {e}")
    return out


if __name__ == "__main__":
    raise SystemExit(main())
