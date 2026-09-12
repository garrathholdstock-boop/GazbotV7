"""GF6 — is the US short just gold falling? Price the DRIFT directly, then net it off.

Every candidate below is a short. Over this sample gold went 4049 -> 5037 -> 4398, and the second
half is a long slide. So before any gate is believed, measure what a lot held short for the same
length of time makes with NO trigger at all, three ways:
    all-minute  short at EVERY minute of the home window     (the map's control)
    fixed-time  short ONCE per session at a fixed clock time (the honest desk control)
    buy&hold    the raw drift of the contract over the sample
"""
from __future__ import annotations
import numpy as np, pandas as pd
import gf6_mgc_gate as G
from gf6_mgc_exitgrid import ENTRIES
from gf6_mgc_verdict import _walk

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

def all_minute(d, sess, side, stop_k, cap, step=5):
    v = []
    for sd, g in d.groupby("sday"):
        g = g.reset_index(drop=True)
        idx = np.where((g.sess.values == sess) & np.isfinite(g.atr60.values))[0][::step]
        v += _walk(g, idx, side, stop_k, cap)
    return float(np.mean(v)), len(v)

def fixed(d, sess, side, stop_k, cap, hhmm):
    v = []
    for sd, g in d.groupby("sday"):
        g = g.reset_index(drop=True)
        k = g.index[g.hhmm == hhmm]
        if len(k): v += _walk(g, [int(k[0])], side, stop_k, cap)
    return float(np.mean(v)), len(v)

if __name__ == "__main__":
    d = G.frame()
    ds = sorted(d.sday.unique()); mid = len(ds)//2
    px = d.groupby("sday").close.last()
    print(f"MGC front-month close: {px.iloc[0]:.1f} ({ds[0]}) -> {px.iloc[mid]:.1f} ({ds[mid]}) "
          f"-> {px.iloc[-1]:.1f} ({ds[-1]})")
    print(f"a single lot held SHORT across the whole sample: "
          f"${(px.iloc[0]-px.iloc[-1])*G.VPP:,.0f};  first half ${(px.iloc[0]-px.iloc[mid])*G.VPP:,.0f}"
          f";  second half ${(px.iloc[mid]-px.iloc[-1])*G.VPP:,.0f}\n")
    rows = []
    for key in ("revS_US_fadeup",):
        sess, trig, side = ENTRIES[key]
        for stop_k, cap in ((99.0, 120), (99.0, 480), (5.0, 240), (7.0, 480)):
            t = G.backtest(d, sess, trig, side, stop_k=stop_k, cap=cap)
            am, an = all_minute(d, sess, side, stop_k, cap)
            fx = {f"{h//60:02d}:{h%60:02d}": fixed(d, sess, side, stop_k, cap, h)[0]
                  for h in (13*60+35, 14*60+30, 15*60, 16*60, 17*60, 18*60, 19*60)}
            rows.append(dict(cfg=f"stop{'none' if stop_k>50 else str(stop_k)+'x'} cap{cap}m",
                             gate_n=len(t), gate=t.pnl.mean(), all_min=am,
                             best_fixed=max(fx.values()), worst_fixed=min(fx.values()),
                             mean_fixed=float(np.mean(list(fx.values()))),
                             **{f"@{k}": v for k, v in fx.items()}))
    r = pd.DataFrame(rows)
    pd.set_option("display.width", 260)
    print(r.round(2).to_string(index=False))
    r.to_csv(f"{OUT}/drift_control.csv", index=False)
