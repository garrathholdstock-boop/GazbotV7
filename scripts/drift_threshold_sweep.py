#!/usr/bin/env python3
"""Sweep the day rider's DRIFT thresholds — the first test that touches the entry.

Every earlier test held the entry fixed and varied the exit, and they all converged on the same
ceiling because the entry is a coin flip. This sweeps efficiency / roundtrip / min-bars against the
best exit found (claim BOTH lots at $200 position dollars, hard stop -$400).

★ THE REAL METRICS, NOT A RE-DERIVATION. drift.compute() is called for every minute of every
session and its OWN efficiency/roundtrip/direction are recorded; the sweep then applies candidate
thresholds to that recorded series. So a cell differs from live ONLY by its thresholds — nothing is
re-implemented, which is how a hand-rolled detector once fabricated a +$819 counterfactual here.

⚠ ANTI-OVERFITTING IS THE POINT, NOT AN ADD-ON. A parameter sweep will always produce a best cell.
Reported per cell: n days confirmed (a cell that fires 20 times is noise however good), strip-best
and strip-3, both halves, months positive — and the NEIGHBOURHOOD, because an isolated peak beside
worse cells is a fit, not an edge. The live cell is marked so its rank is visible.
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

CLAIM_USD, STOP_USD = 200.0, 400.0
DOLLARS_PER_PT, FEES = 4.0, 3.0


def series():
    """Per session: the minute-by-minute (i, eff, rt, dir, px) series the REAL detector produces."""
    import gazbot7.drift as D
    from gazbot7.day_rider import ENTRY_CUTOFF_MIN
    from rider_walk import sessions
    old = D.MIN_BARS
    D.MIN_BARS = 5                        # widen so min_bars can be swept upward from the record
    out = []
    for (day, sess, _i, _dr, _e, _a) in sessions():
        mx = min(len(sess), ENTRY_CUTOFF_MIN - D.OPEN_UTC_MIN)
        pts = []
        for i in range(5, mx + 1):
            r = D.compute(sess[:i])
            if r.ok and r.direction:
                pts.append((i, r.efficiency, r.roundtrip, r.direction, sess[i - 1][3], r.atr))
        out.append((day, sess, pts))
    D.MIN_BARS = old
    return out


def trade(sess, i, direction, entry, arm_atr):
    """claim BOTH lots at +$200, hard stop -$400, else the 20:40 clock. Stop checked first."""
    from gazbot7.day_rider import FLAT_UTC_MIN
    d = 1 if direction == "UP" else -1
    claim_pt, stop_pt = CLAIM_USD / DOLLARS_PER_PT, STOP_USD / DOLLARS_PER_PT
    for b in sess[i:]:
        ts, hi, lo, cl = b
        mod = (ts % 86400) // 60
        if mod >= FLAT_UTC_MIN:
            return (cl - entry) * d * DOLLARS_PER_PT - FEES
        if ((entry - lo) if d > 0 else (hi - entry)) >= stop_pt:
            return -stop_pt * DOLLARS_PER_PT - FEES
        if ((hi - entry) if d > 0 else (entry - lo)) >= claim_pt:
            return claim_pt * DOLLARS_PER_PT - FEES
    return (sess[-1][3] - entry) * d * DOLLARS_PER_PT - FEES


def evaluate(S, er, rt, mb):
    rows = []
    for day, sess, pts in S:
        for (i, e, r, dr, px, atr) in pts:
            if i >= mb and e >= er and r >= rt:
                rows.append((day, trade(sess, i, dr, px, atr)))
                break
    return rows


def main():
    import collections
    S = series()
    print(f"sessions scanned: {len(S)}   exit = claim both @ ${CLAIM_USD:.0f}, stop -${STOP_USD:.0f}\n")
    print(f"  {'ER':>5}{'RT':>6}{'bars':>5}{'n':>5}{'net$':>9}{'$/day':>8}{'win%':>7}{'PF':>6}"
          f"{'strip3':>8}{'H1':>8}{'H2':>8}{'mo+':>6}")
    print("  " + "-" * 79)
    best = []
    for er in (0.10, 0.125, 0.15, 0.175, 0.20, 0.25):
        for rt in (0.35, 0.40, 0.45, 0.50, 0.55):
            for mb in (9,):
                rows = evaluate(S, er, rt, mb)
                n = len(rows)
                if n < 30:
                    continue
                p = [v for _d, v in rows]
                w = [x for x in p if x > 0]
                gl = -sum(x for x in p if x <= 0)
                pf = (sum(w) / gl) if gl else 0
                srt = sorted(p)
                tot = sum(p)
                h1, h2 = sum(p[:n // 2]), sum(p[n // 2:])
                mo = collections.OrderedDict()
                for d, v in rows:
                    mo.setdefault(d[:7], []).append(v)
                pos = sum(1 for v in mo.values() if sum(v) > 0)
                live = " <-- LIVE" if (er == 0.15 and rt == 0.45) else ""
                print(f"  {er:>5.3f}{rt:>6.2f}{mb:>5}{n:>5}{tot:>9,.0f}{tot/n:>8.1f}"
                      f"{100*len(w)/n:>6.1f}%{pf:>6.2f}{tot-sum(srt[-3:]):>8,.0f}"
                      f"{h1:>8,.0f}{h2:>8,.0f}{pos:>3}/{len(mo)}{live}")
                best.append((tot / n, er, rt, n, tot, pf))
    best.sort(reverse=True)
    print("\n  top cells by $/day:")
    for v, er, rt, n, tot, pf in best[:5]:
        print(f"    ER {er:.3f} RT {rt:.2f}  n={n:3d}  net {tot:>8,.0f}  ${v:>6.1f}/day  PF {pf:.2f}")


if __name__ == "__main__":
    main()
