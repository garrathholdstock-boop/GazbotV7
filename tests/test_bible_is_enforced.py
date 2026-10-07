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

from gazbot7.bible import L4_ONE_LINE, LAW_IDS, admissible, gate, laws, missing_laws  # noqa: E402

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
    missing = missing_laws(text)
    assert not missing, f"{mod}.{attr} is missing {missing}"


def test_the_presence_check_catches_a_deleted_law():
    """⚠ The first version of this test was `i not in text`: "L1" is found inside "L10" and
    "LAW 0" inside the laws() preamble, so L1, L2 and L4 could be deleted and it still passed
    (S1 audit, 2026-10-07). Delete each law's heading in turn from the REAL injected text and
    require the check to name exactly that law."""
    import re
    full = laws()
    assert missing_laws(full) == []
    for i in LAW_IDS:
        pat = rf"(?m)^★★★ {re.escape(i)} — .*\n" if i.startswith("LAW") else rf"(?m)^{re.escape(i)} — .*\n"
        cut = re.sub(pat, "", full, count=1)
        assert cut != full, f"could not delete {i} from the real text"
        assert missing_laws(cut) == [i], f"deleting {i} was reported as {missing_laws(cut)}"


def test_the_presence_check_is_not_fooled_by_a_law_mentioned_in_prose():
    text = "LAW 0e says this. L10 is here. see L1 and L2 and L4 and LAW 0"
    assert set(missing_laws(text)) == set(LAW_IDS)


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
    missing = [i for i in LAW_IDS if f"### {i} — " not in doc]
    assert not missing, f"the doc no longer has a heading for {missing}"
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


# ── L4 and L9 say the same thing in the code and in the docs ────────────────────────────
def _flat(t: str) -> str:
    return " ".join(t.split()).lower()


def test_l4_is_worded_as_the_gate_everywhere():
    """S1 audit finding 3: docs said "$/day AND days-positive" while bible.gate() also refuses a
    deeper worst day and a wider spread. The one-line statement must be in both docs."""
    for f in ("docs/CLAUDE.md", "docs/FINE_TUNING_BIBLE.md"):
        t = _flat((GB / f).read_text())
        assert _flat(L4_ONE_LINE) in t, f"{f} no longer states L4 as the gate does"
    assert "worst single day" in _flat(laws()) and "spread/mean" in _flat(laws())
    for f in ("docs/CLAUDE.md", "docs/FINE_TUNING_BIBLE.md"):
        t = (GB / f).read_text()
        assert "L4 beat the champion on $/day **AND**" not in t
        assert "on both axes" not in t.lower().split("### l4", 1)[-1][:200], f


def test_l9_cannot_block_entering_earlier():
    """S1 audit finding 6: L9 and the preflight STOP clause could be read as forbidding Law 0e(1),
    "enter a little earlier". Both the injected bible and the audit prompt must carry the
    exception, and the docs must agree."""
    import preflight_iteration as P
    for name, text in (("bible.laws()", laws()), ("preflight AUDIT", P.AUDIT)):
        t = _flat(text)
        assert "0e(1)" in t and "earlier" in t, f"{name} lost the entering-earlier exception"
    for f in ("docs/CLAUDE.md", "docs/FINE_TUNING_BIBLE.md", "docs/PROJECT_800_A_DAY.md"):
        t = _flat((GB / f).read_text())
        assert "earlier" in t and "0e(1)" in t, f
    assert "not in entry timing" not in _flat(laws())


