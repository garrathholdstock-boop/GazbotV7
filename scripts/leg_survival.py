#!/usr/bin/env python3
"""LEG SURVIVAL — what to say at 15 minutes, at 30, at 60, and when we can honestly say it.

Operator, 2026-09-14: "you can give earlier alerts and say Down Grind 15 minutes... then down grind
30 minutes etc. you can think about it and come up with a system."

★ THE DESIGN. One alert that waits for certainty is useless: a 90-minute detection window lands after
the move. So this ESCALATES - an early, deliberately uncertain notice, upgraded as the leg persists,
with the statistics RECOMPUTED AT EACH MILESTONE. The number that belongs in a message at minute 30
is not "legs run a median 46 minutes" (that is the unconditional figure, and most of those legs never
reached 30). It is "of legs that reached 30 minutes, the median ran another N".

★ THE LEG DEFINITION IS THE RETRACE, because that is how a move actually ends to a human eye: it
lives while price keeps making new extremes and dies when it gives back K x ATR from the best point.
No fixed window, so no fragmentation, and it can be evaluated in real time - at any minute you know
whether the leg is still alive without seeing the future.

⚠ DESCRIPTIVE ONLY. All four tape states measured 49-50% forward. This says what legs like this one
have HISTORICALLY done, as a reference class. It forecasts nothing.
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import numpy as np, pandas as pd
from tunnel_fit_mgc import front_month_minutes, true_range

MILES = (15, 30, 45, 60, 90, 120, 180)


def legs(symbol="MNQ", k_retrace=1.0, min_start=8):
    bars, rolls = front_month_minutes(verbose=False, symbol=symbol)
    trs = true_range(bars, rolls)
    cl = np.array([b["close"] for b in bars], float)
    ts = np.array([b["m"] for b in bars], np.int64)
    tr = np.array([t if t is not None else np.nan for t in trs], float)
    atr = pd.Series(tr).rolling(14, min_periods=5).mean().values
    n = len(cl)
    out, i = [], 20
    while i < n - 2:
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            i += 1; continue
        # A leg BEGINS when the last `min_start` minutes have moved >= 1 ATR in one direction
        mv = cl[i] - cl[i - min_start]
        if abs(mv) < a:
            i += 1; continue
        sgn = 1 if mv > 0 else -1
        start = i - min_start
        ext = cl[i]; j = i
        while j + 1 < n and ts[j + 1] - ts[start] < 86400:
            j += 1
            px = cl[j]
            if sgn * (px - ext) > 0:
                ext = px
            elif sgn * (ext - px) >= k_retrace * a:      # gave back K x ATR from the extreme
                break
        mins = j - start
        if mins >= 10:
            path = np.abs(np.diff(cl[start:j + 1])).sum()
            out.append({"start": start, "mins": mins, "dir": "UP" if sgn > 0 else "DOWN",
                        "travel": sgn * (ext - cl[start]), "atr": a,
                        "er": abs(ext - cl[start]) / max(path, 1e-9),
                        "hour": int((ts[start] % 86400) // 3600)})
        i = j + 1
    return pd.DataFrame(out), len(set(ts // 86400))


def main():
    for k in (0.75, 1.0, 1.5):
        e, nd = legs(k_retrace=k)
        print(f"\n{'='*78}\nLEG = dies on a {k:g}xATR retrace from its extreme · {len(e):,} legs · "
              f"{len(e)/nd:.1f} per session · {nd} sessions")
        print(f"  unconditional: median {e.mins.median():.0f} min / {e.travel.median():.0f}pt · "
              f"p90 {e.mins.quantile(.9):.0f} min / {e.travel.quantile(.9):.0f}pt · "
              f"max {e.mins.max():.0f} min / {e.travel.max():.0f}pt")
        if k != 1.0:
            continue
        print(f"\n  ★ THE ESCALATION TABLE — what is TRUE to say at each milestone")
        print(f"{'at minute':>10}{'still alive':>13}{'% of all legs':>15}{'median MORE':>13}"
              f"{'p75 more':>10}{'median more pt':>16}{'dies in 15m':>13}")
        for m in MILES:
            alive = e[e.mins >= m]
            if len(alive) < 30:
                continue
            more = alive.mins - m
            # travel already banked by minute m is unknown per-leg; use the rate as the estimator
            rate = alive.travel / alive.mins
            more_pt = more * rate
            dies = (alive.mins < m + 15).mean()
            print(f"{m:>9}m{len(alive):>13,}{100*len(alive)/len(e):>14.0f}%{more.median():>12.0f}m"
                  f"{more.quantile(.75):>9.0f}m{more_pt.median():>15.0f}pt{100*dies:>12.0f}%")
        print(f"\n  ★ DETECTION LAG: a leg is first flagged {8} minutes in (>=1 ATR over 8 min),")
        print(f"    so the 15-minute milestone is reached ~7 minutes after the first notice.")
        print(f"  ★ AND THE HONEST HALF: of every leg flagged at the start, "
              f"{100*(e.mins < 30).mean():.0f}% never reach 30 minutes.")
        print(f"\n  by direction:")
        for d, g in e.groupby("dir"):
            print(f"    {d:<5} n={len(g):>5}  median {g.mins.median():>3.0f}m / "
                  f"{g.travel.median():>5.1f}pt   p90 {g.mins.quantile(.9):>3.0f}m / "
                  f"{g.travel.quantile(.9):>5.0f}pt")


if __name__ == "__main__":
    raise SystemExit(main())
