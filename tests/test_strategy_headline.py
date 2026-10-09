"""LAW 0e — THE STRATEGY IS THE HEADLINE — and the S line wired without touching the champion.

Operator, 2026-10-07: *"make it part of the constitution and let's start again."*

Two things must hold at once, and each has a test that calls the REAL entry point
([[a-source-text-test-is-a-lint-not-a-test]]):

  1. The champion's forward test is undisturbed. `shadow_runner` trades `sim_week_recursive.BRIEF`
     every five minutes, so BRIEF is frozen to a sha and the runner must still be using that very
     object. Editing it "to make the strategy the headline" would have silently changed the
     $620/day forward test mid-flight.
  2. The S line really gets the new strategy — the prompt the model receives, not the constant —
     including the grind exception, which the old per-call "YOUR BAND IS 3-6 TRADES" nag would have
     overridden on every call after the first trade.
[[a-memory-is-not-a-rule-until-it-is-in-the-prompt]] · [[a-written-rule-with-no-test-is-a-suggestion]]
"""
from __future__ import annotations

import hashlib
import math
import pathlib
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
sys.path.insert(0, str(GB / "src"))
sys.path.insert(0, str(GB / "scripts"))

import sim_week_recursive as SW          # noqa: E402
import forward_days as FD                # noqa: E402
import shadow_runner                     # noqa: E402
from gazbot7.bible import laws           # noqa: E402

FROZEN_BRIEF_SHA = "b314ac3c6cb758fed0932c02b6ad32d2e58cb97047f765d4bbc122d461697fd5"
DAY = "2026-02-05"


# ── 1. the champion is undisturbed ───────────────────────────────────────────────────────
def test_the_champions_brief_is_byte_identical():
    assert hashlib.sha256(SW.BRIEF.encode()).hexdigest() == FROZEN_BRIEF_SHA, (
        "sim_week_recursive.BRIEF changed — that is the prompt shadow_runner trades the frozen "
        "champion with. A new brief belongs in BRIEF_V2.")


def test_the_shadow_runner_still_trades_that_very_object():
    assert shadow_runner.S is SW
    assert shadow_runner.S.BRIEF is SW.BRIEF
    assert shadow_runner.S.BRIEF != SW.BRIEF_V2


# ── 2. what BRIEF_V2 says ────────────────────────────────────────────────────────────────
def test_brief_v2_carries_the_strategy_in_his_terms():
    b = SW.BRIEF_V2
    for needle in ("Buy (or sell) into the major leg", "you get in LATE", "you get out EARLY",
                   "a little earlier and out a little later", "Always out in profit",
                   "THERE ARE NO STOPS. YOU ARE THE EXIT", "TAKE IT", "$200-300",
                   "never enters against the leg", "its not urgent to jump in",
                   "The cure is to enter later next time, not to exit sooner"):
        assert needle.lower() in b.lower(), f"BRIEF_V2 lost: {needle}"


def test_brief_v2_has_the_grind_exception_and_no_cap():
    b = SW.BRIEF_V2
    assert "That is a\n  description, not a limit." in b
    assert "THE EXCEPTION, and it is great trading" in b
    assert "Asia and London grinds" in b
    assert "Do not hold back because the count is getting high" in b
    assert "target band" not in b and "at or over the limit" not in b.lower()


def test_brief_v2_does_not_contradict_the_strategy():
    """v1 says a +25pt exit on an intact leg is 'leaving the trade early, not banking a win' and
    that the window starts 06:00Z (it is 02:00Z). v2 must say the opposite of the first and the
    truth about the second."""
    b = SW.BRIEF_V2
    assert "leaving the trade early" not in b
    assert "06:00Z" not in b
    assert "the window is 02:00Z-13:30Z" in b and "flattened at 13:30Z" in b
    assert '{"action":"ENTER_LONG|ENTER_SHORT|EXIT|HOLD|WAIT"' in b      # single braces survived the f-string


def test_brief_for_rejects_an_unknown_line():
    assert SW.brief_for("v1") is SW.BRIEF and SW.brief_for("v2") is SW.BRIEF_V2
    with pytest.raises(ValueError):
        SW.brief_for("v9")


# ── 3. the REAL run_day: what the model is actually sent ─────────────────────────────────
def _bars(day: str):
    """1-min (ts, high, low, close) from the 22:00Z anchor to 13:30Z: a drifting, wobbling tape."""
    import datetime as dt
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    out = []
    for i, ts in enumerate(range(d0 - 2 * 3600, d0 + SW.WIN_END_MIN * 60 + 60, 60)):
        c = 20000 + 0.05 * i + 9 * math.sin(i / 11.0)
        out.append((ts, c + 1.0, c - 1.0, c))
    return out


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(SW, "OUT", str(tmp_path))
    monkeypatch.setattr(SW, "load_day", lambda day: (_bars(day), 0))
    seen = []
    cycle = iter(__import__("itertools").cycle(["ENTER_LONG", "EXIT"]))

    def fake_ask(prompt, timeout=180):
        seen.append(prompt)
        return {"action": next(cycle), "confidence": 0.7, "reason": "stub"}
    monkeypatch.setattr(SW, "ask", fake_ask)
    return seen


