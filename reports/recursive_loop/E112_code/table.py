"""E112 running table: one row per finished day, per arm, grouped by month. Read-only.
    .venv/bin/python reports/recursive_loop/E112_code/table.py
"""
import glob
import json
import os
import collections

OUT = "/home/alphabot/gazbot7/reports/e112"
rows = collections.defaultdict(list)
for f in sorted(glob.glob(f"{OUT}/*_20??-??-??.json")):
    arm, day = os.path.basename(f)[:-5].rsplit("_", 1)
    r = json.load(open(f))
    if r.get("skipped"):
        rows[(day[:7], arm)].append((day, None, r["skipped"])); continue
    P = r["presses"]
    if r["calls"] and r["errors"] / len(r["calls"]) > 0.10:
        rows[(day[:7], arm)].append((day, None, f"POISONED ({r['errors']}/{len(r['calls'])} errored calls) - re-running, not counted")); continue
    rows[(day[:7], arm)].append((day, {
        "n": len(P), "w": sum(p["why"] == "TARGET_37.5" for p in P), "l": sum(p["why"] != "TARGET_37.5" for p in P),
        "net": r["net_usd"], "worst": min((p["pnl_usd"] for p in P), default=0), "mae": max((p["mae_pt"] for p in P), default=0),
        "lock": "Y" if r.get("lock") else "", "err": r["errors"], "calls": len(r["calls"])}, None))
for (mon, arm), rs in sorted(rows.items()):
    print(f"\n{mon}  arm {arm}")
    print(f"  {'day':10} {'entries':>7} {'wins':>5} {'losers':>6} {'net $':>8} {'worst entry':>12} {'max MAE':>8} {'lock':>4} {'cum $':>8}")
    cum, days, pos, tot = 0, 0, 0, collections.Counter()
    for day, s, why in rs:
        if s is None:
            print(f"  {day:10}  skipped: {why}"); continue
        cum += s["net"]; days += 1; pos += s["net"] > 0
        tot.update({k: s[k] for k in ("n", "w", "l")}); tot["le1k"] += s["worst"] <= -1000
        print(f"  {day:10} {s['n']:>7} {s['w']:>5} {s['l']:>6} {s['net']:>+8,.0f} {s['worst']:>+12,.0f} {s['mae']:>8.0f} {s['lock']:>4} {cum:>+8,.0f}")
    nets = [s["net"] for _, s, _ in rs if s]
    print(f"  {'TOTAL':10} {tot['n']:>7} {tot['w']:>5} {tot['l']:>6} {cum:>+8,.0f}   days {days}, positive {pos}, worst day {min(nets, default=0):+,.0f},"
          f" $/day {cum / max(days, 1):+,.0f}")
