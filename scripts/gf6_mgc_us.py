"""GF6 — the US session is the only place the split-half test survived. Interrogate it per SIDE.

The 2x2 needs LONG and SHORT separately, so the whole-session average is not good enough: 'gold
mean-reverts in the US session' could be one side doing all the work.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from gf6_mgc_map import load, VPP, COST, boot

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

def prep(df, w=30, k=1.0):
    d = df.copy()
    d["up"] = d[f"ret{w}"] >= k * d.atr60 * np.sqrt(w / 14)
    d["dn"] = d[f"ret{w}"] <= -k * d.atr60 * np.sqrt(w / 14)
    return d

def block(d, label):
    rows = []
    for sname, s in d.groupby("sess"):
        for h in (30, 60, 120):
            f = s[f"fwd{h}"]
            for t, sg, cell in (("UP", -1, "REVERSION-SHORT"), ("DN", +1, "REVERSION-LONG")):
                m = s[t.lower()] & f.notna()
                if m.sum() < 200: continue
                v = sg * f[m] * VPP - COST
                lo, hi = boot(s.sday[m].values, v.values, n=300)
                rows.append(dict(block=label, sess=sname, cell=cell, h=h, n=int(m.sum()),
                                 days=int(s.sday[m].nunique()), usd=v.mean(),
                                 med=float(np.median(v)), win=float((v > 0).mean()),
                                 lo=lo, hi=hi))
    return pd.DataFrame(rows)

def main():
    d = prep(load())
    ds = sorted(d.sday.unique()); mid = len(ds) // 2
    parts = [block(d, "FULL"),
             block(d[d.sday.isin(ds[:mid])], "H1"),
             block(d[d.sday.isin(ds[mid:])], "H2")]
    r = pd.concat(parts)
    r.to_csv(f"{OUT}/us_sides.csv", index=False)
    pd.set_option("display.width", 200)
    for cell in ("REVERSION-SHORT", "REVERSION-LONG"):
        print(f"\n===== {cell} — fade the move, $/trade net of ${COST:.2f} =====")
        p = r[r.cell == cell].pivot_table(index=["sess", "h"], columns="block", values="usd")
        n = r[r.cell == cell].pivot_table(index=["sess", "h"], columns="block", values="n")
        out = p[["FULL", "H1", "H2"]].round(2)
        out["n_full"] = n["FULL"].astype(int)
        out["held"] = np.where(np.sign(p.H1) == np.sign(p.H2), "yes", "NO")
        print(out.to_string())

if __name__ == "__main__":
    main()
