#!/usr/bin/env python3
"""S08 — two things S07 forced into view.

(A) THE BASELINE. S07's L3 table says the regime-transition strategy itself is NEGATIVE on the
    book window: -3.5 to -9.4 pt/trade at 1.25pt friction. That is measured on the subset of
    transitions that HAVE book features, so it could be a selection artefact of my own join.
    Recomputed here straight from S02's transition table, which never touches the book at all.
    ⚠ This is NOT a contradiction of the incumbent: the incumbent's +0.82pt/+0.47pt is the mean
    over its WHOLE span (2025-09..2026-08, TRAIN+VALIDATE+TEST). This is the most recent 31
    sessions only. But it is the window the book exists for, and it sets what the book is being
    asked to rescue.

(B) THE CONTRARIAN READING, pre-registered from S06 rather than mined. S06 showed OFI's price
    impact is CONTEMPORANEOUS (r=+0.688 same-minute) and slightly NEGATIVE forward (-0.013 at
    +1min): transient impact that partly reverts. If that is real, side = -sign(book) should
    beat side = +sign(book). L1/L2 hit rates sat at 0.491-0.496 in EVERY cell, which is the
    same claim. So this is one named hypothesis with a stated direction, tested against a
    DAY-BLOCK SIGN-FLIP permutation of the whole L1/L2 grid — max|statistic| familywise, so a
    lucky cell cannot be reported as a finding.
"""
import duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
FRIC, NPERM, NBOOT = 1.25, 4000, 4000
rng = np.random.default_rng(90120)
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "800MB"})
rep = []

# ───────────────────────── (A) baseline, book never touched ─────────────────────────
tr = pd.read_csv(f"{OUT}/s02_transitions_bookwindow.csv")
alltr = pd.read_csv(f"{OUT}/s02_transitions_all.csv")

def boot(v, s, n=NBOOT):
    """Day-block bootstrap, vectorised through per-session sufficient statistics:
    resampling whole sessions means the bootstrap mean is (sum of picked session sums) /
    (sum of picked session counts). No concatenation, no python loop over draws."""
    ss, inv = np.unique(s, return_inverse=True)
    S = np.bincount(inv, weights=v, minlength=len(ss))
    N = np.bincount(inv, minlength=len(ss)).astype(float)
    pick = rng.integers(0, len(ss), size=(n, len(ss)))
    o = S[pick].sum(1) / N[pick].sum(1)
    return np.percentile(o, [2.5, 97.5])

rep.append("(A) BASELINE — the regime-transition strategy on the BOOK WINDOW (2026-07-31..09-11),")
rep.append("    straight from S02's transition table. Book features play no part in this number.")
rep.append(f"{'hold':>6}{'clean':>7}{'n':>6}{'net pt':>9}{'win%':>7}{'day-block 95% CI':>22}"
           f"{'$/trade':>10}")
for hold_m, col in [(30, "raw30"), (60, "raw60"), (90, "raw90")]:
    for cln in (False, True):
        q = tr[tr.clean == True] if cln else tr
        q = q[q[col].notna()]
        if len(q) < 30: continue
        v = q[col].values - FRIC
        lo, hi = boot(v, q.sess.values)
        rep.append(f"{hold_m:>5}m{'  yes' if cln else '   no':>9}{len(q):>6}{v.mean():>9.2f}"
                   f"{100*(v>0).mean():>6.0f}%{f'[{lo:+.2f}, {hi:+.2f}]':>22}{v.mean()*2:>10.2f}")
rep.append("    for contrast, the SAME cells over the incumbent's full span (all sessions on the")
rep.append("    capture tape 2026-07-15..09-11 is still short; this is the whole transition table):")
for hold_m, col in [(60, "raw60"), (90, "raw90")]:
    for cln in (False, True):
        q = alltr[alltr.clean == True] if cln else alltr
        q = q[q[col].notna()]
        v = q[col].values - FRIC
        rep.append(f"      {hold_m}m clean={cln!s:<5} n={len(q):<5} net {v.mean():+.2f} pt")

# ───────────────────────── (B) contrarian + familywise permutation ─────────────────────────
d = con.execute(f"select * from read_parquet('{OUT}/s05_decision_features.parquet')").df().sort_values("bt")
g = con.execute(f"select bt, sess, open, close from read_parquet('{OUT}/s02_bars15.parquet')").df().sort_values("bt").reset_index(drop=True)
bt2i = {b: i for i, b in enumerate(g.bt.values)}
op, cl, sv = g.open.values, g.close.values, g.sess.values
HOLDS = {"15m": 1, "30m": 2, "60m": 4, "90m": 6}
for lbl, h in HOLDS.items():
    o = np.full(len(d), np.nan)
    for r_, b in enumerate(d.bt.values):
        i = bt2i.get(b)
        if i is None or i+1+h >= len(g) or sv[i] != sv[i+h] or sv[i] != sv[i+1]: continue
        o[r_] = cl[i+h] - op[i+1]
    d["fwd_"+lbl] = o
