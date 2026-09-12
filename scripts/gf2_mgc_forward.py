#!/usr/bin/env python3
"""GF2 MGC — THE FORWARD TEST. Last week's gold survivors, on tape they have never seen.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_forward.py

★ WHY THIS IS THE FIRST THING IN THE SECTION. The 2026-08-15 report proposed two gold candidates
(`mgc_hole_break_fade` reversion pair, `mgc_wall_break_go` momentum pair) fitted on a 22-day quote
tape ending 2026-08-14. Five trading days have happened since (08-17..08-21) and NOTHING in that
study could have seen them. That is a real held-out leg, arriving for free, and it outranks every
in-sample robustness test we could invent.

★ NO REFITTING. The spec is frozen exactly as §6.1 of last week's section wrote it. Anything I
change here I state; the point of a forward test is that you do not get to touch it.

★ REGIME LABELS ARE CUT ON THE IN-SAMPLE BLOCK ONLY and applied forward, so the labelling itself
carries no peek at the held-out days (last week's cuts were taken on the whole sample - a mild
in-sample convenience for LABELLING that would become a real leak the moment it straddles a split).

MGC $10.00/pt · fee $1.50/RT · both legs cross the ~0.30pt spread (true cost ~$7.50/RT).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_cells import (Racer, break_entries, five_second, run_entries, side_split, stat)  # noqa: E402
from gf_mgc_l2 import attach, load_book_5s  # noqa: E402
from gf_mgc_tape import atr, build_tape, eff_ratio, session_of  # noqa: E402

pd.set_option("display.width", 260)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf2"
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
SPLIT = "2026-08-17"          # first FORWARD day; everything before is what the 08-15 study saw
R: dict = {}


def regime_is_cuts(m: pd.DataFrame, is_mask: pd.Series) -> pd.DataFrame:
    """Same five-way regime as last week, but the percentile cuts come from the IN-SAMPLE block."""
    m = m.copy()
    m["atr"] = atr(m)
    m["er"] = eff_ratio(m["close"])
    m["session"] = session_of(m.index).values
    m["day"] = m.index.strftime("%Y-%m-%d")
    ins = m[is_mask]
    a_lo, a_hi = ins["atr"].quantile(0.33), ins["atr"].quantile(0.67)
    e_lo, e_hi = ins["er"].quantile(0.40), ins["er"].quantile(0.75)
    reg = pd.Series("NORMAL_CHOP", index=m.index)
    reg[(m["atr"] <= a_lo) & (m["er"] <= e_hi)] = "DEAD_CHOP"
    reg[(m["atr"] >= a_hi) & (m["er"] >= e_hi)] = "CLEAN_TREND"
    reg[(m["atr"] >= a_hi) & (m["er"] <= e_lo)] = "VIOLENT_WHIPSAW"
    reg[(m["atr"].between(a_lo, a_hi, inclusive="neither")) & (m["er"] >= e_hi)] = "BUILDING"
    m["regime"] = reg.values
    m.attrs["cuts"] = {"atr_p33": float(a_lo), "atr_p67": float(a_hi),
                       "er_p40": float(e_lo), "er_p75": float(e_hi)}
    return m


def blk(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return d[d["day"] < SPLIT], d[d["day"] >= SPLIT]


def show(name: str, r: pd.DataFrame) -> dict:
    i, f = blk(r)
    si, sf, sa = stat(i), stat(f), stat(r)
    print(f"\n{name}")
    print(f"  IN-SAMPLE  07-16..08-14   n={si['n']:>4}  {si['days']:>2}d  "
          f"net ${si['net']:>8,.0f}  {si['per']:>7.2f}/tr  win {si['win']:>5.1f}%  med {si['med']:>7.2f}")
    print(f"  ★ FORWARD  08-17..08-21   n={sf['n']:>4}  {sf['days']:>2}d  "
          f"net ${sf['net']:>8,.0f}  {sf['per']:>7.2f}/tr  win {sf['win']:>5.1f}%  med {sf['med']:>7.2f}")
    print(f"  ALL 27 days                n={sa['n']:>4}  {sa['days']:>2}d  "
          f"net ${sa['net']:>8,.0f}  {sa['per']:>7.2f}/tr  win {sa['win']:>5.1f}%")
    if not f.empty:
        bd = f.groupby("day")["true_pnl"].agg(["size", "sum"])
        print("     forward, day by day: " +
              "  ".join(f"{d[5:]} n={int(a)} ${b:+,.0f}" for d, (a, b) in bd.iterrows()))
        ss = side_split(f)
        print(f"     forward LONG  {ss['LONG']}")
        print(f"     forward SHORT {ss['SHORT']}")
    return {"is": si, "fwd": sf, "all": sa,
            "fwd_by_day": {d: [int(a), round(float(b), 2)]
                           for d, (a, b) in f.groupby("day")["true_pnl"].agg(["size", "sum"]).iterrows()}
            if not f.empty else {},
            "fwd_sides": side_split(f) if not f.empty else {}}


def main() -> None:
    m0, q = build_tape()
    is_mask = pd.Series(m0.index.strftime("%Y-%m-%d") < SPLIT, index=m0.index)
    m = regime_is_cuts(m0, is_mask)
    print("=" * 126)
    print("GF2 — MGC FORWARD TEST.  frozen 08-15 spec, run on 5 days it has never seen")
    print("=" * 126)
    print(f"tape: {m['day'].nunique()} days {m['day'].min()} .. {m['day'].max()}   "
          f"{len(m):,} minutes   split at {SPLIT}")
    print(f"IS minutes {int(is_mask.sum()):,}   FWD minutes {int((~is_mask).sum()):,}")
    print(f"regime cuts (IS only): {m.attrs['cuts']}")

    racer = Racer(five_second(q))
    print("\nloading 10-level MGC depth ...", flush=True)
    bk = load_book_5s()
    print(f"  {len(bk):,} book snapshots {bk.index.min()} .. {bk.index.max()}")

    e_all = attach(break_entries(m, fade=True), bk)
    e_all["day"] = e_all["ts"].dt.strftime("%Y-%m-%d")
    ei, ef = blk(e_all)
    print(f"\nBREAKS with a causal book read: {len(e_all)}   IS {len(ei)}  FORWARD {len(ef)}")
    print(f"  break rate: IS {len(ei)/max(ei['day'].nunique(),1):.1f}/day   "
          f"FWD {len(ef)/max(ef['day'].nunique(),1):.1f}/day")

    vac = e_all["obstacle"] == 0
    hole = (e_all["obstacle"] == 0) & (e_all["support"] == 0)
    wall = (e_all["ratio"] > 1) & e_all["ratio"].notna()
    for lbl, msk in (("vacuum obstacle==0", vac), ("double-hole obst==0 & supp==0", hole),
                     ("wall ratio>1", wall)):
        a, b = blk(e_all[msk.fillna(False)])
        print(f"  population {lbl:<30} IS {len(a):>4} ({100*len(a)/max(len(ei),1):>4.1f}%)   "
              f"FWD {len(b):>4} ({100*len(b)/max(len(ef),1):>4.1f}%)")
        R.setdefault("population", {})[lbl] = {"is": len(a), "fwd": len(b)}

    print("\n" + "=" * 126)
    print("THE FROZEN 08-15 SPEC, IN-SAMPLE vs FORWARD  (chandelier stop3/arm2/trail2, cap 480m)")
    print("=" * 126)

    R["primary_vacuum_fade"] = show(
        "[A] PRIMARY SHADOW ARM — mgc_hole_break_fade, obstacle==0, FADE the break",
        run_entries(racer, e_all[vac].reset_index(drop=True), **CHAND))

    R["refined_double_hole"] = show(
        "[B] REFINED ARM — obstacle==0 AND support==0 (the double hole), FADE",
        run_entries(racer, e_all[hole].reset_index(drop=True), **CHAND))

    ew = e_all[wall.fillna(False)].reset_index(drop=True).copy()
    ew["side"] = -ew["side"]
    R["wall_break_go"] = show(
        "[C] MOMENTUM ARM — mgc_wall_break_go, ratio>1, FOLLOW the break",
        run_entries(racer, ew, **CHAND))

    ec = e_all.reset_index(drop=True)
    R["control_all_fade"] = show(
        "[D] CONTROL — every break faded, NO book gate (the attribution control)",
        run_entries(racer, ec, **CHAND))
    ecf = ec.copy(); ecf["side"] = -ecf["side"]
    R["control_all_follow"] = show(
        "[E] CONTROL — every break followed, NO book gate",
        run_entries(racer, ecf, **CHAND))
    en = e_all[~vac & ~wall.fillna(False)].reset_index(drop=True)
    R["middle_fade"] = show("[F] THE MIDDLE BUCKET — book has no opinion, faded", run_entries(racer, en, **CHAND))

    json.dump(R, open(f"{OUT}/forward.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/forward.json")


if __name__ == "__main__":
    main()
