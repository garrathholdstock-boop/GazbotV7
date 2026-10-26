"""E118 afternoon chain: three target arms on the live v1.03 setup, one unseen week at a time (13:35Z-20:45Z only). Read-only on the desk.
    (PYTHONPATH=src setsid nohup .venv/bin/python reports/recursive_loop/E112_code/e118_chain.py --start 13:36 >> reports/e112/e118_chain.log 2>&1 &)
"""
import argparse, datetime as dt, json, os, subprocess, time, collections
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/e112"; PY = f"{GB}/.venv/bin/python"
ARMS = tuple(os.environ.get("E118_ARMS", "v103,v103T30,v103D,v103F,v103B,v103C").split(","))   # E119 arms ride the same weeks
WEEKS = [["2025-11-24", "2025-11-25", "2025-11-26", "2025-11-27", "2025-11-28"], ["2025-12-01", "2025-12-02", "2025-12-03", "2025-12-04", "2025-12-05"],
         ["2025-12-08", "2025-12-09", "2025-12-10", "2025-12-11", "2025-12-12"], ["2025-12-15", "2025-12-16", "2025-12-17", "2025-12-18", "2025-12-19"],
         ["2025-12-22", "2025-12-23", "2025-12-24", "2025-12-25", "2025-12-26"], ["2025-12-29", "2025-12-30", "2025-12-31", "2026-01-01", "2026-01-02"]]
UTC = dt.timezone.utc
def log(m): print(f"[{dt.datetime.now(UTC):%H:%M:%SZ}] {m}", flush=True)
def window_ok():
    n = dt.datetime.now(UTC); mm = n.hour * 60 + n.minute
    if os.environ.get("E118_ALLOW_LIVE_HOURS") == "1":
        return mm < 20 * 60 + 45 and mm >= 2 * 60                # operator: also during live hours (guarded in replay.py), never 20:45Z-02:00Z
    return 13 * 60 + 35 <= mm < 20 * 60 + 45
def rec(arm, d):
    p = f"{OUT}/{arm}_{d}.json"
    if not os.path.exists(p): return None
    r = json.load(open(p)); c = r.get("calls") or []
    if r.get("skipped"): return "skip"
    return r if c and sum(1 for x in c if x.get("error")) / len(c) <= 0.10 else None
def table(weeks_done):
    L = [f"E118 - target arms on the live v1.03 setup, unseen weeks (written {dt.datetime.now(UTC):%Y-%m-%d %H:%MZ})"]
    cum = {a: collections.Counter() for a in ARMS}; cumd = {a: [] for a in ARMS}
    for w in weeks_done:
        days = [d for d in w if all(isinstance(rec(a, d), dict) for a in ARMS)]
        L.append(f"\nWEEK {w[0]}  ({len(days)} paired sessions)")
        L.append(f"  {'arm':9}{'total $':>9}{'days+':>7}{'worst day':>10}{'d<=-2k':>7}{'entries':>8}{'wins':>6}{'<=-1k':>6}   per day")
        for a in ARMS:
            rs = [rec(a, d) for d in days]; nets = [r["net_usd"] for r in rs]; P = [p for r in rs for p in r["presses"]]
            cumd[a] += nets; cum[a].update({"e": len(P), "w": sum(p["why"].startswith("TARGET") for p in P), "l1": sum(p["pnl_usd"] <= -1000 for p in P)})
            L.append(f"  {a:9}{sum(nets):>9,.0f}{sum(n > 0 for n in nets):>4}/{len(nets)}{min(nets, default=0):>10,.0f}{sum(n <= -2000 for n in nets):>7}{len(P):>8}"
                     f"{cum[a]['w'] - (cum[a]['w'] - sum(p['why'].startswith('TARGET') for p in P)):>6}{sum(p['pnl_usd'] <= -1000 for p in P):>6}   " + " ".join(f"{n:+.0f}" for n in nets))
    L.append("\nCUMULATIVE")
    for a in ARMS:
        n = cumd[a]
        if n:
            L.append(f"  {a:9} total {sum(n):>+8,.0f}  $/day {sum(n)/len(n):>+5.0f}  days+ {sum(x > 0 for x in n)}/{len(n)}  worst day {min(n):+,.0f}  d<=-2k {sum(x <= -2000 for x in n)}"
                     f"  entries {cum[a]['e']}  wins {cum[a]['w']}  <=-1k {cum[a]['l1']}")
    open(f"{OUT}/E118_weeks.txt", "w").write("\n".join(L) + "\n")
    return "\n".join(L)
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--start", default="13:36"); a = ap.parse_args()
    h, m = map(int, a.start.split(":")); now = dt.datetime.now(UTC); t0 = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t0 > now: log(f"waiting until {t0:%H:%M}Z"); time.sleep((t0 - now).total_seconds())
    done = []
    for w in WEEKS:
        if not window_ok(): log("outside 13:35-20:45Z - chain stops; re-launch tomorrow afternoon (resumable)"); break
        if not all(rec(x, d) is not None for x in ARMS for d in w):
            log(f"week {w[0]}: running {ARMS}")
            subprocess.run([PY, f"{GB}/reports/recursive_loop/E112_code/replay.py"] + sum([["--arm", x] for x in ARMS], []) + ["--days", ",".join(w), "--workers", "3"],
                           cwd=GB, env={**os.environ, "PYTHONPATH": "src", **({"E112_MAX_CALLS": str(800 * len(ARMS))} if os.environ.get("E112_MAX_CALLS") else {})},
                           stdout=open(f"{OUT}/e118_replay.log", "a"), stderr=subprocess.STDOUT)
        if not all(rec(x, d) is not None for x in ARMS for d in w):
            log(f"week {w[0]}: incomplete (window guard or error abort) - chain stops"); break
        done.append(w); log("\n" + table(done))
    if done: table(done)
if __name__ == "__main__":
    main()
