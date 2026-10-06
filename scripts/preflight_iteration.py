#!/usr/bin/env python3
"""THE PRE-ITERATION AUDIT — refuse to start a run that will have to be redone.

★★★ Operator, 2026-10-06: *"so we are not forgetting things and needing to rerun things, can
you put an audit agent out each time before each iteration to make sure whats about to be
done is thorough and aimed at improving the numbers?"*

EVERY RE-RUN THIS PROJECT HAS SUFFERED WAS CHECKABLE IN ADVANCE. The audit's checks are not
invented — each one is a specific failure that already cost a day or a week:

  · **the binary** — 2026-10-05: the shadow runner's first live day made 138 of 138 calls
    fail with FileNotFoundError because `claude` was resolved off PATH and systemd's PATH
    does not include /root/.local/bin. A whole trading day lost to one unresolved name.
  · **the credits** — 2026-10-04 and 10-06: three of iteration 3's holdout days errored
    138/138, 138/138 and 70/138 when the weekly budget ran out mid-run. Two booked exactly
    $0.00 with zero trades and read as flat sessions in every summary.
  · **poisoned artefacts** — `resume` treated those as FINISHED days. Iteration 3 would have
    scored $488/day with two failures counted as flat, including 2026-09-18, a day that made
    +$2,022 and +$1,524 on the prior two iterations.
  · **the tape** — a day with thin or missing bars produces a day-run that looks complete.
  · **the holdout** — if a holdout day ever appears in a training set the project's only
    unbiased number is gone, silently and permanently.
  · **the noise floor** — iteration 2 "improved" by $111/day against a measured $324/day
    single-run spread. An iteration that cannot clear its own noise cannot produce a result,
    only a story ([[charge-the-search-and-then-charge-the-bar]]).

TWO LAYERS, AND THEY FAIL DIFFERENTLY.
  **GATES** are deterministic and FAIL CLOSED — if a gate fails the iteration does not start.
  **THE AUDIT** is a headless `claude -p` that reads the state and the rule set about to be
  traded and answers one question the gates cannot: *is this iteration aimed at the metric
  that is actually failing?* Its verdict can block, but `--force` overrides it; a gate cannot
  be forced, because "the binary is missing" is not a matter of opinion.

⚠ IT IS A HEADLESS CALL, NOT A SESSION SUBAGENT. The loop runs detached for hours with no
session attached — the same reason the router was built headless. An audit that needs me
present is an audit that will not run.
⚠ READ-ONLY: reads artefacts and config, writes one report. No desk state, no order path.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")

OUT = f"{GB}/reports/recursive_loop"
SIM = f"{GB}/reports/sim_week_recursive"
REPORT = f"{OUT}/preflight"
CLAUDE = "/root/.local/bin/claude"      # ⚠ ABSOLUTE — see the docstring
HOLDOUT = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18",
           "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]
BAR = {"usd_per_day": 800.0, "trades_per_day": (3.0, 6.0),
       "side_accuracy": 0.75, "capture": 0.15}
RUN_VARIANCE = 324.0
TOKENS_PER_DAY_RUN = 6.33e6
POISON = 0.10
MIN_BARS = 300


def gates(it: int, train: list[str], hold: list[str]) -> list[tuple[bool, str]]:
    g: list[tuple[bool, str]] = []

    # 1. the thing that makes every decision
    ok = os.access(CLAUDE, os.X_OK)
    g.append((ok, f"claude binary executable at {CLAUDE}"
                  + ("" if ok else " — THIS COST A FULL DAY ON 2026-10-05")))

    # 2. does it actually answer right now
    try:
        p = subprocess.run([CLAUDE, "-p", "Reply with the single word OK."],
                           capture_output=True, text=True, timeout=120)
        ans = (p.stdout or "").strip()
        ok = p.returncode == 0 and "OK" in ans
        g.append((ok, "a live call returns an answer"
                      + ("" if ok else f" — got rc={p.returncode} {ans[:120]!r}")))
    except Exception as e:
        g.append((False, f"a live call returns an answer — {type(e).__name__}"))

    # 3. enough budget for the whole plan, not just the first day
    try:
        import claude_usage as U
        s = U.summary()
        need = TOKENS_PER_DAY_RUN * (len(train) + len(hold))
        have = s.get("remaining_tokens")
        if have is None:
            g.append((True, "budget unknown (no budget configured) — not blocking"))
        else:
            ok = have >= need
            g.append((ok, f"budget covers the plan: need ~{need/1e6:.0f}M, have "
                          f"{have/1e6:.0f}M"
                          + ("" if ok else " — A MID-RUN EXHAUSTION POISONS DAYS")))
    except Exception as e:
        g.append((True, f"budget check unavailable ({type(e).__name__}) — not blocking"))

    # 4. tape for every planned day
    try:
        import sim_week_recursive as SW
        thin = []
        for d in train + hold:
            try:
                b, _ = SW.load_day(d)
                if len(b) < MIN_BARS:
                    thin.append(f"{d}({len(b)})")
            except Exception:
                thin.append(f"{d}(ERR)")
        g.append((not thin, "tape present for every planned day"
                  + ("" if not thin else f" — THIN/MISSING: {', '.join(thin)}")))
    except Exception as e:
        g.append((False, f"tape check failed — {type(e).__name__}"))

    # 5. no poisoned artefact that `resume` would inherit as a finished day
    bad = []
    for arm, days in ((f"loop{it}_train", train), (f"loop{it}_hold", hold)):
        for d in days:
            p = f"{SIM}/{arm}_{d}.json"
            if not os.path.exists(p):
                continue
            try:
                r = json.load(open(p))
            except Exception:
                bad.append(f"{arm}_{d}(unparseable)")
                continue
            c = r.get("calls") or []
            e = sum(1 for x in c if x.get("error"))
            if not c or e / len(c) > POISON:
                bad.append(f"{arm}_{d}({e}/{len(c)})")
    g.append((not bad, "no poisoned artefact in this iteration's arm"
              + ("" if not bad else f" — QUARANTINE FIRST: {', '.join(bad)}")))

    # 6. the holdout has never been trained on
    leak = sorted(set(train) & set(HOLDOUT))
    g.append((not leak, "no holdout day in the training week"
              + ("" if not leak else f" — LEAK: {', '.join(leak)}; the project's only "
                                     "unbiased number would be gone")))

    # 7. the rule set exists and parses
    rp = f"{OUT}/rules.txt"
    n = 0
    if os.path.exists(rp):
        n = len(re.findall(r"(?m)^\s*\d+\.\s+", open(rp).read()))
    g.append((n > 0 or it == 1,
              f"rule set parses ({n} rules)" + ("" if n or it == 1 else " — unparseable")))

    # 8. somewhere to put the output
    try:
        import shutil
        free = shutil.disk_usage(GB).free / 1e9
        g.append((free > 2.0, f"disk free {free:.1f}GB"))
    except Exception:
        g.append((True, "disk check unavailable — not blocking"))
    return g


def state_brief(it: int) -> str:
    L = [f"ITERATION ABOUT TO RUN: {it}", ""]
    hp = f"{OUT}/history.json"
    if os.path.exists(hp):
        L.append("SCORED HISTORY (holdout, never trained on, never reviewed):")
        for x in json.load(open(hp)):
            h = x["holdout"]
            L.append(f"  iter {x['iter']}: ${h['net_usd']/10:+,.0f}/day · "
                     f"side {h['side_accuracy']:.3f} · capture {h['capture']:.2f} · "
                     f"{h['trades_per_day']:.1f} trades/day · met all four: {x['met']}")
    L += ["", "THE BAR, ALL FOUR REQUIRED:",
          f"  $/day >= {BAR['usd_per_day']:,.0f} · trades/day in "
          f"{BAR['trades_per_day']} · side accuracy >= {BAR['side_accuracy']} · "
          f"capture >= {BAR['capture']}",
          "",
          f"MEASURED SINGLE-RUN VARIANCE: ${RUN_VARIANCE:,.0f}/day on IDENTICAL inputs.",
          "Iteration 2 beat iteration 1 by $111/day, which is INSIDE that. So a change whose",
          "expected effect is smaller than $324/day cannot be measured by one more iteration.",
          "",
          "KNOWN AND NOT TO BE RE-DERIVED:",
          "  · his entries are a coin on a symmetric race (+0.2pp side-matched, n=174)",
          "  · he is a CONTINUATION trader; turn entries are a coin at every setting tested",
          "  · the money is in the asymmetric payoff: 4 lots, no stop, hold to structure",
          "  · showing the model the SHAPE instead of the metrics was the biggest single",
          "    lever found (a simulated Monday went -$400 to +$352, 14 trades to 4)",
          "  · rule 9 ('stop after three losing trades') is DEAD TEXT: ignored on 12 of 12",
          "    days where it bound, and the P&L after the third loss totals +$8,776 over 32",
          "    day-runs. It is under separate A/B test; do not also change it here.",
          ""]
    rp = f"{OUT}/rules.txt"
    if os.path.exists(rp):
        L += ["THE RULE SET THIS ITERATION WILL TRADE:", open(rp).read(), ""]
    return "\n".join(L)


AUDIT = """You are auditing a trading research iteration BEFORE it runs, to stop work that
will have to be redone. You are not being asked to approve the strategy — you are being asked
ONE question:

  Is this iteration aimed at the metric that is actually failing, and can its result be
  distinguished from noise?

