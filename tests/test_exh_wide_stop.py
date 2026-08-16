"""exhaustion_short on the WIDE STOP — the live config, pinned to the report's tested cell.

Operator, 2026-08-16: "i want the wide stop that produces 3459.98 on exh short made live now.
as per the report. not into shadow."

REV2 Q2 answered "which exhaustion_short exit?" with the wide stop: **+$3,459.98** against
**-$339.06** for the tight chandelier on the same 87 signals, the chandelier sitting at the 58th
percentile of its own random-entry control. The report filed it as BUILD #1 (shadow); the operator
took it live. These tests exist so the SHIPPED config stays the TESTED config — CLAUDE.md's standing
trap is a grind_long deploy where it did not ("FIX0's +$3,024 was measured with all six at 24, so
the shipped config is not the tested one").

The cell, in the report's units and ours:
    report:  stop 1.5xATR / target 2.0R / no cap
    ours:    stop_atr_mult=1.5, target_r=2.0  ->  target = 2.0 * 1.5 * ATR = 3.0 x ATR
             (which is why exh_exit_grid2.json indexes the same cell as tgt_k=3.0)
"""
import json

from gazbot7.slot_strategy import scaleout_slots

OVERRIDES = "/home/alphabot/gazbot7/data/exit_overrides.json"


def _exh():
    return [s for s in scaleout_slots() if s.tag.startswith("exhaustion_short")]


def test_both_lots_run_the_tested_policy():
    """The grid tested ONE policy per signal, so both lots carry it — not an A/B."""
    lots = _exh()
    assert len(lots) == 2
    for s in lots:
        assert s.exit == "scalp", "the chandelier is NOT-AN-ACTION #14 — it cannot beat a coin"
        assert s.stop_atr_mult == 1.5, "the wide stop IS the finding; 1.0 is the losing config"
        assert s.target_r == 2.0
        assert s.target_r * s.stop_atr_mult == 3.0, "target must be 3.0 x ATR from entry"


def test_no_quiet_tape_clip_because_the_tested_policy_had_none():
    """The clip rewrites both lots' targets below ATR 22. The graded cell had no clip, so leaving it
    on would ship a config the grid never measured — silently, and only on quiet days."""
    for s in _exh():
        assert s.atr_split == 0.0, "the quiet-tape clip must be OFF for this gate"
        assert s.lo_target_usd == 0.0 and s.lo_target_r == 0.0


def test_no_time_cap_because_the_cell_was_no_cap():
    for s in _exh():
        assert s.max_hold_s == 0.0, "'no cap' is part of the tested policy"


def test_NO_OTHER_GATE_MOVED():
    """`stop_k` is a new lever on a SHARED code path. Everything without the key must be untouched —
    a default that leaked would re-stop the whole desk on one gate's evidence."""
    others = [s for s in scaleout_slots() if not s.tag.startswith("exhaustion_short")]
    assert others, "sanity: the slate is not empty"
    for s in others:
        assert s.stop_atr_mult == 1.0, f"{s.tag} stop moved and should not have"


def test_the_override_file_says_what_the_slate_resolved_to():
    """Verify config via scaleout_slots(), never source — and check the FILE agrees, because the
    slate is built from it and a hand-edit is how the two drift apart."""
    o = json.load(open(OVERRIDES))["exhaustion_short"]
    assert o == {"a_r": 2.0, "b": 2.0, "stop_k": 1.5}, o
    assert "atr_split" not in o and "lo" not in o


def test_stop_k_is_validated_and_cannot_size_the_desk_by_typo():
    from gazbot7.slot_strategy import _load_exit_overrides
    import tempfile, os, gazbot7.slot_strategy as ss

    def _with(raw):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(raw, f)
        old = ss._EXIT_OVERRIDES_PATH
        ss._EXIT_OVERRIDES_PATH = path
        try:
            return _load_exit_overrides()
        finally:
            ss._EXIT_OVERRIDES_PATH = old
            os.unlink(path)

    assert _with({"g": {"a_r": 2.0, "b": 2.0, "stop_k": 1.5}})["g"]["stop_k"] == 1.5
    for bad in (0, -1, 50, 5.1, "wide", None):
        got = _with({"g": {"a_r": 2.0, "b": 2.0, "stop_k": bad}})["g"]
        assert "stop_k" not in got, f"stop_k={bad!r} must be rejected, falling back to 1.0"
