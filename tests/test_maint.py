"""S10 — DB hygiene: WAL checkpoint + VACUUM-INTO backup with the 0-byte trap."""

from __future__ import annotations

import os

from gazbot7 import maint
from gazbot7.store import Fill, open_store, record_fill


def _db(tmp_path):
    db = tmp_path / "gazbot7.db"
    s = open_store(db)
    record_fill(s, Fill("e1", "o", "MNQ", "BUY", 1, 100.0, "2026-07-15T13:00:00+00:00"))
    s.close()
    return str(db)


def test_checkpoint_does_not_raise(tmp_path):
    maint.checkpoint(_db(tmp_path))  # WAL truncate on a real store


def test_backup_produces_nonempty_copy(tmp_path):
    db = _db(tmp_path)
    out = maint.backup(db, str(tmp_path / "bk"), stamp="20260715T000000Z")
    assert os.path.exists(out) and os.path.getsize(out) > 0
    # the copy is a real DB with the fill in it
    import sqlite3
    assert sqlite3.connect(out).execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1


def test_backup_prunes_to_keep(tmp_path):
    db = _db(tmp_path)
    bk = str(tmp_path / "bk")
    for stamp in ("20260715T000001Z", "20260715T000002Z", "20260715T000003Z"):
        maint.backup(db, bk, keep=2, stamp=stamp)
    from pathlib import Path
    remaining = sorted(p.name for p in Path(bk).glob("gazbot7.*.db"))
    assert remaining == ["gazbot7.20260715T000002Z.db", "gazbot7.20260715T000003Z.db"]  # newest 2
