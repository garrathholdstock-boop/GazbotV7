"""THE BIBLE MUST BE IN EVERY PROMPT THAT WRITES OR JUDGES A RULE SET.

★★★ Operator, 2026-10-06: *"how do we make the AI always abide. Just like Claude code does.
If it sits outside CLAUDE.md you don't do it."*

That is the whole design question and he answered it himself. `CLAUDE.md` binds because it is
injected into every session automatically — not because it is well written. So this test is
the enforcement, and `docs/FINE_TUNING_BIBLE.md` is only documentation.

⚠⚠ THE FAILURE THIS EXISTS TO CATCH ALREADY HAPPENED. The first attempt at these laws patched
`recursive_loop`'s module DOCSTRING instead of its `CONSOLIDATE` prompt. The diff read
correctly. Capturing the assembled prompt and grepping it showed L1, L2 and L5 MISSING while
the champion block was present — i.e. the loop would have run for hours believing itself
governed by laws no model ever saw.
[[a-written-rule-with-no-test-is-a-suggestion]] · [[a-memory-is-not-a-rule-until-it-is-in-the-prompt]]
"""
from __future__ import annotations

import pathlib
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
sys.path.insert(0, str(GB / "src"))
sys.path.insert(0, str(GB / "scripts"))

from gazbot7.bible import LAW_IDS, admissible, gate, laws        # noqa: E402

# (module, prompt attribute) — every place a rule set is written, reviewed or judged
BOUND = [
    ("recursive_loop", "CONSOLIDATE"),   # writes the next rule set
    ("sim_week_recursive", "REVIEW"),    # writes the lessons that become rules
    ("preflight_iteration", "AUDIT"),    # judges whether a planned change is sound
]


@pytest.mark.parametrize("mod,attr", BOUND)
def test_prompt_contains_every_law(mod, attr):
    m = __import__(mod)
    text = getattr(m, attr)
    assert isinstance(text, str) and text, f"{mod}.{attr} is not a prompt string"
    missing = [i for i in LAW_IDS if i not in text]
    assert not missing, f"{mod}.{attr} is missing {missing}"


@pytest.mark.parametrize("mod,attr", BOUND)
def test_law_zero_is_present_and_named_as_first(mod, attr):
    """Consistency outranks return. If only one law survives an edit, it must be this one."""
    text = getattr(__import__(mod), attr)
    assert "CONSISTENCY OUTRANKS RETURN" in text, f"{mod}.{attr} lost Law 0"
    assert "THIS IS THE FIRST LAW" in text


def test_the_doc_and_the_code_cannot_drift():
    """docs/FINE_TUNING_BIBLE.md is documentation; bible.py is the source. The doc must still
    name every law, or a reader is told a different set of rules than the model is given."""
    doc = (GB / "docs" / "FINE_TUNING_BIBLE.md").read_text()
    missing = [i for i in LAW_IDS if i not in doc]
    assert not missing, f"the doc no longer names {missing}"
    assert "bible.py" in doc or "FINE_TUNING_BIBLE" in doc


# ── the gate itself, on the real measured arms ──────────────────────────────────────────
CHAMP = dict(days_positive=9, worst_day=-496.0, daily_sd=724.0, usd_per_day=619.6)


@pytest.mark.parametrize("name,arm", [
    ("iter1", dict(days_positive=6, worst_day=-1180.0, daily_sd=1024.0, usd_per_day=508.6)),
    ("iter3", dict(days_positive=6, worst_day=-780.0, daily_sd=910.0, usd_per_day=405.6)),
    ("exitfix", dict(days_positive=6, worst_day=-1882.0, daily_sd=1060.0, usd_per_day=294.0)),
])
def test_gate_rejects_every_arm_measured_so_far(name, arm):
    ok, why = gate(arm, CHAMP)
    assert not ok, f"{name} should not replace the champion: {why}"
    assert "CONSISTENCY GATE FAILED" in why


def test_gate_rejects_a_higher_average_bought_with_worse_consistency():
    """The operator's exact objection: *"If we maximise one day to $2000 but then have 3
    negatives or $200 days it's no good."* A challenger earning MORE on average must still be
    refused when it lurches."""
    lurchy = dict(days_positive=6, worst_day=-2000.0, daily_sd=1800.0, usd_per_day=900.0)
    ok, why = gate(lurchy, CHAMP)
    assert not ok, "a lurching challenger with a higher average was accepted"
    assert "CONSISTENCY GATE FAILED" in why


