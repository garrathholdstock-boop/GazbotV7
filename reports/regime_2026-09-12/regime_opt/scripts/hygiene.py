#!/usr/bin/env python3
"""HYGIENE - two things that can invent a result, checked before any of it is believed.

1. CONTRACT ROLL. The front-month tape is stitched per UTC CALENDAR DATE, but the CME session
   runs 22:00Z->21:00Z, so a roll lands in the MIDDLE of a session. A stitched jump is a fake
   move: it feeds the drift features AND can be booked by a trade held across it.
2. THE SHIFTED-WORLD NULL scores ~2.5pt WORSE than real on the grid average. Before that is
   called signal, check the mechanical explanation: is the null's long/short mix different, and
   does the market's own +21% drift over the sample do the work?
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

g = R.load_bars(15)
c = g.close.values; o = g.open.values
d = np.diff(c, prepend=c[0])
sess = g.sess.values
# a 15-min bar-to-bar jump of >150pt with a small bar range is a stitch, not a trade
big = np.argsort(np.abs(d))[-12:]
print("TWELVE LARGEST BAR-TO-BAR CLOSE CHANGES (a roll shows up as a jump with no range)")
print(pd.DataFrame({"dt": g.dt.values[big], "sess": sess[big], "d_close": d[big],
                    "bar_range": (g.high.values - g.low.values)[big]})
      .sort_values("d_close", key=abs, ascending=False).to_string(index=False))

print("\nPER-SESSION close-to-close gaps at the session seam (21:00Z->22:00Z) are normal;")
print("what matters is an INTRA-session jump. Counting bars where |dclose| > 6x the bar range:")
susp = np.abs(d) > 6 * np.maximum(g.high.values - g.low.values, .25)
print(pd.DataFrame({"dt": g.dt.values[susp], "d": d[susp]}).to_string(index=False))

ROLL_SESS = sorted(set(sess[susp]))
print("\nSESSIONS TO EXCLUDE AS ROLL-CONTAMINATED:", ROLL_SESS)
pd.Series([str(s) for s in ROLL_SESS]).to_csv(f"{R.ART}/tables/roll_sessions.csv",
                                              index=False, header=["sess"])

# ── 2. is the shifted-world null mechanically biased? ──
M = R.Model(15, 3, "base", g=g)
idx = R.signals(M, clean=2)
T = R.trades(M, idx, hold=6, friction=1.25)
print(f"\nREAL   n={len(T)} long%={100*(T.side>0).mean():.0f}  mean net={T.pt.mean():.2f}  "
      f"mean raw move (long-equivalent)={np.mean(T.gross*T.side):.2f}")
orig = (M.state, M.lab, M.sign, M.tp)
rows = []
ss = sorted(g.sess.unique()); pos = {s: k for k, s in enumerate(ss)}
sidx = np.array([pos[s] for s in g.sess.values])
key = pd.DataFrame({"s": sidx, "r": np.arange(len(g))}); key["rk"] = key.groupby("s").cumcount()
for sh in (-53, -37, -23, 17, 31, 47):
    tgt = key.copy(); tgt["s"] = (tgt.s + sh) % len(ss)
    m = key.merge(tgt, on=["s", "rk"], how="left", suffixes=("", "_t"))
    src = m["r_t"].values; good = ~np.isnan(src)
    srci = np.where(good, np.nan_to_num(src, nan=0).astype(int), 0)
    M.state = np.where(good, orig[0][srci], -1); M.lab = np.where(good, orig[1][srci], "NA")
    M.sign = np.where(good, orig[2][srci], 0);   M.tp = np.where(good, orig[3][srci], np.nan)
    i2 = R.signals(M, clean=2); T2 = R.trades(M, i2, hold=6, friction=1.25)
    rows.append(dict(shift=sh, n=len(T2), long_pct=100*(T2.side > 0).mean(),
                     net=T2.pt.mean(), raw=np.mean(T2.gross*T2.side)))
M.state, M.lab, M.sign, M.tp = orig
print(pd.DataFrame(rows).round(2).to_string(index=False))
sc = R.sign_control(T, draws=4000, block="day")
print(f"\nSIGN CONTROL (same entries, random sides, day-blocked): mean {sc['mean']:.2f} "
      f"sd {sc['sd']:.2f}  observed {sc['obs']:.2f}  p={sc['p']:.3f}")
print(f"BUY-AND-HOLD control, 90-min hold, every bar: {R.buy_hold_control(M, 6)}")
