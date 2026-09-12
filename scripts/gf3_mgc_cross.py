#!/usr/bin/env python3
"""GF3_MGC CROSS — gold against the Nasdaq on the same clock. The stone last week left unturned.

    PYTHONPATH=src .venv/bin/python scripts/gf3_mgc_cross.py

★ THE QUESTION, quoting gf_MGC.md section 13 verbatim:
    "Every source this desk has pointed at gold is gold's own price and gold's own book. The one
     genuinely different input we have never used is the relationship between MGC and MNQ on the
     same clock ... A break in gold that coincides with a matching break in the Nasdaq is a
     different event from one that does not, and nothing in this section can tell them apart."

★ WHY IT MATTERS FOR THE MOMENTUM CELLS SPECIFICALLY. Gold's momentum cells are the weak half of the
2x2 - `mgc_wall_break_go` fails the random-minute placebo and lost on last week's held-out leg. Every
momentum attack so far has been built on gold's OWN tape, which is the thing that is refuted. A
cross-asset confirm is a genuinely different input, and it is the only untried one we hold.

★ TWO TAPES, TWO JOBS.
    BOOK WINDOW  2026-07-16 .. 2026-08-24, MGC breaks with the L2 hole gate, MNQ from 5s lake bars.
                 High fidelity, small n. This is where a filter has to survive.
    PAIRED YEAR  2025-09-14 .. 2026-08-19, both symbols' backfill 1-min bars, ~11 months.
                 No book, coarse fills - but n in the thousands, so a cross-asset effect that is
                 real should be visible and one that is noise should not.

★ EVERY FILTER IS PLACEBO-CONTROLLED BY COUNT. A cut that keeps 40% of trades looks brilliant
whenever the 60% it dropped happened to lose; the only honest control is keeping the SAME NUMBER at
random, many times. That control has killed more gold ideas on this desk than any other test.

MGC = $10.00/point. MNQ = $2.00/point (used here only as a SIGNAL, never traded).
"""
from __future__ import annotations

import json
import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_cells import Racer, break_entries, five_second, run_entries, stat  # noqa: E402
from gf_mgc_l2 import attach, load_book_5s  # noqa: E402
from gf_mgc_tape import build_tape, atr as atr_fn  # noqa: E402
from gf3_mgc_forward import regime_with_frozen_cuts  # noqa: E402
from gf3_mgc_year import BarRacer, label, load_year, run as run_bar  # noqa: E402

pd.set_option("display.width", 250)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
LAKE = "/home/alphabot/gazbot7/data/tape/bars"
IS_END = "2026-08-15"
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
R: dict = {}


def line(t: str) -> None:
    print("\n" + "=" * 106 + f"\n{t}\n" + "=" * 106, flush=True)


def mnq_minutes(source: str) -> pd.DataFrame:
    """MNQ 1-minute closes. `daily` = the 5s lake files resampled (covers the book window);
    `backfill` = the year-long 1-min file."""
    c = duckdb.connect()
    if source == "backfill":
        df = c.execute(f"""SELECT bar_ts, open, high, low, close FROM
                           read_parquet('{LAKE}/MNQ/backfill_1min.parquet')
                           WHERE timeframe='1min' AND close>0 ORDER BY bar_ts""").df()
        df["ts"] = pd.to_datetime(df["bar_ts"], unit="s", utc=True)
        return df.set_index("ts")[["open", "high", "low", "close"]]
    df = c.execute(f"""SELECT bar_ts, open, high, low, close FROM
                       read_parquet('{LAKE}/MNQ/2026-*.parquet')
                       WHERE timeframe='5s' AND close>0 ORDER BY bar_ts""").df()
    df["ts"] = pd.to_datetime(df["bar_ts"], unit="s", utc=True)
    o = df.set_index("ts")["close"].resample("1min").ohlc().dropna()
    return o


