"""GF6 — the clock. Every trigger I built was beaten by 'short one lot at a fixed time', so the clock
has to be measured properly before any of them can be judged.

Sweep EVERY half hour of the session, both sides, several holding times. A real intraday seasonality
is a smooth curve with a plateau; a cherry-picked hour is a lone spike beside two negative neighbours.
"""
from __future__ import annotations
import numpy as np, pandas as pd
import gf6_mgc_gate as G
from gf6_mgc_verdict import _walk

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

def clock(d, side, stop_k, cap, step=30):
    frames = {sd: g.reset_index(drop=True) for sd, g in d.groupby("sday")}
    rows = []
    for hhmm in range(0, 1440, step):
        v, dd = [], []
        for sd, g in frames.items():
            k = g.index[g.hhmm == hhmm]
            if not len(k): continue
            r = _walk(g, [int(k[0])], side, stop_k, cap)
            if r: v.append(r[0]); dd.append(sd)
        if len(v) < 100: continue
        s = pd.Series(v, index=dd)
        days = sorted(s.index); mid = len(days) // 2
        order = s.sort_values(ascending=False).index
        mo = s.groupby([x[:7] for x in s.index]).mean()
        rows.append(dict(t=f"{hhmm//60:02d}:{hhmm%60:02d}", n=len(v), per=s.mean(),
                         med=float(s.median()), win=float((s > 0).mean()),
                         h1=s[s.index.isin(days[:mid])].mean(),
                         h2=s[s.index.isin(days[mid:])].mean(),
                         mo_pos=int((mo > 0).sum()), mo_n=len(mo),
                         strip3=float(s[~s.index.isin(order[:3])].mean())))
    return pd.DataFrame(rows)

if __name__ == "__main__":
    d = G.frame()
    pd.set_option("display.width", 260)
    out = []
    for side, sname in ((-1, "SHORT"), (+1, "LONG")):
        for stop_k, cap in ((7.0, 480), (7.0, 240), (99.0, 240)):
            r = clock(d, side, stop_k, cap)
            r["side"] = sname; r["cfg"] = f"stop{'none' if stop_k>50 else f'{stop_k:g}x'} cap{cap}m"
            out.append(r)
    a = pd.concat(out)
    a.to_csv(f"{OUT}/clock.csv", index=False)
    for cfg in a.cfg.unique():
        for sname in ("SHORT", "LONG"):
            g = a[(a.cfg == cfg) & (a.side == sname)]
            if g.empty: continue
            print(f"\n===== enter {sname} at a fixed clock time, {cfg} =====")
            print(g[["t", "n", "per", "med", "win", "h1", "h2", "mo_pos", "mo_n",
                     "strip3"]].round(2).to_string(index=False))
