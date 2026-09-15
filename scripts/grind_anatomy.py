#!/usr/bin/env python3
"""THE ANATOMY OF LEGS AND TUNNELS — on the DISPLACEMENT axis, where the operator's words live.

★★★ THIS FILE REPLACES A WRONG MEASUREMENT. The first version classified the tape by TRUE RANGE
(quiet vs loud) and reported angled grinds with a median life of 8 minutes and 5 points. Both the
axis and the numbers were wrong, and the operator caught it three separate ways:
  · his "persistent downward grind" of 2026-09-14 ran at 1.2-1.6x baseline true range, so the
    volatility taxonomy filed it as a THRUST;
  · a 15-minute efficiency window chopped that same 2h40m move into six fragments;
  · and on 2026-09-15 he said "its back in a tunnel" while true range read 1.24x baseline - the tape
    had 38 points of range and +3.5 points of PROGRESS over 30 minutes.
★ A TUNNEL IS NOT QUIET, IT IS DIRECTIONLESS. It can thrash and still be a tunnel because it ends
where it started. Once that is said, the whole taxonomy collapses to ONE axis - net displacement
per minute - and volatility drops out entirely:  ~0 -> tunnel · slow -> grind · fast -> jump.

THE DEFINITION, identical to the live leg_watch so the anatomy describes what the watcher sees:
a leg OPENS on 1 x ATR of displacement in 8 minutes and DIES on a 3 x ATR retrace from its extreme.
No window, so no fragmentation; no volatility term, so nothing to mis-classify. A TUNNEL is simply
the gap between one leg dying and the next one opening.
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import numpy as np, pandas as pd
from leg_survival import legs


def main():
    e, nd = legs(symbol="MNQ", k_retrace=3.0)
    e = e[e.travel >= 3 * e.atr].copy()          # a leg worth the name
    e["rate_atr"] = (e.travel / e.mins) / e.atr  # ATR per minute — scale-free across eras
    print(f"MNQ · {nd} sessions · {len(e):,} legs ({len(e)/nd:.1f}/session)\n")

    print("CLASSIFIED BY RATE OF DISPLACEMENT — his one axis, in ATR per minute")
    e["kind"] = pd.cut(e.rate_atr, [0, 0.05, 0.15, 99],
                       labels=["SLOW GRIND", "GRIND", "JUMP"])
    print(f"{'kind':<13}{'ATR/min':>14}{'n':>7}{'/sess':>7}{'med DUR':>9}{'med TRAVEL':>12}"
          f"{'p90 dur':>9}{'p90 travel':>12}{'med pt/min':>12}")
    for k, g in e.groupby("kind", observed=True):
        print(f"{str(k):<13}{g.rate_atr.min():>6.3f}-{g.rate_atr.max():<7.3f}{len(g):>7}"
              f"{len(g)/nd:>7.1f}{g.mins.median():>8.0f}m{g.travel.median():>11.0f}pt"
              f"{g.mins.quantile(.9):>8.0f}m{g.travel.quantile(.9):>11.0f}pt"
              f"{(g.travel/g.mins).median():>12.2f}")

    print(f"\nDURATION, all legs")
    q = e.mins.quantile([.1, .25, .5, .75, .9])
    print(f"  p10 {q[.1]:>4.0f}  p25 {q[.25]:>4.0f}  MED {q[.5]:>4.0f}  p75 {q[.75]:>4.0f}  "
          f"p90 {q[.9]:>4.0f}  MAX {e.mins.max():>5.0f} min")
    t = e.travel.quantile([.1, .25, .5, .75, .9])
    print(f"TRAVEL")
    print(f"  p10 {t[.1]:>4.0f}  p25 {t[.25]:>4.0f}  MED {t[.5]:>4.0f}  p75 {t[.75]:>4.0f}  "
          f"p90 {t[.9]:>4.0f}  MAX {e.travel.max():>5.0f} pt")

    # ── THE TUNNEL is the gap between legs: where price goes nowhere ──────────
    e = e.sort_values("start")
    gaps = (e.start.values[1:] - (e.start.values[:-1] + e.mins.values[:-1]))
    gaps = gaps[(gaps > 0) & (gaps < 600)]
    print(f"\nTUNNELS — the gap between one leg dying and the next opening  (n={len(gaps):,})")
    gq = np.percentile(gaps, [10, 25, 50, 75, 90])
    print(f"  p10 {gq[0]:>4.0f}  p25 {gq[1]:>4.0f}  MED {gq[2]:>4.0f}  p75 {gq[3]:>4.0f}  "
          f"p90 {gq[4]:>4.0f}  MAX {gaps.max():>5.0f} min")
    print(f"  the tape is IN a leg {100*e.mins.sum()/(e.mins.sum()+gaps.sum()):.0f}% of the time, "
          f"in a tunnel {100*gaps.sum()/(e.mins.sum()+gaps.sum()):.0f}%")

    print(f"\nUP vs DOWN")
    for d, g in e.groupby("dir"):
        print(f"  {d:<5} n={len(g):>5}  med {g.mins.median():>3.0f}m / {g.travel.median():>4.0f}pt"
              f"   p90 {g.mins.quantile(.9):>3.0f}m / {g.travel.quantile(.9):>4.0f}pt")

    print(f"\n⚠ VOLATILITY DOES NOT APPEAR ANYWHERE IN THIS FILE. That is the fix.")
    e.to_csv("/home/alphabot/gazbot7/reports/leg_anatomy_MNQ.csv", index=False)
    print(f"   -> reports/leg_anatomy_MNQ.csv")


if __name__ == "__main__":
    raise SystemExit(main())
