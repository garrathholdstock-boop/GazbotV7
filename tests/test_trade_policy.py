"""THE TRADE POLICY AND THE NIGHTLY LAB — the leash, and the floor it may not reach.

★★★ docs/SCOPE_RECURSIVE_TRADING_LOOP.md. Operator: *"the nightly lab should just be fine tuning
entries and exits. thats it. metrics changed sloghrly for the next day."*

These tests exist because this is the first thing on the desk that CHANGES TRADING NUMBERS WITHOUT A
HUMAN IN THE LOOP. Everything that makes that safe is mechanical and therefore testable: the loop
writes data and never code, one parameter moves per night by one step, the floor is unreachable, and
an invalid file degrades to BASELINE rather than to whatever happened to be in the file.
"""

from __future__ import annotations

import ast
import json

import pytest

from gazbot7 import trade_policy as tp

LAB = "scripts/nightly_lab.py"


# ── THE FLOOR IS UNREACHABLE ────────────────────────────────────────────────────────────────────

def test_the_policy_cannot_name_the_safety_floor():
    """⚠⚠⚠ The 20:40Z hard flat, eod_flatten, desk_reconcile, the daily loss limit and the
    catastrophe stop are the FLOOR. A research loop may not reach them at any price. A cross-desk
    kill once disarmed the desk it was protecting for four hours; the floor is what stops a bad
    number becoming a bad position."""
    for forbidden in ("daily_loss_limit", "hard_flat_utc", "venue_stop_pt", "kill_switch",
                      "lots", "account_id"):
        ok, why = tp.validate({**tp.BASELINE, forbidden: 1.0})
        assert not ok, f"{forbidden} was accepted into a policy"
        assert forbidden.split("_")[0] in why.lower() or "undeclared" in why.lower()


def test_no_parameter_controls_SIZE_or_the_ORDER_PATH():
    """The loop tunes WHEN to enter and exit. It may never tune HOW MUCH — size is the one knob
    that turns a bad rule into a large loss."""
    for p in tp.PARAMS:
        assert not any(w in p.name for w in ("lot", "qty", "size", "account")) \
            or p.name == "exit_lot1_target_pt", f"{p.name} looks like a sizing parameter"
    assert all(p.unit in ("ATR", "minutes", "points", "trades") for p in tp.PARAMS)


# ── THE LEASH: ONE PARAMETER, ONE STEP ──────────────────────────────────────────────────────────

def test_every_candidate_is_ONE_STEP_on_ONE_PARAMETER():
    """★★ "changed slightly", made mechanical. A grid over seven parameters is how a nightly loop
    becomes a noise-mining machine; a one-step walk has to survive forward evidence at every
    intermediate point."""
    for name, value, cand in tp.neighbours(tp.BASELINE):
        diff = [k for k in tp.BY_NAME if cand[k] != tp.BASELINE[k]]
        assert diff == [name], f"candidate moved {diff}, not just {name}"
        p = tp.BY_NAME[name]
        assert abs(abs(value - tp.BASELINE[name]) - p.step) < 1e-9, \
            f"{name} moved more than one step"


def test_the_candidate_set_is_small_and_bounded():
    """At most 2 per parameter. If this ever grows into the hundreds the leash has been cut."""
    n = len(tp.neighbours(tp.BASELINE))
    assert n <= 2 * len(tp.PARAMS)
    assert n < 40, f"{n} candidates a night is a grid search, not a fine-tune"


def test_candidates_never_leave_the_declared_range():
    edge = {p.name: p.hi for p in tp.PARAMS}
    for _n, _v, cand in tp.neighbours(edge):
        ok, why = tp.validate(cand)
        assert ok, why


# ── FAIL CLOSED ─────────────────────────────────────────────────────────────────────────────────

def test_an_INVALID_file_falls_back_to_BASELINE_and_says_so(tmp_path):
    """⚠ Not to the file's contents, and not silently. A coerced value is a number nobody can
    trace to an experiment, and traceability is this layer's whole promise."""
    f = tmp_path / "p.json"
    f.write_text(json.dumps({**tp.BASELINE, "exit_min_hold_min": 999.0}))
    pol, note = tp.load(str(f))
    assert pol == tp.BASELINE
    assert "INVALID" in note and "999" in note


