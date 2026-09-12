"""GF6 — is the conditional map STRUCTURE, or is it 288 lottery tickets?

I tested 4 horizons x 4 sessions x 3 ATR buckets x 3 ER buckets x 2 triggers. At a 90% band you get
~29 'significant' cells from pure noise, and I kept ~40. The survivor list on its own is worth
nothing. Two tests that noise cannot pass:

  A. SIGN CONSISTENCY ACROSS HORIZON. A real reversion cell is reversion at 30, 60, 120 AND 240
     minutes. Noise picks a horizon at random. Count cells that agree on all four.
  B. SPLIT-HALF. Fit nothing; just ask whether the sign found in the FIRST half of the sessions
     survives into the SECOND half, cell by cell. Report the hit rate against the 50% coin.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from gf6_mgc_map import load, VPP, COST

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

def cells(df, w=30, k=1.0):
    d = df.copy()
    d["atr_b"] = pd.cut(d.atr_rel, [0, .8, 1.25, 99], labels=["CALM", "NORMAL", "HOT"])
    d["er_b"] = pd.cut(d.er60, [-.01, .08, .20, 1.01], labels=["CHOP", "MID", "TREND"])
    d["up"] = d[f"ret{w}"] >= k * d.atr60 * np.sqrt(w / 14)
    d["dn"] = d[f"ret{w}"] <= -k * d.atr60 * np.sqrt(w / 14)
    return d

def table(d, days=None):
    sub = d if days is None else d[d.sday.isin(days)]
    out = []
    for h in (30, 60, 120, 240):
        f = sub[f"fwd{h}"]
        for key, s3 in sub.groupby(["sess", "atr_b", "er_b"], observed=True):
            for t, sg in (("UP", +1), ("DN", -1)):
                m = s3[t.lower()] & f.loc[s3.index].notna()
                if m.sum() < 300: continue
                mom = (sg * f.loc[s3.index][m] * VPP - COST).mean()
                out.append(dict(h=h, sess=key[0], atr=str(key[1]), er=str(key[2]), trig=t,
                                n=int(m.sum()), mom=mom))
    return pd.DataFrame(out)

def main():
    df = cells(load())
    full = table(df)
    piv = full.pivot_table(index=["sess", "atr", "er", "trig"], columns="h", values="mom")
    piv = piv.dropna()
    sgn = np.sign(piv)
    agree = (sgn.abs().sum(axis=1) == 4) & (sgn.sum(axis=1).abs() == 4)
    print(f"cells with all four horizons present: {len(piv)}")
    print(f"cells whose SIGN agrees across all 4 horizons: {int(agree.sum())} "
          f"({100*agree.mean():.0f}%)   [coin-flip expectation 2/16 = 12.5%]")
    print(f"   of those, REVERSION (mom<0): {int((agree & (sgn[30] < 0)).sum())}   "
          f"MOMENTUM (mom>0): {int((agree & (sgn[30] > 0)).sum())}")
    print()
    print("=== the horizon-consistent cells, $/trade by hold length ===")
    print(piv[agree].round(1).to_string())
    piv[agree].to_csv(f"{OUT}/signcheck_consistent.csv")

    # ---- B. split half ----------------------------------------------------------------
    ds = sorted(df.sday.unique()); mid = len(ds) // 2
    a, b = table(df, ds[:mid]), table(df, ds[mid:])
    j = a.merge(b, on=["h", "sess", "atr", "er", "trig"], suffixes=("_a", "_b"))
    j = j[(j.n_a >= 300) & (j.n_b >= 300)]
    hit = float((np.sign(j.mom_a) == np.sign(j.mom_b)).mean())
    print(f"\nSPLIT-HALF: {len(j)} cells in both halves; sign held {100*hit:.1f}% "
          f"(coin = 50%). first half {ds[0]}..{ds[mid-1]}, second {ds[mid]}..{ds[-1]}")
    for s, g in j.groupby("sess"):
        print(f"   {s:7} n={len(g):3d} sign held {100*(np.sign(g.mom_a)==np.sign(g.mom_b)).mean():5.1f}%  "
              f"mean $/tr h1 {g.mom_a.mean():7.2f}  h2 {g.mom_b.mean():7.2f}")
    j.to_csv(f"{OUT}/signcheck_splithalf.csv", index=False)

if __name__ == "__main__":
    main()
