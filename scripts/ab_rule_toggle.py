#!/usr/bin/env python3
"""ATTRIBUTION: DOES ONE RULE ACTUALLY DO ANYTHING? — paired, same tape, with a noise arm.

★★★ Operator, 2026-10-06: *"we absolutely need to know why its improving or getting worse?"*
and then, given credits: *"i have credits, do it."*

WHY THIS EXISTS. The recursive loop rewrites up to ten rules at once and runs each iteration
ONCE, so iteration-to-iteration P&L cannot attribute anything: iteration 2 beat iteration 1
by **$111/day against a measured $324/day single-run spread**. This is the design that CAN
attribute — the same days, the same tape, one rule changed, plus a replicate of the control
so the noise is measured in the same experiment rather than quoted from another one.

THE RULE UNDER TEST IS RULE 9 of iteration 2's set: *"Stop for the session after three
losing trades, and never try to recover a losing day by taking the other side."*
Two observations put it first in the queue:
  · On 2026-08-21 — the single day carrying iteration 2's whole lead — the model took three
    losses and then made **+$318 and +$218**. Obeying rule 9 turns that day from +$200 into
    roughly −$356, and iteration 2 then LOSES to iteration 1.
  · Across 32 clean day-runs where the rule would have bound, the P&L earned AFTER the third
    loss totals **+$8,776**, positive on 15 of 32.

⚠⚠ AND THE RULE IS CURRENTLY DEAD TEXT: on **12 of 12** iteration-2 days where it bound, the
model kept trading anyway. So testing "rule present vs absent" would compare two arms that
behave identically and would prove nothing. The arms therefore test ENFORCEMENT:

  SOFT_1  the rule exactly as iteration 2 wrote it            ← the incumbent
  SOFT_2  byte-identical to SOFT_1                            ← THE NOISE ARM
  OFF     rule 9 deleted and the list renumbered
  HARD    rule 9 rewritten as an unconditional stop

★ SOFT_2 IS THE MOST IMPORTANT ARM. Without it, any gap between SOFT and HARD gets read as
the rule's effect when it may be the model's own run-to-run variance — the mistake that
produced four fake results on this project in two days
([[charge-the-search-and-then-charge-the-bar]], [[a-control-is-supposed-to-lose]]).
**No effect is reportable unless |SOFT−HARD| or |SOFT−OFF| exceeds |SOFT_1−SOFT_2|.**

⚠⚠⚠ THE QUESTION IS NARROWER THAN "DOES A STOP-AFTER-LOSSES RULE HELP", AND THE
PRE-ITERATION AUDIT CAUGHT THAT AFTER THIS RUN HAD ALREADY LAUNCHED. Rule 1 of the same set
ends *"...it is chop — minimum size, and after two losers in that state, stop for the day"* —
a SECOND stop-after-losses rule, present in **all four arms** including OFF. So "no stop
rule" was never an arm, and the honest statement of what this measures is:

    does rule 9 add anything ON TOP OF rule 1's chop-conditional two-loss stop?

That is still a real and useful question — it is the same shape as the book-thinning prereg,
where the verdict is "C must beat A" and an indistinguishable addition is REFUTED because
replacing a shipped rule with an equivalent one is churn. But it is NOT the question "should
the strategy stop after three losses", and this file must not be read as answering it. A
clean test of that needs a fifth arm with BOTH stops removed, which has not been run.
⚠ The run was left going rather than restarted: the arms are valid for the narrower question
and restarting would spend ~127M tokens to re-ask it.

⚠ RUN ON A TRAINING-POOL WEEK, NEVER THE HOLDOUT. The holdout is the only unbiased estimate
of the project's bar and spending it on attribution would quietly convert it into another
training set. The effect was SEEN on a holdout day; it is TESTED here on 24-28 Aug.
⚠ A poisoned day (model never answered) is excluded from every arm, in pairs — dropping it
from one arm only would unbalance the pairing.
⚠ READ-ONLY on the desk: simulated fills, no broker, no order path.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import sim_week_recursive as SW                      # noqa: E402

OUT = f"{GB}/reports/ab_rule_toggle"
RULES = f"{GB}/reports/recursive_loop/rules_iter2.txt"
DAYS = ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]
TARGET = 9
POISON = 0.10

HARD_TEXT = ("Stop for the session after three losing trades. This is an UNCONDITIONAL "
             "STOP, not a guideline: once three trades have closed at a loss you take no "
             "further entry for the rest of the session under any circumstances, however "
             "good the next setup looks, and you flatten any open position at the next "
             "decision. Never try to recover a losing day by taking the other side.")


def split_rules(txt: str) -> list[str]:
    parts = re.split(r"(?m)^\s*(\d+)\.\s+", txt)
    return [" ".join(parts[i + 1].split()) for i in range(1, len(parts) - 1, 2)]


def variant(rules: list[str], mode: str) -> str:
    rs = list(rules)
    if mode == "off":
        del rs[TARGET - 1]
    elif mode == "hard":
        rs[TARGET - 1] = HARD_TEXT
    return "\n\n".join(f"{i}. {r}" for i, r in enumerate(rs, 1))


ARMS = {"soft1": "soft", "soft2": "soft", "off": "off", "hard": "hard"}


def run_arm(arm: str, mode: str, rules_txt: str, days: list[str]) -> list[dict]:
    recs = []
    for d in days:
        r = SW.run_day(d, rules_txt, f"ab9_{arm}", resume=True, self_aware=True)
        e = sum(1 for c in r["calls"] if c.get("error"))
        r["_err_rate"] = e / max(1, len(r["calls"]))
        recs.append(r)
        print(f"  [{arm}] {d}  ${r['net_usd']:>+9,.2f}  {len(r['trades'])} tr  "
              f"{e}/{len(r['calls'])} err", flush=True)
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2,
                    help="arms in parallel; 1 is slowest and gentlest on the rate limit")
    ap.add_argument("--days", default=",".join(DAYS))
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    days = [x.strip() for x in a.days.split(",") if x.strip()]
    os.makedirs(OUT, exist_ok=True)

    base = split_rules(open(RULES).read())
    if len(base) < TARGET:
        print(f"rule {TARGET} not found — only {len(base)} rules parsed")
        return 1
    print(f"RULE UNDER TEST (#{TARGET} of {len(base)}):")
    print(f"  {base[TARGET - 1][:200]}\n")

    texts = {arm: variant(base, mode) for arm, mode in ARMS.items()}
    # SOFT_2 must be byte-identical to SOFT_1 or it is not a noise arm
    assert texts["soft1"] == texts["soft2"], "noise arm differs from the control"
    for arm, t in texts.items():
        open(f"{OUT}/rules_{arm}.txt", "w").write(t)

    if not a.report_only:
        if a.workers > 1:
            with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
                futs = {ex.submit(run_arm, arm, ARMS[arm], texts[arm], days): arm
                        for arm in ARMS}
                for f in cf.as_completed(futs):
                    f.result()
        else:
            for arm in ARMS:
                run_arm(arm, ARMS[arm], texts[arm], days)

    # ── report ──────────────────────────────────────────────────────────────────────────
    got = {}
    for arm in ARMS:
        rows = {}
        for d in days:
            p = f"{SW.OUT}/ab9_{arm}_{d}.json"
            if os.path.exists(p):
                r = json.load(open(p))
                e = sum(1 for c in r["calls"] if c.get("error"))
                if e / max(1, len(r["calls"])) <= POISON:
                    rows[d] = r
        got[arm] = rows
    common = [d for d in days if all(d in got[arm] for arm in ARMS)]
    print(f"\n=== PAIRED ON {len(common)} DAY(S) CLEAN IN ALL FOUR ARMS ===")
    if not common:
        print("  nothing paired yet")
        return 0
    print(f"  {'day':12} " + " ".join(f"{a_:>11}" for a_ in ARMS))
    for d in common:
        print(f"  {d:12} " + " ".join(f"{got[a_][d]['net_usd']:>+11,.0f}" for a_ in ARMS))
    print("  " + "-" * 60)
    tot = {a_: sum(got[a_][d]["net_usd"] for d in common) for a_ in ARMS}
    pd = {a_: tot[a_] / len(common) for a_ in ARMS}
    print(f"  {'$/day':12} " + " ".join(f"{pd[a_]:>+11,.0f}" for a_ in ARMS))
    tr = {a_: sum(len(got[a_][d]["trades"]) for d in common) / len(common) for a_ in ARMS}
    print(f"  {'trades/day':12} " + " ".join(f"{tr[a_]:>11.1f}" for a_ in ARMS))

    noise = abs(pd["soft1"] - pd["soft2"])
    soft = (pd["soft1"] + pd["soft2"]) / 2
    print(f"\n  NOISE (soft1 vs soft2, identical rules): ${noise:,.0f}/day")
    for arm in ("off", "hard"):
        eff = pd[arm] - soft
        verdict = ("REPORTABLE — larger than this experiment's own noise"
                   if abs(eff) > noise else
                   "NOT REPORTABLE — inside this experiment's own noise")
        print(f"  {arm.upper():5} vs SOFT: ${eff:+,.0f}/day   → {verdict}")
    json.dump({"days": common, "per_day": pd, "trades_per_day": tr, "noise": noise,
               "generated": dt.datetime.now(dt.UTC).isoformat()},
              open(f"{OUT}/result.json", "w"), indent=1)
    print(f"\n  → {OUT}/result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
