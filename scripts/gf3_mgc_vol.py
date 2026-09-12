#!/usr/bin/env python3
"""GF3_MGC VOL — does gold's COMPRESSION predict its EXPANSION? The straddle cell, re-opened.

    PYTHONPATH=src .venv/bin/python scripts/gf3_mgc_vol.py

★ WHY THIS IS BEING RE-RUN AFTER BEING REFUTED. gf_MGC.md 2.2 killed the breakout-either-way cell on
22 days with a clean table: the tightest 20-minute-range quintile went on to move LESS than average
(-$6.23), and rank corr(20-min range, next 60-min size) was +0.036. The premise of a straddle - tight
now means big soon - looked simply false.

But that test measured the RAW 20-minute range, and on a tape where rank corr(ATR, next-60-min size)
is +0.412, the raw range is mostly a proxy for the volatility LEVEL. Sorting on it sorts on ATR, and
"high ATR now -> big move next" is volatility clustering, which is not a coil at all.

The question a straddle actually asks is different: **is this quiet RELATIVE TO ITS OWN recent
volatility, and does that relative quiet pay?** That is `range20 / ATR`, not `range20`. On the
320-day tape the two measures disagree completely, so both are computed here, side by side, on the
same rows - and then the thing is actually TRADED, because a gradient in absolute dollars can still
be worth nothing once the stop is scaled to the same small ATR.

★ THE TRADE, if the gradient is real: a genuine either-way entry. Bracket the current price with a
stop-entry above and below at +/- k x ATR, take whichever fills, stop the loser's distance, and ride
the winner. No direction is called anywhere - which is the point, because gold's DIRECTION is the
thing this desk has refuted six ways.

MGC = $10.00/point, tick 0.10pt = $1.00. Fee $1.50 per ROUND TRIP.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_cells import Racer, five_second, stat  # noqa: E402
from gf_mgc_tape import VPP, FEE_RT, build_tape  # noqa: E402
from gf3_mgc_year import BarRacer, label, load_year  # noqa: E402

pd.set_option("display.width", 250)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
R: dict = {}


def line(t: str) -> None:
    print("\n" + "=" * 104 + f"\n{t}\n" + "=" * 104, flush=True)


def gradients(y: pd.DataFrame) -> None:
    """The two compression measures, on identical rows, in dollars AND in ATR units."""
    z = y.dropna(subset=["atr"]).copy()
    z["rng20"] = z["high"].rolling(20).max() - z["low"].rolling(20).min()
    z["fwd60"] = (z["close"].shift(-60) - z["close"]).abs()
    z = z.dropna(subset=["rng20", "fwd60"])
    z = z[(z["atr"] > 0) & np.isfinite(z["rng20"]) & (z["rng20"] > 0)]
    z["comp_norm"] = z["rng20"] / z["atr"]
    z["fwd_atr"] = z["fwd60"] / z["atr"]
    R["n_minutes"] = int(len(z))
    R["days"] = int(z["day"].nunique())
    print(f"  n = {len(z):,} minutes over {z['day'].nunique()} days\n")

    for meas, lbl in (("rng20", "RAW 20-min range   (last week's measure)"),
                      ("comp_norm", "20-min range / ATR (relative quiet)")):
        z["q"] = pd.qcut(z[meas].rank(method="first"), 5,
                         labels=["Q1 tightest", "Q2", "Q3", "Q4", "Q5 widest"])
        g = z.groupby("q", observed=True).agg(n=("fwd60", "size"), fwd_usd=("fwd60", "mean"),
                                              fwd_ATR=("fwd_atr", "mean"), atr=("atr", "mean"))
        g["fwd_usd"] = g["fwd_usd"] * VPP
        g["vs_all_usd"] = g["fwd_usd"] - z["fwd60"].mean() * VPP
        g["vs_all_ATR"] = g["fwd_ATR"] - z["fwd_atr"].mean()
        print(f"  --- sorted on {lbl} ---")
        print(g.round(3).to_string())
        rc = float(z[meas].rank().corr(z["fwd60"].rank()))
        rn = float(z[meas].rank().corr(z["fwd_atr"].rank()))
        print(f"  rank corr vs |fwd60| in $: {rc:+.3f}     vs |fwd60| in ATR units: {rn:+.3f}\n")
        R[f"grad_{meas}"] = {"table": {str(k): [int(v["n"]), round(float(v["fwd_usd"]), 2),
                                                round(float(v["fwd_ATR"]), 3), round(float(v["vs_all_usd"]), 2),
                                                round(float(v["vs_all_ATR"]), 3)] for k, v in g.iterrows()},
                             "rank_corr_dollars": round(rc, 3), "rank_corr_atr": round(rn, 3)}


def straddle(y: pd.DataFrame, racer: BarRacer, *, comp_max: float, trig_k: float, stop_k: float,
             arm_k: float | None, trail_k: float | None, target_k: float | None,
             cap_min: int, cool_min: int = 60, slip_pt: float = 0.0) -> pd.DataFrame:
    """Either-way breakout. At a qualifying minute, arm stop-entries at +/- trig_k x ATR. Whichever
    level trades first (searched forward bar by bar, LOW checked before HIGH so ties go against us)
    is the entry; the trade then runs the given exit. No direction is ever called."""
    z = y.dropna(subset=["atr"]).copy()
    z["rng20"] = z["high"].rolling(20).max() - z["low"].rolling(20).min()
    z["comp"] = z["rng20"] / z["atr"]
    z = z[(z["atr"] > 0) & np.isfinite(z["comp"])]
    # comp_max is a QUANTILE of gold's own compression distribution (1.0 = no filter). Absolute
    # thresholds do not transfer: on 1-min bars a 20-min range is several ATRs by construction.
    sel = z if comp_max >= 1.0 else z[z["comp"] <= z["comp"].quantile(comp_max)]
    hi, lo, idx = y["high"].to_numpy(), y["low"].to_numpy(), y.index
    pos = {t: i for i, t in enumerate(idx)}
    out, last = [], None
    for ts, row in sel.iterrows():
        if last is not None and (ts - last).total_seconds() < cool_min * 60:
            continue
        i = pos.get(ts)
        if i is None or i + 2 >= len(idx):
            continue
        a = float(row["atr"]); ref = float(row["close"])
        up, dn = ref + trig_k * a, ref - trig_k * a
        side, j = 0, None
        for k in range(i + 1, min(i + 1 + 60, len(idx))):      # 60-min arming window
            if lo[k] <= dn:
                side, j = -1, k; break
            if hi[k] >= up:
                side, j = 1, k; break
        if side == 0 or j is None or j + 1 >= len(idx):
            continue
        last = ts
        # ⚠ CAUSALITY. Bar j's HIGH/LOW is what told us the level broke, and a bar's extremes are
        # only known once it has CLOSED. Entering at bar j's open would be buying at a price we only
        # chose because we had already seen the rest of that bar - a guaranteed favourable fill and
        # a pure look-ahead. It inflated this cell to +$71,608 before it was caught. Entry is
        # therefore the open of bar j+1, the first price genuinely available after the signal.
        j = j + 1
        res = racer.race(idx[j], side, stop_pts=stop_k * a,
                         arm_pts=arm_k * a if arm_k else None,
                         trail_pts=trail_k * a if trail_k else None,
                         target_pts=target_k * a if target_k else None,
                         cap_min=cap_min, cross_pt=0.15, slip_pt=slip_pt)
        if res:
            out.append({"ts": idx[j], "day": row["day"], "side": side, "atr": a,
                        "regime": row["regime"], "session": row["session"],
                        "comp": round(float(row["comp"]), 3), **res})
    return pd.DataFrame(out)


def show(tag, d, w=48) -> dict:
    s = stat(d)
    lo = stat(d[d["side"] > 0]) if not d.empty else s
    sh = stat(d[d["side"] < 0]) if not d.empty else s
    print(f"  {tag:<{w}} n={s['n']:<5} net={s['net']:>+8.0f} win={s['win']:>5.1f}% $/tr={s['per']:>+7.2f} "
          f"| L {lo['n']:>4}/{lo['per']:>+7.2f} S {sh['n']:>4}/{sh['per']:>+7.2f}")
    return {"pooled": s, "long": lo, "short": sh}


def main() -> None:
    y = label(load_year())
    line("1. ★★ THE TWO COMPRESSION MEASURES — same 320 days, same rows, opposite answers")
    gradients(y)
    print("  READ IT PLAINLY: sorting on the RAW range mostly sorts on ATR (rank corr ATR vs next-60")
    print("  size = +0.412), so it measures volatility CLUSTERING, not a coil. Dividing by ATR asks")
    print("  the straddle's actual question - and the sign flips. Both are true of their own measure.")

    racer = BarRacer(y)
    line("2. IS THE GRADIENT TRADEABLE? — the either-way breakout, swept (320 days, 1-min bars)")
    R["straddle"] = {}
    print("  entry: stop-orders +/- trig x ATR around the close of a compressed minute, 60-min arming\n")
    for comp_max, trig, stop, arm, trail, cap in (
            (0.20, 0.75, 2.0, 1.5, 1.5, 240), (0.20, 1.0, 3.0, 2.0, 2.0, 480),
            (0.33, 0.75, 2.0, 1.5, 1.5, 240), (0.33, 1.0, 3.0, 2.0, 2.0, 480),
            (0.50, 0.75, 2.0, 1.5, 1.5, 240), (0.50, 1.0, 3.0, 2.0, 2.0, 480),
            (0.50, 0.5, 1.5, 1.0, 1.0, 240), (0.33, 0.5, 1.5, 1.0, 1.0, 240)):
        d = straddle(y, racer, comp_max=comp_max, trig_k=trig, stop_k=stop, arm_k=arm,
                     trail_k=trail, target_k=None, cap_min=cap)
        R["straddle"][f"compQ{comp_max} trig{trig} stop{stop} chand{arm}/{trail} cap{cap}"] = show(
            f"comp <= Q{comp_max:.2f}  trig {trig}  stop {stop}  chand {arm}/{trail}  cap {cap}", d)

    line("3. THE CONTROL — the SAME either-way entry with NO compression filter")
    print("  If the uncompressed tape pays the same, the compression is doing nothing and the")
    print("  straddle is just a breakout gate wearing a coil's clothes.\n")
    R["control"] = {}
    for trig, stop, arm, trail, cap in ((0.75, 2.0, 1.5, 1.5, 240), (1.0, 3.0, 2.0, 2.0, 480),
                                        (0.5, 1.5, 1.0, 1.0, 240)):
        d = straddle(y, racer, comp_max=1.0, trig_k=trig, stop_k=stop, arm_k=arm,
                     trail_k=trail, target_k=None, cap_min=cap)
        R["control"][f"NOFILTER trig{trig} stop{stop} chand{arm}/{trail} cap{cap}"] = show(
            f"NO compression filter  trig {trig}  stop {stop}  chand {arm}/{trail}", d)

    line("4. THE BEST STRADDLE CELL, TAKEN APART")
    best = straddle(y, racer, comp_max=0.33, trig_k=1.0, stop_k=3.0, arm_k=2.0, trail_k=2.0,
                    target_k=None, cap_min=480)
    if not best.empty:
        v = best["true_pnl"].sort_values()
        byday = best.groupby("day")["true_pnl"].sum()
        bm = best.copy(); bm["ym"] = pd.to_datetime(bm["day"]).dt.strftime("%Y-%m")
        g = bm.groupby("ym")["true_pnl"].agg(["count", "sum"]).round(0)
        print(g.to_string())
        bat = {"n": int(len(v)), "net": round(float(v.sum()), 0),
               "strip_best_3": round(float(v.iloc[:-3].sum()), 0),
               "strip_best_10": round(float(v.iloc[:-10].sum()), 0),
               "drop_best_day": round(float(byday.sum() - byday.max()), 0),
               "days_green": round(100.0 * float((byday > 0).mean()), 1),
               "green_months": [int((g["sum"] > 0).sum()), int(len(g))]}
        print("\n  " + "   ".join(f"{k}={v_}" for k, v_ in bat.items()))
        print("\n  by session:")
        print(best.groupby("session")["true_pnl"].agg(["count", "sum", "mean"]).round(2).to_string())
        print("\n  slippage:")
        for t in (0, 1, 2, 3):
            vv = best["true_pnl"] - t * 0.10 * 2 * VPP
            print(f"    +{t} tick/leg   net {vv.sum():>+8.0f}   $/tr {vv.mean():>+6.2f}")
        R["best_cell"] = bat
        R["best_by_month"] = {k: [int(v_["count"]), float(v_["sum"])] for k, v_ in g.iterrows()}

    with open(f"{OUT}/gf3_mgc_vol.json", "w") as fh:
        json.dump(R, fh, indent=1, default=str)
    print(f"\nwrote {OUT}/gf3_mgc_vol.json")


if __name__ == "__main__":
    main()
