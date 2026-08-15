"""CHOP-DAY SCALP — Step 7: the robustness battery.

Applied identically to every candidate that reaches it, so nothing is graded on a
kinder ruler than anything else:

  per-day  ·  leave-one-day-out  ·  strip-the-best-3  ·  side symmetry
  cost stress  ·  regime split  ·  time-of-day split  ·  OOS leg (THIS WEEK)
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import gf_cs_bt as B
import gf_cs_lib as L

pd.set_option("display.width", 250)
CACHE: dict = {}


def battery(name, ks, kt, hold, params=None, label=""):
    print(f"\n{'='*100}\n### {label or name}   stop={ks} ATR  target={kt} ATR  hold={hold}s"
          f"   params={params or 'base'}\n{'='*100}")
    tr = B.backtest(name, ks, kt, hold, days=L.DAYS, params=params, cache=CACHE)
    if tr.empty:
        print("  no trades")
        return tr
    tr["seg"] = np.where(tr["day"].isin(L.IS_DAYS), "IS", "OOS")

    for seg in ["IS", "OOS"]:
        s = L.stats(tr[tr["seg"] == seg])
        print(f"  {seg:>4s}  n={s['n']:4d}  net=${s['net']:9.2f}  win={s['win']:5.1f}%  "
              f"$/trade={s['per']:7.2f}")
    s = L.stats(tr)
    print(f"  ALL   n={s['n']:4d}  net=${s['net']:9.2f}  win={s['win']:5.1f}%  "
          f"$/trade={s['per']:7.2f}")

    print("\n  -- per day --")
    d = tr.groupby("day").agg(n=("net", "size"), net=("net", "sum"),
                              w=("net", lambda x: (x > 0).mean()))
    d["win%"] = (100 * d["w"]).round(1)
    d["$/tr"] = (d["net"] / d["n"]).round(2)
    d["seg"] = ["OOS" if x in L.OOS_DAYS else "IS" for x in d.index]
    print(d[["seg", "n", "net", "win%", "$/tr"]].round(2).to_string())
    print(f"  green days: {(d['net']>0).sum()}/{len(d)}")

    print("\n  -- leave-one-day-out (net with that day removed) --")
    tot = tr["net"].sum()
    loo = [(day, round(tot - g["net"].sum(), 2)) for day, g in tr.groupby("day")]
    loo = pd.DataFrame(loo, columns=["day_removed", "net_without"])
    print(f"     min={loo['net_without'].min():.2f}  max={loo['net_without'].max():.2f}  "
          f"negative_after_removal={(loo['net_without']<0).sum()}/{len(loo)}")

    print("\n  -- strip the best trades --")
    srt = tr["net"].sort_values(ascending=False)
    for k in (1, 3, 5):
        print(f"     strip-{k}: ${tot - srt.head(k).sum():9.2f}   "
              f"($/trade {(tot - srt.head(k).sum())/(len(tr)-k):.2f})")

    print("\n  -- side symmetry --")
    g = tr.groupby("side").agg(n=("net", "size"), net=("net", "sum"))
    g["$/tr"] = (g["net"] / g["n"]).round(2)
    print(g.to_string())

    print("\n  -- cost stress ($/RT; base 1.50 + 1 tick entry slip already in) --")
    for extra in (0.0, 0.50, 1.00, 2.00):
        n2 = tot - extra * len(tr)
        print(f"     +${extra:4.2f}/RT: ${n2:9.2f}  ($/trade {n2/len(tr):6.2f})")

    print("\n  -- regime (ER30 of the entry bar) --")
    tr["reg"] = pd.cut(tr["er30"], [-1, 0.09, 0.20, 0.30, 1.01],
                       labels=["dead<0.09", "0.09-0.20", "0.20-0.30", "trend>0.30"])
    g = tr.groupby("reg", observed=True).agg(n=("net", "size"), net=("net", "sum"))
    g["$/tr"] = (g["net"] / g["n"]).round(2)
    print(g.to_string())

    print("\n  -- time of day --")
    g = tr.groupby("tod").agg(n=("net", "size"), net=("net", "sum"))
    g["$/tr"] = (g["net"] / g["n"]).round(2)
    print(g.to_string())

    print("\n  -- exit mix --")
    g = tr.groupby("reason").agg(n=("net", "size"), net=("net", "sum"))
    g["$/tr"] = (g["net"] / g["n"]).round(2)
    print(g.to_string())
    return tr


if __name__ == "__main__":
    for nm in (sys.argv[1:] or list(B.CANDIDATES)):
        battery(nm, 1.5, 0.75, 600)