def test_a_MISSING_file_runs_baseline(tmp_path):
    pol, note = tp.load(str(tmp_path / "nope.json"))
    assert pol == tp.BASELINE and "BASELINE" in note


def test_an_OFF_GRID_value_is_refused(tmp_path):
    ok, why = tp.validate({**tp.BASELINE, "exit_min_hold_min": 7.5})
    assert not ok and "step grid" in why


def test_save_REFUSES_to_write_an_invalid_policy(tmp_path):
    with pytest.raises(ValueError):
        tp.save({**tp.BASELINE, "exit_giveback_atr": 99.0}, str(tmp_path / "x.json"))


def test_save_is_ATOMIC(tmp_path):
    """A reader must never see half a policy — the rider would read it mid-write."""
    src = open("src/gazbot7/trade_policy.py", encoding="utf-8").read()
    assert "os.replace" in src, "write must be a rename, not an in-place truncate"


# ── THE LAB ITSELF ──────────────────────────────────────────────────────────────────────────────

def test_the_lab_writes_SHADOW_and_never_the_ACTIVE_policy():
    """⚠⚠⚠ Promotion is a human act. Nothing trades on the shadow file."""
    src = open(LAB, encoding="utf-8").read()
    assert "tp.SHADOW_PATH" in src
    assert "tp.POLICY_PATH" not in src.split("def main")[1], \
        "the lab must not write the active policy"


def test_the_lab_has_NO_order_path_and_makes_NO_broker_calls():
    """Asserted against the SOURCE via AST, the same standard every read-only watcher here meets."""
    src = open(LAB, encoding="utf-8").read()
    for banned in ("ib_async", "connectAsync", "placeOrder", "/api/control",
                   "day_rider_claim", "day_rider_buy", "gate_switches", "subprocess"):
        assert banned not in src, f"the lab must not reference {banned}"
    tree = ast.parse(src)
    imports = {n.module.split(".")[0] for n in ast.walk(tree)
               if isinstance(n, ast.ImportFrom) and n.module}
    imports |= {a.name.split(".")[0] for n in ast.walk(tree)
                if isinstance(n, ast.Import) for a in n.names}
    assert "subprocess" not in imports and "requests" not in imports


def test_the_lab_CHARGES_THE_SEARCH():
    """⚠ 16 candidates against a holdout is 16 chances to be fooled. 5,026 specs once reproduced a
    published t=5.83 from pure noise 13% of the time here, and 6 of 6 NULL worlds cleared three
    naive bars. The margin must scale with the number of candidates scored."""
    src = open(LAB, encoding="utf-8").read()
    assert "charged" in src and "len(cands)" in src
    assert "MARGIN_PP" in src


def test_the_lab_requires_NEIGHBOURHOOD_AGREEMENT():
    """A lone good cell is noise. The step's own next step must also beat baseline."""
    src = open(LAB, encoding="utf-8").read()
    assert "agree" in src and "further" in src


def test_the_lab_does_not_tune_ENTRY_parameters_yet():
    """★ Every automated entry rule measured so far sits inside the noise of a random entry on the
    same tape, so tuning one would be tuning noise. The parameters are CARRIED and REPORTED but
    skipped, and the report says why. This test is the thing that makes that a rule rather than an
    intention — and it should be DELETED, deliberately, when the greenfield study names a signal."""
    src = open(LAB, encoding="utf-8").read()
    assert 'name.startswith("entry_")' in src and "continue" in src


def test_the_decision_metric_can_actually_MOVE():
    """⚠⚠2026-10-02 THE FIRST DRY RUN SCORED +0.00pp ON ALL 16 CANDIDATES. LCR is floored at 0 for a
    losing exit and about half of any entry sample loses, so the MEDIAN pins to 0.0 and no exit
    parameter can shift it. A metric that cannot move is indistinguishable from a rule that does not
    work: the lab would have reported a confident NO CHANGE every night forever. The decision metric
    is the MEAN for exactly this reason."""
    src = open(LAB, encoding="utf-8").read()
    dec = src.split("scored.sort", 1)[0].split("cands = tp.neighbours", 1)[1]
    assert 'lcr_mean' in dec, "the decision must be taken on the mean, not the pinned median"
    assert 'lcr_median' not in dec.split("delta =")[1].split("\n")[0]
