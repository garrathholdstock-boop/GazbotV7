#!/usr/bin/env python3
"""S07 — THE MAIN TEST. Does the order book add DIRECTION at regime transitions?

A POWER LADDER, so that a null at the small n is anchored by a null at the large n:
  L1  every 15-min decision window in the book window   n ~ 2,700
  L2  regime-transition windows only                    n ~ 300
  L3  the book as a FILTER on the regime strategy's own side  (THE MISSION)

CONTROLS
  * matched: features are z-scored inside the SAME SESSION and, separately, against the same
    15-min-of-day slot across OTHER sessions (leave-one-out). Never a global average.
  * L3's null is a DAY-BLOCK SIGN-FLIP permutation of the book's agreement: a whole session's
    agreement signs flip together. This is a strictly better control than the incumbent's 5-way
    label permutation — it destroys ONLY the book's relationship to the outcome while leaving
    the regime labels, the entry population and the return series exactly as they are. The
    label permutation could not do that: with 3 states it has only 5 arrangements and moving
    CHOP onto a drift state changes which bars are even entered.
  * MULTIPLE COMPARISONS: the grid is (feature x normalisation x hold), so a single lucky cell
    is expected. The headline statistic is therefore MAX |t| ACROSS THE WHOLE GRID compared to
    the max |t| of each permuted draw. [a control is supposed to lose] and [this desk killed
    four single-quintile islands today].
  * CIs are DAY-BLOCK BOOTSTRAP (resample sessions with replacement), never per-trade.

FRICTION 1.25 pt = $1.50/RT (0.75pt) + the 0.25pt tick crossed once. The desk's measured cost.
"""
import duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
FRIC, VPP, NBOOT, NPERM = 1.25, 2.0, 4000, 4000
rng = np.random.default_rng(20260912)
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "800MB"})

d = con.execute(f"select * from read_parquet('{OUT}/s05_decision_features.parquet')").df().sort_values("bt")
g = con.execute(f"select bt, sess, open, close from read_parquet('{OUT}/s02_bars15.parquet')").df().sort_values("bt")
g = g.reset_index(drop=True)
bt2i = {b: i for i, b in enumerate(g.bt.values)}
op, cl, sv = g.open.values, g.close.values, g.sess.values

HOLDS = {"15m": 1, "30m": 2, "60m": 4, "90m": 6}
for lbl, h in HOLDS.items():
    out = np.full(len(d), np.nan)
    for r_, b in enumerate(d.bt.values):
        i = bt2i.get(b)
        if i is None or i+1+h >= len(g): continue
        if sv[i] != sv[i+h] or sv[i] != sv[i+1]: continue
        out[r_] = cl[i+h] - op[i+1]        # LONG-side forward move from the next bar's open
    d["fwd_"+lbl] = out

tr = pd.read_csv(f"{OUT}/s02_transitions_bookwindow.csv")
d = d.merge(tr[["bt", "side", "clean", "label"]], on="bt", how="left")
d["is_tr"] = d.side.notna()

SIGNED = ["imb3", "imb_touch", "imb3_L", "imbT_L", "imb3_5", "ofi_n", "ofi5_n", "tsi", "tsi5", "slope_asym"]
NORMS = ["", "_zs", "_ztod"]

def dayblock_boot(vals, sess, stat=np.mean):
    """CI by resampling SESSIONS with replacement — trades inside a day are not independent."""
    ss = pd.unique(sess); idx = {s: np.where(sess == s)[0] for s in ss}
    out = np.empty(NBOOT)
    for b in range(NBOOT):
        pick = rng.choice(ss, len(ss), replace=True)
        out[b] = stat(np.concatenate([vals[idx[s]] for s in pick]))
    return np.percentile(out, [2.5, 97.5])

# ══════════════════ L1 / L2 : does a signed book feature predict the direction? ══════════════
rows = []
for scope, sub in (("L1 all windows", d), ("L2 transitions", d[d.is_tr]),
                   ("L2 clean transitions", d[d.is_tr & (d.clean == True)])):
    for f in SIGNED:
        for nz in NORMS:
            col = f + nz
            if col not in sub: continue
            for lbl in HOLDS:
                s = sub[[col, "fwd_"+lbl, "sess"]].dropna()
                if len(s) < 60: continue
                x, y = s[col].values, s["fwd_"+lbl].values
                r = np.corrcoef(x, y)[0, 1] if x.std() > 0 else np.nan
                t = r*np.sqrt((len(x)-2)/max(1-r*r, 1e-12))
                nz0 = (x != 0) & (y != 0)
                hit = (np.sign(x[nz0]) == np.sign(y[nz0])).mean() if nz0.sum() else np.nan
                pnl = np.sign(x)*y - FRIC
                lo, hi = dayblock_boot(pnl, s.sess.values)
                rows.append(dict(scope=scope, feat=col, hold=lbl, n=len(s), r=round(r, 4),
                                 t=round(t, 2), hit=round(hit, 4),
                                 net_pt=round(pnl.mean(), 3), lo=round(lo, 2), hi=round(hi, 2),
                                 excl0=bool(lo > 0 or hi < 0)))