def tag_cross(e: pd.DataFrame, x: pd.DataFrame, *, look: int = 60) -> pd.DataFrame:
    """Attach MNQ's state AT THE SIGNAL MINUTE. Strictly causal: everything is computed from bars
    at or before `sig_ts`, and the 60-min extreme is shifted so the signal bar is excluded."""
    x = x.copy()
    x["atr"] = atr_fn(x)
    x["hi"] = x["high"].rolling(look).max().shift(1)
    x["lo"] = x["low"].rolling(look).min().shift(1)
    x["r15"] = x["close"].diff(15)
    x["r60"] = x["close"].diff(60)
    xi = x.index.tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]").astype("int64")
    out = []
    for r in e.itertuples():
        v = np.int64(pd.Timestamp(r.sig_ts).value)
        i = int(np.searchsorted(xi, v, side="right")) - 1
        if i < 0 or i >= len(x):
            continue
        row = x.iloc[i]
        a = float(row["atr"]) if np.isfinite(row["atr"]) and row["atr"] > 0 else np.nan
        # is MNQ itself beyond its own 60-min extreme right now?
        mb = 0
        if np.isfinite(row["hi"]) and row["close"] >= row["hi"]:
            mb = 1
        elif np.isfinite(row["lo"]) and row["close"] <= row["lo"]:
            mb = -1
        r15a = float(row["r15"]) / a if (a and np.isfinite(row["r15"])) else np.nan
        # agreement is measured against the GOLD BREAK's direction, not the trade's
        agree = int(np.sign(r15a) == np.sign(r.brk)) if np.isfinite(r15a) and r15a != 0 else -1
        out.append({**{c: getattr(r, c) for c in e.columns},
                    "mnq_brk": mb, "mnq_r15_atr": round(r15a, 3) if np.isfinite(r15a) else np.nan,
                    "mnq_agree": agree,
                    "mnq_confirm": int(mb == r.brk and mb != 0),
                    "mnq_oppose": int(mb == -r.brk and mb != 0)})
    return pd.DataFrame(out)


def filter_placebo(d: pd.DataFrame, keep: pd.Series, *, runs: int = 200, seed: int = 20260825) -> dict:
    """Keep the SAME NUMBER of trades at random, `runs` times. The only honest control for a cut."""
    k = int(keep.sum())
    if k == 0 or k == len(d):
        return {"runs": 0}
    real = float(d.loc[keep, "true_pnl"].sum())
    rng = np.random.default_rng(seed)
    v = d["true_pnl"].to_numpy()
    nets = [float(v[rng.choice(len(v), size=k, replace=False)].sum()) for _ in range(runs)]
    beaten = sum(1 for x in nets if x >= real)
    return {"keep_n": k, "real": round(real, 0), "rand_mean": round(float(np.mean(nets)), 0),
            "beaten": beaten, "runs": runs,
            "pctile": round(100.0 * float(np.mean([x < real for x in nets])), 1)}


def show(tag, d, w=44) -> dict:
    s = stat(d)
    lo = stat(d[d["side"] > 0]) if not d.empty else s
    sh = stat(d[d["side"] < 0]) if not d.empty else s
    print(f"  {tag:<{w}} n={s['n']:<5} net={s['net']:>+8.0f} win={s['win']:>5.1f}% $/tr={s['per']:>+7.2f} "
          f"| L {lo['per']:>+7.2f} S {sh['per']:>+7.2f}")
    return {"pooled": s, "long": lo, "short": sh}


