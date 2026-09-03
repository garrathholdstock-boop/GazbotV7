"""Freshness of a WAL database is the WAL's mtime, not the main file's.

★2026-09-03. `shadow_mgc.db` was reported "unwritten for 230h" on 08-30 and believed. It was never
dead: SQLite in WAL mode does not touch the main `.db` on a write, only on a checkpoint, and that
store had 201 shadow trades with the newest stamped that same morning. The check was reading the
wrong file. These tests EXECUTE the accessor against real files on disk.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import data_inventory as di  # noqa: E402


def _touch(path, when):
    path.write_bytes(b"x")
    os.utime(path, (when, when))


def test_the_wal_counts_as_a_write(tmp_path):
    db = tmp_path / "s.db"
    now = time.time()
    _touch(db, now - 300 * 3600)                 # main file checkpointed 12 days ago
    _touch(tmp_path / "s.db-wal", now - 600)     # but written to 10 minutes ago
    assert now - di._written_at(str(db)) < 700, "a live WAL must read as a live store"


def test_the_shm_does_not_count_as_a_write(tmp_path):
    """`-shm` mtime moves on READS. Counting it would make any store look fresh the moment
    something opened it — healthy-about-what-it-never-checked, in one line."""
    db = tmp_path / "s.db"
    now = time.time()
    _touch(db, now - 300 * 3600)
    _touch(tmp_path / "s.db-shm", now)           # a reader just opened it
    assert (now - di._written_at(str(db))) / 3600 > 299, "an opened-but-unwritten store is STALE"


def test_a_plain_db_with_no_wal_is_unchanged(tmp_path):
    db = tmp_path / "s.db"
    now = time.time()
    _touch(db, now - 3600)
    assert (now - di._written_at(str(db))) == __import__("pytest").approx(3600, abs=5)


def test_a_missing_store_reads_as_epoch_zero_not_a_crash(tmp_path):
    assert di._written_at(str(tmp_path / "nope.db")) == 0.0
