"""EXHAUSTION_SHORT REHAB — the exit grid, DECOUPLED.

The first grid swept the stop in ATR multiples and the target in R-multiples of that stop, so
"1.5xATR stop / 0.75R target" widens the stop AND the target together. That confounds the two
knobs and it is what produced the apparent cliff (0.5-1.0xATR flat and negative, then 1.5xATR
ten times better at one step). A jump like that at a single cell is exactly the curve-fit tell
the operator's own backtest discipline says to distrust.

So here both legs are in the SAME unit — multiples of the signal's entry ATR — and swept
independently. If the gate really wants a wider stop there will be a PLATEAU across neighbouring
cells, not one hot square.
"""
from __future__ import annotations

import collections
import json
import statistics

VPP, FEE = 2.0, 1.50
IN = "reports/friday_v7/sections/exh_signals.json"
OUT = "reports/friday_v7/sections/exh_exit_grid2.json"
STOPS = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5)
TGTS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)


def load():
    S = [s for s in json.load(open(IN))["signals"] if s["path_n"] > 0 and s["atr"]]
    return sorted(S, key=lambda s: s["ts_ms"])


def run(s, k_stop, k_tgt, cap_ms):
    e, atr = s["entry"], s["atr"]
    stop, tgt = e + atr * k_stop, e - atr * k_tgt
    for t, px in s["path"]:
        if t < 0:
            continue
        if px >= stop:
            return (e - stop) * VPP - FEE, "STOP"
        if px <= tgt:
            return (e - tgt) * VPP - FEE, "TARGET"
        if t >= cap_ms:
            return (e - px) * VPP - FEE, "TIME"
    last = [px for t, px in s["path"] if t >= 0]
    return ((e - last[-1]) * VPP - FEE, "TIME") if last else None


def score(S, k_stop, k_tgt, cap_ms=900_000):
    per, ex = [], collections.Counter()
    for s in S:
        r = run(s, k_stop, k_tgt, cap_ms)
        if r:
            per.append((s, r[0] * s["n_legs"]))
            ex[r[1]] += 1
    net = sum(p for _, p in per)
    days = collections.defaultdict(float)
    for s, p in per:
        days[s["date"]] += p
    best3 = sorted((p for _, p in per), reverse=True)[:3]
    return {"stop_k": k_stop, "tgt_k": k_tgt, "n": len(per), "net": round(net, 2),
            "per_trade": round(net / len(per), 2) if per else 0,
            "win_pct": round(100.0 * sum(1 for _, p in per if p > 0) / len(per), 1) if per else 0,
            "time_exits": ex["TIME"], "exits": dict(ex),
            "lodo_worst": round(min(net - v for v in days.values()), 2) if days else 0,
            "strip3": round(net - sum(best3), 2),
            "days_green": sum(1 for v in days.values() if v > 0), "days": len(days),
            "worst_day": round(min(days.values()), 2) if days else 0}


def main() -> None:
    S = load()
    print(f"n={len(S)} signals, live net ${sum(s['pnl'] for s in S):.2f}, "
          f"median entry ATR {statistics.median([s['atr'] for s in S]):.1f}pt")
    holds = [(s["closed_ms"] - s["ts_ms"]) / 60000.0 for s in S]
    holds.sort()
    print(f"LIVE hold time (min): median {statistics.median(holds):.1f}  p75 {holds[int(.75*len(holds))]:.1f}  "
          f"p90 {holds[int(.90*len(holds))]:.1f}  max {holds[-1]:.1f}  "
          f"— share over the 15-min tape window: {100.0*sum(1 for h in holds if h>15)/len(holds):.0f}%\n")

    cells = [score(S, k, m) for k in STOPS for m in TGTS]
    json.dump({"cells": cells, "live_net": round(sum(s["pnl"] for s in S), 2), "n": len(S)},
              open(OUT, "w"), indent=1)

    print("NET $ — stop (rows, xATR) vs target (cols, xATR), 2 lots, 15-min outer cap")
    print(f"{'stop\\tgt':10s}" + "".join(f"{m:>10.2f}" for m in TGTS))
    for k in STOPS:
        row = f"{k:<10.2f}"
        for m in TGTS:
            c = next(c for c in cells if c["stop_k"] == k and c["tgt_k"] == m)
            row += f"{c['net']:10.0f}"
        print(row)
    print("\nTIME-exits (how many of the 87 ran out the 15-min tape window rather than hitting a level)")
    print(f"{'stop\\tgt':10s}" + "".join(f"{m:>10.2f}" for m in TGTS))
    for k in STOPS:
        row = f"{k:<10.2f}"
        for m in TGTS:
            c = next(c for c in cells if c["stop_k"] == k and c["tgt_k"] == m)
            row += f"{c['time_exits']:10d}"
        print(row)

    top = sorted(cells, key=lambda c: -c["net"])[:12]
    print("\nTOP 12 cells with robustness:")
    print(f"{'stop':>6s} {'tgt':>6s} {'net$':>9s} {'$/sig':>7s} {'win%':>6s} {'TIME':>5s} "
          f"{'LODOworst':>10s} {'strip3':>9s} {'worstday':>9s} {'gdays':>7s}")
    for c in top:
        print(f"{c['stop_k']:6.2f} {c['tgt_k']:6.2f} {c['net']:9.2f} {c['per_trade']:7.2f} "
              f"{c['win_pct']:5.1f}% {c['time_exits']:5d} {c['lodo_worst']:10.2f} {c['strip3']:9.2f} "
              f"{c['worst_day']:9.2f} {c['days_green']:3d}/{c['days']:<3d}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
