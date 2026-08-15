#!/usr/bin/env python3
"""GF UNCLASS — STEP 2: RIDE IT, and sweep the EXIT WIDE before judging the entry.

The entry is deliberately dumb and direction-agnostic, exactly as the operator specified: at the
close of minute t, if the last w minutes have covered >= k x ATR net in ONE direction, take that
direction at the open of minute t+1. No prediction, no classification, boarded late on purpose.

The UNCLASS bucket is defined by the census waterfall as *not* 13:00-15:00 UTC, so this study runs
on the UNCLASS-ELIGIBLE tape only: every hour of the session EXCEPT the 13-15 cash-open window.
That is not a convenience — it is what the label means, and it is what makes this phase's home turf
disjoint from the pooled rider's 13:00-20:00 window (which benches 20 of the 34 members outright).

Three independent results this week said the EXIT is the game, so the grid is swept wide (stops to
4xATR, targets to 10xATR and "no target") BEFORE any conclusion about the entry.

Segments are the operator's: never one blanket config across the whole tape.
    ASIA   00:00-06:00   EUROPE 06:00-13:00   US-PM 15:00-20:00   LATE 20:00-24:00
and cross-cut by the desk's own five ATR/ER regimes.

    PYTHONPATH=src .venv/bin/python scripts/gf_uncl_ride.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gf_rider_engine import Racer, run_trades, stat, line, by      # noqa: E402
from gf_rider_tape import build                                    # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CACHE = "/home/alphabot/gazbot7/data/gf_uncl"
CENSUS_WK = ("2026-08-09", "2026-08-14")


def segment(hh: pd.Series) -> pd.Series:
    s = pd.Series("US-OPEN", index=hh.index, dtype=object)   # 13-15, NOT part of UNCLASS
    s[hh < 6] = "ASIA"
    s[(hh >= 6) & (hh < 13)] = "EUROPE"
    s[(hh >= 15) & (hh < 20)] = "US-PM"
    s[hh >= 20] = "LATE"
    return s


def signals(m1: pd.DataFrame, w: int, k: float, *, eligible_only: bool = True) -> pd.DataFrame:
    """Thrust fires on the CLOSE of t; the fill is the OPEN of t+1 — it can never see its own bar."""
    d = m1.copy()
    net = d[f"net{w}"]
    fire = net.abs() >= k * d["atr"]
    d["side"] = np.sign(net.fillna(0.0)).astype(int)
    d["entry"] = d["o"].shift(-1)            # next bar's open
    d["ts_fill"] = d["ts"].shift(-1)
    # the fill bar must be the very next minute of the SAME session block
    ok = fire & d["entry"].notna() & (d["ts_fill"] == d["ts"] + 60) & d["atr"].notna() & (d["side"] != 0)
    if eligible_only:
        ok &= ~((d["hh"] >= 13) & (d["hh"] < 15))            # UNCLASS excludes the cash open
    s = d[ok].copy()
    s["ts"] = s["ts_fill"].astype("int64")
    s["seg"] = segment(s["hh"])
    return s[["ts", "side", "entry", "atr", "atr_pr", "day", "hh", "seg", "regime", "er15",
              "rvol", "flow15", "has_flow", "v", "vol30", f"net{w}"]].rename(
                  columns={f"net{w}": "net"}).reset_index(drop=True)


def main():
    os.makedirs(CACHE, exist_ok=True)
    m1, s5 = build()
    racer = Racer(s5)
    print(f"tape: {m1.day.nunique()} sessions  {m1.day.min()}..{m1.day.max()}  {len(m1):,} minutes")

    # ── how common is the fire? (a run-catcher that fires every other minute is not a catcher) ──
    print("\n══ FIRE RATE on the UNCLASS-eligible tape ══")
    for w in (5, 10, 15):
        for k in (1.5, 2.0, 2.5, 3.0):
            s = signals(m1, w, k)
            print(f"   w={w:>2} k={k:<4}  {len(s):>6,} fires  "
                  f"({100*len(s)/len(m1):>5.2f}% of minutes)  {len(s)/m1.day.nunique():>6.1f}/session")

    # ── STEP 2: THE EXIT GRID, wide, per segment. Base entry w=10 k=2.0 (the pooled study's) ────
    W, K, CAP = 10, 2.0, 120
    sig = signals(m1, W, K)
    print(f"\nbase signal w={W} k={K}: {len(sig):,} fires")
    print(sig.groupby("seg").size().to_string())

    rows = []
    stops = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    targs = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, np.inf]
    print(f"\n══ EXIT GRID — net $ (n) per SEGMENT, cap {CAP}min, entry w={W} k={K} ══")
    for seg in ("ASIA", "EUROPE", "US-PM", "LATE", "ALL-ELIGIBLE"):
        ss = sig if seg == "ALL-ELIGIBLE" else sig[sig.seg == seg]
        if not len(ss):
            continue
        print(f"\n-- {seg}  (n_fires={len(ss)}) --")
        hdr = "  stop\\targ " + "".join(f"{('inf' if not np.isfinite(t) else f'{t:g}'):>13}" for t in targs)
        print(hdr)
        for sa in stops:
            cells = []
            for ta in targs:
                t = run_trades(racer, ss, stop_a=sa, targ_a=ta, cap_min=CAP)
                st = stat(t)
                cells.append(f"{st['net']:>8,.0f}({st['n']:>3d})")
                rows.append(dict(seg=seg, stop=sa, targ=(None if not np.isfinite(ta) else ta), **st))
            print(f"  {sa:>4}     " + "".join(f"{c:>13}" for c in cells))

    G = pd.DataFrame(rows)
    G.to_pickle(f"{CACHE}/exitgrid.pkl")
    json.dump(G.replace({np.nan: None}).to_dict("records"),
              open(f"{SEC}/gf_uncl_exitgrid.json", "w"), indent=1, default=float)

    print("\n══ BEST CELL PER SEGMENT (by $/trade, n>=20) ══")
    for seg, g in G[G.n >= 20].groupby("seg"):
        b = g.sort_values("per", ascending=False).head(3)
        for _, r in b.iterrows():
            print(f"   {seg:<14} stop={r.stop} targ={r.targ if r.targ else 'inf':<5} "
                  f"n={r.n:>4.0f} net=${r.net:>8,.0f} {r.win:>5.1f}%w ${r.per:>7.2f}/tr pf={r.pf}")

    print(f"\n-> {SEC}/gf_uncl_exitgrid.json")


if __name__ == "__main__":
    main()
