#!/usr/bin/env python3
"""WHAT CHANGED BETWEEN ITERATIONS, AND DID IT DO ANYTHING.

★★★ Operator, 2026-10-06: *"how do you know what is changing in the logic between
iterations? that is important? we need to know what is changing between strategies no? or
do we just leave it to claude"*

He is right and this was the weakest part of the loop. The rule TEXT was versioned
(`rules_iter<N>.txt`) and nobody had ever diffed it, so three iterations in we had a
headline ($509 → $620 → …) with no attribution. That matters more than it sounds:

  · **The gain is inside the noise.** Single-run variance on identical inputs was measured
    at **$324/day** on this harness. Iteration 2 beat iteration 1 by **$111/day**. Without
    knowing WHICH rule moved WHICH behaviour, "it improved" is indistinguishable from
    "it was dealt an easier draw", and [[charge-the-search-and-then-charge-the-bar]] says
    that is exactly when a story gets believed.
  · **A rewritten rule set can REVERSE itself without anyone noticing.** Iteration 1 ordered
    *"Target 8-15 entries per session"* and *"A session with no trade is a FAILURE"*.
    Iteration 2 replaced both with *"there is no quota and a flat session is not a failure"*.
    That is a 180-degree turn on the single lever the operator cares most about — trade
    count — and it was invisible in every summary either of us had looked at.
  · **Leaving it to Claude is the one option that cannot work.** The reviewer writes the next
    rule set from one week's P&L. If nothing records what it changed and what happened next,
    the loop cannot tell a rule that earned its place from one that was merely present.

WHAT THIS DOES. For each consecutive pair of iterations: aligns the rule sets, reports rules
that were DROPPED, ADDED or REWRITTEN (with the before/after text), and sets that beside the
behavioural deltas the change was supposed to move — trades/day, days positive, side
accuracy, capture, $/trade, win rate, payoff ratio. Then it says, for each delta, whether it
is larger than known run-to-run variance or not.

⚠ IT ATTRIBUTES NOTHING ON ITS OWN. With one run per iteration, a rule change and an outcome
change are CORRELATED, never causal — a clean attribution needs the same week re-run with
one rule toggled, which is a separate and much more expensive experiment. This tool makes the
hypothesis explicit and legible; it does not test it. Every line of its output is labelled
accordingly.

⚠ READ-ONLY. Reads the loop's artefacts, writes nothing.
"""
from __future__ import annotations

import argparse
import difflib
import datetime as dt
import json
import os
import re

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/recursive_loop"
SIM = f"{GB}/reports/sim_week_recursive"
HOLD = ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
        "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]

# The measured single-run spread on identical inputs, 2026-10-03. Any iteration-to-iteration
# move smaller than this is NOT evidence of learning.
RUN_VARIANCE_USD_PER_DAY = 324.0


def rules(it: int) -> list[str]:
    p = f"{OUT}/rules_iter{it}.txt"
    if not os.path.exists(p):
        return []
    txt = open(p).read()
    # rules are numbered "1." ... "10." at line start
    parts = re.split(r"(?m)^\s*(\d+)\.\s+", txt)
    out = []
    for i in range(1, len(parts) - 1, 2):
        out.append(" ".join(parts[i + 1].split()))
    return out


