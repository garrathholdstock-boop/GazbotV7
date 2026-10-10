"""Fit a CAUSAL major-intraday-leg detector to the operator's labelled legs (scripts/mil_labels.py).
Detectors are zigzags on 1-min closes run CONTINUOUSLY from 2026-09-30 so the first leg of each labelled day is
not a cold start. A turn is only known when the retrace is confirmed, so every score separates WHERE the pivot
was (matched to his label) from WHEN we could have known (confirm lag, price given back)."""
import sys, os, itertools, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mil_labels as ML

WARM = ["2026-09-30", "2026-10-01", "2026-10-02"]
DAYS = list(ML.LABELS)
MATCH_MIN = 100


def series():
    allb, ts = [], set()
    for d in WARM + DAYS:
        for b in ML.minute_bars(d):
            if b[0] not in ts:
                ts.add(b[0]); allb.append(b)
    allb.sort()
    return allb


def atr14(bars):
    out, trs = [], []
    for i, b in enumerate(bars):
        pc = bars[i - 1][3] if i else b[3]
        trs.append(max(b[1] - b[2], abs(b[1] - pc), abs(b[2] - pc), 0.25))
        out.append(sum(trs[-14:]) / len(trs[-14:]))
    return out


def zigzag(bars, atr, thr):
    """thr(leg_pts, atr) -> retrace in points needed to confirm a turn. Returns pivots:
    (pivot_ts, pivot_px, new_dir, confirm_ts, confirm_px)."""
    cl = [b[3] for b in bars]
    dirn = 1 if cl[30] > cl[0] else -1
    ext, ei, last_px = cl[0], 0, cl[0]
    out = []
    for i in range(1, len(bars)):
        c = cl[i]
        if dirn * (c - ext) > 0:
            ext, ei = c, i
        elif dirn * (ext - c) >= thr(dirn * (ext - last_px), atr[i]):
            out.append((bars[ei][0], ext, -dirn, bars[i][0], c))
            last_px, dirn, ext, ei = ext, -dirn, c, i
    return out


def score(piv, bars):
    """Match detected pivots to labelled turns day by day."""
    res = dict(tp=0, miss=0, extra=0, lag=[], giveback=[], err=[], pairs=[])
    for d in DAYS:
        bd = ML.minute_bars(d)
        lab = ML.snapped_turns(d, bd)
        s, e = bd[0][0], bd[-1][0]
        det = [p for p in piv if s <= p[0] <= e]
        used = set()
        for (lt, lp, nd) in lab:
            best = None
            for k, p in enumerate(det):
                if k in used or p[2] != nd:
                    continue
                if abs(p[0] - lt) <= MATCH_MIN * 60 and (best is None or abs(p[0] - lt) < abs(det[best][0] - lt)):
                    best = k
            if best is None:
                res["miss"] += 1
            else:
                used.add(best); p = det[best]
                res["tp"] += 1
                res["lag"].append((p[3] - p[0]) / 60)
                res["giveback"].append(abs(p[4] - p[1]))
                res["err"].append((p[0] - lt) / 60)
        res["extra"] += len(det) - len(used)
    return res


def ride(piv, bars):
    """Causal ride: on each confirmed turn flip to the new direction at the confirm price. Points per day."""
    per = {}
    for d in DAYS:
        bd = ML.minute_bars(d)
        s, e = bd[0][0], bd[-1][0]
        pos, entry, pnl, n = 0, 0, 0.0, 0
        for p in [q for q in piv if s <= q[3] <= e]:
            if pos:
                pnl += pos * (p[4] - entry) - 0.75   # MNQ round trip ~$1.50 = 0.75pt
                n += 1
            pos, entry = p[2], p[4]
        if pos:
            pnl += pos * (bd[-1][3] - entry) - 0.75
            n += 1
        per[d] = (pnl, n)
    return per


def main():
    bars = series()
    atr = atr14(bars)
    fams = {}
    for k in (7, 10, 15, 20, 25, 30, 40):
        fams[f"ATR x{k}"] = (lambda k: lambda leg, a: k * a)(k)
    for p in (40, 60, 80, 100, 120, 150):
        fams[f"fixed {p}pt"] = (lambda p: lambda leg, a: p)(p)
    for f, fl in itertools.product((0.2, 0.3, 0.4, 0.5), (30, 45, 60)):
        fams[f"frac {f} floor {fl}"] = (lambda f, fl: lambda leg, a: max(fl, f * leg))(f, fl)
    print(f"labelled turns: {sum(len(ML.LABELS[d])-1 for d in DAYS)}  match window +-{MATCH_MIN}min\n")
    print(f"{'detector':22}{'hit':>4}{'miss':>5}{'extra':>6}{'lag med':>9}{'giveback':>10}{'err med':>9}{'ride pts/day':>14}{'trades':>8}")
    rows = []
    for name, thr in fams.items():
        piv = zigzag(bars, atr, thr)
        r = score(piv, bars)
        rd = ride(piv, bars)
        med = lambda x: sorted(x)[len(x) // 2] if x else float("nan")
        pts = sum(v[0] for v in rd.values()) / len(rd); nt = sum(v[1] for v in rd.values())
        rows.append((name, r, pts, nt))
        print(f"{name:22}{r['tp']:>4}{r['miss']:>5}{r['extra']:>6}{med(r['lag']):>8.0f}m{med(r['giveback']):>9.0f}p{med(r['err']):>8.0f}m{pts:>14.0f}{nt:>8}")
    # perfect hindsight: ride each labelled leg exactly
    tot = 0
    for d in DAYS:
        bd = ML.minute_bars(d); tp = ML.snapped_turns(d, bd)
        prev = bd[0][3]
        for (t, p, nd), (dr, h) in zip(tp, ML.LABELS[d]):
            tot += abs(p - prev); prev = p
        tot += abs(bd[-1][3] - prev)
    print(f"\nlabelled legs, full length (hindsight ceiling, incl. truncated first legs): {tot/len(DAYS):.0f} pt/day")


if __name__ == "__main__":
    main()
