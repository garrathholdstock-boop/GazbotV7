#!/usr/bin/env python3
"""How far GREEN does the day rider get — the money that is actually claimable.

Operator, 2026-08-19: "it doesnt need to go in a direction and stay there. as i can claim profit.
what % of days go past $200 green. $300 green. $400 green. because thats the money we can make."

Correct reframing: persistence to the close is irrelevant if you exit on the way. What matters is
maximum FAVOURABLE excursion — how far green it gets while you can still act.

⚠⚠ THIS IS THE MFE TRAP, AND IT IS THIS DESK'S MOST EXPENSIVE ONE. "% of trades that reached N"
ignores whether something ELSE happened first. Measured that way it once turned a 29% win rate into
78% and shipped a losing config live ([[mfe-is-not-a-win-rate]]). So this reports THREE numbers, and
only the third is money:
    RAW MFE      peak green at any point in the session      <- the flattering number
    CLAIMABLE    peak green BEFORE the trail or clock exits   <- what you could actually have taken
    HEAT FIRST   of those, how many went RED past -$X first   <- what you had to sit through
It also reports TIME-TO-REACH, because a level hit at 19:50 is not one you were watching for.
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

DOLLARS_PER_PT = 4.0        # MNQ $2/pt x 2 lots
LEVELS = (100, 200, 300, 400, 500, 750, 1000)


def walk(sess, i, direction, entry, arm_atr):
    """Minute-by-minute after entry. Returns the excursion profile up to the real exit."""
    from gazbot7.day_rider import FLAT_UTC_MIN, trail_level
    d = 1 if direction == "UP" else -1
    peak = entry
    t0 = (sess[i - 1][0] % 86400) // 60
    raw_mfe = 0.0
    claim_mfe = 0.0
    mae = 0.0
    hit_time: dict = {}
    heat_before: dict = {}
    exited = False
    for b in sess[i:]:
        ts, hi, lo, cl = b
        mod = (ts % 86400) // 60
        fav = ((hi - entry) if d > 0 else (entry - lo)) * DOLLARS_PER_PT
        adv = ((entry - lo) if d > 0 else (hi - entry)) * DOLLARS_PER_PT
        raw_mfe = max(raw_mfe, fav)
        if not exited:
            mae = max(mae, adv)
            claim_mfe = max(claim_mfe, fav)
            for L in LEVELS:
                if L not in hit_time and fav >= L:
                    hit_time[L] = mod - t0
                    heat_before[L] = mae
        # did the trade end this bar?
        if not exited:
            if mod >= FLAT_UTC_MIN:
                exited = True
            else:
                peak = max(peak, hi) if d > 0 else min(peak, lo)
                tr = trail_level(d, entry, peak, arm_atr)
                if tr is not None and ((lo <= tr) if d > 0 else (hi >= tr)):
                    exited = True
    return {"raw": raw_mfe, "claim": claim_mfe, "mae": mae,
            "hit": hit_time, "heat": heat_before}


def main():
    from rider_walk import sessions
    S = sessions()
    rows = [walk(sess, i, dr, e, a) for (_d, sess, i, dr, e, a) in S]
    n = len(rows)
    print(f"MNQ day rider — {n} sessions with a confirmed direction, "
          f"{S[0][0]} .. {S[-1][0]}\n")
    print(f"  {'level':>7} {'RAW MFE':>18} {'CLAIMABLE':>20} {'median time':>13} {'median heat first':>19}")
    print("  " + "-" * 82)
    for L in LEVELS:
        raw = sum(1 for r in rows if r["raw"] >= L)
        clm = [r for r in rows if r["claim"] >= L]
        ts = sorted(r["hit"][L] for r in clm if L in r["hit"])
        ht = sorted(r["heat"][L] for r in clm if L in r["heat"])
        print(f"  ${L:>6} {raw:>6} = {100*raw/n:>5.1f}%   {len(clm):>6} = {100*len(clm)/n:>5.1f}%"
              f"   {(str(ts[len(ts)//2])+'min') if ts else '-':>13}"
              f"   {('-$%.0f' % ht[len(ht)//2]) if ht else '-':>19}")
    mae = sorted(r["mae"] for r in rows)
    print(f"\n  adverse excursion before exit: median -${mae[n//2]:,.0f} · "
          f"75th -${mae[int(n*.75)]:,.0f} · worst -${mae[-1]:,.0f}")
    both = sum(1 for r in rows if r["claim"] >= 400 and r["mae"] >= 400)
    print(f"  sessions that went BOTH +$400 green and -$400 red before exit: {both} ({100*both/n:.1f}%)")


if __name__ == "__main__":
    main()
