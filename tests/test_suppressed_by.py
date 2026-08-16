"""BUILD #6 — `signal_journal.suppressed_by` stops being a dead column.

It was NULL in every row because the one caller passed neither it nor `taken`, so any question of
the form "the gate fired, why didn't we take it?" was unanswerable from the journal that exists to
answer exactly that.

⚠ THESE TESTS EXIST BECAUSE THE FIRST IMPLEMENTATION FAILED SILENTLY. `_switches_off()` uses
`os.path.getmtime`, `os` was not imported in this module, the NameError was swallowed by the
fail-open handler, and the reasoner cheerfully reported that NO gate was switched off while three
were. Fail-open is right — inventing suppressions would be worse — but it means only a test can tell
you the reader works.
"""
import json
import os

import pytest

from gazbot7 import cl_sims as C


class _F:
    """Minimal Features stand-in — the reasoner reads only .atr."""

    def __init__(self, atr):
        self.atr = atr


@pytest.fixture
def switches(tmp_path, monkeypatch):
    """Point the reader at a scratch switch file and clear its mtime cache."""
    p = tmp_path / "gate_switches.env"

    def _write(text):
        p.write_text(text)
        monkeypatch.setattr(C, "_SWITCH_PATH", str(p))
        C._SW_CACHE["mtime"] = -1.0
        return p

    return _write


def test_the_reader_ACTUALLY_READS_the_file(switches):
    """The regression test for the os-import bug: an empty result must mean an empty file."""
    switches("grind_long=off\nrgv_short=off\ncapitulation_long=on\n")
    assert C._switches_off() == frozenset({"grind_long", "rgv_short"})


def test_an_unreadable_file_is_UNKNOWN_not_an_empty_set(monkeypatch):
    """★ AUDIT FINDING. This used to return frozenset() — correct in that it invents no
    suppressions, but it then made a BENCHED gate read as 'none_visible': the exact wrong story this
    column exists to stop telling, written PERMANENTLY into signal_journal rather than transiently
    into a report. Two states were not enough; there is now a third for "could not tell"."""
    monkeypatch.setattr(C, "_SWITCH_PATH", "/nonexistent/gate_switches.env")
    C._SW_CACHE["mtime"] = -1.0
    assert C._switches_off() is None, "unreadable must be None, not 'nothing is off'"

    class _F:
        atr = 8.0
    assert C.suppression_reason("grind_long", _F()) == C.SWITCH_UNREADABLE
    assert C.SWITCH_UNREADABLE != C.NOT_VISIBLE


def test_the_cache_notices_an_edit(switches):
    switches("grind_long=off\n")
    assert "grind_long" in C._switches_off()
    p = switches("grind_long=on\n")
    os.utime(p, (0, 0))          # force a distinct mtime
    C._SW_CACHE["mtime"] = -1.0
    assert C._switches_off() == frozenset()


def test_the_switch_is_checked_BEFORE_the_floors(switches):
    """A benched gate never reaches its ATR floor in tournament.step(), so reporting 'atr_floor'
    would be a true statement about a test the desk never ran."""
    switches("grind_long=off\n")
    assert C.suppression_reason("grind_long", _F(atr=8.0)) == "switch_off"


def test_the_atr_floor_is_reported_when_the_gate_is_armed(switches):
    switches("")
    assert C.suppression_reason("capitulation_long", _F(atr=8.0)) == "atr_floor"   # floor 10
    assert C.suppression_reason("capitulation_long", _F(atr=30.0)) == C.NOT_VISIBLE


def test_an_UNSUPPRESSED_fire_is_a_SENTINEL_never_NULL(switches):
    """NULL would read exactly like 'nothing suppressed it' — the dead-column bug one level down."""
    switches("")
    r = C.suppression_reason("abs_veto_short", _F(atr=30.0))
    assert r == "none_visible" and r is not None


def test_the_blind_spots_are_not_silently_claimed():
    """slot_busy and veto need live desk state this loop does not have. If a future change starts
    emitting them from here, it is either wired to the desk (fine — update this test) or lying."""
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "src", "gazbot7", "cl_sims.py")).read()
    body = src[src.index("def suppression_reason"):src.index("def journal(")]
    for blind in ("slot_busy", "veto"):
        assert f'"{blind}"' not in body, \
            f"{blind} cannot be determined from the shadow loop — see the module note"


def test_journal_writes_the_reason_and_leaves_taken_NULL(tmp_path):
    """`taken` must stay NULL: this loop cannot see whether a live position resulted, and a guessed
    1 would replace a dead column with a wrong one."""
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.executescript(C.SCHEMA if hasattr(C, "SCHEMA") else "")
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='signal_journal'").fetchone()
    if not row:
        pytest.skip("schema not exposed as a module constant; covered by the live table")
    class _Bar:
        high = low = close = 100.0

    class _Full(_F):
        """journal() reads the WHOLE feature row. A thin stub makes it raise, and its handler is a
        deliberate bare `except: pass` — so an incomplete stub here looks exactly like a write that
        did not happen, which is how this test failed the first time it was run."""
        atr_pct = 0.002
        ext_atr = 0.5
        vwap_slope_atr = 0.1
        vwap_slope_fast = 0.1
        net_atr_2 = 0.0
        net_atr_5 = 0.0

    C.journal(con, ts_ms=1, gate="grind_long", side="LONG", price=100.0,
              f=_Full(atr=20.0), bars=[_Bar()] * 40, tape_net=0,
              suppressed_by="switch_off")
    got = con.execute("SELECT taken, suppressed_by FROM signal_journal").fetchone()
    assert got == (None, "switch_off")
