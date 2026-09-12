#!/usr/bin/env python3
"""CONTROL AUDIT - does each control trade the SAME ENTRIES as the real arm?

Prompted by the lead-lag agent's measured defect: a within-session shuffle scored +2.40pt NET,
because shuffling re-selected WHICH bars cleared the threshold. A control that makes money is
broken, and the diagnosis is always the same - it is trading a different entry population.

For every control here we report, for one fixed cell:
    entries (n) · timestamp overlap with the real arm · long share · mean net
A control whose overlap is not 100% is measuring entry SELECTION and direction at once.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

CELL = dict(bar=15, K=3, fset="base", clean=2, hold=6, friction=1.25)
g = R.load_bars(CELL["bar"])
M = R.Model(CELL["bar"], CELL["K"], CELL["fset"], g=g)
idx = R.signals(M, clean=CELL["clean"])
T = R.trades(M, idx, hold=CELL["hold"], friction=CELL["friction"])
real_bars = set(T.i.values)
rows = [dict(control="REAL (the arm itself)", n=len(T), overlap_pct=100.0,
             long_pct=100*(T.side > 0).mean(), mean_net=T.pt.mean(), note="")]

# ── 1. SIGN-FLIP, same entries. The shape the lead-lag harness recommends. ──
rng = np.random.default_rng(4)
codes = pd.factorize(T.sess.values)[0]
flip = rng.choice((-1, 1), codes.max()+1)[codes]
T1 = R.trades(M, T.i.values, hold=CELL["hold"], friction=CELL["friction"],
              side_override=T.side.values*flip)
rows.append(dict(control="SIGN-FLIP (day-blocked), same bars", n=len(T1),
                 overlap_pct=100*len(real_bars & set(T1.i.values))/len(real_bars),
                 long_pct=100*(T1.side > 0).mean(), mean_net=T1.pt.mean(),
                 note="identical entry set by construction - verified, not asserted"))
# ── 2. ALWAYS-LONG, same entries. ──
T2 = R.trades(M, T.i.values, hold=CELL["hold"], friction=CELL["friction"],
              side_override=np.ones(len(T), int))
rows.append(dict(control="ALWAYS-LONG, same bars", n=len(T2),
                 overlap_pct=100*len(real_bars & set(T2.i.values))/len(real_bars),
                 long_pct=100.0, mean_net=T2.pt.mean(), note="same bars, direction fixed"))

# ── 3. THE 5-WAY LABEL PERMUTATION the addendum criticised - now measured. ──
vals = [M.name[k] for k in range(M.K)]
orig_name, orig_lab, orig_sign = dict(M.name), M.lab.copy(), M.sign.copy()
perm_rows = []
import itertools
for perm in itertools.permutations(vals):
    if list(perm) == vals:
        continue
    M.name = {k: perm[k] for k in range(M.K)}
    M.lab = np.array([M.name.get(s, "NA") if s >= 0 else "NA" for s in M.state])
    M.sign = np.where(M.lab == "BULLISH", 1, np.where(M.lab == "BEARISH", -1, 0))
    i2 = R.signals(M, clean=CELL["clean"])
    T3 = R.trades(M, i2, hold=CELL["hold"], friction=CELL["friction"])
    perm_rows.append((str(perm), len(T3), 100*len(real_bars & set(T3.i.values))/len(real_bars),
                      100*(T3.side > 0).mean(), T3.pt.mean()))
M.name, M.lab, M.sign = orig_name, orig_lab, orig_sign
P = pd.DataFrame(perm_rows, columns=["perm", "n", "overlap_pct", "long_pct", "mean_net"])
print("THE 5-WAY LABEL PERMUTATION (the incumbent control) - all five arrangements")
print(P.round(2).to_string(index=False))
print(f"\n  -> entry count swings {P.n.min()}..{P.n.max()} against the real arm's {len(T)}; "
      f"bar overlap {P.overlap_pct.min():.0f}-{P.overlap_pct.max():.0f}%.")
rows.append(dict(control="LABEL PERMUTATION (mean of 5)", n=int(P.n.mean()),
                 overlap_pct=P.overlap_pct.mean(), long_pct=P.long_pct.mean(),
                 mean_net=P.mean_net.mean(),
                 note="ENTRY SET MOVES - measures selection and direction at once"))

# ── 4. SESSION-SHIFT (my structural null). Honest about what it changes. ──
ss = sorted(g.sess.unique()); pos = {s: k for k, s in enumerate(ss)}
sidx = np.array([pos[s] for s in g.sess.values])
key = pd.DataFrame({"s": sidx, "r": np.arange(len(g))}); key["rk"] = key.groupby("s").cumcount()
orig = (M.state, M.lab, M.sign, M.tp)
sh_rows = []
for sh in (-53, -37, -23, 17, 31, 47):
    tgt = key.copy(); tgt["s"] = (tgt.s + sh) % len(ss)
    m = key.merge(tgt, on=["s", "rk"], how="left", suffixes=("", "_t"))
    src = m["r_t"].values; good = ~np.isnan(src)
    si = np.where(good, np.nan_to_num(src, nan=0).astype(int), 0)
    M.state = np.where(good, orig[0][si], -1); M.lab = np.where(good, orig[1][si], "NA")
    M.sign = np.where(good, orig[2][si], 0);   M.tp = np.where(good, orig[3][si], np.nan)
    i4 = R.signals(M, clean=CELL["clean"]); T4 = R.trades(M, i4, hold=CELL["hold"],
                                                          friction=CELL["friction"])
    sh_rows.append((sh, len(T4), 100*len(real_bars & set(T4.i.values))/len(real_bars),
                    100*(T4.side > 0).mean(), T4.pt.mean()))
M.state, M.lab, M.sign, M.tp = orig
S = pd.DataFrame(sh_rows, columns=["shift", "n", "overlap_pct", "long_pct", "mean_net"])
print("\nSESSION-SHIFT NULL - rotate the fitted state series by whole sessions")
print(S.round(2).to_string(index=False))
rows.append(dict(control="SESSION-SHIFT (mean of 6)", n=int(S.n.mean()),
                 overlap_pct=S.overlap_pct.mean(), long_pct=S.long_pct.mean(),
                 mean_net=S.mean_net.mean(),
                 note="entry TIMES move by design - a structural null, NOT like-for-like"))

D = pd.DataFrame(rows)
print(f"\n{'='*104}\nCONTROL AUDIT - cell: 15-min, 3 states, base features, clean=2, "
      f"90-min hold, 1.25pt")
print(D.round(2).to_string(index=False))
D.to_csv(f"{R.ART}/tables/control_audit.csv", index=False)
print("\nVERDICT ON THE CONTROLS:")
print("  SIGN-FLIP and ALWAYS-LONG take the identical bars (100% overlap) and change only")
print("  direction -> these are the like-for-like controls, and the ones this study decides on.")
print("  The LABEL PERMUTATION moves the entry set and is reported for comparison only.")
print("  The SESSION-SHIFT answers a different question (is the state series aligned to price")
print("  at all) and is used for the multiple-testing null over the whole grid, never as a")
print("  single cell's twin.")