def test_v2_prompt_never_carries_the_band_nag(harness):
    rec = SW.run_day(DAY, "", "s_v2", resume=False, self_aware=True, line="v2")
    assert len(rec["trades"]) > 6, "the stub must trade past 6 or the over-the-limit branch is untested"
    assert rec["line"] == "v2"
    assert harness and all(p.startswith(SW.BRIEF_V2) for p in harness)
    assert not any("YOUR BAND IS" in p or "AT OR OVER THE LIMIT" in p for p in harness)
    assert any("WHAT YOU HAVE ALREADY DONE TODAY" in p for p in harness), \
        "self-awareness must stay on for v2 — only the nag is removed"


def test_v1_is_exactly_as_before(harness):
    rec = SW.run_day(DAY, "", "s_v1", resume=False, self_aware=True)
    assert rec["line"] == "v1"
    assert all(p.startswith(SW.BRIEF) for p in harness)
    assert any("YOUR BAND IS 3-6 TRADES A DAY" in p for p in harness)
    assert any("YOU ARE AT OR OVER THE LIMIT" in p for p in harness), "the v1 branch the champion sees is gone"


def test_an_unknown_line_costs_nothing(harness):
    with pytest.raises(ValueError):
        SW.run_day(DAY, "", "s_bad", resume=False, line="v9")
    assert harness == [], "a typo in the line must fail before a single paid call"


def test_resume_does_not_inherit_a_day_made_under_the_other_brief(harness):
    SW.run_day(DAY, "", "same_tag", resume=True, self_aware=True, line="v1")
    n_v1 = len(harness)
    SW.run_day(DAY, "", "same_tag", resume=True, self_aware=True, line="v1")
    assert len(harness) == n_v1, "same line + clean artefact must resume, not re-pay"
    rec = SW.run_day(DAY, "", "same_tag", resume=True, self_aware=True, line="v2")
    assert len(harness) > n_v1, "a v1 artefact was inherited as a v2 day"
    assert rec["line"] == "v2"


def test_an_artefact_from_before_the_line_key_existed_counts_as_v1(harness):
    """Every record on disk from before 2026-10-07 has no 'line'; they are v1 and must stay usable."""
    import json
    SW.run_day(DAY, "", "old_tag", resume=True, self_aware=True)
    p = pathlib.Path(SW.OUT) / f"old_tag_{DAY}.json"
    rec = json.loads(p.read_text()); rec.pop("line"); p.write_text(json.dumps(rec))
    n = len(harness)
    SW.run_day(DAY, "", "old_tag", resume=True, self_aware=True, line="v1")
    assert len(harness) == n
    assert FD.is_clean("old_tag", DAY, "v1") and not FD.is_clean("old_tag", DAY, "v2")


# ── 4. forward_days: the REAL main() routes the line to the right arm ────────────────────
def test_forward_days_routes_each_arm_to_its_own_line(harness, tmp_path, monkeypatch):
    rules_old = tmp_path / "IT2.txt"; rules_old.write_text("1. a rule\n")
    rules_new = tmp_path / "S1.txt"; rules_new.write_text("")
    calls = []

    def recorder(day, lessons, arm, resume=True, self_aware=False, line="v1", mil=False):
        calls.append((arm, line, self_aware, lessons))
        raise RuntimeError("stop after recording")        # main() logs a worker error and carries on
    monkeypatch.setattr(SW, "run_day", recorder)
    monkeypatch.setattr(FD, "OUT", str(tmp_path / "fd"))
    monkeypatch.setattr(FD, "say", lambda m: None)
    monkeypatch.setattr(FD.PA, "avail_mb", lambda: 10 ** 9)
    monkeypatch.setattr(sys, "argv", ["forward_days.py", "--days", DAY, "--model", "default",
                                      "--prefix", "tst", "--name", "route_test", "--workers", "1",
                                      "--arm", f"it2={rules_old}", "--arm", f"s1={rules_new}@v2"])
    assert FD.main() == 1                                  # nothing paired: the recorder never writes a day
    by_arm = {arm: (line, aware, lessons) for arm, line, aware, lessons in calls}
    assert by_arm["tst_it2"] == ("v1", True, "1. a rule\n")
    assert by_arm["tst_s1"] == ("v2", True, "")


def test_forward_days_still_refuses_a_holdout_day(monkeypatch, tmp_path):
    f = tmp_path / "r.txt"; f.write_text("")
    monkeypatch.setattr(sys, "argv", ["forward_days.py", "--days", "2026-09-15", "--model", "default",
                                      "--name", "holdout_probe", "--arm", f"s1={f}@v2"])
    with pytest.raises(AssertionError):
        FD.main()


def test_forward_days_requires_an_explicit_name(monkeypatch, tmp_path):
    f = tmp_path / "r.txt"; f.write_text("")
    monkeypatch.setattr(sys, "argv", ["forward_days.py", "--days", "2026-02-05", "--model", "default",
                                      "--arm", f"s1={f}@v2"])
    with pytest.raises(SystemExit):
        FD.main()