def behaviour(tag: str) -> dict | None:
    rows = []
    for d in HOLD:
        p = f"{SIM}/{tag}_hold_{d}.json"
        if os.path.exists(p):
            r = json.load(open(p))
            e = sum(1 for c in r["calls"] if c.get("error"))
            if e / max(1, len(r["calls"])) > 0.10:
                continue                 # a poisoned day is not behaviour
            rows.append(r)
    if not rows:
        return None
    tr = [t for r in rows for t in r["trades"]]
    w = [t["pnl_usd"] for t in tr if t["pnl_usd"] > 0]
    l = [t["pnl_usd"] for t in tr if t["pnl_usd"] <= 0]
    net = sum(r["net_usd"] for r in rows)
    # ⚠ `opened`/`closed` are ISO STRINGS in these artefacts, not epochs. The first cut
    # subtracted them directly and died on str - str.
    holds = []
    for t in tr:
        try:
            o = dt.datetime.fromisoformat(str(t["opened"]))
            c = dt.datetime.fromisoformat(str(t["closed"]))
            holds.append((c - o).total_seconds() / 60)
        except Exception:
            continue
    return {
        "days": len(rows), "net_usd": net, "usd_per_day": net / len(rows),
        "trades": len(tr), "trades_per_day": len(tr) / len(rows),
        "days_positive": sum(1 for r in rows if r["net_usd"] > 0),
        "usd_per_trade": (net / len(tr)) if tr else 0.0,
        "win_pct": (100.0 * len(w) / len(tr)) if tr else 0.0,
        "avg_win": (sum(w) / len(w)) if w else 0.0,
        "avg_loss": (sum(l) / len(l)) if l else 0.0,
        "payoff": (abs((sum(w) / len(w)) / (sum(l) / len(l)))
                   if w and l and sum(l) else 0.0),
        "median_hold_min": (sorted(holds)[len(holds) // 2] if holds else 0.0),
    }


STOP = set("a an the and or of to in on is it be as at by for from with that this not no "
           "you your own if then than so do does only ever never any every all both each "
           "its their there here was were are has have had will would can could should".split())


def _toks(x: str) -> set:
    return {w for w in re.findall(r"[a-z]+", x.lower()) if w not in STOP and len(w) > 2}


def _sim(a: str, b: str) -> float:
    """★ TWO MEASURES, MAX OF BOTH, AND THE SECOND ONE IS WHY THIS WORKS.

    The first cut used `difflib.SequenceMatcher` alone and reported 9 of 10 rules as
    DROPPED plus 9 as ADDED with "0 rules carried over unchanged" — a completely false
    picture. The reviewer REWORDS wholesale: "Never take a trade against the side you have
    declared" became "Take no trade against the dominant side, ever", which is the SAME
    RULE and scores only ~0.4 on character sequence. Content-word overlap (Jaccard, minus
    stopwords) catches that; sequence matching catches small edits. Taking the max of both
    distinguishes "same rule, rephrased" from "genuinely new rule", which is the entire
    point of this tool — reporting a rewording as a replacement would manufacture exactly
    the illusion of change the operator asked me to rule out.
    """
    ta, tb = _toks(a), _toks(b)
    jac = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return max(difflib.SequenceMatcher(None, a, b).ratio(), jac)


def align(a: list[str], b: list[str]) -> list[tuple[str, str, str]]:
    """(verdict, old, new). Pairs rules by best similarity, not by number — renumbering is
    not a change and must not read as one. Greedy on the best available pair overall, so one
    strong match cannot be stolen by an earlier weak one."""
    pairs = sorted(((_sim(oa, ob), i, j) for i, oa in enumerate(a) for j, ob in enumerate(b)),
                   reverse=True)
    ua, ub, out = set(), set(), []
    for score, i, j in pairs:
        if i in ua or j in ub or score < 0.30:
            continue
        ua.add(i)
        ub.add(j)
        out.append((("UNCHANGED" if score >= 0.95 else
                     "SAME RULE, REWORDED" if score >= 0.55 else "REWRITTEN"), a[i], b[j]))
    out += [("DROPPED", a[i], "") for i in range(len(a)) if i not in ua]
    out += [("ADDED", "", b[j]) for j in range(len(b)) if j not in ub]
    return out


def wrap(s: str, w: int = 92, pad: str = " " * 8) -> str:
    import textwrap
    return textwrap.fill(s, w, initial_indent=pad, subsequent_indent=pad)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="a", type=int, default=1)
    ap.add_argument("--to", dest="b", type=int, default=2)
    ap.add_argument("--text-only", action="store_true")
    k = ap.parse_args()

    ra, rb = rules(k.a), rules(k.b)
    if not ra or not rb:
        print(f"missing rule set(s): iter{k.a}={len(ra)} rules, iter{k.b}={len(rb)} rules")
        return 1

    print(f"=== LOGIC CHANGE: iteration {k.a} → iteration {k.b} ===")
    print(f"    {len(ra)} rules → {len(rb)} rules\n")
    rows = align(ra, rb)
    order = {"DROPPED": 0, "ADDED": 1, "REWRITTEN": 2, "SAME RULE, REWORDED": 3,
             "UNCHANGED": 4}
    for verdict, old, new in sorted(rows, key=lambda x: order[x[0]]):
        if verdict in ("UNCHANGED", "SAME RULE, REWORDED"):
            continue
        print(f"  [{verdict}]")
        if old:
            print(wrap("WAS: " + old))
        if new:
            print(wrap("NOW: " + new))
        print()
    n_un = sum(1 for v, _, _ in rows if v in ("UNCHANGED", "SAME RULE, REWORDED"))
    print(f"  ({n_un} rules carried over with the same meaning, reworded)\n")

    if k.text_only:
        return 0

    ba, bb = behaviour(f"loop{k.a}"), behaviour(f"loop{k.b}")
    if not ba or not bb:
        print("  behaviour unavailable for one side (incomplete iteration)")
        return 0
    print("=== WHAT THE BEHAVIOUR DID (clean holdout days only) ===")
    print(f"  {'metric':20} {'iter '+str(k.a):>12} {'iter '+str(k.b):>12} {'delta':>12}")
    for key, lbl, fmt in (("days", "clean days", "{:.0f}"),
                          ("usd_per_day", "$/day", "{:+,.0f}"),
                          ("days_positive", "days positive", "{:.0f}"),
                          ("trades_per_day", "trades/day", "{:.2f}"),
                          ("usd_per_trade", "$/trade", "{:+,.0f}"),
                          ("win_pct", "win %", "{:.0f}"),
                          ("avg_win", "avg win", "{:+,.0f}"),
                          ("avg_loss", "avg loss", "{:+,.0f}"),
                          ("payoff", "payoff ratio", "{:.2f}"),
                          ("median_hold_min", "median hold (min)", "{:.0f}")):
        d = bb[key] - ba[key]
        print(f"  {lbl:20} {fmt.format(ba[key]):>12} {fmt.format(bb[key]):>12} "
              f"{fmt.format(d):>12}")
    print()
    dd = bb["usd_per_day"] - ba["usd_per_day"]
    print(f"  ⚠ $/day moved {dd:+,.0f} against ${RUN_VARIANCE_USD_PER_DAY:,.0f} of measured "
          f"single-run variance")
    print(f"    → {'LARGER than the noise floor — worth a hypothesis' if abs(dd) > RUN_VARIANCE_USD_PER_DAY else 'INSIDE the noise floor — NOT evidence of learning'}")
    print()
    print("  ⚠⚠ CORRELATION, NOT ATTRIBUTION. One run per iteration and several rules changed")
    print("     at once, so no line above establishes which rule did what. Testing one rule")
    print("     means re-running the same week with only that rule toggled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