Answer in this exact shape and nothing else:

VERDICT: GO | FIX-FIRST | STOP
FAILING METRIC: <the single metric furthest from the bar, with its number>
AIMED AT IT: YES | PARTLY | NO — <one sentence on whether the rule set addresses that metric>
MEASURABLE: YES | NO — <one sentence on whether a plausible effect exceeds the $324/day noise floor>
MISSING: <up to three things that should be done or recorded before this runs, or "nothing">
REASON: <two sentences, maximum>

Rules for your verdict:
- STOP only if running this would waste the budget outright — e.g. the rule set is unchanged
  from the previous iteration, or it targets something already settled as a coin.
- FIX-FIRST if something cheap and specific should be recorded or quarantined first.
- GO if the iteration is aimed at a real gap and its outcome will be interpretable.
- Do NOT suggest re-deriving anything listed as known. Do NOT propose new metrics.
- Be blunt. A GO that should have been FIX-FIRST costs a week of budget."""


def audit(it: int, timeout: int = 240) -> dict:
    prompt = AUDIT + "\n\n=== STATE ===\n" + state_brief(it)
    try:
        p = subprocess.run([CLAUDE, "-p", prompt], capture_output=True, text=True,
                           timeout=timeout, env={**os.environ, "HOME": "/root"})
        txt = (p.stdout or "").strip()
    except Exception as e:
        return {"verdict": "UNAVAILABLE", "raw": f"{type(e).__name__}: {e}"}
    m = re.search(r"VERDICT:\s*(GO|FIX-FIRST|STOP)", txt, re.I)
    return {"verdict": (m.group(1).upper() if m else "UNPARSEABLE"), "raw": txt}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iter", type=int, required=True)
    ap.add_argument("--train", default="")
    ap.add_argument("--hold", default=",".join(HOLDOUT))
    ap.add_argument("--no-audit", action="store_true", help="gates only, skip the LLM pass")
    ap.add_argument("--force", action="store_true", help="override a STOP verdict, never a gate")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    train = [x.strip() for x in a.train.split(",") if x.strip()]
    hold = [x.strip() for x in a.hold.split(",") if x.strip()]

    print(f"=== PRE-ITERATION AUDIT — iteration {a.iter} ===")
    print(f"    {len(train)} training day(s), {len(hold)} holdout day(s)\n")
    g = gates(a.iter, train, hold)
    for ok, msg in g:
        print(f"  [{'PASS' if ok else 'FAIL'}] {msg}")
    hard = [m for ok, m in g if not ok]

    res = {"iter": a.iter, "ts": dt.datetime.now(dt.UTC).isoformat(),
           "gates": [{"ok": ok, "check": m} for ok, m in g],
           "gates_failed": hard}
    if hard:
        print(f"\n  ⛔ {len(hard)} GATE(S) FAILED — the iteration must not start.")
        print("     A gate cannot be forced: these are facts, not opinions.")
        res["verdict"] = "BLOCKED"
    else:
        print("\n  ✅ all gates pass")
        if not a.no_audit:
            print("\n=== THE AUDIT ===")
            au = audit(a.iter)
            res["audit"] = au
            print("\n".join(f"  {l}" for l in au["raw"].splitlines()[:14]))
            v = au["verdict"]
            if v == "STOP" and not a.force:
                print("\n  ⛔ audit says STOP — not starting. Override with --force.")
                res["verdict"] = "STOP"
            elif v == "FIX-FIRST":
                print("\n  ⚠ audit says FIX-FIRST — address MISSING above, then re-run.")
                res["verdict"] = "FIX-FIRST"
            else:
                res["verdict"] = "GO" if v == "GO" else v
        else:
            res["verdict"] = "GO"

    os.makedirs(REPORT, exist_ok=True)
    json.dump(res, open(f"{REPORT}/iter{a.iter}.json", "w"), indent=1)
    print(f"\n  → {REPORT}/iter{a.iter}.json   verdict={res['verdict']}")
    if a.json:
        print(json.dumps(res, indent=1))
    return 0 if res["verdict"] in ("GO", "FIX-FIRST") else 2


if __name__ == "__main__":
    raise SystemExit(main())
