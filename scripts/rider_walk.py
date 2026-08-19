#!/usr/bin/env python3
"""Walk the ACTUAL day rider — trail and all — across the full backfilled MNQ history.

Operator, 2026-08-19: "walk the actual rider with the trail across all 231 sessions... but i have
also manually claimed many... when i notice it sitting at 4-500 profit ill claim it."

★ THE MANUAL CLAIM IS BACKTESTABLE. "Claim when it's showing $400-500" is a TAKE-PROFIT rule, and a
clean one: 2 lots MNQ at $2/pt means $400 = 100pt, $500 = 125pt. It is modelled here as a level and
swept, so the discretion becomes a measurable policy rather than an unknown.

★ CALLS THE REAL trail_level(). It is a pure function in day_rider, so the arming and trail rules are
the SHIPPED ones, not a re-derivation. arm_atr is the ATR FROZEN AT ENTRY — day_rider is explicit
that scaling off a live ATR would be a different rule from the one backtested.

⚠ INTRABAR AMBIGUITY IS RESOLVED AGAINST US. If a single minute both extends the peak past a claim
level AND trades back through the trail, the order is unknowable from OHLC, so the WORSE of the two
exits is booked. Anything else would flatter every variant that has two exits.

⚠ NO 5s TAPE FOR MOST OF THIS WINDOW, so fills are minute-resolution. A trail crossed and reclaimed
inside one minute is booked as a fill at the trail — the same optimism the shadow book is criticised
for, and the reason these numbers are a RANKING tool, not a P&L forecast.
"""
from __future__ import annotations
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")

VPP, LOTS, FEE_RT = 2.0, 2.0, 1.50          # MNQ $2/pt · rider trades 2 lots · $1.50/RT per lot
DOLLARS_PER_PT = VPP * LOTS                  # $4/pt
FEES = FEE_RT * LOTS                         # $3.00 round trip


def sessions():
    """(day, bars, confirmation) for every session the real detector confirms before the cutoff."""
    from gazbot7.day_rider import ENTRY_CUTOFF_MIN
    from gazbot7.drift import MIN_BARS, OPEN_UTC_MIN, compute
    from gazbot7.lake import connect
    con = connect(symbol="MNQ")
    tf = con.execute("""SELECT timeframe FROM bars WHERE symbol='MNQ'
                        AND timeframe IN ('5s','1min','1m') GROUP BY 1
                        ORDER BY MAX(bar_ts)-MIN(bar_ts) DESC LIMIT 1""").fetchone()[0]
    rows = con.execute(f"""
        SELECT CAST(to_timestamp(bar_ts) AS DATE) d, CAST(bar_ts/60 AS INT)*60 t,
               MAX(high) h, MIN(low) l, arg_max(close, bar_ts) c
        FROM bars WHERE symbol='MNQ' AND timeframe='{tf}'
        GROUP BY d, t ORDER BY d, t""").fetchall()
    con.close()
    byday: dict = {}
    for d, t, h, low, c in rows:
        byday.setdefault(str(d), []).append((int(t), float(h), float(low), float(c)))
    out = []
    for day, bars in sorted(byday.items()):
        sess = [b for b in bars if OPEN_UTC_MIN * 60 <= (b[0] % 86400) < 21 * 3600]
        if len(sess) < 120:
            continue
        mx = min(len(sess), ENTRY_CUTOFF_MIN - OPEN_UTC_MIN)
        for i in range(MIN_BARS, mx + 1):
            r = compute(sess[:i])
            if r.confirmed:
                out.append((day, sess, i, r.direction, sess[i - 1][3], r.atr))
                break
    return out


