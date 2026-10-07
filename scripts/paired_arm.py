#!/usr/bin/env python3
"""ONE CLAUSE CHANGED, PAIRED AGAINST THE CHAMPION ON THE SAME TEN DAYS.

★★★ Why this replaces another free-running iteration. Three iterations of rewriting up to ten
rules at once produced $509 / $620 / $406 per day and, measured across all 30 holdout
day-runs, moved the exit NOT AT ALL:

    median hold          45 -> 48 -> 50 min      (legs of 40pt+ run a median of 106 min)
    holds >= 2 hours     11 -> 11 -> 9
    PREMATURE exits      48% -> 56% -> 56%       (price resumed our way within 30 min)
    median capture       -6% -> -4% -> -5%       (the median trade LOSES ground on its leg)
    $ left at exit    $4,172 -> $4,440 -> $2,965 PER DAY, against $620/day realised

Entries DID improve (lateness 46% -> 33%, against-leg trades halved). The exit is untouched
and it is where seven times the book is sitting.

THE CAUSE IS ONE CLAUSE, and both rule sets share it:
    champion  "Hold each entry until price makes a lower low than THE PULLBACK YOU ENTERED FROM"
    iter 2    "exit when price takes out THE LOW OF THE PULLBACK YOU ENTERED FROM"
That anchors the exit to a micro-level often a few points wide. On 2026-08-21 trade #4 was cut
on a 3pt break inside a 30pt range and left 108pt ($863) behind. The rule fired correctly; the
REFERENCE LEVEL was wrong.

THE DESIGN
  · ARM = the champion's rule set with rule 7's reference moved to the leg's trailing swing
    low. Byte-identical otherwise — verified by diff: one line removed, one added, 10 rules
    both sides.
  · BASELINE = iteration 2's holdout, ALREADY MEASURED on these exact ten days. So this costs
    10 day-runs, not 20, and the day-to-day variance cancels because both arms trade the same
    sessions. Unpaired, a $300 difference is unreadable; paired, the $1,000/day spread that
    produces the famous "$324 noise floor" drops out of the comparison entirely.

⚠⚠ THE PREDICTIONS ARE FROZEN BELOW, BEFORE THE RUN. They are COUNTS, not dollars, and that
is deliberate: the $180 gap to the $800 bar is smaller than the standard error of a ten-day
mean, so $/day cannot be the verdict on one run — while median hold and premature-exit rate
can. A result that moves the counts and not the dollars is still a result. Writing the
predictions down first is what stops the outcome being reinterpreted to fit
([[charge-the-search-and-then-charge-the-bar]]).

⚠ KNOWN COST, STATED IN ADVANCE: holding to leg structure instead of a micro-pullback will
WIDEN the losing tail. The champion's worst day is -$496. If the worst day deteriorates while
the counts improve, that is the trade-off working as expected, not a failure — and it is what
will constrain sizing later.

⚠ READ-ONLY on the desk: simulated fills, no broker, no order path.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import statistics as st
import time
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import sim_week_recursive as SW          # noqa: E402
import trade_review as TR                # noqa: E402

OUT = f"{GB}/reports/paired_arm"
HOLD = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18",
        "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]
POISON = 0.10
MEM_FLOOR_MB = 1800     # refuse to start another day below this; the desk needs ~820MB


def avail_mb() -> int:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 10 ** 6          # unknown: do not block on a reading we could not take

# ── FROZEN BEFORE THE RUN ────────────────────────────────────────────────────────────────
PREDICTION = {
    "median_hold_min": {"baseline": 48.0, "direction": "up",
                        "why": "the exit reference widens from a micro-pullback to the leg"},
    "premature_pct": {"baseline": 56.0, "direction": "down",
                      "why": "fewer exits should be followed by price resuming our way"},
    "capture_pct": {"baseline": 14.7, "direction": "up",
                    "why": "longer holds on the same entries take more of each leg"},
}
NOT_DECIDABLE = ("usd_per_day — the $180 gap to the bar is inside the standard error of a "
                 "10-day mean (~$229 on the champion). Recorded, not a verdict.")


def clean_days(tag: str) -> list[str]:
    out = []
    for d in HOLD:
        p = f"{SW.OUT}/{tag}_{d}.json"
        if not os.path.exists(p):
            continue
        r = json.load(open(p))
        if sum(1 for c in r["calls"] if c.get("error")) / max(1, len(r["calls"])) <= POISON:
            out.append(d)
    return out


def metrics(tag: str, days_only: list[str] | None = None) -> dict | None:
    """⚠⚠ `days_only` IS NOT OPTIONAL IN PRACTICE AND THE FIRST CUT OMITTED IT.

    Without it this computed the baseline over all 10 of its clean days and the arm over
    whichever of ITS days were clean, then printed the differences as if they were paired.
    On 2026-10-06 that produced "PAIRED ON 6 DAY(S)" with a champion column covering ten —
    including +$1,422 and +$1,386 August days the arm's six did not contain. Every delta in
    that table was meaningless, and the headline ($/day +$78) was an artefact of comparing
    different sessions. A paired design that silently stops pairing is worse than an
    unpaired one, because it still claims the pairing.
    """
    rows, days, prem, ntr, off, took, nets = [], 0, 0, 0, 0.0, 0.0, []
    for d in (days_only if days_only is not None else HOLD):
        p = f"{SW.OUT}/{tag}_{d}.json"
        if not os.path.exists(p):
            continue
        r = json.load(open(p))
        if sum(1 for c in r["calls"] if c.get("error")) / max(1, len(r["calls"])) > POISON:
            continue
        a = TR.analyse(d, r["trades"], r["calls"])
        days += 1
        prem += a["premature_exits"]
        off += a["offered_pt"]
        took += a["took_pt"]
        nets.append(r["net_usd"])
        rows += a["rows"]
        ntr += len(a["rows"])
    if not days:
        return None
    holds = [x["held_min"] for x in rows if x["held_min"]]
    return {"days": days, "trades": ntr,
            "median_hold_min": round(st.median(holds), 1) if holds else 0.0,
            "holds_over_2h": sum(1 for h in holds if h >= 120),
            "premature_pct": round(100.0 * prem / max(1, ntr), 1),
            "capture_pct": round(100.0 * took / max(1e-9, off), 1),
            "usd_per_day": round(sum(nets) / days, 2),
            "daily_sd": round(st.stdev(nets), 2) if len(nets) > 1 else 0.0,
            "days_positive": sum(1 for x in nets if x > 0),
            "worst_day": round(min(nets), 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", default=f"{GB}/reports/recursive_loop/rules_exitfix.txt")
    ap.add_argument("--arm", default="exitfix")
    ap.add_argument("--baseline", default="loop2_hold")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--workers", type=int, default=4,
                    help="days in parallel. Days are independent; the 138 decisions inside "
                         "a day are not and never run concurrently.")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    print("=== FROZEN PREDICTIONS (written before the run) ===")
    for k, v in PREDICTION.items():
        print(f"  {k}: baseline {v['baseline']} must go {v['direction'].upper()} — {v['why']}")
    print(f"  NOT DECIDABLE: {NOT_DECIDABLE}\n")

    if not a.report_only:
        rules = open(a.rules).read()

        def one(d: str):
            # ⚠ FAIL SAFE ON MEMORY, NEVER OOM. The box is 7.5GB and CLAUDE.md records three
            # global_oom kills that took the DESK down — "it presents as everything keeps
            # exiting". A research run is never allowed to be the process that does that,
            # especially while the operator holds a position. Measured: one sim `claude -p`
            # is ~190MB RSS (the 2.3GB in CLAUDE.md is the Friday report, whose contexts are
            # far larger), so MEM_FLOOR_MB leaves the desk its ~820MB plus room to breathe.
            if avail_mb() < MEM_FLOOR_MB:
                print(f"  [{a.arm}] {d} DEFERRED — only {avail_mb()}MB available, "
                      f"floor is {MEM_FLOOR_MB}MB", flush=True)
                time.sleep(60)
                if avail_mb() < MEM_FLOOR_MB:
                    return None
            r = SW.run_day(d, rules, f"{a.arm}_hold", resume=True, self_aware=True)
            e = sum(1 for c in r["calls"] if c.get("error"))
            print(f"  [{a.arm}] {d}  ${r['net_usd']:>+9,.2f}  {len(r['trades'])} tr  "
                  f"{e}/{len(r['calls'])} err", flush=True)
            return r

        # ★2026-10-06 DAYS RUN IN PARALLEL. Within a day the 138 decisions MUST be sequential
        # — each one depends on whether the previous left a position open — but the days are
        # independent replays, so ten of them serially was 4.5 hours of wall clock for no
        # reason. Operator: *"if the box can handle it run a few at a time"*.
        # ⚠ NOT all ten at once: memory is fine (~1.9GB) but concurrent `claude -p` calls hit
        # rate limits, and a rate-limited call errors — which is exactly how the rule-9 A/B
        # lost 16 of 20 arms. Four is the compromise; raise it only with the guard watching.
        if a.workers > 1:
            with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
                list(ex.map(one, HOLD))
        else:
            for d in HOLD:
                one(d)

    # pair on days clean in BOTH arms, and say so loudly when days are dropped
    cb, ca = clean_days(a.baseline), clean_days(f"{a.arm}_hold")
    common = [d for d in HOLD if d in cb and d in ca]
    dropped = [d for d in HOLD if d not in common]
    if dropped:
        print(f"  ⚠ {len(dropped)} day(s) EXCLUDED (poisoned or missing in one arm): "
              f"{', '.join(dropped)}")
        print("    The comparison below covers ONLY the days clean in both arms.\n")
    base = metrics(a.baseline, common)
    arm = metrics(f"{a.arm}_hold", common)
    if not base or not arm:
        print(f"\n  incomplete: baseline={bool(base)} arm={bool(arm)}")
        return 0
    print(f"\n=== PAIRED ON {arm['days']} DAY(S) ===")
    print(f"  {'metric':22} {'champion':>12} {'exit-fix':>12} {'delta':>12}  verdict")
    verdicts = {}
    for k in ("median_hold_min", "premature_pct", "capture_pct"):
        d = arm[k] - base[k]
        want = PREDICTION[k]["direction"]
        hit = (d > 0) if want == "up" else (d < 0)
        verdicts[k] = hit
        print(f"  {k:22} {base[k]:>12} {arm[k]:>12} {d:>+12.1f}  "
              f"{'AS PREDICTED' if hit else 'AGAINST PREDICTION'}")
    for k in ("holds_over_2h", "trades", "days_positive", "worst_day", "usd_per_day"):
        print(f"  {k:22} {base[k]:>12} {arm[k]:>12} {arm[k]-base[k]:>+12.1f}  "
              f"{'(not decidable)' if k == 'usd_per_day' else ''}")
    # ★2026-10-06 USE THE GATE, DO NOT HAND-ROLL THE COMPARISON. An audit found this file
    # computing days_positive, worst_day and usd_per_day and then ranking on $/day alone,
    # while `bible.gate()` sits in the repo expecting exactly those keys.
    try:
        from gazbot7.bible import gate as _gate
        arm2 = dict(arm); arm2["daily_sd"] = arm2.get("daily_sd") or 0.0
        base2 = dict(base); base2["daily_sd"] = base2.get("daily_sd") or 0.0
        if arm2["daily_sd"] and base2["daily_sd"]:
            okg, whyg = _gate(arm2, base2)
            print(f"\n  CONSISTENCY GATE (bible Law 0): "
                  f"{'the arm would REPLACE the champion' if okg else 'REJECTED'} — {whyg}")
    except Exception as e:
        print(f"\n  gate unavailable: {type(e).__name__}")
    n_hit = sum(verdicts.values())
    print(f"\n  {n_hit} of 3 frozen predictions met.")
    print("  ⚠ $/day is recorded, not a verdict — see NOT DECIDABLE above.")
    if arm["worst_day"] < base["worst_day"]:
        print(f"  ⚠ worst day deteriorated ${base['worst_day']:+,.0f} → "
              f"${arm['worst_day']:+,.0f} — the stated cost of holding to leg structure.")
    json.dump({"prediction": PREDICTION, "baseline": base, "arm": arm,
               "predictions_met": n_hit,
               "generated": dt.datetime.now(dt.UTC).isoformat()},
              open(f"{OUT}/{a.arm}.json", "w"), indent=1)
    print(f"\n  → {OUT}/{a.arm}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