L12 = pd.DataFrame(rows); L12.to_csv(f"{OUT}/s07_L1_L2_direction.csv", index=False)

# ══════════════════ L3 : the book as a FILTER on the regime strategy's own side ══════════════
tt = d[d.is_tr].copy()
tt["sideN"] = tt.side.astype(float)
res = []
for f in SIGNED:
    for nz in NORMS:
        col = f + nz
        if col not in tt: continue
        for lbl in HOLDS:
            s = tt[[col, "fwd_"+lbl, "sess", "sideN", "clean"]].dropna()
            for cln in (False, True):
                q = s[s.clean == True] if cln else s
                if len(q) < 60: continue
                pnl_all = q.sideN.values*q["fwd_"+lbl].values - FRIC
                agree = np.sign(q[col].values)*q.sideN.values          # +1 book agrees with regime
                A, D = agree > 0, agree < 0
                if A.sum() < 25 or D.sum() < 25: continue
                contrast = pnl_all[A].mean() - pnl_all[D].mean()
                loA, hiA = dayblock_boot(pnl_all[A], q.sess.values[A])
                res.append(dict(feat=col, hold=lbl, clean=cln, n_all=len(q),
                                base_pt=round(pnl_all.mean(), 3),
                                nA=int(A.sum()), agree_pt=round(pnl_all[A].mean(), 3),
                                nD=int(D.sum()), disagree_pt=round(pnl_all[D].mean(), 3),
                                contrast=round(contrast, 3),
                                agree_lo=round(loA, 2), agree_hi=round(hiA, 2),
                                agree_excl0=bool(loA > 0),
                                _key=(col, lbl, cln)))
L3 = pd.DataFrame(res)

# ── day-block SIGN-FLIP permutation null, and the MAX-|contrast| statistic over the whole grid
sessions = pd.unique(tt.sess.values)
perm_max = np.empty(NPERM); perm_cells = {k: [] for k in L3._key} if len(L3) else {}
cache = {}
for k in perm_cells:
    col, lbl, cln = k
    s = tt[[col, "fwd_"+lbl, "sess", "sideN", "clean"]].dropna()
    q = s[s.clean == True] if cln else s
    cache[k] = (np.sign(q[col].values)*q.sideN.values,
                q.sideN.values*q["fwd_"+lbl].values - FRIC, q.sess.values)
for b in range(NPERM):
    flip = {s: (1 if rng.random() < .5 else -1) for s in sessions}
    mx = 0.0
    for k in perm_cells:
        agree, pnl, sess = cache[k]
        fl = np.array([flip[s] for s in sess])
        a2 = agree*fl
        A, D = a2 > 0, a2 < 0
        if A.sum() < 25 or D.sum() < 25:
            perm_cells[k].append(np.nan); continue
        c = pnl[A].mean() - pnl[D].mean()
        perm_cells[k].append(c); mx = max(mx, abs(c))
    perm_max[b] = mx
if len(L3):
    L3["perm_sd"] = [np.nanstd(perm_cells[k], ddof=1) for k in L3._key]
    L3["perm_p_cell"] = [float(np.nanmean(np.abs(perm_cells[k]) >= abs(c)))
                         for k, c in zip(L3._key, L3.contrast)]
    obs_max = L3.contrast.abs().max()
    L3["perm_p_familywise"] = float((perm_max >= obs_max).mean())
    L3 = L3.drop(columns=["_key"])
L3.to_csv(f"{OUT}/s07_L3_book_as_filter.csv", index=False)
np.save(f"{OUT}/s07_perm_max.npy", perm_max)
print(f"L1/L2 cells {len(L12)} · L3 cells {len(L3)} · perm draws {NPERM} · boot draws {NBOOT}")
print(f"OBSERVED max |contrast| = {L3.contrast.abs().max():.3f} pt · "
      f"permutation max null 95th pct = {np.percentile(perm_max,95):.3f} pt · "
      f"FAMILYWISE p = {L3.perm_p_familywise.iloc[0]:.4f}")
