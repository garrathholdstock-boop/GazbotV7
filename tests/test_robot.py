"""PROJECT ROBOT — the discipline is code, so the discipline is tested (docs/PROJECT_ROBOT.md §11).

Every test calls the REAL entry point; the reviewer and the trading step are the only stubs, and the
captured reviewer prompt is grepped ([[a-memory-is-not-a-rule-until-it-is-in-the-prompt]]).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
sys.path.insert(0, str(GB / "src"))
sys.path.insert(0, str(GB / "scripts"))

import robot_core as RC     # noqa: E402
import robot_loop as RL     # noqa: E402

DAY_L, DAY_V = "2026-04-09", "2026-07-01"
RULE1 = "1. When a position is up at least 2x ATR(14,1m) on the page, claim it.\n"


@pytest.fixture()
def rd(tmp_path, monkeypatch):
    monkeypatch.setattr(RC, "ROBOT_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_MODEL", "x")           # restored on teardown, so the pin never leaks between tests
    monkeypatch.setenv("ROBOT_NO_TOOLS", "0")            # likewise for the tools switch sw() sets
    RL.sw()
    RC.save_rules(0, RULE1)
    RL.set_champion(0, RULE1, 0, "seed")
    return tmp_path


def trade(opened="05:10", entry=100.0, pnl=100.0, peak=10.0, day=DAY_L):
    return {"side": "LONG", "entry": entry, "exit": entry + 5, "opened": f"{day}T{opened}:00+00:00",
            "closed": f"{day}T{opened[:2]}:59:00+00:00", "held_min": 30.0, "points": pnl / 8, "peak_pt": peak,
            "pnl_usd": pnl, "why": "CLAUDE_EXIT", "entry_reason": "r", "peak_1m": peak}


def rec(day, trades, net=None, err=0):
    calls = [{"ts": f"{day}T05:{i:02d}:00+00:00", "px": 100.0, "action": "WAIT", "conf": 5, "reason": "x",
              "error": "boom" if i < err else None, "holding": False} for i in range(20)]
    return {"day": day, "arm": "stub", "line": "v2", "trades": trades, "calls": calls,
            "net_usd": net if net is not None else sum(t["pnl_usd"] for t in trades)}


def prop(**kw):
    p = {"change": "ADD", "new_text": "After a claim, do not re-enter the same side for 15 minutes.",
         "serves": "EXITS_IN_PROFIT", "metric": "same_side_rebuy_15", "direction": "down", "min_move": 1,
         "trigger_on_page": "a claim just printed", "expected_cost": "misses a fast resumption",
         "not_a_stop_not_a_cap": True,
         "cited_trades": [{"opened": "05:10", "entry": 100.0, "why_it_matters": "a"},
                          {"opened": "06:10", "entry": 101.0, "why_it_matters": "b"},
                          {"opened": "07:10", "entry": 102.0, "why_it_matters": "c"}]}
    p.update(kw)
    return p


LT = [trade("05:10", 100.0), trade("06:10", 101.0), trade("07:10", 102.0)]


# ---------------------------------------------------------------- one-rule diff validator
def test_valid_add_passes_and_is_one_rule():
    ok, why = RC.validate_proposal(prop(), RULE1, [], LT, DAY_L)
    assert ok, why
    assert RC.diff_is_one_rule(RULE1, RC.apply_proposal(RULE1, prop()))


@pytest.mark.parametrize("bad,frag", [
    ({"not_a_stop_not_a_cap": False}, "stop"),
    ({"new_text": "Exit at 09:30 every day."}, "clock"),
    ({"new_text": "Cut the position at a loss of $300."}, ""),
    ({"new_text": "Use a hard stop 10 points below entry."}, ""),
    ({"metric": "sharpe"}, "menu"),
    ({"metric": "trades_per_day"}, "trade cap"),
    ({"serves": "MORE_MONEY"}, "serves"),
    ({"min_move": 0}, "min_move"),
    ({"direction": "sideways"}, "direction"),
    ({"expected_cost": ""}, "expected_cost"),
    ({"cited_trades": prop()["cited_trades"][:2]}, "3 cited"),
    ({"change": "EDIT", "rule_no": 7}, "rule_no"),
])
def test_hard_rejections(bad, frag):
    ok, why = RC.validate_proposal(prop(**bad), RULE1, [], LT, DAY_L)
    assert not ok and frag in why


def test_fabricated_citation_is_rejected():
    c = prop()["cited_trades"]
    c[2] = {"opened": "11:11", "entry": 555.0, "why_it_matters": "made up"}
    ok, why = RC.validate_proposal(prop(cited_trades=c), RULE1, [], LT, DAY_L)
    assert not ok and "matches no recorded trade" in why


def test_rejected_text_cannot_be_retried_verbatim():
    hist = [{"cycle": 2, "decision": "REJECT", "reason": "A2", "proposal": prop()}]
    ok, why = RC.validate_proposal(prop(), RULE1, hist, LT, DAY_L)
    assert not ok and "near-duplicate" in why


def test_two_rule_change_is_not_one_rule():
    two = RC.render_rules(RC.parse_rules(RULE1) + ["a", "b"])
    assert not RC.diff_is_one_rule(RULE1, two)


# ---------------------------------------------------------------- the accept function (truth table)
def m(net=0.0, share=0.5, worst=-200.0, rebuy=3.0):
    return {"net_usd": net, "exits_in_profit_share": share, "worst_trade": worst, "same_side_rebuy_15": rebuy}


def test_accept_truth_table():
    P_ = prop()
    ok = (True, "valid")
    acc = RC.decide(P_, ok, m(rebuy=3), m(rebuy=1), m(net=0, rebuy=3), m(net=0, rebuy=2), 324)
    assert acc["decision"] == "ACCEPT"
    # A1
    assert RC.decide(P_, (False, "bad"), m(), m(), None, None, 324)["decision"] == "REJECT"
    # A2: mechanism did not move enough on L
    assert RC.decide(P_, ok, m(rebuy=3), m(rebuy=3), m(), m(rebuy=1), 324)["decision"] == "REJECT"
    # A2: wrong direction
    assert RC.decide(P_, ok, m(rebuy=3), m(rebuy=5), m(), m(rebuy=1), 324)["decision"] == "REJECT"
    # A3: V net below the champion's on the same day — any amount, not a noise band
    r = RC.decide(P_, ok, m(rebuy=3), m(rebuy=1), m(net=0, rebuy=3), m(net=-1, rebuy=1), 324)
    assert r["decision"] == "REJECT" and "A3" in r["reason"]
    # A3: exit share falls >10pp
    r = RC.decide(P_, ok, m(rebuy=3), m(rebuy=1), m(share=.6, rebuy=3), m(share=.4, rebuy=1), 324)
    assert r["decision"] == "REJECT" and "A3" in r["reason"]
    # A3: worst trade $350 worse
    r = RC.decide(P_, ok, m(rebuy=3), m(rebuy=1), m(worst=-200, rebuy=3), m(worst=-550, rebuy=1), 324)
    assert r["decision"] == "REJECT" and "A3" in r["reason"]
    # A4: mechanism did not transfer to V
    r = RC.decide(P_, ok, m(rebuy=3), m(rebuy=1), m(rebuy=3), m(rebuy=3), 324)
    assert r["decision"] == "REJECT" and "A4" in r["reason"]
    # dollars alone never accept: big net gain, mechanism not moved
    r = RC.decide(P_, ok, m(rebuy=3), m(rebuy=3), m(net=0), m(net=+5000), 324)
    assert r["decision"] == "REJECT"
    # missing V -> doubts reject
    assert RC.decide(P_, ok, m(rebuy=3), m(rebuy=1), None, None, 324)["decision"] == "REJECT"


# ---------------------------------------------------------------- ledger
def test_ledger_is_append_only_and_tamper_evident(rd):
    for i in range(3):
        RC.ledger_append({"kind": "cycle", "cycle": i + 1, "decision": "NO_CHANGE"})
    assert RC.ledger_verify()[0]
    p = rd / "ledger.jsonl"
    lines = p.read_text().splitlines()
    row = json.loads(lines[1])
    row["decision"] = "ACCEPT"
    lines[1] = json.dumps(row)
    p.write_text("\n".join(lines) + "\n")
    ok, why = RC.ledger_verify()
    assert not ok and "seq 2" in why
    p.write_text("\n".join([lines[0], lines[2]]) + "\n")       # deleting a row also breaks the chain
    assert not RC.ledger_verify()[0]


def test_rule_versions_are_immutable(rd):
    with pytest.raises(RuntimeError):
        RC.save_rules(0, "1. something else\n")
    RC.save_rules(0, RULE1)                                    # identical rewrite is a no-op


# ---------------------------------------------------------------- frozen hashes / pre-gates
def test_pre_gates_halt_on_frozen_hash_mismatch(rd, monkeypatch):
    assert RL.pre_gates(None, 0, offline=True) == []
    monkeypatch.setitem(RL.FROZEN, "brief_v2_sha", "0" * 64)
    assert any("BRIEF_V2" in b for b in RL.pre_gates(None, 0, offline=True))


def test_pre_gates_halt_on_broken_ledger(rd):
    RC.ledger_append({"kind": "cycle", "cycle": 1, "decision": "NO_CHANGE"})
    (rd / "ledger.jsonl").write_text((rd / "ledger.jsonl").read_text().replace("NO_CHANGE", "ACCEPT"))
    assert any("ledger broken" in b for b in RL.pre_gates(None, 0, offline=True))


def test_pre_gates_refuse_exam_and_holdout_days(rd):
    bad = RL.pre_gates((RC.EXAM[0], "2026-08-18"), 0, offline=True)
    assert sum("exam or holdout" in b for b in bad) == 2


def test_model_is_sonnet_only(rd, monkeypatch):
    assert RC.MODEL == "claude-sonnet-5"
    RL.sw()
    import os
    assert os.environ["ANTHROPIC_MODEL"] == RC.MODEL
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5")
    assert any("Sonnet-only" in b for b in RL.pre_gates(None, 0, offline=True))
    RL.sw()


# ---------------------------------------------------------------- the pool
def test_pool_never_contains_exam_or_holdout_days():
    cands = RC.EXAM + sorted(RC.HOLDOUT_DAYS) + [f"2026-0{m}-{d:02d}" for m in (4, 5) for d in range(1, 20)]
    pool = RC.build_pool(7, cands, lambda d: float(hash(d) % 100))
    flat = [d for b in pool["buckets"] for d in b]
    assert flat and not set(flat) & (set(RC.EXAM) | RC.HOLDOUT_DAYS)


def test_pairs_come_without_replacement_from_the_pool():
    pool = {"buckets": [[f"a{i}" for i in range(4)], [f"b{i}" for i in range(4)], [f"c{i}" for i in range(4)]]}
    used = []
    for n in range(1, 7):
        l, v = RC.next_pair(pool, used, n)
        assert l != v and l not in used and v not in used
        used += [l, v]
    assert len(set(used)) == len(used)


# ---------------------------------------------------------------- the full cycle, stubbed reviewer + trader
def stub_trader(rules_text, day, rep=""):
    # a rule set containing the 15-minute rule has fewer rebuys; otherwise 3 trades
    base = [trade("05:10", 100.0, 100, day=day), trade("05:20", 101.0, 100, day=day), trade("05:30", 102.0, 100, day=day)]
    if "15 minutes" in rules_text:
        base = [trade("05:10", 100.0, 350, day=day)]            # fewer rebuys AND no less money (A3 needs V net >= champion's)
    return rec(day, base)


def test_cycle_accepts_a_rule_that_moves_its_metric_and_records_everything(rd):
    pair = (DAY_L, DAY_V)
    RC.ledger_append({"kind": "phase0", "days": [], "band_usd": 0})
    reviewer = lambda prompt: json.dumps({"decision": "PROPOSE", **prop(cited_trades=[
        {"opened": "05:10", "entry": 100.0, "why_it_matters": "a"}, {"opened": "05:20", "entry": 101.0, "why_it_matters": "b"},
        {"opened": "05:30", "entry": 102.0, "why_it_matters": "c"}])})
    row = RL.run_cycle(1, pair, stub_trader, reviewer, lambda p: "I expected fewer rebuys and got them.")
    assert row["decision"] == "ACCEPT", row["reason"]
    assert RL.champion()["version"] == 1
    assert (rd / "rules" / "R001.txt").read_text() != (rd / "rules" / "R000.txt").read_text()
    assert (rd / "cycles" / "c0001" / "review_prompt.txt").exists()
    assert (rd / "cycles" / "c0001" / "decision.json").exists()
    assert RC.ledger_verify()[0]
    assert "cycle 1" in (rd / "CHANGELOG.md").read_text()
    assert "fewer rebuys" in RC.lessons_text()


def test_cycle_rejects_and_keeps_champion_when_mechanism_does_not_move(rd):
    lazy = lambda rules_text, day, rep="": rec(day, [trade("05:10", 100.0, 100, day=day), trade("05:20", 101.0, 100, day=day),
                                                     trade("05:30", 102.0, 100, day=day)])
    reviewer = lambda prompt: json.dumps({"decision": "PROPOSE", **prop(cited_trades=[
        {"opened": "05:10", "entry": 100.0, "why_it_matters": "a"}, {"opened": "05:20", "entry": 101.0, "why_it_matters": "b"},
        {"opened": "05:30", "entry": 102.0, "why_it_matters": "c"}])})
    row = RL.run_cycle(1, (DAY_L, DAY_V), lazy, reviewer, lambda p: "lesson")
    assert row["decision"] == "REJECT" and "A2" in row["reason"]
    assert RL.champion()["version"] == 0


def test_no_change_and_garbage_are_first_class(rd):
    row = RL.run_cycle(1, (DAY_L, DAY_V), stub_trader, lambda p: '{"decision":"NO_CHANGE","reason":"nothing supported"}', lambda p: "")
    assert row["decision"] == "NO_CHANGE"
    n_rows = len(RC.ledger_read())
    with pytest.raises(RL.Halt):                                    # an unreadable reply is an outage, not a verdict
        RL.run_cycle(2, (DAY_L, DAY_V), stub_trader, lambda p: "I think we should do stuff", lambda p: "")
    assert len(RC.ledger_read()) == n_rows and RL.champion()["version"] == 0


# ---------------------------------------------------------------- the captured reviewer prompt
def test_reviewer_prompt_has_laws_ledger_and_no_validation_day_or_exam(rd):
    from gazbot7.bible import laws
    RC.ledger_append({"kind": "cycle", "cycle": 1, "L": "2026-01-02", "V": "2026-01-05", "decision": "REJECT",
                      "reason": "A2 mechanism: nothing moved", "proposal": prop()})
    seen = {}
    def reviewer(p):
        seen["p"] = p
        return '{"decision":"NO_CHANGE","reason":"x"}'
    RL.run_cycle(2, (DAY_L, DAY_V), stub_trader, reviewer, lambda p: "")
    p = seen["p"]
    for law in ("LAW 0", "L2", "L3", "L5", "L6", "L7", "L8", "L9", "L10"):
        assert law in laws() and law in p, law
    assert "cycle 1: tried ADD" in p and "A2 mechanism: nothing moved" in p        # the ledger digest is on the page
    assert "R000" not in p and RULE1.strip()[:30] in p                              # the champion's text is on the page
    assert DAY_V not in p
    assert "exam" not in p.lower().replace("examp", "")                              # never the exam, never its dates
    for d in RC.EXAM + sorted(RC.HOLDOUT_DAYS):
        assert d not in p
    assert "NO_CHANGE is always legal" in p


# ====================================================================================================
# PRE-LAUNCH FIXES (round-1 audit, 13 items) — each one has a test that calls the real entry point
# ====================================================================================================
GP_RULE = "{w}: when a claim has just printed, wait for the next push in the same direction before re-entering."


def gp_trader(rules_text, day, rep=""):
    pnl = 100 + 600 * ("ALPHA" in rules_text) + 800 * ("BETA" in rules_text) + 1000 * ("GAMMA" in rules_text)
    return rec(day, [trade("05:10", 100.0, pnl, day=day), trade("05:20", 101.0, pnl, day=day), trade("05:30", 102.0, pnl, day=day)])


def gp_reviewer(word, **kw):
    cites = [{"opened": "05:10", "entry": 100.0, "why_it_matters": "a"}, {"opened": "05:20", "entry": 101.0, "why_it_matters": "b"},
             {"opened": "05:30", "entry": 102.0, "why_it_matters": "c"}]
    body = prop(new_text=GP_RULE.format(w=word), metric="gross_points", direction="up", min_move=60, cited_trades=cites, **kw)
    return lambda prompt: json.dumps({"decision": "PROPOSE", **body})


# ---- fix 1: version allocation never reuses a number
def test_version_allocation_accept_accept_rollback_accept(rd):
    for n, w in ((1, "ALPHA"), (2, "BETA")):
        row = RL.run_cycle(n, (DAY_L, DAY_V), gp_trader, gp_reviewer(w), lambda p: "lesson")
        assert row["decision"] == "ACCEPT", row["reason"]
    assert RL.champion()["version"] == 2
    v2 = (rd / "rules" / "R002.txt").read_text()
    RL.set_champion(1, (rd / "rules" / "R001.txt").read_text(), 2, "rollback")           # champion goes back to v1
    assert RL.champion()["version"] == 1
    row = RL.run_cycle(3, (DAY_L, DAY_V), gp_trader, gp_reviewer("GAMMA"), lambda p: "lesson")
    assert row["decision"] == "ACCEPT", row["reason"]
    assert RL.champion()["version"] == 3 and row["new_version"] == 3                     # not 2 — R002 is not overwritten
    assert (rd / "rules" / "R002.txt").read_text() == v2 and "BETA" in v2
    r3 = (rd / "rules" / "R003.txt").read_text()
    assert "ALPHA" in r3 and "GAMMA" in r3 and "BETA" not in r3
    assert RC.next_version() == 4


# ---- fix 2: the accept function
def test_decide_vday_net_and_combined_net(rd):
    ok, P_ = (True, "valid"), prop()
    # V net exactly equal to the champion's passes; one dollar below fails
    assert RC.decide(P_, ok, m(rebuy=3), m(rebuy=1), m(net=50, rebuy=3), m(net=50, rebuy=2), 324)["decision"] == "ACCEPT"
    assert RC.decide(P_, ok, m(rebuy=3), m(rebuy=1), m(net=50, rebuy=3), m(net=49, rebuy=2), 324)["decision"] == "REJECT"
    # a V gain that does not pay for the L loss: L+V combined worse than the champion
    r = RC.decide(P_, ok, m(net=0, rebuy=3), m(net=-500, rebuy=1), m(net=0, rebuy=3), m(net=100, rebuy=2), 324)
    assert r["decision"] == "REJECT" and "A3" in r["reason"] and r["A3"]["lv_net"] == -400
    ok_ = RC.decide(P_, ok, m(net=0, rebuy=3), m(net=-100, rebuy=1), m(net=0, rebuy=3), m(net=100, rebuy=2), 324)
    assert ok_["decision"] == "ACCEPT"


def test_decide_min_move_floor_is_per_metric(rd):
    ok = (True, "valid")
    assert RC.MIN_MOVE_FLOOR["net_usd"] == RC.DOLLAR_FLOOR == 474.0
    assert RC.MIN_MOVE_FLOOR["gross_points"] == pytest.approx(474.0 / 8)
    assert "net_usd" in RC.MENU and "gross_points" in RC.MENU and "trades_per_day" not in RC.MENU
    # declared 100 for a dollar metric, moved 400 on L: below the $474 floor -> A2 rejects
    p_ = prop(metric="net_usd", direction="up", min_move=100)
    r = RC.decide(p_, ok, m(net=0), m(net=400), m(net=0), m(net=400), 324)
    assert r["decision"] == "REJECT" and "A2" in r["reason"] and r["A2"]["needed"] == 474.0
    assert RC.decide(p_, ok, m(net=0), m(net=500), m(net=0), m(net=500), 324)["decision"] == "ACCEPT"
    # a declared min_move ABOVE the floor still binds
    p_ = prop(metric="net_usd", direction="up", min_move=900)
    assert RC.decide(p_, ok, m(net=0), m(net=500), m(net=0), m(net=500), 324)["decision"] == "REJECT"
    # count metric: floor is one whole trade even if the model declares 0.2
    p_ = prop(metric="same_side_rebuy_15", direction="down", min_move=0.2)
    assert RC.decide(p_, ok, m(rebuy=3), m(rebuy=2.5), m(rebuy=3), m(rebuy=2), 324)["decision"] == "REJECT"
    # gross_points is computed from trade points
    assert RC.metrics(rec(DAY_L, [trade(pnl=80.0), trade(pnl=160.0)]))["gross_points"] == pytest.approx(30.0)


def test_trades_per_day_cannot_be_the_declared_primary(rd):
    ok, why = RC.validate_proposal(prop(metric="trades_per_day"), RULE1, [], LT, DAY_L)
    assert not ok and "trade cap" in why


# ---- fix 3: the exam is informational
def test_checkpoint_exam_never_rolls_back_or_selects(rd, monkeypatch):
    RL.set_champion(1, RULE1 + "2. ALPHA keep going.\n", 1, "t")
    monkeypatch.setattr(RL, "baseline_problems", lambda *a, **k: [])
    monkeypatch.setattr(RL, "nets_for", lambda tag, days: {d: 1000.0 for d in days})
    res = RL.exam("checkpoint", lambda r, d, rep="": {"net_usd": -500.0})           # far below S3
    assert res["informational"] is True and res["rollback"] is False and res["usd_per_day_below_s3"] is True
    assert RL.champion()["version"] == 1                                               # champion untouched
    assert "SELECTED-ON" in res["label"] and "NOT out-of-sample" in res["label"]
    row = RC.ledger_read()[-1]
    assert row["kind"] == "exam" and row["informational"] is True
    RC.write_status({})
    assert "SELECTED-ON" in (rd / "STATUS.md").read_text()


def test_exam_halts_on_missing_or_poisoned_baselines(rd, monkeypatch):
    monkeypatch.setattr(RL, "baseline_problems", lambda *a, **k: ["S1b record for 2026-02-05 is missing"])
    with pytest.raises(RL.Halt):
        RL.exam("final", lambda r, d, rep="": {"net_usd": 0.0})


def test_baseline_problems_reads_the_records(rd, tmp_path, monkeypatch):
    SW = RL.sw()
    out = tmp_path / "simout"
    out.mkdir()
    monkeypatch.setattr(SW, "OUT", str(out))
    day = RC.EXAM[0]
    assert any("missing" in x for x in RL.baseline_problems([day]))
    good, bad = rec(day, [trade(day=day)]), rec(day, [trade(day=day)], err=20)
    (out / f"{RL.S3_TAG}_{day}.json").write_text(json.dumps(good))
    (out / f"{RL.S1B_TAG}_{day}.json").write_text(json.dumps(bad))
    probs = RL.baseline_problems([day])
    assert len(probs) == 1 and "S1b" in probs[0] and "poisoned" in probs[0]
    (out / f"{RL.S1B_TAG}_{day}.json").write_text(json.dumps(good))
    assert RL.baseline_problems([day]) == []


# ---- fix 4: no target, uninformative stop, confirmation days, one-shot confirm
def test_uninformative_stop_message_and_no_target_in_status(rd, monkeypatch):
    json.dump({"pool": {"buckets": [["d1"], ["d2"], ["d3"]]}}, open(rd / "PROJECT.json", "w"))
    for i in range(RL.NO_ACCEPT_STOP):
        RC.ledger_append({"kind": "cycle", "cycle": i + 1, "L": f"l{i}", "V": f"v{i}", "decision": "REJECT", "reason": "A2 x"})
    called = []
    rc = RL.run(3, lambda *a, **k: called.append(1), lambda p: called.append(1) or "", lambda p: "", offline=True)
    st = (rd / "STATUS.md").read_text()
    assert rc == 0 and not called and "UNINFORMATIVE" in st and "15-30%" in st
    assert "800" not in st and RL.MAX_CYCLES == 12


def test_confirmation_days_are_fixed_untouched_and_disjoint_from_pool():
    cands = [f"2025-{mo:02d}-{d:02d}" for mo in range(1, 7) for d in range(1, 29)] + RC.EXAM + sorted(RC.HOLDOUT_DAYS)
    char = lambda d: float(sum(map(ord, d)) % 97)
    a = RC.pick_confirmation(RC.CONFIRMATION_SEED, cands, char)
    assert a == RC.pick_confirmation(RC.CONFIRMATION_SEED, cands, char) and len(a) == RC.CONFIRMATION_N == 22
    assert not set(a) & (set(RC.EXAM) | RC.HOLDOUT_DAYS)
    pool = RC.build_pool(20261008, [c for c in cands if c not in a], char)
    assert not set(a) & {d for b in pool["buckets"] for d in b}


def test_paired_summary_numbers():
    ps = RC.paired_summary([10, 12, 14], [0, 0, 0])
    assert ps["mean_diff"] == 12 and ps["n"] == 3 and ps["days_positive_diff"] == 3
    assert ps["lower90"] == pytest.approx(12 - 1.886 * 2 / 3 ** 0.5, rel=1e-3)


def _confirm_setup(rd, n=RC.CONFIRMATION_N):
    json.dump({"confirmation_days": [f"2026-05-{i:02d}" for i in range(1, n + 1)]}, open(rd / "PROJECT.json", "w"))
    RL.set_champion(1, RULE1 + "2. ALPHA keep going.\n", 1, "t")
    return lambda rules, day, rep="": {"net_usd": float(day[-2:]) * 10 + (100.0 if "ALPHA" in rules else 0.0)}


def test_confirm_runs_once_paired_and_refuses_a_second_time(rd):
    td = _confirm_setup(rd)
    res = RL.confirm(td)
    assert res["paired"]["n"] == 22 and res["paired"]["mean_diff"] == pytest.approx(100.0)
    assert res["paired"]["days_positive_diff"] == 22 and res["lower90_above_zero"] is True
    kinds = [r["kind"] for r in RC.ledger_read()]
    assert kinds.count("confirm_started") == 1 and kinds.count("confirm") == 1
    with pytest.raises(RL.Halt, match="already been run"):
        RL.confirm(td)


def test_confirm_refuses_without_22_stamped_days(rd):
    td = _confirm_setup(rd, n=5)
    with pytest.raises(RL.Halt):
        RL.confirm(td)


# ---- fix 5: rule 1's claim level is not tunable
RULE1_WORDS = "1. When a position is up about two times the ATR(14,1m) on the page, claim it.\n"


@pytest.mark.parametrize("rules", [RULE1, RULE1_WORDS])
def test_rule_one_claim_level_cannot_be_changed_or_removed_or_restated(rules):
    assert RC.claim_levels(rules) == [2.0]
    new1 = "1. When a position is up at least 3x ATR(14,1m) on the page, claim it." if rules is RULE1 else \
        "1. When a position is up about three times the ATR(14,1m) on the page, claim it."
    ok, why = RC.validate_proposal(prop(change="EDIT", rule_no=1, new_text=new1), rules, [], LT, DAY_L)
    assert not ok and "claim level" in why
    ok, why = RC.validate_proposal(prop(change="REMOVE", rule_no=1), rules, [], LT, DAY_L)
    assert not ok and "not removable" in why
    ok, why = RC.validate_proposal(prop(new_text="Claim at 3x ATR of profit, then wait for the next push."), rules, [], LT, DAY_L)
    assert not ok and "claim level" in why
    ok, why = RC.validate_proposal(prop(new_text="Claim at three times the ATR of profit, then wait."), rules, [], LT, DAY_L)
    assert not ok and "claim level" in why


def test_rule_one_may_be_reworded_if_the_level_is_unchanged_and_other_rules_may_use_atr():
    same = "1. When a position is up at least 2x ATR(14,1m) on the page, claim it and say why in the reason."
    ok, why = RC.validate_proposal(prop(change="EDIT", rule_no=1, new_text=same), RULE1, [], LT, DAY_L)
    assert ok, why
    ok, why = RC.validate_proposal(prop(new_text="Enter only when the last push was larger than 1x ATR of the prior pullback."), RULE1, [], LT, DAY_L)
    assert ok, why


# ---- fix 6: lock, fsync, fail-closed ledger, write order, reconcile
def test_lock_is_exclusive_and_releasable(rd):
    ok, _ = RC.acquire_lock()
    assert ok
    ok2, why = RC.acquire_lock()
    assert not ok2 and "refusing to run two" in why
    RC.release_lock()
    ok3, _ = RC.acquire_lock()
    assert ok3
    RC.release_lock()


def test_mutating_commands_take_the_lock_and_fail_fast(rd, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["robot_loop", "--run", "--cycles", "1"])
    ok, _ = RC.acquire_lock()
    assert ok
    try:
        monkeypatch.setattr(RL, "run", lambda *a, **k: pytest.fail("ran without the lock"))
        assert RL.main() == 5
    finally:
        RC.release_lock()
    assert "refusing to run two" in capsys.readouterr().out


def test_ledger_append_fsyncs(rd, monkeypatch):
    calls = []
    real = os.fsync
    monkeypatch.setattr(RC.os, "fsync", lambda fd: (calls.append(fd), real(fd))[1])
    RC.ledger_append({"kind": "cycle", "cycle": 1, "decision": "NO_CHANGE"})
    assert len(calls) >= 1


def test_truncated_final_ledger_line_fails_closed(rd, monkeypatch):
    RC.ledger_append({"kind": "cycle", "cycle": 1, "decision": "NO_CHANGE"})
    with open(rd / "ledger.jsonl", "a") as f:
        f.write('{"kind": "cycle", "cyc')
    with pytest.raises(RC.LedgerError, match="FINAL line"):
        RC.ledger_read()
    with pytest.raises(RC.LedgerError):
        RC.ledger_append({"kind": "cycle", "cycle": 2})                                 # never appends over a damaged chain
    json.dump({"pool": {"buckets": [["a"], ["b"], ["c"]]}}, open(rd / "PROJECT.json", "w"))
    assert RL.run(1, gp_trader, lambda p: "", lambda p: "", offline=True) == RL.HALT_RC
    assert "HALTED" in (rd / "STATUS.md").read_text()


def test_ledger_row_is_written_before_the_champion_and_reconcile_repairs_a_crash(rd, monkeypatch):
    orig = RL.set_champion
    monkeypatch.setattr(RL, "set_champion", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash after the ledger row")))
    with pytest.raises(RuntimeError):
        RL.run_cycle(1, (DAY_L, DAY_V), gp_trader, gp_reviewer("ALPHA"), lambda p: "I expected more points and got them.")
    rows = [r for r in RC.ledger_read() if r.get("kind") == "cycle"]
    assert len(rows) == 1 and rows[0]["decision"] == "ACCEPT" and rows[0]["new_version"] == 1     # the record exists...
    assert RL.champion()["version"] == 0 and (rd / "rules" / "R001.txt").exists()                  # ...the pointer lags
    assert "more points" not in RC.lessons_text()
    monkeypatch.setattr(RL, "set_champion", orig)
    notes = RL.reconcile()
    assert RL.champion()["version"] == 1 and any("champion reconciled" in n for n in notes)
    assert "more points" in RC.lessons_text()
    assert RL.reconcile() == []                                                                    # idempotent


def test_reconcile_halts_when_champion_is_ahead_of_the_ledger(rd):
    RL.set_champion(5, RULE1 + "2. ALPHA x.\n", 1, "hand edit")
    with pytest.raises(RL.Halt, match="disagree"):
        RL.reconcile()


def test_a_critic_halt_persists_nothing(rd):
    def dead_critic(p):
        return "[review failed: usage limit reached]"
    with pytest.raises(RL.Halt):
        RL.run_cycle(1, (DAY_L, DAY_V), gp_trader, gp_reviewer("ALPHA"), dead_critic)
    assert [r for r in RC.ledger_read() if r.get("kind") == "cycle"] == []
    assert RL.champion()["version"] == 0 and not (rd / "rules" / "R001.txt").exists()


# ---- fix 7: the validator never raises; unusable replies Halt (not a spent cycle)
@pytest.mark.parametrize("bad", [
    None, "a string", [], {"change": "ADD"},
    prop(cited_trades="nope"), prop(cited_trades=[{"opened": "05:10", "entry": "abc"}] * 3),
    prop(cited_trades=[None, None, None]), prop(min_move=[1]), prop(change="EDIT", rule_no="x"),
    prop(new_text=12345), prop(serves=["x"]), prop(metric={"a": 1}),
])
def test_validator_never_raises(bad):
    ok, why = RC.validate_proposal(bad, RULE1, [], LT, DAY_L)
    assert ok is False and isinstance(why, str) and why


@pytest.mark.parametrize("reply", ["", "[review failed: FileNotFoundError: claude]", "[review timed out after 420s]",
                                   "You've hit your weekly limit. Resets at 5am", "I think we should do stuff"])
def test_unusable_reviewer_reply_halts_and_spends_nothing(rd, reply):
    with pytest.raises(RL.Halt):
        RL.run_cycle(1, (DAY_L, DAY_V), gp_trader, lambda p: reply, lambda p: "")
    assert [r for r in RC.ledger_read() if r.get("kind") == "cycle"] == []


def test_run_writes_halted_status_nonzero_exit_and_does_not_consume_the_pair(rd):
    json.dump({"pool": {"buckets": [[DAY_L], [DAY_V], []]}}, open(rd / "PROJECT.json", "w"))
    asked = []
    rc = RL.run(1, gp_trader, lambda p: asked.append(1) or "[usage limit reached]", lambda p: "", offline=True,
                bars_fn=lambda d: None)
    assert rc == RL.HALT_RC and asked
    assert "HALTED" in (rd / "STATUS.md").read_text()
    assert RL.used_days() == []                                                         # day pair not consumed
    assert not [r for r in RC.ledger_read() if r.get("kind") == "cycle"]                # not counted toward NO_ACCEPT_STOP


def test_a_halted_review_is_resumed_with_the_same_answer_when_the_prompt_is_unchanged(rd):
    good = gp_reviewer("ALPHA")
    seen = []
    def reviewer(p):
        seen.append(p)
        return good(p)
    RL.run_cycle(1, (DAY_L, DAY_V), gp_trader, reviewer, lambda p: "[usage limit]") if False else None
    with pytest.raises(RL.Halt):
        RL.run_cycle(1, (DAY_L, DAY_V), gp_trader, reviewer, lambda p: "[usage limit reached]")      # critic dies
    assert len(seen) == 1
    row = RL.run_cycle(1, (DAY_L, DAY_V), gp_trader, reviewer, lambda p: "a lesson")
    assert row["decision"] == "ACCEPT" and len(seen) == 1                                 # the paid-for review is reused


# ---- fix 8: the budget gate
def test_budget_gate_reserves_the_standing_burn(rd, monkeypatch):
    monkeypatch.setattr(RL, "standing_burn_per_day", lambda: 30_000_000)
    monkeypatch.setattr(RL, "budget_summary", lambda: {"remaining_tokens": 140_000_000, "hours_left": 48.0})
    assert RL.budget_gate(2 * RL.CYCLE_ESTIMATE_TOKENS) == []                          # 140M >= 60M + 22M + 44M
    bad = RL.budget_gate(4 * RL.CYCLE_ESTIMATE_TOKENS)                                   # 60 + 22 + 88 = 170M
    assert bad and "budget" in bad[0]
    monkeypatch.setattr(RL, "budget_summary", lambda: {"remaining_tokens": None, "hours_left": 48.0})
    assert RL.budget_gate(0)


def test_run_refuses_when_the_requested_cycles_are_not_covered(rd, monkeypatch):
    json.dump({"pool": {"buckets": [[DAY_L], [DAY_V], []]}}, open(rd / "PROJECT.json", "w"))
    monkeypatch.setattr(RL, "standing_burn_per_day", lambda: 30_000_000)
    monkeypatch.setattr(RL, "budget_summary", lambda: {"remaining_tokens": 100_000_000, "hours_left": 120.0})
    spent = []
    rc = RL.run(4, lambda *a, **k: spent.append(1), lambda p: spent.append(1) or "", lambda p: "", offline=False)
    assert rc == 3 and not spent and "HALTED" in (rd / "STATUS.md").read_text()


def test_standing_burn_excludes_robot_and_sim_projects(tmp_path, monkeypatch):
    import claude_usage as CU
    f = tmp_path / "u.json"
    f.write_text(json.dumps({"days": {"d1": {}, "d2": {}}, "by_project": {
        "-home-alphabot-gazbot7": {"in": 40_000_000, "out": 0, "cache_create": 0},
        "-tmp-sim-week-x": {"in": 900_000_000, "out": 0, "cache_create": 0},
        "-tmp-robot-y": {"in": 900_000_000, "out": 0, "cache_create": 0}}}))
    monkeypatch.setattr(CU, "OUT", str(f))
    assert RL.standing_burn_per_day() == 20_000_000
    monkeypatch.setattr(CU, "OUT", str(tmp_path / "missing.json"))
    assert RL.standing_burn_per_day() == RL.STANDING_BURN_DEFAULT


def test_budget_file_env_is_honoured(tmp_path, monkeypatch):
    import claude_usage as CU
    bf = tmp_path / "b.json"
    bf.write_text(json.dumps({"weekly_token_budget": 123456789}))
    monkeypatch.setattr(CU, "BUDGET", CU.BUDGET)
    monkeypatch.setenv("ROBOT_BUDGET_FILE", str(bf))
    assert RL.budget_summary()["budget_tokens"] == 123456789


# ---- fix 9: no V-day numbers reach later cycles
def test_no_validation_day_numbers_in_digest_or_lessons(rd):
    def trader(rules_text, day, rep=""):
        pnl = 300 if "ALPHA" not in rules_text else (700 if day == DAY_L else 50)
        return rec(day, [trade("05:10", 100.0, pnl, day=day), trade("05:20", 101.0, pnl, day=day), trade("05:30", 102.0, pnl, day=day)])
    seen = {}
    def critic(p):
        seen["p"] = p
        return "I expected +$300 and got -$412 on the V day, net 640 below."
    row = RL.run_cycle(1, (DAY_L, DAY_V), trader, gp_reviewer("ALPHA"), critic)
    assert row["decision"] == "REJECT" and "A3" in row["reason"] and "$" in row["reason"]          # the ledger keeps the truth
    dg = RC.digest(RC.ledger_read())
    assert "$" not in dg and not re.search(r"\d", re.sub(r"cycle \d+|A\d", "", dg))
    res_line = seen["p"].split("RESULT (computed by code):")[1]
    assert "$" not in res_line and not re.search(r"\d", re.sub(r"A\d", "", res_line))
    lt = RC.lessons_text()
    assert "$300" not in lt and "$412" not in lt and "$#" in lt
    old = [{"kind": "cycle", "cycle": 1, "decision": "REJECT", "reason": "A3 guard failed: net below by $412; L+V -1,200", "proposal": prop()}]
    d2 = RC.digest(old)
    assert "412" not in d2 and "1,200" not in d2


# ---- fix 10: tools are off for ROBOT's calls only
def _fake_run(captured, stdout="OK"):
    class R:
        pass
    def run(cmd, **kw):
        captured.append(cmd)
        r = R()
        r.stdout, r.returncode = stdout, 0
        return r
    return run


def test_tools_switch_is_on_for_robot_and_off_by_default(rd, monkeypatch):
    SW = RL.sw()
    got = []
    monkeypatch.setattr(SW.subprocess, "run", _fake_run(got))
    monkeypatch.setenv("ROBOT_NO_TOOLS", "1")
    SW.ask_text("hello")
    SW.ask("hello")
    assert got[0] == [SW.CLAUDE, "--tools=", "-p", "hello"] and got[1] == [SW.CLAUDE, "--tools=", "-p", "hello"]
    monkeypatch.delenv("ROBOT_NO_TOOLS")
    SW.ask_text("hello")
    assert got[2] == [SW.CLAUDE, "-p", "hello"]                                         # every other caller is unchanged


def test_sw_sets_the_switch_and_pre_gates_require_it(rd, monkeypatch):
    monkeypatch.delenv("ROBOT_NO_TOOLS")
    monkeypatch.delenv("ANTHROPIC_MODEL")
    RL.sw()
    assert os.environ["ROBOT_NO_TOOLS"] == "1" and os.environ["ANTHROPIC_MODEL"] == RC.MODEL
    assert RL.pre_gates(None, 0, offline=True) == []                                    # sw() set the env BEFORE the check: not vacuous
    monkeypatch.delenv("ROBOT_NO_TOOLS")
    assert any("ROBOT_NO_TOOLS" in b for b in RL.pre_gates(None, 0, offline=True))


def test_live_model_check_reads_modelusage(rd, monkeypatch):
    SW = RL.sw()
    monkeypatch.setattr(RL, "_MODEL_VERIFIED", False)
    got = []
    monkeypatch.setattr(SW.subprocess, "run", _fake_run(got, json.dumps({"modelUsage": {"claude-opus-5": {}}})))
    bad = RL.verify_model_live()
    assert bad and "Sonnet-only" in bad[0] and "--tools=" in got[0] and "json" in got[0]
    monkeypatch.setattr(SW.subprocess, "run", _fake_run(got, json.dumps({"modelUsage": {"claude-sonnet-5": {}}})))
    assert RL.verify_model_live() == []
    monkeypatch.setattr(RL, "_MODEL_VERIFIED", False)
    monkeypatch.setattr(SW.subprocess, "run", _fake_run(got, "not json"))
    assert RL.verify_model_live()                                                       # fails closed


# ---- fix 11: --check-start exits nonzero on failure
@pytest.mark.parametrize("ok,rc", [(True, 0), (False, 1)])
def test_check_start_exit_code(rd, monkeypatch, ok, rc, capsys):
    monkeypatch.setattr(RL, "start_condition", lambda: {"ok": ok, "reasons": [] if ok else ["x"]})
    monkeypatch.setattr(sys, "argv", ["robot_loop", "--check-start"])
    assert RL.main() == rc


# ---- fix 12: the hour block is learning-days only
def test_hour_block_uses_only_earlier_learning_days(rd, tmp_path, monkeypatch):
    SW = RL.sw()
    out = tmp_path / "simout"
    out.mkdir()
    monkeypatch.setattr(SW, "OUT", str(out))
    tag = RL.tag_for(RULE1)
    other_l, exam_day, v_day = "2026-03-02", RC.EXAM[0], "2026-03-03"
    for d in (other_l, exam_day, v_day):
        (out / f"{tag}_{d}.json").write_text(json.dumps(rec(d, [trade(day=d, pnl=100.0)] * 2)))
    rows = [{"kind": "cycle", "cycle": 1, "L": other_l, "V": v_day, "champion_version": 0},
            {"kind": "cycle", "cycle": 2, "L": exam_day, "V": "2026-03-04", "champion_version": 0}]
    recL = rec(DAY_L, [trade(day=DAY_L, pnl=100.0)])
    recs = RL.hour_recs(rows, recL)
    assert [r["day"] for r in recs] == [other_l, DAY_L]                                 # no exam day, no validation day
    blk = RC.hour_block(recs)
    assert "05:00-05:59" in blk and "n=  3" in blk and "+300" in blk and "+318" in blk
    seen = {}
    RC.ledger_append({"kind": "cycle", "cycle": 1, "L": other_l, "V": v_day, "champion_version": 0, "decision": "NO_CHANGE"})
    RL.run_cycle(2, (DAY_L, DAY_V), gp_trader, lambda p: seen.update(p=p) or '{"decision":"NO_CHANGE","reason":"x"}', lambda p: "")
    assert "WHEN YOUR TRADES OPENED" in seen["p"] and DAY_V not in seen["p"]


# ---- fix 13: the doc's STATUS line
def test_doc_status_line_is_the_post_fix_state():
    doc = (GB / "docs" / "PROJECT_ROBOT.md").read_text()
    assert "BUILT, AUDITED ONCE (round 1), FIXES APPLIED, NOT RUN" in doc
    assert "2026-10-14T05:00Z" in doc and "fix re-audit" in doc


# ---- re-audit round 2
def test_decide_rejects_when_v_is_negative_even_if_l_plus_v_is_positive(rd):
    ok, P_ = (True, "valid"), prop()
    r = RC.decide(P_, ok, m(net=0, rebuy=3), m(net=600, rebuy=1), m(net=0, rebuy=3), m(net=-50, rebuy=2), 324)
    assert r["decision"] == "REJECT" and r["A3"]["lv_net"] == 550 and r["A3"]["d_net"] == -50


@pytest.mark.parametrize("text", [
    "Take profit once two ATR of open profit is reached.",
    "Exit when open profit is double the ATR.",
    "Bank the trade at 3 ATR of open profit.",
    "Claim when the position is up twice the ATR.",
])
def test_claim_level_regex_catches_spelled_and_bare_forms(text):
    ok, why = RC.validate_proposal(prop(new_text=text), RULE1, [], LT, DAY_L)
    assert not ok and "claim level" in why, text


def test_entry_rule_with_take_and_atr_is_not_a_claim_restatement():
    t = "Enter after price has run 1.5 x ATR from the swing low; take the entry only on the first pullback."
    ok, why = RC.validate_proposal(prop(new_text=t), RULE1, [], LT, DAY_L)
    assert ok, why


def test_touched_days_excludes_sim_records_and_doc_mentions(tmp_path):
    sim, doc = tmp_path / "sim", tmp_path / "doc"
    sim.mkdir(); doc.mkdir()
    (sim / "sline_s3_2026-03-05.json").write_text("{}")
    (doc / "S1_change.txt").write_text("days 2026-06-24 and 2026-06-29 were used")
    assert RC.touched_days(str(sim), [str(doc)]) == {"2026-03-05", "2026-06-24", "2026-06-29"}
    cands = ["2026-03-05", "2026-06-24", "2026-07-01", "2026-07-02", "2026-07-03"]
    t = RC.touched_days(str(sim), [str(doc)])
    conf = RC.pick_confirmation(1, [c for c in cands if c not in t], lambda d: 1.0, k=3)
    assert not set(conf) & t and len(conf) == 3