# ── S1 audit finding 1: the v2 page must not carry the v1 leg list / band ───────────────
def _run_day_prompts(monkeypatch, tmp_path, line):
    """Call the REAL run_day on synthetic bars with ask() captured — no clock, no claude, no lake."""
    import datetime as dt
    import sim_week_recursive as SW
    day = "2026-02-05"
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    bars = []
    for k in range(-180, 14 * 60):                       # 21:00Z the evening before → 14:00Z
        ts = d0 + k * 60
        c = 20000.0 + max(k, 0) * 0.35 + (3.0 if k % 7 == 0 else 0.0)     # a steady up-leg
        bars.append((ts, c + 1.0, c - 1.0, c))
    seen: list[str] = []

    def fake_ask(prompt, *a, **kw):
        seen.append(prompt)
        act = {1: "ENTER_LONG", 2: "EXIT"}.get(len(seen), "WAIT")     # one closed trade, so the band line can render
        return {"action": act, "confidence": 0.5, "reason": "test"}

    monkeypatch.setattr(SW, "load_day", lambda d: (bars, bars[0][3]))
    monkeypatch.setattr(SW, "ask", fake_ask)
    monkeypatch.setattr(SW, "OUT", str(tmp_path))
    monkeypatch.setattr(SW, "WIN_START_MIN", 5 * 60)
    monkeypatch.setattr(SW, "WIN_END_MIN", 5 * 60 + 15)
    SW.run_day(day, "", f"t_{line}", resume=False, self_aware=True, line=line)
    assert seen, "run_day made no calls"
    return seen[-1]


def test_v2_page_carries_one_leg_picture_and_v1_is_unchanged(monkeypatch, tmp_path):
    v2 = _run_day_prompts(monkeypatch, tmp_path, "v2")
    v1 = _run_day_prompts(monkeypatch, tmp_path, "v1")
    assert "THE TAPE" in v2 and "THE TAPE" in v1
    for needle in ("the same legs as a list", "YOUR BAND"):
        assert needle not in v2, f"the v2 page still carries {needle!r} (S1 audit finding 1)"
    assert "the same legs as a list" in v1, "v1/shadow page lost the leg list it was frozen with"
    assert "YOUR BAND" in v1, "with self_aware=True the v1 page must still show its band (the mutation guard for v2)"


# ── the frozen champion's page: pinned against the code it was scored with ─────────────────
def _drive(monkeypatch, tmp_path, line, script, win_len=70):
    """Real run_day on deterministic synthetic bars; returns (every prompt, the day record)."""
    import datetime as dt
    import sim_week_recursive as SW
    day = "2026-02-05"
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    bars = []
    for k in range(-180, 14 * 60):
        ts = d0 + k * 60
        c = 20000.0 + max(k, 0) * 0.35 + (3.0 if k % 7 == 0 else 0.0) - (40.0 if 330 < k < 336 else 0.0)
        bars.append((ts, c + 1.0, c - 1.0, c))
    seen: list[str] = []

    def fake_ask(prompt, *a, **kw):
        seen.append(prompt)
        return {"action": script.get(len(seen), "WAIT"), "confidence": 0.5, "reason": "probe"}

    monkeypatch.setattr(SW, "load_day", lambda d: (bars, bars[0][3]))
    monkeypatch.setattr(SW, "ask", fake_ask)
    monkeypatch.setattr(SW, "OUT", str(tmp_path))
    monkeypatch.setattr(SW, "WIN_START_MIN", 300)
    monkeypatch.setattr(SW, "WIN_END_MIN", 300 + win_len)
    rec = SW.run_day(day, "", f"d_{line}", resume=False, self_aware=True, line=line)
    return seen, rec


PROBE = {1: "ENTER_LONG", 6: "EXIT", 7: "ENTER_SHORT", 11: "EXIT", 12: "ENTER_LONG"}
# sha256 prefix of the 14 assembled v1 pages for PROBE, computed from the code at commit 6e6f8f3 —
# BEFORE the S1 work touched sim_week_recursive — and identical on 72d47b5. shadow_runner trades the
# champion on this page; if this moves, the forward test is no longer a test of what scored $620.
V1_PAGES_SHA = "be3fbf009452658d"


def test_the_v1_page_is_byte_identical_to_the_one_the_champion_was_scored_on(monkeypatch, tmp_path):
    import hashlib
    seen, _ = _drive(monkeypatch, tmp_path, "v1", PROBE)
    assert len(seen) == 14
    got = hashlib.sha256("\n<<<>>>\n".join(seen).encode()).hexdigest()[:16]
    assert got == V1_PAGES_SHA, (
        "the v1 page changed. It is the FROZEN champion's input (shadow_runner imports it): "
        "put new behaviour behind line == 'v2', never into v1")


