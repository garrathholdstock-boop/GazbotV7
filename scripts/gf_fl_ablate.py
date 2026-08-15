#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 5: THE ABLATION. Does the FLOW half of FBREAK do any work at all?

FBREAK is two rules stapled together: a 15-minute range BREAK, and a >=z aggressor-flow event
agreeing with it. The sweep says the pair makes money. That is not yet a FLOW-LED finding — it is
only a FLOW-LED finding if removing the flow condition makes it worse.

So, same exit, same costs, same one-position-at-a-time book, four versions:

  FBREAK      break + flow agreeing (|fz| >= z, sign = break direction)   <- the candidate
  BRKONLY     break, NO flow condition at all                             <- the ablation
  BRKAGAINST  break + flow DISAGREEING (the VACUUM-flavoured break)       <- the mirror
  FLOWONLY    flow event, no break                                        <- already FBURST, re-run
                                                                            here at the same exit

If BRKONLY >= FBREAK, the edge is the BREAKOUT and this section's honest verdict is that the flow
label contributes nothing — which is a finding about the CLUSTER, and it outranks the gate.

Also sweeps the breakout LOOKBACK and extends the HOLD past the sweep's 60-minute right edge, since
the sweep's best cells sat exactly on that edge (an edge-of-grid optimum is not a proven one).

Writes reports/friday_v7/sections/fl/ablate.json
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
from gf_fl_cands import _mk, load_feat, run, splits  # noqa: E402

DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"
OUT = f"{DIR}/ablate.json"


def breaks(df, look=15):
    hi = df["hi"].rolling(look, min_periods=look).max().shift(1)
    lo = df["lo"].rolling(look, min_periods=look).min().shift(1)
    up = df["close"] > hi
    dn = df["close"] < lo
    return up, dn


def sig_variant(df, kind, z=2.0, look=15):
    up, dn = breaks(df, look)
    f = np.sign(df["flow"])
    ev = (df["fz"].abs() >= z) & df["fz"].notna()
    if kind == "FBREAK":
        m = ev & (((f > 0) & up) | ((f < 0) & dn))
        d = np.where(up, 1, -1)
    elif kind == "BRKONLY":
        m = up | dn
        d = np.where(up, 1, -1)
    elif kind == "BRKAGAINST":
        m = ev & (((f < 0) & up) | ((f > 0) & dn))
        d = np.where(up, 1, -1)
    elif kind == "FLOWONLY":
        m = ev
        d = np.sign(df["flow"])
    else:
        raise SystemExit(kind)
    return _mk(df, m, pd.Series(d, index=df.index))


def main():
    df = load_feat()
    res = {"ablation": [], "lookback_sweep": [], "hold_extension": [], "splits": {}}

    # ── the four versions at the sweep's plateau exit ────────────────────────────────────────
    for kind in ("FBREAK", "BRKONLY", "BRKAGAINST", "FLOWONLY"):
        for z in ([2.0] if kind != "BRKONLY" else [0.0]):
            sigs = sig_variant(df, kind, z=z)
            trades, sc = run(kind, sigs, stop_k=1.5, targ_k=3.0, hold=60)
            sc["kind"], sc["z"] = kind, z
            res["ablation"].append(sc)
            res["splits"][kind] = splits(trades)
            pd.DataFrame(trades).to_csv(f"{DIR}/trades_abl_{kind}.csv", index=False)
            print(kind, sc, flush=True)

    # ── does the LOOKBACK matter, or is any break as good? ───────────────────────────────────
    for look in (5, 10, 15, 30, 60):
        for kind in ("FBREAK", "BRKONLY"):
            sigs = sig_variant(df, kind, z=2.0 if kind == "FBREAK" else 0.0, look=look)
            _, sc = run(kind, sigs, stop_k=1.5, targ_k=3.0, hold=60)
            sc.update(kind=kind, look=look)
            res["lookback_sweep"].append(sc)
            print("look", look, kind, sc["n"], sc["net"], sc["per_trade"], flush=True)

    # ── the hold was at the RIGHT EDGE of the sweep grid — push it out ───────────────────────
    for hold, tk in itertools.product((30, 60, 90, 120, 180), (3.0, 4.0)):
        for kind in ("FBREAK", "BRKONLY"):
            sigs = sig_variant(df, kind, z=2.0 if kind == "FBREAK" else 0.0)
            _, sc = run(kind, sigs, stop_k=1.5, targ_k=tk, hold=hold)
            sc.update(kind=kind, hold=hold, targ_k=tk)
            res["hold_extension"].append(sc)
            print("hold", hold, tk, kind, sc["n"], sc["net"], sc["per_trade"], flush=True)

    json.dump(res, open(OUT, "w"), indent=1)
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
