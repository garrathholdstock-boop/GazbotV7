#!/usr/bin/env python3
"""GF UNCLASS — STEP 9: the ONE promising thread, validated on 15 sessions instead of 6.

On the census week alone, boarding only when the FAR side of the book was thin (`far_share < 0.48`
at the minute before the fill) turned +$107 into +$735 and beat its placebo p95. n=76 trades on six
sessions is not a result, it is a hint — and capture.db keeps only 5 trading days of book, which is
why no study on this desk has ever tested it properly.

But the PARQUET LAKE carries MNQ `book` for **15 sessions (2026-07-31 .. 2026-08-15, 170M rows)**.
That is 2.5x the window and it is the correct source. This file rebuilds the per-minute L2 imbalance
from the lake and re-runs the cut with the full battery: parameter sweep, placebo, strip-3,
leave-one-day-out, long/short, cost stress.

    PYTHONPATH=src .venv/bin/python scripts/gf_uncl_book.py [--force]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect                                   # noqa: E402
from gf_rider_engine import (Racer, run_trades, stat, line, strip_best, loo_days,  # noqa: E402
                             placebo, cost_stress)
from gf_rider_tape import build                                    # noqa: E402
from gf_uncl_ride import signals                                   # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CACHE = "/home/alphabot/gazbot7/data/gf_uncl"
EX = dict(stop_a=2.5, targ_a=6.0, cap_min=120)
OUT = {}


def book_minutes(force=False) -> pd.DataFrame:
    os.makedirs(CACHE, exist_ok=True)
    p = f"{CACHE}/book_m1.pkl"
    if os.path.exists(p) and not force:
        return pd.read_pickle(p)
    con = connect(symbol="MNQ")
    print("aggregating 170M book rows to per-minute L1-L3 depth ...", flush=True)
    df = con.execute("""
        SELECT ts_ms // 60000 * 60 AS m,
               SUM(CASE WHEN side='bid' THEN size END) AS bid,
               SUM(CASE WHEN side='ask' THEN size END) AS ask,
               COUNT(*) AS nev
        FROM book WHERE level <= 3 GROUP BY 1 ORDER BY 1""").df()
    con.close()
    df.to_pickle(p)
    return df


def main():
    m1, s5 = build()
    racer = Racer(s5)
    bk = book_minutes("--force" in sys.argv)
    days = pd.to_datetime(bk.m, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    print(f"book minutes: {len(bk):,} over {days.nunique()} sessions {days.min()}..{days.max()}")
    OUT["book_sessions"] = int(days.nunique())

    sig = signals(m1, 10, 2.0)
    sig = sig[sig.day.isin(set(days))].reset_index(drop=True)      # only book-carrying sessions
    j = sig.copy()
    j["m"] = j["ts"] - 60                                          # strictly the minute BEFORE the fill
    j = j.merge(bk, on="m", how="left")
    j["far"] = np.where(j.side > 0, j.ask, j.bid)
    j["near"] = np.where(j.side > 0, j.bid, j.ask)
    j["far_share"] = j.far / (j.far + j.near)
    j = j[j.far_share.notna()].reset_index(drop=True)
    print(f"eligible fires with a book read: {len(j):,} over {j.day.nunique()} sessions")

    base = run_trades(racer, j, **EX)
    print("\n══ BASELINE (all eligible hours, book-carrying sessions, no book cut) ══")
    print("   " + line("no cut", stat(base)))
    OUT["baseline"] = stat(base)

    # ── the sweep: is there a plateau in the threshold, or one lucky cell? ────────────────────
    print("\n══ PARAMETER SWEEP — far_share threshold (thin far side = price runs into a vacuum) ══")
    rows = []
    for thr in (0.42, 0.44, 0.46, 0.48, 0.50, 0.52, 0.54):
        s = j[j.far_share < thr]
        if len(s) < 40:
            print(f"   far_share < {thr}: n_fires={len(s)} SKIPPED")
            continue
        tr = run_trades(racer, s, **EX)
        pl = placebo(racer, j, len(s), 200, **EX)
        st = stat(tr)
        beats = st["per"] > pl["per_p95"]
        print("   " + line(f"far_share < {thr}", st,
                           f"strip3=${strip_best(tr,3):>7,.0f}  placebo p95 ${pl['per_p95']:>6.2f} "
                           f"{'BEATS' if beats else 'fails'}"))
        rows.append(dict(thr=thr, **st, strip3=float(strip_best(tr, 3)),
                         pl_p95=pl["per_p95"], beats=bool(beats)))
    OUT["sweep"] = rows
    # the mirror image — a THICK far side should be the losing half if the read is causal
    for thr in (0.52, 0.54):
        s = j[j.far_share > thr]
        if len(s) >= 40:
            print("   " + line(f"far_share > {thr} (mirror)", stat(run_trades(racer, s, **EX))))
            OUT.setdefault("mirror", []).append(dict(thr=thr, **stat(run_trades(racer, s, **EX))))

    if not rows:
        json.dump(OUT, open(f"{SEC}/gf_uncl_book.json", "w"), indent=1, default=float)
        return
    best = max(rows, key=lambda r: r["net"])
    THR = best["thr"]
    cand = run_trades(racer, j[j.far_share < THR], **EX)
    print(f"\n══ BATTERY on far_share < {THR} ══")
    print("   " + line("candidate", stat(cand)))
    print(f"   STRIP-3-BEST      ${strip_best(cand,3):>8,.0f}   STRIP-5 ${strip_best(cand,5):>8,.0f}")
    lo = loo_days(cand)
    print(f"   LODO worst        ${lo.iloc[0]['without']:>8,.0f}  (drop {lo.iloc[0]['day']}, "
          f"${lo.iloc[0]['day_net']:,.0f} on {lo.iloc[0]['n_day']:.0f} trades)")
    print(f"   sessions green    {(lo['day_net']>0).sum()}/{len(lo)}")
    print("   " + line("LONG", stat(cand[cand.side > 0])))
    print("   " + line("SHORT", stat(cand[cand.side < 0])))
    for mlt in (2.0, 3.0):
        print("   " + line(f"COST x{mlt:g}", cost_stress(cand, mlt)))
    # shifted-signal placebo, keeping the book cut
    sh = j[j.far_share < THR].copy()
    sh["ts"] = sh["ts"] + 1800
    sh["entry"] = sh["ts"].map(m1.set_index("ts")["o"])
    sh = sh[sh.entry.notna()]
    print("   " + line("SHIFTED +30min (fake signal)", stat(run_trades(racer, sh, **EX))))
    # OOS split: first half of the book sessions vs second half
    ds = sorted(cand.day.unique())
    half = ds[len(ds) // 2]
    print("   " + line(f"first half (<{half})", stat(cand[cand.day < half])))
    print("   " + line(f"second half (>={half})", stat(cand[cand.day >= half])))
    print("\n   by segment:")
    from gf_rider_engine import by
    print(by(cand, "seg").to_string(index=False))
    OUT["battery"] = dict(thr=THR, stat=stat(cand), strip3=float(strip_best(cand, 3)),
                          strip5=float(strip_best(cand, 5)),
                          lodo_worst=float(lo.iloc[0]["without"]),
                          green_sessions=f"{(lo['day_net']>0).sum()}/{len(lo)}",
                          long=stat(cand[cand.side > 0]), short=stat(cand[cand.side < 0]),
                          cost_x2=cost_stress(cand, 2.0), cost_x3=cost_stress(cand, 3.0),
                          shift30=stat(run_trades(racer, sh, **EX)),
                          first_half=stat(cand[cand.day < half]),
                          second_half=stat(cand[cand.day >= half]),
                          by_seg=by(cand, "seg").to_dict("records"))
    json.dump(OUT, open(f"{SEC}/gf_uncl_book.json", "w"), indent=1, default=float)
    print(f"\n-> {SEC}/gf_uncl_book.json")


if __name__ == "__main__":
    main()