# ── 5. the constitution ──────────────────────────────────────────────────────────────────
def test_law_0e_text_carries_his_words_the_check_and_the_restart():
    t = laws()
    for needle in ("LAW 0e", "THE STRATEGY IS THE HEADLINE",
                   "buy late, half way up the leg and exit early to be safe",
                   "fine tune slightly and safely so we get in a little bit earlier",
                   "Always exiting in profit",
                   "If we are doing things outside that then we need to simplify",
                   "You'll\nbe stop lossed out all the time",
                   "(1) it enters a little EARLIER", "(2) it exits a little LATER",
                   "(3) it keeps exits IN PROFIT", "is CUT", "SIMPLIFIED",
                   "3-6 is a description of a normal day, NOT a limit",
                   "No prompt, rule or review may cap the count",
                   "THE RESTART", "EMPTY rule set", "A RESTART IS THE OPERATOR'S ALONE"):
        assert needle in t, f"Law 0e lost: {needle}"


def test_consistency_is_still_the_first_law():
    t = laws()
    assert t.index("LAW 0 —") < t.index("LAW 0e —")
    assert "THIS IS THE FIRST LAW" in t
    assert "LAW 0 (consistency) still decides which configuration is BETTER" in t


def test_the_s_line_starts_with_an_empty_rule_set():
    s1 = GB / "reports" / "recursive_loop" / "S1.txt"
    assert s1.exists() and s1.read_text().strip() == "", \
        "S1 is the restart: IT2's rules are NOT carried over (Law 0e)"


# ── 6. the pre-iteration audit lets the restart through — and ONLY the restart ───────────
import preflight_iteration as PF             # noqa: E402


@pytest.fixture
def pf(tmp_path, monkeypatch):
    rules = tmp_path / "rules.txt"; change = tmp_path / "change.txt"
    monkeypatch.setattr(PF, "RULES", str(rules)); monkeypatch.setattr(PF, "CHANGE", str(change))
    return rules, change


def test_an_empty_rule_set_is_refused_without_a_declared_restart(pf):
    rules, change = pf
    rules.write_text(""); change.write_text("IT6: tweak rule 3\n")
    ok, why = PF.rules_gate(6)
    assert not ok and "unparseable" in why, "a truncated file must still block an ordinary iteration"


def test_an_empty_rule_set_passes_only_with_the_restart_declared(pf):
    rules, change = pf
    rules.write_text("  \n"); change.write_text("S1 — DECLARED CHANGE   RESTART (LAW 0e)\n")
    ok, why = PF.rules_gate(6)
    assert ok and "EMPTY BY DESIGN" in why


def test_a_missing_rule_file_is_never_empty_by_design(pf):
    rules, change = pf
    change.write_text("RESTART (LAW 0e)\n")                 # the declaration alone is not enough
    assert not PF.rules_gate(6)[0]


def test_text_that_is_not_rules_is_never_empty_by_design(pf):
    rules, change = pf
    rules.write_text("be careful out there\n"); change.write_text("RESTART (LAW 0e)\n")
    assert not PF.rules_gate(6)[0], "garbage in the rules file is a parse failure, restart or not"


def test_numbered_rules_still_pass_as_before(pf):
    rules, change = pf
    rules.write_text("1. one\n2. two\n"); change.write_text("")
    assert PF.rules_gate(6) == (True, "rule set parses (2 rules)")


def test_the_audit_is_shown_the_brief_that_is_the_whole_strategy(pf):
    """With zero rules, BRIEF_V2 IS the strategy. An audit judging an empty file would judge nothing."""
    rules, change = pf
    rules.write_text(""); change.write_text("RESTART (LAW 0e)\n")
    brief = PF.state_brief(6)
    assert SW.BRIEF_V2 in brief and "THIS IS A LAW 0e RESTART" in brief
    change.write_text("IT6: ordinary\n"); rules.write_text("1. a\n")
    assert SW.BRIEF_V2 not in PF.state_brief(6), "an ordinary iteration must not be shown the S-line brief"


def test_the_audit_prompt_itself_carries_law_0e():
    assert "LAW 0e" in PF.AUDIT and "A RESTART IS THE OPERATOR'S ALONE" in PF.AUDIT


def test_an_s_line_change_is_shown_brief_v2_and_not_the_it_line_dead_text(pf):
    """S2 onward: rules are non-empty but the brief traded is BRIEF_V2. The audit must judge that, not rule 9."""
    rules, change = pf
    rules.write_text("1. a\n"); change.write_text("S2\nS LINE (BRIEF_V2)\n")
    brief = PF.state_brief(7)
    assert SW.BRIEF_V2 in brief and "S-LINE ITERATION" in brief
    assert "rule 9 ('stop after three losing trades') is DEAD TEXT" not in brief
    assert "THIS IS A LAW 0e RESTART" not in brief
    assert not PF.restart_declared(), "an S-line mark must never be read as a restart"