def test_peak_is_the_one_minute_peak_on_v2_and_the_sampled_one_on_v1(monkeypatch, tmp_path):
    """S1 audit: `peak` was updated only at 5-min call times, so a spike between calls vanished and
    the trade record's peak_pt (and the 'peak favourable so far' the model sees) under-read it."""
    _, r1 = _drive(monkeypatch, tmp_path, "v1", PROBE)
    _, r2 = _drive(monkeypatch, tmp_path, "v2", PROBE)
    short1, short2 = r1["trades"][1], r2["trades"][1]
    assert short1["peak_pt"] == 38.12 and short1["peak_1m"] > short1["peak_pt"], \
        "v1 must keep the sampled peak_pt (frozen) and only RECORD the true one beside it"
    assert short2["peak_pt"] == short2["peak_1m"] > short1["peak_pt"], "v2 must score on the true peak"


# ── the numbers a citation states are checked, not just its entry and exit ──────────────────
TRADE_N = dict(TRADE, side="SHORT", points=64.74, peak_pt=70.12, held_min=65.0)
CITE_N = dict(CITE, side="SHORT", recorded_pts=64.74, peak_pt=70.12, held_min=65.0)


def _find_n(day, t, entry):
    return TRADE_N if (day, round(entry, 2)) == ("2026-09-15", 29446.62) else None


def test_an_accurate_numeric_citation_is_admitted():
    ok, why = admissible({"trades": [CITE_N]}, _find_n)
    assert ok, why


@pytest.mark.parametrize("field,wrong", [("peak_pt", 120.0), ("recorded_pts", -5.0),
                                         ("held_min", 250.0), ("side", "LONG")])
def test_a_misstated_number_in_a_citation_is_refused(field, wrong):
    """'87pt in profit at its best' is the whole case for a claim rule; stating 120 when the
    record says 70 is the guess Law 0c exists to stop."""
    ok, why = admissible({"trades": [dict(CITE_N, **{field: wrong})]}, _find_n)
    assert not ok and field in why, why


def test_the_real_s1_citations_verify_against_the_recorded_runs():
    import glob
    import json
    cites = json.load(open(GB / "reports/recursive_loop/S1_cited_trades.json"))["trades"]
    by: dict = {}
    for f in glob.glob(str(GB / "reports/sim_week_recursive/fwd_it2_2026-06_*.json")):
        day = f.rsplit("_", 1)[1][:-5]
        by[day] = json.load(open(f))["trades"]
    if not by:
        pytest.skip("the recorded June runs are not on this box")
    ok, why = admissible({"trades": cites},
                         lambda d, t, e: next((x for x in by.get(d, []) if abs(x["entry"] - e) < 0.01), None))
    assert ok, why


# ── missing_laws checks the body, not just the heading ──────────────────────────────────────
def test_a_law_with_its_heading_kept_and_its_body_gutted_is_caught():
    """A prompt that kept 'L2 — ONE RULE PER ITERATION.' and lost the sentence that says what it
    means told the model a law exists and not what it says."""
    full = laws()
    cut = full.replace('Exactly one. Not "one theme", not "a few related clauses".', "")
    assert cut != full and missing_laws(cut) == ["L2"]
    cut0 = full.replace("THIS IS THE FIRST LAW.", "")
    assert cut0 != full and missing_laws(cut0) == ["LAW 0"]


# ── dated numbers, and one L9 ────────────────────────────────────────────────────────────────
def test_the_gate_text_dates_its_champion_numbers_and_points_at_the_live_record():
    from gazbot7.bible import GATE
    assert "AS OF 2026-10-07" in GATE and "CHAMPION.json" in GATE


def test_l9_is_one_sentence_everywhere_and_demands_a_confirmed_leg():
    import preflight_iteration as P
    import recursive_loop as RL
    for name, text in (("bible.laws()", laws()), ("preflight AUDIT", P.AUDIT), ("CONSOLIDATE", RL.CONSOLIDATE)):
        t = _flat(text)
        assert "already trades" not in t and "hold to structure" not in t, name
    for f in ("docs/CLAUDE.md", "docs/FINE_TUNING_BIBLE.md"):
        t = _flat((GB / f).read_text())
        assert "already trades" not in t and "hold to structure" not in t, f
        assert "confirmed" in t.split("l9", 1)[-1][:900], f
    assert "confirmed" in _flat(laws()).split("l9 — ", 1)[1][:900]


