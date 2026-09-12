"""GF6 — the control that decides it: does the TRIGGER add anything over ALWAYS SHORT?

Gold fell from 5037 in February to 4398 in September. If the US session simply carried a downward
drift then 'short after an up-extension' pays for a reason that has nothing to do with the extension,
and the honest gate is 'short', not 'fade'. So every US number is scored three ways:

  triggered      short only after a 30-min up-extension of k ATR
  always_short   short at EVERY US minute, same holding time  (the best CONSTANT)
  placebo        short at the SAME NUMBER of US minutes, chosen at random, 200 draws
"""
from __future__ import annotations
import numpy as np, pandas as pd
from gf6_mgc_map import load, VPP, COST

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

def main(w=30, k=1.0):
    d = load()
    d["up"] = d[f"ret{w}"] >= k * d.atr60 * np.sqrt(w / 14)
    d["dn"] = d[f"ret{w}"] <= -k * d.atr60 * np.sqrt(w / 14)
    rng = np.random.default_rng(11)
    rows = []
    for sname, s in d.groupby("sess"):
        for h in (30, 60, 120):
            f = s[f"fwd{h}"]
            ok = f.notna()
            allshort = (-f[ok] * VPP - COST)
            alllong = (f[ok] * VPP - COST)
            for tname, m, side in (("fade-up SHORT", s.up & ok, -1),
                                   ("follow-dn SHORT", s.dn & ok, -1),
                                   ("fade-dn LONG", s.dn & ok, +1),
                                   ("follow-up LONG", s.up & ok, +1)):
                if m.sum() < 200: continue
                v = (side * f[m] * VPP - COST)
                base = allshort if side < 0 else alllong
                idx = np.arange(ok.sum())
                pl = np.array([base.values[rng.choice(idx, int(m.sum()), replace=False)].mean()
                               for _ in range(200)])
                rows.append(dict(sess=sname, h=h, arm=tname, n=int(m.sum()),
                                 usd=v.mean(), const=base.mean(),
                                 edge=v.mean() - base.mean(),
                                 pctile=float((pl < v.mean()).mean() * 100)))
    r = pd.DataFrame(rows)
    r.to_csv(f"{OUT}/const_control.csv", index=False)
    pd.set_option("display.width", 200)
    for sname in ("US", "LONDON", "ASIA", "LATE"):
        g = r[r.sess == sname]
        if g.empty: continue
        print(f"\n===== {sname} — $/trade, and what the trigger ADDS over the constant =====")
        print(g[["h", "arm", "n", "usd", "const", "edge", "pctile"]].round(2).to_string(index=False))

if __name__ == "__main__":
    main()
