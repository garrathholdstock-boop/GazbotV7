"""CHOP-SCALP 2026-08-29 — the full grave list on the EXTENDED 21-day tape.

Same 17 named candidates as the 2026-08-25 study, same 48-cell target/stop grid, now with four
more trading days. Reported per candidate as the MEDIAN $/trade over its whole grid (the plateau
number -- a max over 48 cells is a search result, not an edge) plus the ORIG/NEW split so every
grave shows whether it died the same way twice.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, load_events
from cs2_sweep import sequential, F, CANDS, GRID

OUT3 = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs3"
ORIG = ["2026-07-31"] + [f"2026-08-{x:02d}" for x in (3,4,5,6,7,10,11,12,13,14,17,18,19,20,21,24)]
NEW  = ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]

d = load_events()
print(f"[events] {len(d):,} over {d.date.nunique()} days")
rows = []
for name in CANDS:
    m = F(d, name)
    for tp, sp in GRID:
        sub = d[m]
        if not len(sub):
            continue
        o = pd.concat([sequential(g.sort_values("dts"), tp, sp) for _, g in sub.groupby("date")],
                      ignore_index=True)
        if len(o) < 10:
            continue
        r = dict(label=name, tp=tp, sp=sp, n=len(o), net=round(float(o.usd.sum()), 2),
                 per_tr=round(float(o.usd.mean()), 3), win=round(float((o.usd > 0).mean()), 3),
                 days=int(o.date.nunique()), open=int((o.kind == "OPEN").sum()))
        for tag, days in (("ORIG", ORIG), ("NEW", NEW)):
            s = o[o.date.isin(days)]
            r[f"n_{tag}"] = len(s)
            r[f"ptr_{tag}"] = round(float(s.usd.mean()), 3) if len(s) else np.nan
        rows.append(r)
R = pd.DataFrame(rows)
R.to_csv(f"{OUT3}/sweep_21d.csv", index=False)

g = R.groupby("label").agg(cells=("per_tr", "size"), pos=("per_tr", lambda s: int((s > 0).sum())),
                           med_ptr=("per_tr", "median"), max_ptr=("per_tr", "max"),
                           med_n=("n", "median"),
                           med_ORIG=("ptr_ORIG", "median"), med_NEW=("ptr_NEW", "median")
                           ).round(3).sort_values("med_ptr", ascending=False)
print(f"\n=== GRAVE LIST — 21 days, median $/trade over each candidate's 48-cell grid ===")
print(g.to_string())
g.to_csv(f"{OUT3}/graves_21d.csv")
print(f"\n[cells] {len(R)}   candidates with ANY positive cell: "
      f"{int((g.pos>0).sum())}/{len(g)}")
print(f"[wrote] {OUT3}/sweep_21d.csv, {OUT3}/graves_21d.csv")
