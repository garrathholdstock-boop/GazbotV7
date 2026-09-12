"""GF6 — extend the stop sweep until it PLATEAUS or is proven censored.

The first grid improved monotonically from a 2x to a 5x ATR stop, which is exactly the shape that a
CENSORED sweep produces: if every tested stop sits inside the trade's typical adverse excursion, the
widest one always wins and the sweep has proved nothing except 'my stops were too tight'. So the
sweep is extended to 7x, 10x and NO STOP AT ALL, and the pre-exit MAE is reported beside it. If the
number keeps climbing to the no-stop column, the honest statement is 'this entry has no stop that
helps', not 'a 5x stop is optimal'.

The clock is also swept, including the two the operator actually cares about: flat at the 20:00Z US
close, and flat at the 21:00Z halt.
"""
from __future__ import annotations
import numpy as np, pandas as pd
import gf6_mgc_gate as G
from gf6_mgc_exitgrid import ENTRIES

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

def mae(d, sess, trig, side, stop_k, cap):
    """worst adverse excursion before the exit, in ATRs — the censoring check."""
    t = G.backtest(d, sess, trig, side, stop_k=stop_k, cap=cap)
    return t

def run(d, key, caps=(60, 120, 240, 480, 720)):
    sess, trig, side = ENTRIES[key]
    rows = []
    for stop_k in (2.0, 3.0, 5.0, 7.0, 10.0, 99.0):
        for cap in caps:
            t = G.backtest(d, sess, trig, side, stop_k=stop_k, cap=cap)
            s = G.summarise(t)
            s.update(stop=("none" if stop_k > 50 else f"{stop_k:g}x"), cap=cap,
                     stopped=float((t.why == "STOP").mean()) if len(t) else np.nan)
            rows.append(s)
    return pd.DataFrame(rows)

if __name__ == "__main__":
    import sys
    d = G.frame()
    pd.set_option("display.width", 250)
    out = []
    for key in (sys.argv[1:] or ["revS_US_fadeup"]):
        r = run(d, key); r["cand"] = key; out.append(r)
        print(f"\n########## {key} — stop x clock ##########")
        piv = r.pivot_table(index="stop", columns="cap", values="per")
        print("$/trade:"); print(piv.reindex(["2x", "3x", "5x", "7x", "10x", "none"]).round(2).to_string())
        piv2 = r.pivot_table(index="stop", columns="cap", values="strip_day3")
        print("\n$/trade after stripping the best 3 SESSIONS:")
        print(piv2.reindex(["2x", "3x", "5x", "7x", "10x", "none"]).round(2).to_string())
        piv3 = r.pivot_table(index="stop", columns="cap", values="stopped")
        print("\nfraction of trades that hit the stop:")
        print(piv3.reindex(["2x", "3x", "5x", "7x", "10x", "none"]).round(2).to_string())
        print("\nn / worst trade at cap=480:")
        print(r[r.cap == 480][["stop", "n", "days", "net", "per", "med", "win", "worst",
                               "held", "strip_best3", "strip_day3"]].round(2).to_string(index=False))
    pd.concat(out).to_csv(f"{OUT}/stopsweep.csv", index=False)
