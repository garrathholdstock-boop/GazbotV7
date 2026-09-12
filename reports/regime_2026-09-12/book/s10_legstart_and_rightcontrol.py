#!/usr/bin/env python3
"""S10 — two things S09 and S08 forced.

(A) THE EVENT-LEVEL POSITIVE CONTROL. S09 found NO depth withdrawal at a 15-min regime
    transition (ratio 1.003, CI spans 1). That is either a dead pipeline or a real statement
    about the event. Resolve it by running the SAME features on the event the desk's prior
    result was measured on — the START OF A DIRECTIONAL LEG at minute scale — where depth is
    known to fall to 0.72x. If my pipeline recovers ~0.72x there and ~1.00x at a regime
    transition, the pipeline is fine and the two events are simply different: a GMM regime
    label built from 4- and 8-BAR net moves cannot mark the start of anything, it confirms a
    move that began 1-2 hours earlier. Causal: features come from [m-5, m), the leg from m on.

(B) THE RIGHT CONTROL FOR THE CONTRARIAN GLIMMER. S08's best cells fade the book at transitions
    for ~+10pt. But the regime strategy itself is ~-9pt on this window, so simply FADING THE
    REGIME already earns most of that, mechanically, with no book at all. [a control is supposed
    to lose]: the control for "fade the book" is NOT zero, it is "fade the regime". Only the
    increment over that control can be attributed to the order book.
"""
import duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
W = "/tmp/claude-0/-root/7d23ea02-1a64-45f1-9faa-faa8101cea4d/scratchpad"
FRIC = 1.25
rng = np.random.default_rng(101)
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "800MB"})
rep = []

def boot(v, s, n=4000):
    ss, inv = np.unique(s, return_inverse=True)
    S = np.bincount(inv, weights=v, minlength=len(ss)); N = np.bincount(inv, minlength=len(ss)).astype(float)
    p = rng.integers(0, len(ss), size=(n, len(ss)))
    return np.percentile(S[p].sum(1)/N[p].sum(1), [2.5, 97.5])

# ═══════════ (A) leg starts at minute scale ═══════════
m = con.execute(f"""select m, mid_last, db3_mean, da3_mean, b0s_mean, a0s_mean, spread_mean, n_chg, n_snap
                    from read_parquet('{W}/bookfeat/*.parquet') order by m""").df()
