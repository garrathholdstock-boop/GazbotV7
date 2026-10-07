#!/usr/bin/env python3
"""RUN A FROZEN RULE SET OVER A WHOLE MONTH IT HAS NEVER SEEN — NO REVIEW, NO REWRITE.

Operator, 2026-10-06: "Run it2 on a month we've never seen before and see how it goes."
IT2's $620/day, 9/10 days came from 10 held-out days. This is the wider test: ~22 sessions
from the lake, none of which any iteration trained on or reviewed, rules byte-frozen (sha
printed and stamped), same harness, same `self_aware=True`, same fills as the holdout.

Bars come from the lake (1-min), the default source of sim_week_recursive.load_day.
READ-ONLY on the desk: simulated fills, no broker, no order path, no review/consolidate step.
A poisoned day (>10% of calls errored) is never scored and is re-run in a second pass.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import statistics as st
import sys
import time

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import sim_week_recursive as SW          # noqa: E402
import paired_arm as PA                  # noqa: E402
from gazbot7.notify import notify, in_quiet_hours   # noqa: E402

POISON = 0.10
OUT = f"{GB}/reports/forward_month"
HOLDOUT = {"2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
           "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"}
IT2_HOLDOUT = {"usd_per_day": 619.6, "days_positive": "9/10", "daily_sd": 724, "worst_day": -496}


def month_days(month: str) -> list[str]:
    d = dt.date.fromisoformat(month + "-01")
    out = []
    while d.month == dt.date.fromisoformat(month + "-01").month:
        if d.weekday() < 5:
            bars, _ = SW.load_day(d.isoformat())
            if len(bars) >= 600:
                out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def is_clean(tag: str, day: str) -> bool:
    p = f"{SW.OUT}/{tag}_{day}.json"
    if not os.path.exists(p):
        return False
    r = json.load(open(p))
    c = r.get("calls") or []
    return bool(c) and sum(1 for x in c if x.get("error")) / len(c) <= POISON


def say(msg: str, state: dict) -> None:
    state["pending"] = msg
    if not in_quiet_hours(dt.datetime.now(dt.UTC)):
        notify(msg, critical=False, mark=False, weekend_ok=True)
        state["pending"] = None


def summarise(tag: str, days: list[str]) -> dict | None:
    clean = [d for d in days if is_clean(tag, d)]
    m = PA.metrics(tag, clean)
    if not m:
        return None
    nets = {d: json.load(open(f"{SW.OUT}/{tag}_{d}.json"))["net_usd"] for d in clean}
    weeks: dict[str, float] = {}
    for d, v in nets.items():
        wk = (dt.date.fromisoformat(d) - dt.timedelta(days=dt.date.fromisoformat(d).weekday())).isoformat()
        weeks[wk] = weeks.get(wk, 0.0) + v
    m["clean_days"] = len(clean)
    m["se"] = round(m["daily_sd"] / max(1, len(clean)) ** 0.5, 1)
    m["trades_per_day"] = round(m["trades"] / max(1, len(clean)), 2)
    m["week_totals"] = {k: round(v, 2) for k, v in sorted(weeks.items())}
    m["nets"] = {d: round(v, 2) for d, v in sorted(nets.items())}
    return m


def line(m: dict) -> str:
    return (f"{m['clean_days']} days · ${m['usd_per_day']:+,.0f}/day · {m['days_positive']}/{m['clean_days']} positive · "
            f"worst ${m['worst_day']:+,.0f} · SD ${m['daily_sd']:,.0f} · {m['trades_per_day']} trades/day")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--rules", default=f"{GB}/reports/recursive_loop/IT2.txt")
    ap.add_argument("--label", default="it2")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    rules = open(a.rules).read()
    sha = hashlib.sha256(rules.encode()).hexdigest()[:12]
    tag = f"fwd_{a.label}_{a.month}"
    days = month_days(a.month)
    seen = sorted(set(days) & HOLDOUT)
    assert not seen, f"holdout days inside the month: {seen}"
    print(f"{tag}: rules sha {sha}, {len(days)} sessions {days[0]}..{days[-1]}, "
          f"workers {a.workers}, source: lake", flush=True)
    state = {"pending": None}

    def one(d: str):
        if PA.avail_mb() < PA.MEM_FLOOR_MB:
            time.sleep(60)
            if PA.avail_mb() < PA.MEM_FLOOR_MB:
                print(f"  {d} DEFERRED (memory)", flush=True)
                return None
        r = SW.run_day(d, rules, tag, resume=True, self_aware=True)
        e = sum(1 for c in r["calls"] if c.get("error"))
        print(f"  {d}  ${r['net_usd']:>+9,.2f}  {len(r['trades'])} tr  {e}/{len(r['calls'])} err", flush=True)
        return d

    if not a.report_only:
        marks = {max(1, round(len(days) * f)) for f in (0.25, 0.5, 0.75)}
        for pass_no in (1, 2, 3):
            todo = [d for d in days if not is_clean(tag, d)]
            if not todo:
                break
            print(f"pass {pass_no}: {len(todo)} day(s) to run", flush=True)
            done_n = len(days) - len(todo)
            with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
                for fut in cf.as_completed([ex.submit(one, d) for d in todo]):
                    try:
                        fut.result()
                    except Exception as e:
                        print(f"  worker error {type(e).__name__}: {e}", flush=True)
                        continue
                    done_n += 1
                    if done_n in marks:
                        m = summarise(tag, days)
                        if m:
                            say(f"IT2 on {a.month} (never seen) — {done_n}/{len(days)} sessions in: {line(m)}\n"
                                f"For scale, IT2 on the 10 holdout days: $620/day, 9/10 positive.", state)

    m = summarise(tag, days)
    dropped = [d for d in days if not is_clean(tag, d)]
    if not m:
        print("no clean days")
        return 1
    rep = {"tag": tag, "rules_sha": sha, "month": a.month, "sessions": len(days),
           "dropped_poisoned_or_missing": dropped, "it2_holdout_for_scale": IT2_HOLDOUT,
           "result": m, "generated": dt.datetime.now(dt.UTC).isoformat()}
    json.dump(rep, open(f"{OUT}/{tag}.json", "w"), indent=1)
    print("\n=== RESULT ===")
    print(line(m))
    print(f"SE of the mean ${m['se']}  ·  median hold {m['median_hold_min']}min  ·  premature exits {m['premature_pct']}%  ·  capture {m['capture_pct']}%")
    for k, v in m["week_totals"].items():
        print(f"  week of {k}: ${v:+,.0f}")
    if dropped:
        print(f"⚠ {len(dropped)} day(s) excluded (poisoned/missing): {', '.join(dropped)}")
    if not a.report_only:
        msg = (f"IT2 on {a.month} (a month it never saw) — FINISHED: {line(m)}\n"
               f"Weeks: " + ", ".join(f"{k[5:]} ${v:+,.0f}" for k, v in m["week_totals"].items()) +
               f"\nIT2 holdout for scale: $620/day, 9/10 positive.")
        while in_quiet_hours(dt.datetime.now(dt.UTC)):
            time.sleep(300)
        notify(msg, critical=False, mark=False, weekend_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
