"""E112 overnight chain (A0c / A1). Waits for the token-window reset, then:
  - finishes October v102 (10-24, 10-30, 10-31) and keeps the November v102 arm going (both resumable),
  - runs the rule arm (v102R1) ONE unseen week at a time, after that week's v102 days exist,
  - applies the A0c STOP/CONTINUE rule mechanically after each week; on STOP it halts (a revision needs a frozen R2),
  - runs the informational in-sample veto check once October is complete.
replay.py's own guards stop all calls 01:45Z..13:35Z and on 15 consecutive errors; this chain then exits and is re-launched later.

    nohup .venv/bin/python reports/recursive_loop/E112_code/night.py --start 22:36 > reports/e112/night.log 2>&1 &
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"
CODE = f"{GB}/reports/recursive_loop/E112_code"
OUT = f"{GB}/reports/e112"
R1 = f"{GB}/reports/recursive_loop/E112_R1.txt"
UTC = dt.timezone.utc
ENV = {**os.environ, "PYTHONPATH": "src"}
OCT_LEFT = ["2025-10-24", "2025-10-30", "2025-10-31"]
WEEKS = [["2025-11-03", "2025-11-04", "2025-11-05", "2025-11-06", "2025-11-07"],
         ["2025-11-10", "2025-11-11", "2025-11-12", "2025-11-13", "2025-11-14"],
         ["2025-11-17", "2025-11-18", "2025-11-19", "2025-11-20", "2025-11-21"],
         ["2025-11-24", "2025-11-25", "2025-11-26", "2025-11-27", "2025-11-28"]]


def log(m):
    print(f"[{dt.datetime.now(UTC):%H:%M:%SZ}] {m}", flush=True)


def live_hours():
    n = dt.datetime.now(UTC)
    return (n.hour, n.minute) >= (1, 45) and n.hour * 60 + n.minute < 13 * 60 + 35


def clean(arm, day):
    p = f"{OUT}/{arm}_{day}.json"
    if not os.path.exists(p):
        return False
    r = json.load(open(p))
    if r.get("skipped"):
        return True
    c = r.get("calls") or []
    return bool(c) and sum(1 for x in c if x.get("error")) / len(c) <= 0.10


def replay(arm_spec, days, workers, logname):
    cmd = [PY, f"{CODE}/replay.py", "--arm", arm_spec, "--days", ",".join(days), "--workers", str(workers)]
    return subprocess.Popen(cmd, cwd=GB, env=ENV, stdout=open(f"{OUT}/{logname}", "a"), stderr=subprocess.STDOUT)


def decide(week):
    """A0c: STOP if [rule worst day < v102 worst day AND rule <=-$1k entries > v102's] OR [v102 presses the rule arm did not take
    contained more winners than BAD (<=-$1,000 or MAE>=150pt) entries]. Days skipped as holidays are ignored."""
    b, r = {}, {}
    for d in week:
        for arm, dst in (("v102", b), ("v102R1", r)):
            x = json.load(open(f"{OUT}/{arm}_{d}.json"))
            if not x.get("skipped"):
                dst[d] = x
    days = sorted(set(b) & set(r))
    bw = min(b[d]["net_usd"] for d in days); rw = min(r[d]["net_usd"] for d in days)
    b1k = sum(p["pnl_usd"] <= -1000 for d in days for p in b[d]["presses"])
    r1k = sum(p["pnl_usd"] <= -1000 for d in days for p in r[d]["presses"])
    taken = {(d, p["decision_ts"]) for d in days for p in r[d]["presses"]}
    declined = [p for d in days for p in b[d]["presses"] if (d, p["decision_ts"]) not in taken]
    dw = sum(p["why"] == "TARGET_37.5" for p in declined)
    dbad = sum(p["pnl_usd"] <= -1000 or p["mae_pt"] >= 150 for p in declined)
    stop = (rw < bw and r1k > b1k) or dw > dbad
    s = {"week": week[0], "days": len(days), "v102_net": sum(b[d]["net_usd"] for d in days), "R1_net": sum(r[d]["net_usd"] for d in days),
         "v102_worst_day": bw, "R1_worst_day": rw, "v102_le1k": b1k, "R1_le1k": r1k, "v102_presses_not_taken": len(declined),
         "of_which_winners": dw, "of_which_bad": dbad, "decision": "STOP" if stop else "CONTINUE"}
    json.dump(s, open(f"{OUT}/decision_{week[0]}.json", "w"), indent=1)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="22:36", help="UTC HH:MM to begin (token-window reset)")
    a = ap.parse_args()
    h, m = map(int, a.start.split(":"))
    now = dt.datetime.now(UTC)
    t0 = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t0 > now:
        log(f"waiting until {t0:%H:%M}Z"); time.sleep((t0 - now).total_seconds())
    log("start")
    me = os.getpid()
    old = subprocess.run(["pgrep", "-f", "E112_code/replay.py"], capture_output=True, text=True).stdout.split()
    for pid in old:                                      # resumable: an unfinished day is simply re-run
        if int(pid) != me:
            subprocess.run(["kill", pid])
    if old:
        log(f"stopped {len(old)} earlier replay process(es) so no day runs twice"); time.sleep(20)
    bg = [replay("v102", [d for d in OCT_LEFT if not clean("v102", d)], 1, "oct_rest.log")] if any(not clean("v102", d) for d in OCT_LEFT) else []
    nov_all = [d for w in WEEKS for d in w]
    bg.append(replay("v102", nov_all, 1, "nov_v102.log"))
    veto_done = False
    for week in WEEKS:
        while not all(clean("v102", d) for d in week):          # the comparison days must exist (the v102 arm runs ahead)
            if live_hours():
                log("live hours - chain pauses; re-launch after 13:35Z"); return
            if not veto_done and all(clean("v102", d) for d in OCT_LEFT):
                subprocess.Popen([PY, f"{CODE}/vetocheck.py", "--rules", R1, "--days", ",".join(
                    sorted(f[5:15] for f in os.listdir(OUT) if f.startswith("v102_2025-10")))],
                    cwd=GB, env=ENV, stdout=open(f"{OUT}/vetocheck_R1.txt", "w"), stderr=subprocess.STDOUT)
                veto_done = True
            time.sleep(60)
        if all(clean("v102R1", d) for d in week):
            log(f"week {week[0]}: rule arm already done")
        else:
            log(f"week {week[0]}: running v102R1")
            p = replay(f"v102R1={R1}", week, 2, "rule_R1.log"); p.wait()
            if not all(clean("v102R1", d) for d in week):
                log(f"week {week[0]}: rule arm incomplete (live-hours guard or error abort) - chain exits"); return
        s = decide(week)
        log(f"week {week[0]} decision: {json.dumps(s)}")
        if s["decision"] == "STOP":
            log("STOP - R1 halted per A0c; a revision R2 must be written and frozen before the next unseen week"); return
    log("all November weeks done")
    for p in bg:
        p.wait()


if __name__ == "__main__":
    main()