# ── the loop defends the champion the gate chose, and shows the reviewer THAT set ────────────
def test_consolidate_shows_the_gate_champion_not_the_highest_dollar_iteration(monkeypatch, tmp_path):
    import json
    import recursive_loop as RL

    def h(i, usd, pos, worst, sd):
        return {"iter": i, "holdout": dict(usd_per_day=usd, days_positive=pos, days=10, worst_day=worst,
                                           daily_sd=sd, trades_per_day=4.0)}
    hist = [h(1, 300.0, 6, -900.0, 600.0), h(2, 620.0, 9, -496.0, 725.0),
            h(3, 900.0, 7, -1400.0, 1500.0)]                      # earns most, fails the gate
    (tmp_path / "history.json").write_text(json.dumps(hist))
    for i in (1, 2, 3):
        (tmp_path / f"IT{i}.txt").write_text(f"RULES-OF-ITERATION-{i}")
    monkeypatch.setattr(RL, "OUT", str(tmp_path))
    monkeypatch.setattr(RL.SW, "load_day", lambda d: ([], 0.0))
    monkeypatch.setattr(RL.SP, "page", lambda *a, **k: "PAGE")
    captured = {}

    class _P:
        stdout = "x" * 200

    def fake_run(cmd, **kw):
        captured["prompt"] = cmd[-1]
        return _P()

    monkeypatch.setattr(RL.subprocess, "run", fake_run)
    RL.consolidate([{"day": "2026-02-05", "trades": [], "net_usd": 0.0}], "CARRIED")
    p = captured["prompt"]
    assert "THE CHAMPION IS ITERATION 2's SET" in p and "RULES-OF-ITERATION-2" in p
    assert "RULES-OF-ITERATION-3" not in p and "RULES-OF-ITERATION-1" not in p


def test_a_hand_written_champion_json_is_read_with_its_own_key_names(monkeypatch, tmp_path):
    import json
    import recursive_loop as RL
    (tmp_path / "CHAMPION.json").write_text(json.dumps({"champion_iter": 2, "file": "IT2.txt", "sha": "abc",
                                                       "holdout": {"usd_per_day": 619.6}}))
    monkeypatch.setattr(RL, "OUT", str(tmp_path))
    c = RL.champion_record([])
    assert c["iter"] == 2 and c["rules_path"].endswith("/IT2.txt") and c["rules_sha"] == "abc"


def test_meets_bar_reports_trades_per_day_but_does_not_fail_on_it():
    import recursive_loop as RL
    ok, why = RL.meets_bar({"usd_per_day": RL.BAR["usd_per_day"] + 1, "side_accuracy": 0.9, "capture": 0.9,
                            "trades_per_day": 12.0})
    assert ok and "ALL THREE MET" in why and "not a bar" in why


def test_gate_does_not_hand_a_free_pass_to_a_challenger_over_a_losing_baseline():
    """S1 baseline audit: abs(sd/mean) made a small-NEGATIVE baseline look hugely spread, so any
    challenger cleared the CV term for free. A non-positive mean has no CV; a challenger that does
    not itself earn must be refused, and one that earns is judged on the other terms."""
    base = dict(days_positive=3, worst_day=-900.0, daily_sd=800.0, usd_per_day=-20.0)
    still_losing = dict(days_positive=4, worst_day=-800.0, daily_sd=500.0, usd_per_day=-5.0)
    ok, why = gate(still_losing, base)
    assert not ok and "not profitable" in why, why
    earning = dict(days_positive=5, worst_day=-700.0, daily_sd=600.0, usd_per_day=150.0)
    ok, why = gate(earning, base)
    assert ok, why
    worse_days = dict(days_positive=2, worst_day=-700.0, daily_sd=600.0, usd_per_day=150.0)
    ok, why = gate(worse_days, base)
    assert not ok and "CONSISTENCY GATE FAILED" in why
