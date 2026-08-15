"""EXHAUSTION_SHORT REHAB — the EXIT grid on the gate's OWN live entries.

Why this exists. The 2026-07-25 rehab revived this gate on ONE argument: a snap-back fade
needs a FIXED 8pt stop / 12pt target because "ATR-2R was too wide for a snap-back", and the
SlotSpec still says so — `exit="fixed", fixed_stop_pt=8.0, fixed_target_pt=12.0`. The stopped
trades say otherwise: the median stop is 20.1pt = 0.98 x ATR. So the exit the gate was
rehabilitated ON is not the exit it is TRADING. This grid asks what the right one is, using
the real fills as entries and the real 250ms tape as the referee.

Every cell is 2 lots (the gate's live base_size), $2.00/pt, $1.50 per round trip per lot, and
is scored on the SAME 87 tape-backed signals as the baseline so the comparison is like-for-like.
"""
from __future__ import annotations

import collections
import json
import statistics

VPP, FEE = 2.0, 1.50          # ⚠ MNQ $/pt and $ per ROUND TRIP per lot. Not 5.0/2.0.
IN = "reports/friday_v7/sections/exh_signals.json"
OUT = "reports/friday_v7/sections/exh_exit_grid.json"


def load():
    S = json.load(open(IN))["signals"]
    S = [s for s in S if s["path_n"] > 0]
    for s in S:
        s["stopped"] = "STOP" in s["reasons"]
    return sorted(S, key=lambda s: s["ts_ms"])


def run_one(s, stop_pt, tgt_pt, hold_s):
    """One SHORT signal under a mechanical stop/target/time exit, on its own tick path.
    stop_pt/tgt_pt may be ('atr', k) to mean k x entry ATR."""
    e = s["entry"]
    sp = s["atr"] * stop_pt[1] if isinstance(stop_pt, tuple) else stop_pt
    tp = (sp * tgt_pt[1] if tgt_pt[0] == "r" else s["atr"] * tgt_pt[1]) if isinstance(tgt_pt, tuple) else tgt_pt
    if not sp or not tp:
        return None
    stop, tgt = e + sp, e - tp
    for t, px in s["path"]:
        if t < 0:
            continue
        if px >= stop:
            return (e - stop) * VPP - FEE, "STOP"
        if px <= tgt:
            return (e - tgt) * VPP - FEE, "TARGET"
        if hold_s and t >= hold_s * 1000:
            return (e - px) * VPP - FEE, "TIME"
    last = [px for t, px in s["path"] if t >= 0]
    return ((e - last[-1]) * VPP - FEE, "END") if last else None


def score(S, stop_pt, tgt_pt, hold_s, label):
    per, reasons = [], collections.Counter()
    for s in S:
        r = run_one(s, stop_pt, tgt_pt, hold_s)
        if r is None:
            continue
        per.append((s, r[0] * s["n_legs"]))
        reasons[r[1]] += 1
    net = sum(p for _, p in per)
    wins = [p for _, p in per if p > 0]
    days = collections.defaultdict(float)
    for s, p in per:
        days[s["date"]] += p
    # leave-one-day-out: the worst fold is the number that matters, not the total
    lodo = sorted(round(net - v, 2) for v in days.values())
    best3 = sorted((p for _, p in per), reverse=True)[:3]
    return {
        "label": label, "n": len(per), "net": round(net, 2),
        "per_trade": round(net / len(per), 2) if per else 0,
        "win_pct": round(100.0 * len(wins) / len(per), 1) if per else 0,
        "exits": dict(reasons),
        "days_green": sum(1 for v in days.values() if v > 0),
        "days": len(days),
        "worst_day": round(min(days.values()), 2) if days else 0,
        "lodo_worst": lodo[0] if lodo else 0,
        "strip3": round(net - sum(best3), 2),
        "by_day": {k: round(v, 2) for k, v in sorted(days.items())},
    }


def main() -> None:
    S = load()
    live = round(sum(s["pnl"] for s in S), 2)
    print(f"tape-backed signals n={len(S)}  LIVE net ${live:.2f}  "
          f"(win {100.0*sum(1 for s in S if s['pnl']>0)/len(S):.1f}%)")
    print(f"median entry ATR {statistics.median([s['atr'] for s in S if s['atr']]):.1f}pt\n")

    cells = []
    # (a) the DESIGN the gate was revived on, and its neighbourhood
    for sp in (4, 6, 8, 10, 12, 14, 16, 20):
        for tp in (6, 8, 10, 12, 16, 20, 24):
            for hold in (120, 300, 0):
                cells.append(score(S, sp, tp, hold, f"stop {sp}pt / target {tp}pt / hold {hold or 'none'}"))
    # (b) what it is ACTUALLY trading — an ATR stop with an R target
    for k in (0.5, 0.75, 1.0, 1.5):
        for r in (0.75, 1.0, 1.5, 2.0):
            cells.append(score(S, ("atr", k), ("r", r), 0, f"stop {k}xATR / target {r}R / no cap"))

    cells.sort(key=lambda c: -c["net"])
    json.dump({"live_net": live, "n": len(S), "cells": cells}, open(OUT, "w"), indent=1)

    print("TOP 20 exit cells (2 lots, tick-honest):")
    print(f"{'exit rule':44s} {'net$':>9s} {'$/sig':>7s} {'win%':>6s} {'LODOworst':>10s} {'strip3':>8s} {'gdays':>7s}")
    for c in cells[:20]:
        print(f"{c['label']:44s} {c['net']:9.2f} {c['per_trade']:7.2f} {c['win_pct']:5.1f}% "
              f"{c['lodo_worst']:10.2f} {c['strip3']:8.2f} {c['days_green']:3d}/{c['days']:<3d}")
    print("\nREFERENCE cells:")
    for want in ("stop 8pt / target 12pt / hold 120", "stop 8pt / target 12pt / hold none",
                 "stop 1.0xATR / target 0.75R / no cap", "stop 1.0xATR / target 1.5R / no cap"):
        for c in cells:
            if c["label"] == want:
                print(f"{c['label']:44s} {c['net']:9.2f} {c['per_trade']:7.2f} {c['win_pct']:5.1f}% "
                      f"{c['lodo_worst']:10.2f} {c['strip3']:8.2f} {c['days_green']:3d}/{c['days']:<3d} {c['exits']}")
    print(f"\nLIVE as traded                               {live:9.2f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
