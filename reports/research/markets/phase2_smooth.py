"""Market suitability research, PHASE 2: leg smoothness from 1-min bars (operator 2026-10-26). Read-only.
Legs = the frozen desk detector (zigzag K x ATR14 on 1-min closes, same code as live) run on each market's own tape, so the comparison is
'what our MIL detector sees on this market'. Per market: legs/session, leg size (pts, ATR, $ per micro), duration, EFFICIENCY (net move /
sum of |1-min moves| inside the leg: 1 = straight line, low = choppy), worst pullback inside the leg as a share of the leg, and how much of
each leg is left after the detector confirms it (what a confirmation trader can still catch)."""
import sys, duckdb, numpy as np, statistics as st
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import mil_detector_fit as DF
K = 11
def bars(path):
    a = duckdb.connect().execute(f"SELECT bar_ts, high, low, close FROM read_parquet('{path}') WHERE timeframe='1min' ORDER BY bar_ts").fetchall()
    return [(int(t), float(h), float(l), float(c)) for t, h, l, c in a]
def stats(name, b, usd):
    atr = DF.atr14(b); piv = DF.zigzag(b, atr, lambda leg, a: K * a)
    ts = np.array([x[0] for x in b]); cl = np.array([x[3] for x in b])
    sessions = len(set((t + 7200) // 86400 for t in ts))
    L = []
    for p0, p1 in zip(piv, piv[1:]):
        i0, i1 = np.searchsorted(ts, p0[0]), np.searchsorted(ts, p1[0])
        if i1 - i0 < 5: continue
        seg = cl[i0:i1 + 1]; d = p0[2]; size = abs(p1[1] - p0[1])
        path = np.abs(np.diff(seg)).sum(); eff = size / path if path else 0
        run = np.maximum.accumulate(seg * d); pull = (run - seg * d).max() / size if size else 0
        ci = np.searchsorted(ts, p0[3]); left = d * (p1[1] - cl[min(ci, len(cl) - 1)]) / size if size else 0
        L.append((size, size / max(atr[i0], 0.25), (ts[i1] - ts[i0]) / 60, eff, pull, left))
    A = np.array(L)
    print(f"{name:6} sessions {sessions:>4}  legs/session {len(L)/sessions:4.1f}  median leg {np.median(A[:,0]):7.1f}pt = ${np.median(A[:,0])*usd:>5,.0f}/micro"
          f" ({np.median(A[:,1]):4.1f} ATR)  {np.median(A[:,2]):5.0f} min  efficiency {np.median(A[:,3]):.3f}  deepest pullback {np.median(A[:,4]):.0%} of leg"
          f"  left after confirm {np.median(A[:,5]):.0%}  ($ left/leg ${np.median(A[:,0]*A[:,5])*usd:,.0f})")
for sym, usd in (("MNQ", 2.0), ("MGC", 10.0)):
    stats(sym, bars(f"/home/alphabot/gazbot7/data/tape/bars/{sym}/backfill_1min.parquet"), usd)
