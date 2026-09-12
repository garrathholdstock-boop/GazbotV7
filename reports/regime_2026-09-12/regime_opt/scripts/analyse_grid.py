#!/usr/bin/env python3
"""Score a grid against its OWN empirical null. Usage: analyse_grid.py <csv> <label>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import regimelab as R

src = sys.argv[1]; label = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(src)
D = pd.read_csv(src)
D["allpos"] = (D.net > 0) & (D.TR > 0) & (D.VA > 0) & (D.TE > 0)
real = D[D.world == "REAL"]
null = D[D.world != "REAL"]
nw = null.world.nunique()

print(f"=== {label} ===")
print(f"CELLS SEARCHED (real): {len(real)}    null worlds: {nw}  null cells: {len(null)}")
print(f"\nSCREEN: net>0 at 1.25pt AND positive in TRAIN, VALIDATE and TEST")
r_rate = real.allpos.mean(); n_rate = null.allpos.mean()
print(f"  REAL passes {real.allpos.sum():>5} / {len(real)}  = {100*r_rate:5.1f}%")
print(f"  NULL passes {null.allpos.sum():>5} / {len(null)}  = {100*n_rate:5.1f}%   "
      f"(per world: " +
      ", ".join(f"{100*v:.1f}%" for v in null.groupby('world').allpos.mean()) + ")")
print(f"  -> the search returns {100*r_rate:.1f}% survivors where nothing-there returns "
      f"{100*n_rate:.1f}%")

print(f"\nBEST-CELL TEST (the only multiple-testing-honest comparison):")
for col, nm in (("net", "net pt/trade"), ("t", "t-stat")):
    rb = real[col].max()
    nb = null.groupby("world")[col].max()
    print(f"  best {nm:<12} REAL {rb:7.2f}   NULL worlds " +
          " ".join(f"{v:6.2f}" for v in nb) + f"   null max {nb.max():6.2f}")
rb = real[real.allpos][["net"]].max().get("net", np.nan)
print(f"\n  best net among three-period survivors: REAL {rb:.2f}")
nb = null[null.allpos].groupby("world").net.max()
print(f"  same for each null world: " + " ".join(f"{v:.2f}" for v in nb))

print(f"\nTOP 20 REAL CELLS BY NET (all three periods shown)")
cols = ["bar", "states", "fset", "clean", "win", "hold_min", "n", "gross", "gross_sd",
        "net", "t", "TR_n", "TR", "VA_n", "VA", "TE_n", "TE", "allpos"]
print(real.sort_values("net", ascending=False).head(20)[cols].round(2).to_string(index=False))

print(f"\nTOP 15 REAL CELLS THAT PASS THE THREE-PERIOD SCREEN")
S = real[real.allpos].sort_values("net", ascending=False).head(15)
print(S[cols].round(2).to_string(index=False) if len(S) else "  (none)")

print(f"\nMARGINALS - mean net pt by each dimension (real cells only)")
for d in ("bar", "states", "fset", "clean", "win", "hold_min"):
    m = real.groupby(d).agg(cells=("net", "size"), mean_net=("net", "mean"),
                            best=("net", "max"), pass_rate=("allpos", "mean"))
    mn = null.groupby(d).net.mean().rename("null_net")
    print(f"\n  {d}:")
    print(m.join(mn).round(3).to_string())
D.to_csv(src.replace(".csv", "_scored.csv"), index=False)
