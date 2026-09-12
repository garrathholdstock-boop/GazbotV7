#!/usr/bin/env python3
"""REV2 — Movement 3 §2's Family A/B split, recomputed on the UNSELECTED population.

WHY. This report documents, in Movement 3's VACUUM appendix, that `run_census.py`'s keep-strongest
dedup selects LOCAL EXTREMA: prior-5-minute direction agreement shifts 48.66% -> 22.55% across that
dedup, the VACUUM rate climbs 10.45% -> 14.01% -> 21.87%, and the finding "invalidates every pre-run
price-path statistic quoted off the run list". §3 of the same section obeys that and works on the
unselected population. §2's Family A/B split did not — it is computed on the 62 deduped runs.

So this re-runs §2's exact test (famA = pre-10-minute max volz >= 2.0 OR max atr_exp >= 1.15) on
EVERY minute of the census week whose forward-15-minute move clears the same 55-point threshold the
census uses, with no dedup at all. Same features, same window, same threshold, different population.

It reuses gf5_m3_lab's own minutes()/ticks_min()/pre() so the two numbers are comparable by
construction rather than by hope.

  PYTHONPATH=src .venv/bin/python scripts/rev2_family_unselected.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")

import gf5_m3_lab as L                                                    # noqa: E402

OUT = pathlib.Path(f"{GB}/reports/friday_v7/sections/rev2_family_unselected.json")
W0, W1 = "2026-08-23 22:00", "2026-08-28 21:00"
THRESH = 55.0            # the census's own qualifying move, in points
VPP = 2.0                # MNQ $/point — the "ceiling" column is one lot


def main() -> int:
    m = L.minutes().join(L.ticks_min()[["nt", "ntz", "flow", "fz"]], how="left")
    wk = m.loc[W0:W1].copy()

    # the SAME precursor test, as a rolling 10-minute lookback on every minute (no run list)
    pv = wk["volz"].rolling(10, min_periods=5).max().shift(1)
    pa = wk["atr_exp"].rolling(10, min_periods=5).max().shift(1)
    wk["famA"] = (pv >= 2.0) | (pa >= 1.15)
    wk["pre_volz"], wk["pre_atrexp"] = pv, pa

    big = wk[wk["fwd15"].abs() >= THRESH].dropna(subset=["famA"])
    res = {"window": [W0, W1], "threshold_pt": THRESH,
           "unselected_qualifying_minutes": int(len(big)),
           "all_minutes": int(wk["famA"].notna().sum()),
           "base_rate_pct": round(100 * float(wk["famA"].mean()), 1)}

    fam = {}
    for nm, g in (("A — a precursor is visible", big[big.famA]),
                  ("B — nothing to see", big[~big.famA])):
        fam[nm] = dict(
            n=int(len(g)),
            ceiling=int(round(float(g["fwd15"].abs().sum()) * VPP)),
            median_move=round(float(g["fwd15"].abs().median()), 0) if len(g) else None,
            med_volz=round(float(g["pre_volz"].median()), 2) if len(g) else None,
            med_atrexp=round(float(g["pre_atrexp"].median()), 2) if len(g) else None,
            up=int((g["fwd15"] > 0).sum()), dn=int((g["fwd15"] < 0).sum()))
    res["family_unselected"] = fam
    a, b = fam["A — a precursor is visible"], fam["B — nothing to see"]
    res["famA_share_of_qualifying_minutes"] = round(100 * a["n"] / max(1, a["n"] + b["n"]), 1)
    res["lift_vs_base_rate"] = round(
        res["famA_share_of_qualifying_minutes"] / max(1e-9, res["base_rate_pct"]), 3)

    # and the same thing on the DEDUPED census runs, recomputed here so both come from one process
    runs = L.census()
    sat = runs[runs.us == "sat out"].reset_index(drop=True)

    def pre(ts, col, agg="max"):
        w = m.loc[ts - pd.Timedelta(minutes=10): ts - pd.Timedelta(minutes=1), col].dropna()
        return np.nan if len(w) == 0 else float(w.max() if agg == "max" else w.mean())

    P = pd.DataFrame([{"move": abs(r.move), "ceil": r.ceil, "dir": r["dir"],
                       "volz": pre(r.ts, "volz"), "atr_exp": pre(r.ts, "atr_exp")}
                      for _, r in sat.iterrows()])
    P["famA"] = (P.volz >= 2.0) | (P.atr_exp >= 1.15)
    ded = {}
    for nm, g in (("A — a precursor is visible", P[P.famA]),
                  ("B — nothing to see", P[~P.famA])):
        ded[nm] = dict(n=int(len(g)), ceiling=int(g.ceil.sum()),
                       median_move=round(float(g.move.median()), 0) if len(g) else None,
                       med_volz=round(float(g.volz.median()), 2) if len(g) else None,
                       med_atrexp=round(float(g.atr_exp.median()), 2) if len(g) else None,
                       up=int((g["dir"] > 0).sum()), dn=int((g["dir"] < 0).sum()))
    res["family_deduped_census"] = ded
    res["famA_share_of_census_runs"] = round(100 * float(P.famA.mean()), 1)

    print(json.dumps(res, indent=2))
    OUT.write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
