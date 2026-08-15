#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 5b: WHICH HALF OF THE FLOW CONDITION IS DOING THE WORK?

Step 5 showed break+flow-agreeing (+$6.09/tr) beats break-alone (-$1.29) and flow-alone (-$3.94).
But it ALSO showed break+flow-DISAGREEING at +$14.08/tr on 85 trades — and if both signs of the flow
event work, then what the filter is really detecting is the SIZE of the flow event, not its
DIRECTION. That distinction decides what this section is allowed to claim: a directional FLOW-LED
footprint, or an ACTIVITY filter wearing a directional label.

Five versions of the same break, same exit, same costs:
  BRK_FLOWAGREE   break + |fz|>=2 with the flow agreeing        (= FBREAK)
  BRK_FLOWANY     break + |fz|>=2, EITHER sign                  (the magnitude-only version)
  BRK_FLOWAGAINST break + |fz|>=2 with the flow disagreeing
  BRK_RVOL        break + raw VOLUME surge (rvol>=R), no signed flow at all
  BRK_NONE        break, nothing else
plus a sweep of the flow threshold so the "how big does the event have to be" question has a curve
instead of one guess.

Writes reports/friday_v7/sections/fl/ablate2.json
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("GF_FL_TICK_CACHE", "40")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from gf_fl_ablate import breaks  # noqa: E402
from gf_fl_cands import _mk, load_feat, run, splits  # noqa: E402

DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"
OUT = f"{DIR}/ablate2.json"
EXIT = dict(stop_k=1.5, targ_k=3.0, hold=60)


def variant(df, kind, z=2.0, rvol=2.0, look=15):
    up, dn = breaks(df, look)
    f = np.sign(df["flow"])
    ev = (df["fz"].abs() >= z) & df["fz"].notna()
    d = pd.Series(np.where(up, 1, -1), index=df.index)
    if kind == "BRK_FLOWAGREE":
        m = ev & (((f > 0) & up) | ((f < 0) & dn))
    elif kind == "BRK_FLOWANY":
        m = ev & (up | dn)
    elif kind == "BRK_FLOWAGAINST":
        m = ev & (((f < 0) & up) | ((f > 0) & dn))
    elif kind == "BRK_RVOL":
        m = (df["rvol"] >= rvol) & (up | dn)
    elif kind == "BRK_NONE":
        m = up | dn
    else:
        raise SystemExit(kind)
    return _mk(df, m, d)


def main():
    df = load_feat()
    res = {"variants": [], "flow_threshold_curve": [], "rvol_curve": [], "splits": {}}
    for kind in ("BRK_FLOWAGREE", "BRK_FLOWANY", "BRK_FLOWAGAINST", "BRK_RVOL", "BRK_NONE"):
        sigs = variant(df, kind)
        trades, sc = run(kind, sigs, **EXIT)
        sc["kind"] = kind
        res["variants"].append(sc)
        res["splits"][kind] = splits(trades)
        pd.DataFrame(trades).to_csv(f"{DIR}/trades_ab2_{kind}.csv", index=False)
        print(kind, sc, flush=True)

    for z in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0):
        for kind in ("BRK_FLOWAGREE", "BRK_FLOWANY"):
            _, sc = run(kind, variant(df, kind, z=z), **EXIT)
            sc.update(kind=kind, z=z)
            res["flow_threshold_curve"].append(sc)
            print("z", z, kind, sc["n"], sc["net"], sc["per_trade"], flush=True)

    for rv in (1.0, 1.5, 2.0, 3.0, 4.0):
        _, sc = run("BRK_RVOL", variant(df, "BRK_RVOL", rvol=rv), **EXIT)
        sc.update(kind="BRK_RVOL", rvol=rv)
        res["rvol_curve"].append(sc)
        print("rvol", rv, sc["n"], sc["net"], sc["per_trade"], flush=True)

    json.dump(res, open(OUT, "w"), indent=1)
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
