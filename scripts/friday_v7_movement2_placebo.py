#!/usr/bin/env python3
"""MOVEMENT 2 — the random-entry control.

The kill test for anything that looked positive: if you had simply shown up at a RANDOM second
inside the same 10-minute pre-ignition window, in the run's own direction, with the same gate's
exits and the same costs — what would that have paid? Anything a gate earns has to beat this.
Pool: every 10th second of every sat-out run, priced on the real quote path, per gate lot-pair.
"""
import json
import random
import sqlite3
from collections import defaultdict

LAB = "/home/alphabot/gazbot7/scripts/friday_v7_movement2_lab.py"
exec(open(LAB).read().split("def main()")[0])   # noqa: S102 — shared engine

STEP = 10           # sample every 10th decision second
DRAWS = 2000        # bootstrap draws


def main():
    runs = load_runs()
    sat = [r for r in runs if r["us"] == "sat out"]
    specs = live_specs()
    con = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    con.execute("PRAGMA cache_size=-200000")
    pool = defaultdict(list)          # gate -> [net$ of the A+B pair at a random second]
    for n, r in enumerate(sat, 1):
        t1 = r["ts"]; t0 = t1 - PRE_S
        b5, tk, bk = load_window(con, t0, t1)
        snaps = build_snaps(t0, t1, b5, tk, bk)
        if not snaps:
            continue
        quotes = load_quotes(con, t0 * 1000, (t1 + MAX_HOLD_S + 600) * 1000)
        want = "LONG" if r["dir"] == "UP" else "SHORT"
        got = 0
        for g, (spec, lots) in specs.items():
            tag = g if spec.side == want else g + "|AGAINST"
            for s in snaps[::STEP]:
                i0 = _lower(quotes, s.ms)
                flat = session_flat_ms(s.ms)
                tot = 0.0
                ok = False
                for lot in lots:
                    t = reprice(lot, spec.side, s.f.atr, quotes, i0, flat)
                    if t:
                        tot += t["net"]; ok = True
                if ok:
                    pool[tag].append(tot)
                    got += 1
        print(f"[{n}/{len(sat)}] {r['tm']} samples={got}", flush=True)
    out = {}
    rng = random.Random(20260828)
    for g, v in pool.items():
        out[g] = {"n": len(v), "mean_per_fire": sum(v) / len(v),
                  "pct_positive": 100 * sum(1 for x in v if x > 0) / len(v),
                  "pool": v}
    with open("/home/alphabot/gazbot7/reports/friday_v7/sections/m2_placebo2.json", "w") as f:
        json.dump(out, f)
    for g, d in sorted(out.items()):
        print(f"{g:20s} n={d['n']:5d} mean per fire (A+B) ${d['mean_per_fire']:+8.2f} "
              f"positive {d['pct_positive']:.1f}%")


if __name__ == "__main__":
    main()