m["slot"] = ((m.m % 86400)//900).astype(int)
m["sess"] = pd.to_datetime(m.m+7200, unit="s", utc=True).dt.date
m["depth"] = m.db3_mean + m.da3_mean
m["touch"] = m.b0s_mean + m.a0s_mean
# strictly-prior window [m-5, m): rolling mean of the 5 minutes BEFORE, shifted off the event
for f in ("depth", "touch", "spread_mean"):
    m["pre_"+f] = m[f].rolling(5).mean().shift(1)
fw = m.mid_last.shift(-10) - m.mid_last          # move over the NEXT 10 minutes
bw = m.mid_last - m.mid_last.shift(10)           # move over the PREVIOUS 10 minutes
cont = (m.m.diff(1) == 60) & (m.m.shift(-10) - m.m == 600) & (m.m - m.m.shift(10) == 600)
for TH in (15, 20, 30):
    leg = cont & (fw.abs() >= TH) & (bw.abs() < TH/2)
    sub = m[leg & m.pre_depth.notna()]
    ctl = m[cont & ~leg & m.pre_depth.notna()]
    if len(sub) < 30: continue
    line = {}
    for f in ("depth", "touch", "spread_mean"):
        # matched control: same 15-min-of-day slot, computed on NON-leg minutes only
        cm = ctl.groupby("slot")[f].mean()
        ratio = (sub[f].map(lambda x: x) / sub.slot.map(cm)).where(sub.slot.map(cm).notna())
        pre_ratio = sub["pre_"+f] / sub.slot.map(cm)
        lo, hi = boot(pre_ratio.dropna().values, sub.loc[pre_ratio.notna(), "sess"].values)
        line[f] = (round(pre_ratio.mean(), 4), round(lo, 3), round(hi, 3))
    rep.append(f"  leg = |10-min move| >= {TH}pt after a quiet 10 min · n={len(sub)} legs, "
               f"{sub.sess.nunique()} sessions")
    for f, (r_, lo, hi) in line.items():
        rep.append(f"      PRE-leg {f:<12} = {r_:.3f}x its matched time-of-day control   "
                   f"95% CI [{lo:.3f}, {hi:.3f}]   {'SIG' if hi < 1 or lo > 1 else 'ns'}")
rep.insert(0, "(A) EVENT-LEVEL POSITIVE CONTROL — book in the 5 minutes STRICTLY BEFORE a leg start.")
rep.insert(1, "    Prior desk result to reproduce: 3-level depth 0.72x, touch 0.79x.")

# ═══════════ (B) the right control for the contrarian ═══════════
d = con.execute(f"select * from read_parquet('{OUT}/s05_decision_features.parquet')").df().sort_values("bt")
g = con.execute(f"select bt, sess, open, close from read_parquet('{OUT}/s02_bars15.parquet')").df().sort_values("bt").reset_index(drop=True)
bt2i = {b: i for i, b in enumerate(g.bt.values)}
op, cl, sv = g.open.values, g.close.values, g.sess.values
for lbl, h in {"60m": 4, "90m": 6}.items():
    o = np.full(len(d), np.nan)
    for r_, b in enumerate(d.bt.values):
        i = bt2i.get(b)
        if i is None or i+1+h >= len(g) or sv[i] != sv[i+h] or sv[i] != sv[i+1]: continue
        o[r_] = cl[i+h] - op[i+1]
    d["fwd_"+lbl] = o
tr = pd.read_csv(f"{OUT}/s02_transitions_bookwindow.csv")
d = d.merge(tr[["bt", "side", "clean"]], on="bt", how="left")
tt = d[d.side.notna()].copy()

rep.append("")
rep.append("(B) FADE-THE-BOOK vs its real control, FADE-THE-REGIME, on the same transitions.")
rep.append(f"{'cell':>28}{'n':>6}{'follow regime':>15}{'FADE regime':>13}{'FADE book':>12}"
           f"{'book increment':>16}{'95% CI of increment':>24}")
best = []
for lbl in ("60m", "90m"):
    for cln in (False, True):
        q = tt[tt.clean == True] if cln else tt
        q = q[q["fwd_"+lbl].notna()]
        for f in ["imb3_L", "imb3_L_zs", "tsi", "tsi5_zs", "tsi_ztod", "imbT_L", "ofi5_n"]:
            s = q[q[f].notna()]
            if len(s) < 60: continue
            y = s["fwd_"+lbl].values; sd = s.side.values.astype(float)
            pro = sd*y - FRIC; fade = -sd*y - FRIC
            fb = -np.sign(s[f].values)*y - FRIC
            inc = fb - fade                                   # paired, same trades
            lo, hi = boot(inc, s.sess.values)
            rep.append(f"{f+' '+lbl+(' clean' if cln else ''):>28}{len(s):>6}{pro.mean():>15.2f}"
                       f"{fade.mean():>13.2f}{fb.mean():>12.2f}{inc.mean():>16.2f}"
                       f"{f'[{lo:+.2f}, {hi:+.2f}]':>24}")
            best.append((inc.mean(), lo, hi))
arr = np.array(best)
rep.append(f"\n    increments over the fade-the-regime control: {(arr[:,0]>0).sum()}/{len(arr)} positive, "
           f"{(arr[:,1]>0).sum()}/{len(arr)} with a day-block CI excluding zero.")
txt = "\n".join(rep); open(f"{OUT}/s10_legstart_and_rightcontrol.txt", "w").write(txt+"\n"); print(txt)
