#!/usr/bin/env python3
"""Two-lot SCALE-OUT for the day rider: lot A claims early, lot B runs.

Operator, 2026-08-19: "we could do 2 lots. one claims $200 and one claims $300 or $350."

⚠ "ONE CLAIMS $200" IS AMBIGUOUS AND THE TWO READINGS DIFFER BY 2x. The rider holds 2 lots at
$2/pt each, so a level can mean:
    PER-LOT   lot A banks $200 of its OWN P&L  -> needs a 100pt move
    COMBINED  exit lot A when the whole position shows +$200 -> only a 50pt move
Both are modelled. Getting this wrong is the difference between a level hit on 38% of days and one
hit on 68%, so it is resolved with data rather than assumed.

⚠ Each lot pays its own $1.50 round trip. Two exits = $3.00 total, same as the single exit it
replaces — scaling out does not cost extra commission here, which is worth knowing.

⚠ MINUTE RESOLUTION. A level touched and lost inside one minute counts as filled. Optimistic at
tight targets; these are a RANKING tool.
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

VPP = 2.0          # $ per point PER LOT
FEE = 1.50         # per lot round trip


def run(sess, i, direction, entry, arm_atr, *, a_pt, b_pt, b_trail=True, stop_pt=None):
    """Lot A targets a_pt, lot B targets b_pt (or trails). stop_pt closes BOTH lots.

    ⚠ THE STOP IS CHECKED BEFORE THE TARGETS, on purpose. Inside one minute the order of a stop and
    a target is unknowable from OHLC, and assuming the target came first is exactly how an MFE
    measurement flatters itself. Booking the stop first is the conservative reading and the only one
    that cannot manufacture an edge.
    """
    from gazbot7.day_rider import FLAT_UTC_MIN, trail_level
    d = 1 if direction == "UP" else -1
    peak = entry
    a_done = b_done = None
    for b in sess[i:]:
        ts, hi, lo, cl = b
        mod = (ts % 86400) // 60
        fav_px = hi if d > 0 else lo
        fav_pt = (fav_px - entry) * d
        if mod >= FLAT_UTC_MIN:                      # hard flat closes whatever is left
            if a_done is None:
                a_done = ((cl - entry) * d, "CLOCK")
            if b_done is None:
                b_done = ((cl - entry) * d, "CLOCK")
            break
        # ★ STOP FIRST — see the docstring. adverse excursion this bar, in points.
        adv_pt = (entry - lo) * d if d > 0 else (hi - entry) * -d
        adv_pt = ((entry - lo) if d > 0 else (hi - entry))
        if stop_pt is not None and adv_pt >= stop_pt:
            if a_done is None:
                a_done = (-stop_pt, "STOP")
            if b_done is None:
                b_done = (-stop_pt, "STOP")
            break
        peak = max(peak, hi) if d > 0 else min(peak, lo)
        tr = trail_level(d, entry, peak, arm_atr)
        hit_tr = tr is not None and ((lo <= tr) if d > 0 else (hi >= tr))
        # lot A
        if a_done is None:
            if a_pt and fav_pt >= a_pt and not hit_tr:
                a_done = (a_pt, "TARGET")
            elif hit_tr:
                a_done = ((tr - entry) * d, "TRAIL")
        # lot B
        if b_done is None:
            if b_pt and fav_pt >= b_pt and not hit_tr:
                b_done = (b_pt, "TARGET")
            elif hit_tr and b_trail:
                b_done = ((tr - entry) * d, "TRAIL")
        if a_done and b_done:
            break
    if a_done is None:
        a_done = ((sess[-1][3] - entry) * d, "EOD")
    if b_done is None:
        b_done = ((sess[-1][3] - entry) * d, "EOD")
    pnl = (a_done[0] + b_done[0]) * VPP - 2 * FEE
    return pnl, a_done[1], b_done[1]


def main():
    from collections import Counter
    from rider_walk import sessions
    S = sessions()
    n = len(S)
    print(f"MNQ day rider scale-out — {n} sessions, {S[0][0]} .. {S[-1][0]}")
    print("  2 lots @ $2/pt · each pays $1.50 RT · lot targets in POINTS, shown both ways\n")

    def show(title, variants, stops=None):
        print(f"  === {title} ===")
        print(f"  {'lot A':>8} {'lot B':>10} {'net$':>10} {'$/day':>8} {'win%':>6} {'median':>8} "
              f"{'PF':>6}  exits(A)")
        for idx, (a_pt, b_pt, b_trail, lbl) in enumerate(variants):
            sp = stops[idx] if stops else None
            rows = [run(sess, i, dr, e, at, a_pt=a_pt, b_pt=b_pt, b_trail=b_trail, stop_pt=sp)
                    for (_d, sess, i, dr, e, at) in S]
            p = [r[0] for r in rows]
            w = [x for x in p if x > 0]
            gl = -sum(x for x in p if x <= 0)
            pf = (sum(w) / gl) if gl else float("inf")
            srt = sorted(p)
            c = Counter(r[1] for r in rows)
            print(f"  {lbl:>19} {sum(p):>10,.0f} {sum(p)/n:>8.1f} {100*len(w)/n:>5.1f}% "
                  f"{srt[n//2]:>8.1f} {pf:>6.2f}  {dict(c)}")
        print()

    # ★ THE HARD-STOP SWEEP on the best variant found: combined $200/$300 scale-out.
    # stop is in POINTS of adverse move; $ = pt x $4 across both lots.
    show("HARD STOP sweep — combined $200/$300 scale-out (50pt / 75pt targets)",
         [(50, 75, True, "no stop")] +
         [(50, 75, True, f"stop -${int(sp*4)}") for sp in (200, 150, 125, 100, 75, 50)],
         stops=[None, 200, 150, 125, 100, 75, 50])
    base = [run(sess, i, dr, e, at, a_pt=None, b_pt=None, b_trail=True)
            for (_d, sess, i, dr, e, at) in S]
    bp = [r[0] for r in base]
    print(f"  BASELINE trail-only both lots: net {sum(bp):>9,.0f}  $/day {sum(bp)/n:>7.1f}  "
          f"win {100*sum(1 for x in bp if x>0)/n:.1f}%")


if __name__ == "__main__":
    main()
