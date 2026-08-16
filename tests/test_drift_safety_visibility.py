"""The drift safety-block skip — open since 2026-08-06, now VISIBLE.

On `drift` the tournament's audit loop skips its entire safety block: max-hold, the naked auditor,
re-protect, stop-breach and the exit watchdog. The alarm disables the fire brigade. And because the
cycle still COMPLETED, `audit_age_s` stayed green and sweep read clean for the whole incident — the
loop was turning, only the work inside it was not.

⚠ WHAT THIS CHANGE DOES NOT DO, DELIBERATELY: it does not make any of those checks ACT under drift.
Drift means the book and the venue disagree on a shared, netted account, and acting then is exactly
how 08-06 happened — a flatten sized on the ACCOUNT net, and a stop left resting with no position
behind it that later opened a naked short. "Nobody may act unless venue == the sum of every desk's
claim" is untouched. Promoting any check to act under drift is an operator decision.
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import sweep                                     # noqa: E402


def _core(**over):
    h = {"ts": 0, "conn": "ok", "healthy": True, "place_live": True, "flat": True,
         "halted": False, "protection": {}, "audit_age_s": 1.0, "safety_skipped_cycles": 0}
    h.update(over)
    return h


def _status(h, monkeypatch, tmp_path):
    import json
    p = tmp_path / "core_health.json"
    p.write_text(json.dumps(h))
    return sweep.check_core(str(tmp_path)) if hasattr(sweep, "check_core") else None


def test_the_flag_is_published_at_all():
    """The regression for the whole bug: a number nothing publishes cannot be alarmed on."""
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "src", "gazbot7", "multislot_core.py")).read()
    assert '"safety_skipped_cycles"' in src, "the skip counter must reach core_health.json"
    assert "self._safety_skipped = 0" in src, "it must RESET on a healthy cycle, or it only grows"


def test_sweep_CRITs_when_the_block_is_skipped_while_holding():
    src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "sweep.py")).read()
    i = src.index("safety_skipped_cycles")
    block = src[i:i + 900]
    assert "status = CRIT" in block, "skipping safety while HOLDING must be CRIT, not WARN"
    assert 'not h.get("flat"' in block, "the CRIT must be conditioned on actually holding"


def test_the_alarm_names_what_is_inactive():
    """An alarm that says 'drift' teaches nothing; it must say which protections are off, because
    the whole failure was that nobody knew the fire brigade was disabled."""
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "src", "gazbot7", "multislot_core.py")).read()
    i = src.index("DRIFT: safety block SKIPPED")
    msg = src[i:i + 700]
    for word in ("max-hold", "naked-audit", "re-protect", "stop-breach", "exit watchdog"):
        assert word in msg, f"the alarm must name {word} as inactive"
    assert "audit_age" in msg, "it must say why the green light is meaningless"


def test_the_order_path_is_NOT_armed_under_drift():
    """The safety property. If a future edit moves flatten/reprotect into the drift branch, this
    fails — and that must be a deliberate operator decision, not a refactor."""
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "src", "gazbot7", "multislot_core.py")).read()
    i = src.index("self._safety_skipped = getattr(self")
    branch = src[i:src.index("cycle_ok = True", i)]
    for forbidden in ("_flatten_slot(", "_reprotect_slot(", "time_exit_check(", "claim_check("):
        assert forbidden not in branch, \
            f"{forbidden} must NOT run under drift — the account is shared and netted"