def test_gate_accepts_only_a_genuine_improvement():
    better = dict(days_positive=10, worst_day=-300.0, daily_sd=600.0, usd_per_day=700.0)
    ok, why = gate(better, CHAMP)
    assert ok, why


def test_gate_refuses_a_flat_but_tidy_challenger():
    """Consistency first does NOT mean consistency only — it must also earn more."""
    tidy = dict(days_positive=10, worst_day=-100.0, daily_sd=200.0, usd_per_day=400.0)
    ok, why = gate(tidy, CHAMP)
    assert not ok and "no more money" in why


def test_gate_uses_cv_not_raw_sd():
    """A configuration earning twice as much is allowed twice the absolute spread; comparing
    raw SD would reject every genuine improvement in scale."""
    scaled = dict(days_positive=9, worst_day=-496.0,
                  daily_sd=CHAMP["daily_sd"] * 1.5, usd_per_day=CHAMP["usd_per_day"] * 2)
    ok, why = gate(scaled, CHAMP)
    assert ok, f"raw-SD thinking rejected a scaled improvement: {why}"


# ── Law 0c: no change without trades ────────────────────────────────────────────────────
TRADE = {"entry": 29446.62, "exit": 29381.88, "why": "CLAUDE_EXIT", "entry_reason": "Day's side is short"}
CITE = dict(day="2026-09-15", entry_time="03:20", entry=29446.62, exit=29381.88,
            reason="CLAUDE_EXIT", would_have="held a further 40pt to the 05:55 low")


def _find(day, t, entry):
    return TRADE if (day, round(entry, 2)) == ("2026-09-15", 29446.62) else None


def test_law_0c_is_in_every_bound_prompt():
    for mod, attr in BOUND:
        text = getattr(__import__(mod), attr)
        assert "NO CHANGE WITHOUT TRADES" in text and "ZERO GUESSING" in text, f"{mod}.{attr}"


def test_a_change_naming_no_trade_is_refused():
    ok, why = admissible({"rule": "hold longer"}, _find)
    assert not ok and "guess" in why


def test_a_citation_missing_a_field_is_refused():
    bad = dict(CITE); bad.pop("would_have")
    ok, why = admissible({"trades": [bad]}, _find)
    assert not ok and "would_have" in why


def test_a_trade_that_was_never_taken_is_refused():
    ghost = dict(CITE, entry=30000.0)
    ok, why = admissible({"trades": [ghost]}, _find)
    assert not ok and "matches no recorded trade" in why


def test_a_misstated_exit_is_refused():
    ok, why = admissible({"trades": [dict(CITE, exit=29300.0)]}, _find)
    assert not ok and "misstates" in why


def test_a_verified_citation_is_admitted():
    ok, why = admissible({"trades": [CITE]}, _find)
    assert ok, why


def test_law_0d_claim_the_profit_is_in_every_bound_prompt():
    """2026-10-07: the champion had no rule that claims a profit. The goal must be in the prompt,
    in his words, or the next iteration will not know it exists."""
    for mod, attr in BOUND:
        text = getattr(__import__(mod), attr)
        assert "LAW 0d" in text and "CLAIM THE PROFIT" in text, f"{mod}.{attr}"
        assert "when profit is decent. Take it!" in text, f"{mod}.{attr} lost his words"


def test_law_0e_the_strategy_is_the_headline_is_in_every_bound_prompt():
    """2026-10-07: the operator named the strategy — buy late in the major leg, exit early, always
    in profit — and made it the headline every rule must serve. If the sentence is not in the
    prompt, the next iteration will not know it exists."""
    for mod, attr in BOUND:
        text = getattr(__import__(mod), attr)
        assert "LAW 0e" in text and "THE STRATEGY IS THE HEADLINE" in text, f"{mod}.{attr}"
        assert "Always exiting in profit" in text, f"{mod}.{attr} lost his words"
        assert "A RESTART IS THE OPERATOR'S ALONE" in text, f"{mod}.{attr}"
        assert "No prompt, rule or review may cap the count" in text, f"{mod}.{attr}"
        assert "THIS IS THE FIRST LAW" in text, f"{mod}.{attr}: 0e must not displace Law 0"
