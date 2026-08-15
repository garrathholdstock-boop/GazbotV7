#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 3: the parameter sweep, and the ESCALATION candidate the top-15 built.

Two jobs.

(1) SWEEP. Every threshold in step 1 was a guess (fz>=2, stop 1xATR, target 2xATR, 30-min clock).
    The rule of this desk is that a guess has to be swept and PROVEN, and that an edge which exists
    at exactly one cell and nowhere near it is a curve-fit tell, not an edge. So each candidate is
    swept over z x stop x target x hold and the whole surface is reported — plateau or spike.

(2) THE ESCALATION CANDIDATE. Step 2 found the FLOW-LED footprint only appears in the BIGGEST runs
    (8.4% of all 344 runs wear the label, 18% of the top 50, 28% of the top 25, 40% of the top 15),
    and that every one of the six top-15 FLOW-LED runs ignited between 13:30 and 14:30 UTC on an
    elevated-ATR tape. FBIG is that profile turned into a mechanical gate: a big flow event, in the
    US ignition window, with ATR above its own median. It is the narrowest, most-selected thing this
    section can build — which is exactly why it gets the placebo treatment in step 4.

Writes reports/friday_v7/sections/fl/sweep.json
"""
from __future__ import annotations

import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("GF_FL_TICK_CACHE", "40")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from gf_fl_cands import BUILDERS, load_feat, run, splits  # noqa: E402
from gf_fl_engine import score  # noqa: E402

DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"
OUT = f"{DIR}/sweep.json"


def sig_fbig(df, z=2.5, atr_min_pct=0.5, t0=13 * 60 + 25, t1=14 * 60 + 30, **kw):
    """The top-15 profile, mechanised: a >=z flow event, inside the US ignition window, on a tape
    whose 15-min ATR is above its own median for the sample. Direction = the flow's."""
    a = df["atr15"]
    thr = a.quantile(atr_min_pct)
    m = ((df["fz"].abs() >= z) & df["fz"].notna() & (a >= thr)
         & (df["minute_of_day"] >= t0) & (df["minute_of_day"] < t1))
    from gf_fl_cands import _mk
    return _mk(df, m, np.sign(df["flow"]))


BUILDERS["FBIG"] = sig_fbig


def cell(df, name, z, stop_k, targ_k, hold, extra=None):
    sigs = BUILDERS[name](df, z=z, **(extra or {}))
    trades, sc = run(name, sigs, stop_k=stop_k, targ_k=targ_k, hold=hold)
    sc.update(z=z, stop_k=stop_k, targ_k=targ_k, hold=hold)
    return trades, sc


def main():
    df = load_feat()
    res = {}

    # ── (2) first: the escalation candidate, blanket + splits ────────────────────────────────
    tr, sc = cell(df, "FBIG", 2.5, 1.0, 2.0, 30)
    res["FBIG_base"] = sc
    res["FBIG_splits"] = splits(tr)
    pd.DataFrame(tr).to_csv(f"{DIR}/trades_FBIG.csv", index=False)
    print("FBIG base:", sc)

    # ── (1) the sweeps ───────────────────────────────────────────────────────────────────────
    grids = {
        "FBURST": dict(z=[1.0, 1.5, 2.0, 2.5, 3.0], stop_k=[0.5, 1.0, 1.5], targ_k=[1.5, 2.0, 3.0],
                       hold=[15, 30, 60]),
        "FBREAK": dict(z=[1.0, 1.5, 2.0, 2.5], stop_k=[0.5, 1.0, 1.5], targ_k=[1.5, 2.0, 3.0],
                       hold=[15, 30, 60]),
        "FDWELL": dict(z=[1.0, 1.5, 2.0, 2.5], stop_k=[0.5, 1.0, 1.5], targ_k=[1.5, 2.0, 3.0],
                       hold=[15, 30, 60]),
        "FBIG": dict(z=[1.5, 2.0, 2.5, 3.0, 4.0], stop_k=[0.5, 1.0, 1.5], targ_k=[1.5, 2.0, 3.0],
                     hold=[15, 30, 60]),
        "FFADE": dict(z=[1.5, 2.0, 2.5, 3.0], stop_k=[0.5, 1.0, 1.5], targ_k=[1.5, 2.0, 3.0],
                      hold=[15, 30, 60]),
    }
    for name, g in grids.items():
        rows = []
        for z, sk, tk, h in itertools.product(g["z"], g["stop_k"], g["targ_k"], g["hold"]):
            trades, sc = cell(df, name, z, sk, tk, h)
            # the HOME-segment score matters more than the blanket one for a routed gate
            sp = splits(trades)
            sc["by_regime"] = {k: (v["n"], v["net"], v["per_trade"]) for k, v in sp["regime"].items()}
            sc["by_session"] = {k: (v["n"], v["net"], v["per_trade"]) for k, v in sp["session"].items()}
            rows.append(sc)
            print(f"{name} z={z} stop={sk} targ={tk} hold={h} -> n={sc['n']} net={sc['net']} "
                  f"$/tr={sc['per_trade']}", flush=True)
        rows.sort(key=lambda r: -(r["net"] or 0))
        res[name] = rows
        json.dump(res, open(OUT, "w"), indent=1)
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
