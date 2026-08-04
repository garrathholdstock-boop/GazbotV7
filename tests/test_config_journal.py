"""Pins the startup config journal (★2026-08-04).

The journal exists because epoch reconstruction failed for want of it. Its own failure modes must
therefore be pinned — above all that it can NEVER stop the desk starting, and that it never guesses
about times before it began recording.
"""
from __future__ import annotations

import json

import pytest

from gazbot7 import config_journal as cj
from gazbot7.slot_strategy import scaleout_slots


@pytest.fixture()
def journal(tmp_path, monkeypatch):
    p = tmp_path / "config_journal.jsonl"
    monkeypatch.setattr(cj, "JOURNAL", str(p))
    return p


def test_records_the_resolved_ladder_not_the_source_file(journal):
    specs = scaleout_slots()
    row = cj.record(specs, slate="scaleout", place_live=False)
    assert row is not None
    r = json.loads(journal.read_text().strip())
    # the RESOLVED slate is what the desk runs — every slot must be present
    assert r["n_slots"] == len(specs)
    assert set(r["resolved"]) == {s.tag for s in specs}
    # and the quiet-tape clip must be visible in the resolved ladder, since that is exactly the kind of
    # thing whose absence from the record broke the stop-width study
    ga = r["resolved"]["grind_long_A"]
    assert ga["atr_split"] == 22.0
    assert ga["stop_atr_mult"] == 1.0


def test_identical_config_hashes_identically_and_change_is_flagged(journal):
    specs = scaleout_slots()
    a = cj.record(specs, slate="scaleout", place_live=False)
    b = cj.record(specs, slate="scaleout", place_live=False)
    assert a["config_hash"] == b["config_hash"]
    assert b["changed_from_previous"] is False

    from dataclasses import replace
    widened = [replace(s, stop_atr_mult=2.0) for s in specs]
    c = cj.record(widened, slate="scaleout", place_live=False)
    assert c["config_hash"] != a["config_hash"]
    assert c["changed_from_previous"] is True, "a changed ladder must be flagged, not silently appended"


def test_every_start_gets_a_row_even_when_unchanged(journal):
    specs = scaleout_slots()
    for _ in range(3):
        cj.record(specs, slate="scaleout", place_live=False)
    assert len(journal.read_text().strip().splitlines()) == 3, (
        "a change-only log cannot answer 'what was live at T' without assuming no gaps")


def test_config_at_returns_None_before_the_journal_begins(journal):
    specs = scaleout_slots()
    r = cj.record(specs, slate="scaleout", place_live=False)
    assert cj.config_at(r["ts_ms"] + 1_000) is not None
    assert cj.config_at(r["ts_ms"] - 86_400_000) is None, (
        "must not extrapolate a later ladder backwards — that error produced a false +$2,477 result")


def test_config_at_picks_the_last_start_at_or_before(journal):
    specs = scaleout_slots()
    from dataclasses import replace
    first = cj.record(specs, slate="scaleout", place_live=False)
    second = cj.record([replace(s, target_r=9.0) for s in specs], slate="scaleout", place_live=False)
    got = cj.config_at(second["ts_ms"] + 5_000)
    assert got["config_hash"] == second["config_hash"]
    assert first["config_hash"] != second["config_hash"]


def test_a_broken_journal_never_raises(journal, monkeypatch):
    """The desk must start even if the journal cannot be written or is corrupt."""
    journal.write_text("this is not json\n{also not\n")
    assert cj.rows() == []            # corrupt lines skipped, not fatal
    assert cj.last_hash() is None

    monkeypatch.setattr(cj, "JOURNAL", "/nonexistent-dir/cannot/write.jsonl")
    assert cj.record(scaleout_slots(), slate="scaleout", place_live=False) is None  # swallowed


def test_tournament_main_survives_a_dead_journal(monkeypatch):
    """The wiring in tournament.main must be defensive: journal failure != desk failure."""
    import gazbot7.tournament as t

    def boom(*a, **k):
        raise RuntimeError("journal exploded")

    monkeypatch.setattr(cj, "record", boom)
    called = {}
    # stub `run` itself (not just asyncio.run) so no un-awaited coroutine is ever created
    monkeypatch.setattr(t, "run", lambda *a, **k: "coro-stub")
    monkeypatch.setattr(t.asyncio, "run", lambda *a, **k: called.setdefault("ran", True))
    monkeypatch.setenv("GAZBOT7_TOURNAMENT_SLATE", "scaleout")
    monkeypatch.delenv("GAZBOT7_TOURNAMENT_LIVE", raising=False)
    t.main()
    assert called.get("ran"), "the desk must still start when the config journal raises"


def test_plain_file_backup_covers_the_journal(tmp_path, monkeypatch):
    """★ The journal's whole purpose is durable history, and backup() only handles .db files — so
    without this the record lived on exactly one disk, as unrecoverable as the untracked
    exit_overrides.json it replaced."""
    from gazbot7 import maint
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    (root / "data" / "config_journal.jsonl").write_text('{"config_hash":"abc"}\n')
    (root / "data" / "exit_overrides.json").write_text("{}")
    bdir = tmp_path / "backups"
    out = maint.backup_plain_files(str(bdir), root=str(root), stamp="20260804T000000Z")
    names = {p.split("/")[-1] for p in out}
    assert "config_journal.jsonl.20260804T000000Z" in names
    assert "exit_overrides.json.20260804T000000Z" in names
    # a missing file is skipped, not fatal (gate_switches.env absent here)
    assert len(out) == 2


def test_plain_file_backup_prunes_and_never_raises(tmp_path):
    from gazbot7 import maint
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    (root / "data" / "config_journal.jsonl").write_text("{}\n")
    bdir = tmp_path / "b"
    for i in range(5):
        maint.backup_plain_files(str(bdir), root=str(root), keep=3,
                                 stamp=f"20260804T00000{i}Z")
    kept = sorted((bdir / "config").glob("config_journal.jsonl.*"))
    assert len(kept) == 3, "must prune to keep"
    # An unwritable destination must be swallowed, not raised. Use a FILE as the parent directory:
    # "/nonexistent/..." is not a valid test here because os.makedirs happily creates it when the
    # process can write / (as root in CI), so the copy would legitimately succeed.
    blocker = tmp_path / "iam_a_file"
    blocker.write_text("x")
    assert maint.backup_plain_files(str(blocker), root=str(root)) == []