trm = tr[["bt", "side", "clean"]]
d = d.merge(trm, on="bt", how="left"); d["is_tr"] = d.side.notna()

SIGNED = ["imb3", "imb_touch", "imb3_L", "imbT_L", "imb3_5", "ofi_n", "ofi5_n", "tsi", "tsi5", "slope_asym"]
NORMS = ["", "_zs", "_ztod"]
scopes = {"L1 all windows": d, "L2 transitions": d[d.is_tr],
          "L2 clean transitions": d[d.is_tr & (d.clean == True)]}

cells, keys = {}, []
for sc, sub in scopes.items():
    for f in SIGNED:
        for nz in NORMS:
            c = f+nz
            for lbl in HOLDS:
                s = sub[[c, "fwd_"+lbl, "sess"]].dropna()
                if len(s) < 60: continue
                k = (sc, c, lbl); keys.append(k)
                cells[k] = (np.sign(s[c].values), s["fwd_"+lbl].values, s.sess.values, len(s))

res = []
for k in keys:
    sg, y, ss, n = cells[k]
    con_pt = (-sg)*y - FRIC                      # CONTRARIAN: fade the book
    pro_pt = sg*y - FRIC
    lo, hi = boot(con_pt, ss)
    res.append(dict(scope=k[0], feat=k[1], hold=k[2], n=n,
                    pro_pt=round(pro_pt.mean(), 3), contra_pt=round(con_pt.mean(), 3),
                    contra_lo=round(lo, 2), contra_hi=round(hi, 2),
                    contra_hit=round((np.sign(-sg[y != 0]) == np.sign(y[y != 0])).mean(), 4),
                    gross_edge=round(abs((sg*y).mean()), 3)))
C = pd.DataFrame(res)

# familywise day-block sign-flip null on the GROSS statistic |mean(sign(book)*fwd)|,
# which is friction-free and therefore the same null for pro and contra.
# Vectorised day-block sign-flip: a whole session's signs flip together, so each cell's
# permuted mean is (F @ session_sums)/n with F the +/-1 draw matrix shared across all cells.
allsess = np.unique(d.sess.values.astype(str))
sidx = {s: i for i, s in enumerate(allsess)}
F = rng.choice(np.array([-1.0, 1.0]), size=(NPERM, len(allsess)))
pc = {}
PM = np.empty((NPERM, len(keys)))
for ci, k in enumerate(keys):
    sg, y, ss, n = cells[k]
    col = np.array([sidx[str(x)] for x in ss])
    Ssum = np.bincount(col, weights=sg*y, minlength=len(allsess))
    PM[:, ci] = np.abs(F @ Ssum) / n
    pc[k] = PM[:, ci]
pmax = PM.max(1)
C["perm_p_cell"] = [float((pc[k] >= abs((cells[k][0]*cells[k][1]).mean())).mean()) for k in keys]
obs = C.gross_edge.max()
C["perm_p_familywise"] = float((pmax >= obs).mean())
C.to_csv(f"{OUT}/s08_contrarian.csv", index=False)

rep.append("")
rep.append("(B) CONTRARIAN — fade the book instead of following it. 360 cells, 1.25pt friction.")
rep.append(f"    best gross |edge| anywhere in the grid = {obs:.3f} pt")
rep.append(f"    day-block sign-flip null, max over the grid: 95th pct = {np.percentile(pmax,95):.3f} pt, "
           f"99th = {np.percentile(pmax,99):.3f} pt")
rep.append(f"    FAMILYWISE p = {C.perm_p_familywise.iloc[0]:.4f}")
rep.append(f"    cells with contrarian net > 0 : {(C.contra_pt>0).sum()} / {len(C)}")
rep.append(f"    cells with contrarian CI excluding 0 : {((C.contra_lo>0)).sum()} / {len(C)}")
rep.append(f"    cell-level perm p<0.05 : {(C.perm_p_cell<0.05).sum()} (expected by chance: {0.05*len(C):.0f})")
rep.append("")
rep.append("    top 10 contrarian cells by net pt:")
top = C.sort_values("contra_pt", ascending=False).head(10)
rep.append(top[["scope", "feat", "hold", "n", "pro_pt", "contra_pt", "contra_lo", "contra_hi",
                "contra_hit", "perm_p_cell"]].to_string(index=False))
txt = "\n".join(rep); open(f"{OUT}/s08_baseline_and_contrarian.txt", "w").write(txt+"\n"); print(txt)
