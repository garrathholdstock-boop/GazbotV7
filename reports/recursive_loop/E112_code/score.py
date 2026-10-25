"""E112 scorer: counts, every entry one by one, per-day Law 0 numbers, and (with two arms) the declared verdict.

    .venv/bin/python reports/recursive_loop/E112_code/score.py --arm v102 --days 2025-10-01,... [--arm v102R] [--verdict]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import statistics as st
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
from gazbot7.bible import gate  # noqa: E402

OUT = f"{GB}/reports/e112"


def load(arm, days):
    recs, missing = {}, []
    for d in days:
        p = f"{OUT}/{arm}_{d}.json"
        if not os.path.exists(p):
            missing.append(d); continue
        r = json.load(open(p))
        if r.get("skipped"):
            continue
        c = r["calls"]
        if c and sum(1 for x in c if x.get("error")) / len(c) > 0.10:
            missing.append(d + "(poisoned)"); continue
        recs[d] = r
    return recs, missing


def stats(recs):
    days = sorted(recs)
    daily = [recs[d]["net_usd"] for d in days]
    P = [dict(p, day=d) for d in days for p in recs[d]["presses"]]
    acts = collections.Counter(c.get("entry_action") for d in days for c in recs[d]["calls"] if c.get("entry_action"))
    cum, peak, dd = 0, 0, 0
    for x in daily:
        cum += x; peak = max(peak, cum); dd = max(dd, peak - cum)
    mean = st.mean(daily) if daily else 0
    sd = st.pstdev(daily) if len(daily) > 1 else 0
    srt = sorted(daily)
    return {"sessions": len(days), "calls": sum(len(recs[d]["calls"]) for d in days),
            "errors": sum(recs[d]["errors"] for d in days),
            "enter_calls": sum(1 for d in days for c in recs[d]["calls"] if c["action"] in ("ENTER_LONG", "ENTER_SHORT")),
            "gate": dict(acts), "entries": len(P), "wins": sum(1 for p in P if p["why"] == "TARGET_37.5"),
            "le_1k": sum(1 for p in P if p["pnl_usd"] <= -1000), "le_2k": sum(1 for p in P if p["pnl_usd"] <= -2000),
            "le_4k": sum(1 for p in P if p["pnl_usd"] <= -4000), "mae150": sum(1 for p in P if p["mae_pt"] >= 150),
            "worst_entry": min((p["pnl_usd"] for p in P), default=0),
            "usd_per_day": mean, "days_positive": sum(1 for x in daily if x > 0), "days_flat": sum(1 for x in daily if x == 0),
            "worst_day": min(daily) if daily else 0, "p5_day": srt[max(0, int(0.05 * len(srt)) - 0)] if srt else 0,
            "daily_sd": sd, "cv": sd / mean if mean > 0 else float("inf"), "max_dd": dd,
            "days_le_2k": sum(1 for x in daily if x <= -2000), "lock_days": sum(1 for d in days if recs[d].get("lock")),
            "total": sum(daily), "presses": P, "daily": dict(zip(days, daily))}


def show(arm, s, missing):
    print(f"\n=== ARM {arm} ===  sessions {s['sessions']}  (missing/poisoned: {missing or 'none'})")
    print(f"  calls {s['calls']:,} (errored {s['errors']})  ENTER calls {s['enter_calls']}  gate outcomes {s['gate']}")
    print(f"  ENTRIES {s['entries']}  wins {s['wins']}  <=-$1k {s['le_1k']}  <=-$2k {s['le_2k']}  <=-$4k {s['le_4k']}  MAE>=150pt {s['mae150']}  worst entry ${s['worst_entry']:+,.0f}")
    print(f"  $/day {s['usd_per_day']:+,.0f}  total {s['total']:+,.0f}  days+ {s['days_positive']}/{s['sessions']} (flat {s['days_flat']})  worst day {s['worst_day']:+,.0f}"
          f"  SD {s['daily_sd']:,.0f}  CV {s['cv']:.2f}  maxDD {s['max_dd']:,.0f}  days<=-2k {s['days_le_2k']}  lock days {s['lock_days']}")
    print(f"  {'day':10} {'time':5} {'side':4} {'fill':>9} {'exit':>5} {'why':11} {'held':>6} {'MAE':>6} {'$':>8}  Claude's reason")
    for p in s["presses"]:
        print(f"  {p['day']:10} {p['decision_ts'][11:16]} {p['side']:4} {p['fill']:>9.2f} {p['exit_at'][11:16]} {p['why']:11} {p['held_min']:>6.0f} {p['mae_pt']:>6.0f} {p['pnl_usd']:>+8.0f}  {p['reason'][:150]}")
    print("  per day: " + "  ".join(f"{d[5:]} {v:+.0f}" for d, v in s["daily"].items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", required=True)
    ap.add_argument("--days", required=True)
    ap.add_argument("--verdict", action="store_true")
    a = ap.parse_args()
    days = sorted(a.days.split(","))
    res = {}
    loaded = {arm: load(arm, days) for arm in a.arm}
    common = sorted(set.intersection(*[set(r) for r, _ in loaded.values()]))   # paired days only
    for arm in a.arm:
        recs, missing = loaded[arm]
        res[arm] = stats({d: recs[d] for d in common})
        show(arm, res[arm], missing)
    if a.verdict and len(a.arm) == 2:
        base, ch = res[a.arm[0]], res[a.arm[1]]
        ok, why = gate(ch, base)
        cons = (ch["worst_day"] >= base["worst_day"] and ch["days_positive"] >= base["days_positive"]
                and (ch["cv"] <= base["cv"] or base["cv"] == float("inf")) and ch["le_1k"] < base["le_1k"])
        print(f"\nVERDICT on {len(common)} paired sessions:")
        print(f"  (1) bible.gate({a.arm[1]} vs {a.arm[0]}): {'PASS' if ok else 'FAIL'} - {why}")
        print(f"  (2) consistency (worst day, days+, CV no worse AND fewer entries <= -$1,000): {'PASS' if cons else 'FAIL'}"
              f"  [<=-$1k {ch['le_1k']} vs {base['le_1k']}; worst day {ch['worst_day']:+,.0f} vs {base['worst_day']:+,.0f};"
              f" days+ {ch['days_positive']} vs {base['days_positive']}; CV {ch['cv']:.2f} vs {base['cv']:.2f}]")
        lab = "PROMISING" if cons else ("WORSE" if ch["worst_day"] < base["worst_day"] and ch["le_1k"] > base["le_1k"] else "NO-BETTER")
        print(f"  LABEL: {lab}  (n = {len(common)} sessions: a story, not a result; December 2025 is the reserved confirmation month)")


if __name__ == "__main__":
    main()
