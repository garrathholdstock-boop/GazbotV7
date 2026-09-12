#!/usr/bin/env python3
"""REV2 — is the gold "liquidity hole" a hole, or is it an ABSENT FEED?

The MGC dossier raises this stone and leaves it: the hole cell selects for an empty book, and an
empty book is what a quiet tape and a dropped feed look like alike. If the cell only pays when
nothing is trading, the bar-source fix (BUILD #1) cannot save it — a gate that needs a dead tape
cannot be filled on a live one.

So: take the PRODUCTION fire set (trade bars, which is what the live shadow folds), keep the hole
cell exactly as shipped, and split it by how busy the tape actually was — MGC trade prints per
minute over the 15 minutes before the fire, from the lake's own tick table. Then read the busiest
quartile. If the cell survives there, "hole" means hole. If all the money is in the quietest
quartile, it means absent feed and the whole line is decorative.
"""
from __future__ import annotations
import json
import os
import sys

import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")

from gf_mgc_barsource import atr14, book_rows, fires, raced, trade_bars   # noqa: E402
from gf_mgc_tape import load_quotes, minute_bars                          # noqa: E402


def prints_per_min(ts_ms_list, window_min=15):
    """MGC trade prints per minute over the window_min minutes ENDING at each fire (causal)."""
    from gazbot7 import lake
    c = lake.connect(symbol="MGC")
    t = c.execute("SELECT ts_ms FROM ticks WHERE symbol='MGC' ORDER BY ts_ms").df()["ts_ms"]
    arr = t.to_numpy()
    out = []
    for ts in ts_ms_list:
        a = np.searchsorted(arr, ts - window_min * 60_000, side="left")
        b = np.searchsorted(arr, ts, side="right")
        out.append((b - a) / window_min)
    return np.array(out, dtype=float)


def main():
    q = load_quotes()
    mid = minute_bars(q, col="mid")
    t0, t1 = int(q.index[0].value // 10**6), int(q.index[-1].value // 10**6)
    trd = trade_bars(t0, t1)
    trd = trd[(trd.index >= mid.index[0]) & (trd.index <= mid.index[-1])]
    bk = book_rows()
    bk_ts = bk["ts_ms"].to_numpy()

    out = {"window": [str(mid.index[0]), str(mid.index[-1])], "cells": {}}
    for label, bars in (("PROD (md trade bars)", trd), ("LAB (depth-mid bars)", mid)):
        d = raced(fires(bars), q, bk, bk_ts, bars=bars)
        if not len(d):
            continue
        rate = prints_per_min(d["ts"].to_numpy())
        d = d.assign(rate=rate)
        qs = np.quantile(rate, [0.25, 0.5, 0.75])
        d = d.assign(bucket=np.digitize(rate, qs))
        rec = {"n": int(len(d)), "net": round(float(d["pnl"].sum()), 2),
               "per": round(float(d["pnl"].mean()), 2),
               "win": round(float((d["pnl"] > 0).mean() * 100), 1),
               "rate_quartiles": [round(float(x), 1) for x in qs], "buckets": {}}
        print(f"\n{label}: hole PRIMARY  n={len(d)}  net ${d['pnl'].sum():,.0f}  "
              f"exp ${d['pnl'].mean():.2f}/tr  win {(d['pnl'] > 0).mean():.1%}")
        print(f"  trade prints/min quartile cuts: {qs.round(1)}")
        for b, g in d.groupby("bucket"):
            name = ["Q1 quietest", "Q2", "Q3", "Q4 busiest"][int(b)]
            rec["buckets"][name] = {"n": int(len(g)), "net": round(float(g["pnl"].sum()), 2),
                                    "per": round(float(g["pnl"].mean()), 2),
                                    "win": round(float((g["pnl"] > 0).mean() * 100), 1),
                                    "median_rate": round(float(g["rate"].median()), 1)}
            print(f"   {name:12s} n={len(g):>3}  net ${g['pnl'].sum():>8,.0f}  "
                  f"exp ${g['pnl'].mean():>7.2f}/tr  win {(g['pnl'] > 0).mean():>5.1%}  "
                  f"median {g['rate'].median():.0f} prints/min")
        out["cells"][label] = rec

    json.dump(out, open(f"{GB}/reports/friday_v7/sections/rev2_mgc_hole_by_rate.json", "w"),
              indent=1)
    print("\nwrote rev2_mgc_hole_by_rate.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def robust():
    """Strip-best and leave-one-day-out on the busiest-quartile cell, because a quartile cut found
    AFTER the fact is a sample percentile — the exact error the MGC dossier catches elsewhere."""
    import collections
    import datetime as dt
    q = load_quotes()
    mid = minute_bars(q, col="mid")
    t0, t1 = int(q.index[0].value // 10**6), int(q.index[-1].value // 10**6)
    trd = trade_bars(t0, t1)
    trd = trd[(trd.index >= mid.index[0]) & (trd.index <= mid.index[-1])]
    bk = book_rows(); bk_ts = bk["ts_ms"].to_numpy()
    d = raced(fires(trd), q, bk, bk_ts, bars=trd)
    rate = prints_per_min(d["ts"].to_numpy())
    cut = float(np.quantile(rate, 0.75))
    g = d[rate > cut]
    p = sorted(g["pnl"].to_numpy())
    net = sum(p)
    byday = collections.defaultdict(float)
    for ts, v in zip(g["ts"], g["pnl"]):
        byday[dt.datetime.fromtimestamp(ts / 1000, dt.UTC).date().isoformat()] += v
    print(f"\nQ4 busiest (>{cut:.1f} prints/min): n={len(p)} net ${net:,.0f} "
          f"exp ${net/len(p):.2f}/tr over {len(byday)} days")
    print(f"  strip best 1 ${net - p[-1]:,.0f} · best 3 ${net - sum(p[-3:]):,.0f} "
          f"· best 5 ${net - sum(p[-5:]):,.0f}")
    print(f"  worst leave-one-day-out ${min(net - v for v in byday.values()):,.0f}   "
          f"days green {sum(1 for v in byday.values() if v > 0)}/{len(byday)}")