def main() -> None:
    # ══ PART A — THE BOOK WINDOW ═══════════════════════════════════════════════════════════════
    m_all, q = build_tape()
    _, cuts = regime_with_frozen_cuts(m_all[m_all["day"] < IS_END])
    m, _ = regime_with_frozen_cuts(m_all, cuts)
    print("loading depth + MNQ ...", flush=True)
    bk = load_book_5s()
    xn = mnq_minutes("daily")
    print(f"  MNQ 1-min from 5s lake bars: {len(xn):,} minutes  "
          f"{xn.index.min().date()} .. {xn.index.max().date()}")
    racer = Racer(five_second(q))

    e_raw = break_entries(m, look=60, margin_atr=0.10, cool=45, fade=True)
    eb = attach(e_raw, bk)
    e_prim = eb[eb["obstacle"] == 0].reset_index(drop=True)
    e_prim = tag_cross(e_prim, xn)
    e_rawc = tag_cross(eb.reset_index(drop=True), xn)
    d_prim = run_entries(racer, e_prim, **CHAND)
    d_raw = run_entries(racer, e_rawc, **CHAND)
    cov = d_prim["day"].nunique()
    print(f"  MGC hole-break fades with an MNQ read: n={len(d_prim)} over {cov} days "
          f"(08-25 has no MNQ lake bar yet and drops out)")
    R["coverage"] = {"n_prim": int(len(d_prim)), "days": int(cov)}

    line("A1. ★ DOES THE NASDAQ SPLIT THE GOLD BREAK? — the reversion arm (fade_primary, book window)")
    R["book_split"] = {}
    buckets = {
        "MNQ CONFIRMS the gold break (same-dir break)": d_prim["mnq_confirm"] == 1,
        "MNQ OPPOSES it (breaks the other way)": d_prim["mnq_oppose"] == 1,
        "MNQ is NOT breaking at all": d_prim["mnq_brk"] == 0,
        "MNQ 15-min drift AGREES with the break": d_prim["mnq_agree"] == 1,
        "MNQ 15-min drift OPPOSES the break": d_prim["mnq_agree"] == 0,
    }
    for lbl, sel in buckets.items():
        R["book_split"][lbl] = show(lbl, d_prim[sel])
    print()
    for lbl, sel in buckets.items():
        p = filter_placebo(d_prim, sel)
        if p.get("runs"):
            print(f"  filter-placebo  {lbl:<46} keep {p['keep_n']:<3} real {p['real']:>+6.0f} "
                  f"vs random {p['rand_mean']:>+6.0f}  beaten {p['beaten']}/{p['runs']} (pctile {p['pctile']})")
            R["book_split"][lbl]["placebo"] = p

    line("A2. ★★ THE FRESH MOMENTUM ATTACK — follow a gold break the Nasdaq CONFIRMS")
    print("  Every prior gold momentum gate used gold's own tape, and that family is refuted. This")
    print("  uses a different instrument as the confirm. Trading WITH the break, not against it:\n")
    R["momentum_cross"] = {}
    e_foll = break_entries(m, look=60, margin_atr=0.10, cool=45, fade=False)
    ebf = tag_cross(attach(e_foll, bk).reset_index(drop=True), xn)
    d_foll = run_entries(racer, ebf, **CHAND)
    mom = {
        "FOLLOW, blanket (control)": pd.Series(True, index=d_foll.index),
        "FOLLOW when MNQ confirms the break": d_foll["mnq_confirm"] == 1,
        "FOLLOW when MNQ drift agrees": d_foll["mnq_agree"] == 1,
        "FOLLOW when MNQ confirms AND book has a wall": (d_foll["mnq_confirm"] == 1) & (d_foll["obstacle"] > d_foll["support"]),
        "FOLLOW when MNQ confirms AND obstacle==0": (d_foll["mnq_confirm"] == 1) & (d_foll["obstacle"] == 0),
    }
    for lbl, sel in mom.items():
        R["momentum_cross"][lbl] = show(lbl, d_foll[sel])
    print()
    for lbl, sel in mom.items():
        if lbl.endswith("(control)"):
            continue
        p = filter_placebo(d_foll, sel)
        if p.get("runs"):
            print(f"  filter-placebo  {lbl:<46} keep {p['keep_n']:<3} real {p['real']:>+6.0f} "
                  f"vs random {p['rand_mean']:>+6.0f}  beaten {p['beaten']}/{p['runs']} (pctile {p['pctile']})")
            R["momentum_cross"][lbl]["placebo"] = p

    # ══ PART B — THE PAIRED YEAR ═══════════════════════════════════════════════════════════════
    line("B. THE PAIRED YEAR — same questions, ~11 months of MGC x MNQ minute bars, no book")
    y = label(load_year())
    xb = mnq_minutes("backfill")
    both = max(y.index.min(), xb.index.min())
    y2 = y[y.index >= both]
    print(f"  paired span {y2.index.min().date()} .. {min(y.index.max(), xb.index.max()).date()}  "
          f"({y2['day'].nunique()} MGC trading days)")
    yr = BarRacer(y)
    ey_f = tag_cross(break_entries(y2, look=60, margin_atr=0.10, cool=45, fade=True), xb)
    ey_o = tag_cross(break_entries(y2, look=60, margin_atr=0.10, cool=45, fade=False), xb)
    dy_f = run_bar(yr, ey_f, **CHAND)
    dy_o = run_bar(yr, ey_o, **CHAND)
    R["year_cross"] = {}
    print("\n  --- FADE the gold break (the reversion family) ---")
    for lbl, sel in (("blanket (control)", pd.Series(True, index=dy_f.index)),
                     ("MNQ CONFIRMS the break", dy_f["mnq_confirm"] == 1),
                     ("MNQ OPPOSES the break", dy_f["mnq_oppose"] == 1),
                     ("MNQ not breaking", dy_f["mnq_brk"] == 0),
                     ("MNQ drift AGREES", dy_f["mnq_agree"] == 1),
                     ("MNQ drift OPPOSES", dy_f["mnq_agree"] == 0)):
        R["year_cross"][f"FADE :: {lbl}"] = show(lbl, dy_f[sel])
    print("\n  --- FOLLOW the gold break (the momentum family) ---")
    for lbl, sel in (("blanket (control)", pd.Series(True, index=dy_o.index)),
                     ("MNQ CONFIRMS the break", dy_o["mnq_confirm"] == 1),
                     ("MNQ OPPOSES the break", dy_o["mnq_oppose"] == 1),
                     ("MNQ drift AGREES", dy_o["mnq_agree"] == 1),
                     ("MNQ drift OPPOSES", dy_o["mnq_agree"] == 0)):
        R["year_cross"][f"FOLLOW :: {lbl}"] = show(lbl, dy_o[sel])
    print()
    for nm, dd, sels in (("FADE", dy_f, {"MNQ CONFIRMS the break": dy_f["mnq_confirm"] == 1,
                                         "MNQ OPPOSES the break": dy_f["mnq_oppose"] == 1,
                                         "MNQ drift AGREES": dy_f["mnq_agree"] == 1,
                                         "MNQ drift OPPOSES": dy_f["mnq_agree"] == 0,
                                         "MNQ not breaking": dy_f["mnq_brk"] == 0}),
                         ("FOLLOW", dy_o, {"MNQ CONFIRMS the break": dy_o["mnq_confirm"] == 1,
                                           "MNQ drift AGREES": dy_o["mnq_agree"] == 1})):
        for lbl, sel in sels.items():
            p = filter_placebo(dd, sel, runs=200)
            if p.get("runs"):
                print(f"  filter-placebo  {nm:<7} {lbl:<22} keep {p['keep_n']:<5} real {p['real']:>+7.0f} "
                      f"vs random {p['rand_mean']:>+7.0f}  beaten {p['beaten']}/{p['runs']} (pctile {p['pctile']})")
                R["year_cross"][f"{nm} :: {lbl}"]["placebo"] = p

    # ══ PART C — RE-TEST THE STRADDLE REFUTATION ON 320 DAYS ═══════════════════════════════════
    line("C. THE VOLATILITY / BREAKOUT-EITHER-WAY PREMISE — re-tested on 320 days, not 22")
    print("  gf_MGC.md 2.2 REFUTED it on 22 days: the tightest compression quintile expands LESS.")
    print("  A refutation deserves the bigger sample as much as a survivor does.\n")
    yy = y.dropna(subset=["atr"]).copy()
    yy["rng20"] = (yy["high"].rolling(20).max() - yy["low"].rolling(20).min())
    yy["fwd60"] = (yy["close"].shift(-60) - yy["close"]).abs()
    yy["comp"] = yy["rng20"] / yy["atr"]
    z = yy.dropna(subset=["comp", "fwd60"])
    z = z[np.isfinite(z["comp"]) & (z["comp"] > 0)]
    z["q"] = pd.qcut(z["comp"], 5, labels=["Q1 tightest", "Q2", "Q3", "Q4", "Q5 widest"])
    g = z.groupby("q", observed=True)["fwd60"].agg(["count", "mean"])
    g["mean_$"] = (g["mean"] * 10).round(2)
    g["vs_all_$"] = (g["mean_$"] - z["fwd60"].mean() * 10).round(2)
    print(g.to_string())
    rc = float(z["comp"].rank().corr(z["fwd60"].rank()))
    ra = float(z["atr"].rank().corr(z["fwd60"].rank()))
    print(f"\n  rank corr(20-min range, |next 60 min|) = {rc:+.3f}   "
          f"rank corr(ATR, |next 60 min|) = {ra:+.3f}")
    print(f"  n = {len(z):,} minutes over {z['day'].nunique()} days")
    R["straddle"] = {"quintiles": {str(k): [int(v["count"]), float(v["mean_$"]), float(v["vs_all_$"])]
                                   for k, v in g.iterrows()},
                     "rank_corr_range": round(rc, 3), "rank_corr_atr": round(ra, 3), "n": int(len(z))}

    with open(f"{OUT}/gf3_mgc_cross.json", "w") as fh:
        json.dump(R, fh, indent=1, default=str)
    print(f"\nwrote {OUT}/gf3_mgc_cross.json")


if __name__ == "__main__":
    main()
