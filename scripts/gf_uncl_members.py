#!/usr/bin/env python3
"""GF UNCLASS — STEP 1: cluster the 34 sat-out UNCLASS runs, then ask whether they are BOARDABLE.

Operator, 2026-08-15: *"i feel like unclass gives you the right to say oh well we cant identify so we
move on. NO! find a way to RIDE them!"* — so the clustering here is NOT a gate on whether we attempt
the ride. It runs first only because it is cheap, and its output is used in STEP 2 as a FILTER
candidate, never as a precondition.

Two questions, in order:

  A. WHAT ARE THEY?  hour, direction, ATR regime at the run's start, pre-run efficiency, flow sign,
     what preceded them (was the run a continuation of the prior 30m, or a reversal of it).
  B. CAN WE BOARD THEM?  For a grid of (window w, thrust k) the detector "the last w minutes have
     covered >= k x ATR net in one direction" is walked forward from each run's start; the first
     minute it fires is the boarding point. We report how deep into the run we board and HOW MUCH OF
     THE MOVE IS STILL AHEAD at that point — the number that decides whether a late board is worth
     anything at all.

    PYTHONPATH=src .venv/bin/python scripts/gf_uncl_members.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys, os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gf_rider_tape import build                                    # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CENSUS_TXT = f"{SEC}/census_stdout.txt"
VPP = 2.00


def census_rows() -> pd.DataFrame:
    rows = []
    for ln in open(CENSUS_TXT):
        m = re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]\d+)\s+(\d+)\s+"
                     r"(caught|sat out|FOUGHT)\s+(\S+)\s+([+-]\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", ln)
        if m:
            ts = int(dt.datetime.strptime("2026-" + m.group(1), "%Y-%m-%d %H:%M")
                     .replace(tzinfo=dt.UTC).timestamp())
            rows.append(dict(tm=m.group(1), ts=ts, dir=m.group(2), move=int(m.group(3)),
                             ceil=int(m.group(4)), us=m.group(5), cl=m.group(11),
                             flow=None if m.group(8) == "—" else float(m.group(8))))
    return pd.DataFrame(rows)


def main():
    m1, s5 = build()
    m1 = m1.set_index("ts", drop=False)
    cr = census_rows()
    U = cr[(cr.cl == "UNCLASS") & (cr.us == "sat out")].reset_index(drop=True)
    print(f"sat-out UNCLASS runs: {len(U)}   ceiling ${U.ceil.sum():,.0f}   "
          f"({100*U.ceil.sum()/cr[cr.us=='sat out'].ceil.sum():.0f}% of the ${cr[cr.us=='sat out'].ceil.sum():,.0f} sat-out ceiling)")
    print(f"all sat-out runs: {len(cr[cr.us=='sat out'])}")

    # ── A. WHAT ARE THEY ───────────────────────────────────────────────────────────────────────
    ctx = []
    for r in U.itertuples():
        # the LAST CLOSED minute before the run started — everything here is causal
        row = m1[m1.ts <= r.ts]
        if not len(row):
            ctx.append({})
            continue
        p = row.iloc[-1]
        prior30 = p.net30
        ctx.append(dict(atr=p.atr, atr_pr=p.atr_pr, er15=p.er15, er30=p.er30, regime=p.regime,
                        rvol=p.rvol, hh=p.hh, dow=p.dow,
                        prior30=prior30,
                        cont=("CONT" if (prior30 > 0) == (r.move > 0) and abs(prior30) > 0.5 * p.atr
                              else "REV" if abs(prior30) > 0.5 * p.atr else "FLAT"),
                        day=p.day))
    C = pd.concat([U, pd.DataFrame(ctx)], axis=1)
    C["hbin"] = pd.cut(C.hh, [-.1, 6, 13, 15, 20, 24],
                       labels=["ASIA 00-06", "EUROPE 06-13", "US-OPEN 13-15", "US-PM 15-20", "LATE 20-24"])

    print("\n══ A. WHAT THE 34 UNCLASS SAT-OUT RUNS ARE ══")
    for col in ("hbin", "dir", "regime", "cont"):
        print(f"\n-- by {col} --")
        t = C.groupby(col, observed=True).agg(n=("move", "size"), ceil=("ceil", "sum"),
                                              med_move=("move", lambda s: s.abs().median()))
        t["pct"] = (100 * t.n / len(C)).round(0)
        print(t.to_string())

    print("\n-- the full member list --")
    print(C[["tm", "dir", "move", "ceil", "hbin", "regime", "cont", "atr", "atr_pr", "er15", "rvol"]]
          .round(2).to_string(index=False))

    # ── the pooled rider's own window benches most of this bucket ─────────────────────────────
    inwin = C[(C.hh >= 13) & (C.hh < 20)]
    print(f"\n★ {len(inwin)}/{len(C)} UNCLASS sat-out runs fall inside the POOLED rider's 13:00-20:00 window "
          f"(${inwin.ceil.sum():,.0f} of ${C.ceil.sum():,.0f}); "
          f"{len(C)-len(inwin)} runs / ${C.ceil.sum()-inwin.ceil.sum():,.0f} are OUTSIDE it and are benched by construction.")

    # ── B. CAN WE BOARD THEM ──────────────────────────────────────────────────────────────────
    print("\n══ B. BOARDING GRID — first minute the thrust detector fires INSIDE each run ══")
    print("   (fill at the NEXT minute's open; 'left' = points still ahead to the run's 15-min end,")
    print("    'left60' = best favourable excursion in the 60 minutes after boarding, both in ATR)")
    ts_arr = m1.ts.to_numpy()
    grid = []
    detail = {}
    for w in (5, 10, 15):
        for k in (1.0, 1.5, 2.0, 2.5):
            hits, mins_in, frac_left, r_left, r_left60 = 0, [], [], [], []
            rows = []
            for r in C.itertuples():
                seg = m1[(m1.ts >= r.ts) & (m1.ts <= r.ts + 900)]
                net = seg[f"net{w}"]
                fire = seg[(net.abs() >= k * seg.atr) & (np.sign(net) == (1 if r.move > 0 else -1))]
                if not len(fire):
                    continue
                f0 = fire.iloc[0]
                nxt = m1[m1.ts > f0.ts]
                if not len(nxt):
                    continue
                e = nxt.iloc[0]
                end = m1[m1.ts <= r.ts + 900]
                if not len(end):
                    continue
                endpx = end.iloc[-1].c
                side = 1 if r.move > 0 else -1
                left = (endpx - e.o) * side
                fw = m1[(m1.ts > e.ts) & (m1.ts <= e.ts + 3600)]
                best = ((fw.h.max() - e.o) if side > 0 else (e.o - fw.l.min())) if len(fw) else np.nan
                hits += 1
                mins_in.append((e.ts - r.ts) / 60)
                frac_left.append(100 * left / abs(r.move))
                r_left.append(left / f0.atr)
                r_left60.append(best / f0.atr)
                rows.append(dict(tm=r.tm, min_in=(e.ts - r.ts) / 60, pct_left=100 * left / abs(r.move),
                                 r_left=left / f0.atr, r_left60=best / f0.atr))
            if hits:
                grid.append(dict(w=w, k=k, caught=hits, of=len(C),
                                 med_min=float(np.median(mins_in)),
                                 med_pct_left=float(np.median(frac_left)),
                                 med_r_left=float(np.median(r_left)),
                                 med_r_left60=float(np.nanmedian(r_left60)),
                                 pos_frac=float(np.mean(np.array(frac_left) > 0))))
                detail[f"w{w}k{k}"] = rows
    G = pd.DataFrame(grid)
    print(G.round(2).to_string(index=False))

    json.dump(dict(members=C.drop(columns=["hbin"]).assign(hbin=C.hbin.astype(str))
                   .replace({np.nan: None}).to_dict("records"),
                   grid=G.to_dict("records"),
                   in_pooled_window=int(len(inwin)), ceiling=float(C.ceil.sum())),
              open(f"{SEC}/gf_uncl_members.json", "w"), indent=1, default=float)
    print(f"\n-> {SEC}/gf_uncl_members.json")


if __name__ == "__main__":
    main()