def run_day(sess, i, direction, entry, arm_atr, *, use_trail=True, claim_usd=0.0, stop_usd=0.0):
    """One session. Returns (pnl_usd, exit_reason, held_min, peak_pt).

    ⚠ THE STOP IS CHECKED BEFORE THE CLAIM. Inside one minute the order of a stop and a target is
    unknowable from OHLC, and assuming the target came first is exactly how an MFE measurement
    flatters itself. Booking the stop first is the only reading that cannot manufacture an edge.
    ⚠ claim_usd and stop_usd are POSITION dollars across BOTH lots ($4/pt), matching how the
    operator reads the screen — not per-lot. Mixing those two conventions is what made the earlier
    scale-out table describe a $100/$150 strategy while labelling it $200/$300.
    """
    from gazbot7.day_rider import FLAT_UTC_MIN, trail_level
    d = 1 if direction == "UP" else -1
    peak = entry
    claim_pt = (claim_usd / DOLLARS_PER_PT) if claim_usd else None
    stop_pt = (stop_usd / DOLLARS_PER_PT) if stop_usd else None
    for b in sess[i:]:
        ts, hi, lo, cl = b
        mod = (ts % 86400) // 60
        adv = (entry - lo) if d > 0 else (hi - entry)
        if stop_pt is not None and adv >= stop_pt and mod < FLAT_UTC_MIN:
            held = ((ts % 86400) // 60) - ((sess[i - 1][0] % 86400) // 60)
            return (-stop_pt * DOLLARS_PER_PT - FEES, "STOP", held, (peak - entry) * d)
        if mod >= FLAT_UTC_MIN:                                  # hard flat, never past it
            return ((cl - entry) * d * DOLLARS_PER_PT - FEES, "CLOCK_FLAT",
                    mod - ((sess[i - 1][0] % 86400) // 60), (peak - entry) * d)
        fav = (hi - entry) * d if d > 0 else (entry - lo) * d * -1
        fav = (hi - entry) if d > 0 else (entry - lo)            # favourable excursion this bar, pt
        peak = max(peak, hi) if d > 0 else min(peak, lo)
        trail = trail_level(d, entry, peak, arm_atr) if use_trail else None
        hit_trail = trail is not None and ((lo <= trail) if d > 0 else (hi >= trail))
        hit_claim = claim_pt is not None and fav >= claim_pt
        px = None
        if hit_trail and hit_claim:
            # ⚠ order unknowable inside one bar -> book the WORSE outcome
            px = min(trail, entry + d * claim_pt) if d > 0 else max(trail, entry - claim_pt)
        elif hit_trail:
            px = trail
        elif hit_claim:
            px = entry + d * claim_pt
        if px is not None:
            held = ((ts % 86400) // 60) - ((sess[i - 1][0] % 86400) // 60)
            why = "TRAIL" if (hit_trail and not hit_claim) else ("CLAIM" if hit_claim and not hit_trail else "BOTH")
            return ((px - entry) * d * DOLLARS_PER_PT - FEES, why, held, (peak - entry) * d)
    cl = sess[-1][3]
    return ((cl - entry) * d * DOLLARS_PER_PT - FEES, "EOD",
            len(sess) - i, (peak - entry) * d)


def stat(rows):
    n = len(rows)
    if not n:
        return "  (no trades)"
    pnl = [r[0] for r in rows]
    w = [p for p in pnl if p > 0]
    tot = sum(pnl)
    srt = sorted(pnl)
    best = max(pnl)
    gross_w, gross_l = sum(w), -sum(p for p in pnl if p <= 0)
    pf = (gross_w / gross_l) if gross_l else float("inf")
    return (f"{tot:>9,.0f}  {tot/n:>7.1f}  {100*len(w)/n:>5.1f}%  {srt[n//2]:>7.1f}  "
            f"{pf:>5.2f}  {tot-best:>9,.0f}")


def main():
    S = sessions()
    print(f"sessions with a confirmed direction: {len(S)}   "
          f"{S[0][0]} .. {S[-1][0]}\n")
    variants = [
        ("hold to 20:40 (no exit rule)", dict(use_trail=False, claim_usd=0)),
        ("ATR trail only  [LIVE]", dict(use_trail=True, claim_usd=0)),
        ("claim $300 only", dict(use_trail=False, claim_usd=300)),
        ("claim $400 only", dict(use_trail=False, claim_usd=400)),
        ("claim $500 only", dict(use_trail=False, claim_usd=500)),
        ("claim $600 only", dict(use_trail=False, claim_usd=600)),
        ("trail + claim $300", dict(use_trail=True, claim_usd=300)),
        ("trail + claim $400", dict(use_trail=True, claim_usd=400)),
        ("trail + claim $500", dict(use_trail=True, claim_usd=500)),
        ("trail + claim $600", dict(use_trail=True, claim_usd=600)),
    ]
    print(f"  {'variant':<30} {'net$':>9} {'$/day':>8} {'win%':>6} {'median':>8} {'PF':>6} {'strip-best':>10}")
    print("  " + "-" * 82)
    keep = {}
    for name, kw in variants:
        rows = [run_day(sess, i, dr, e, a, **kw) for (_d, sess, i, dr, e, a) in S]
        keep[name] = rows
        print(f"  {name:<30} {stat(rows)}")
    print()
    for name in ("ATR trail only  [LIVE]", "trail + claim $400", "trail + claim $500"):
        rows = keep[name]
        from collections import Counter
        c = Counter(r[1] for r in rows)
        print(f"  {name}: exits {dict(c)}  median hold {sorted(r[2] for r in rows)[len(rows)//2]}min")


if __name__ == "__main__":
    main()
