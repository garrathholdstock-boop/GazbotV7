#!/usr/bin/env python3
"""GF3_MGC FORWARD — the honest forward walk on last week's gold survivor.

    PYTHONPATH=src .venv/bin/python scripts/gf3_mgc_forward.py

★ WHAT THIS IS AND WHY IT IS THE ONLY TEST THAT MATTERS THIS WEEK.

On 2026-08-15 this desk shadowed `mgc_hole_break_fade` off 22 days of gold (07-16..08-14): a
60-minute level break that runs into a LIQUIDITY HOLE, faded, held on a 3-ATR stop behind a
2-ATR/2-ATR chandelier. It passed every in-sample test we own. Since then the tape has produced
SEVEN NEW TRADING DAYS (08-17,18,19,20,21,24,25) that did not exist when the rule was written.

That is a real forward walk, and it is worth more than any number of fresh in-sample cuts. Nothing
about the gate is re-fitted here. The spec is copied verbatim from gf_MGC.md section 6.1.

★ THE CALIBRATION IS FROZEN TOO, and this is the subtle part. The regime labels (CLEAN_TREND /
NORMAL_CHOP / ...) are ATR and ER PERCENTILE cuts. Recomputing them on all 29 days would let the
out-of-sample week help define its own regime boundaries - a small peek, but exactly the kind this
desk keeps getting caught by. So the cut points are computed on the 22 IN-SAMPLE days ONLY and then
APPLIED to the new week. `add_regime` is not reused for that reason.

★ SELF-CHECK FIRST. Before believing anything about the new week, the harness re-runs the ORIGINAL
22 days and must reproduce last week's headline (+$2,648 pooled / n=157 double-hole,
+$2,730 / n=219 primary). If it does not, the harness changed and no comparison is meaningful.

MGC = $10.00/point. Fee $1.50 per ROUND TRIP; both legs additionally CROSS a ~0.30pt spread, so the
all-in round trip is ~$7.50. `true_pnl` crosses; `desk_pnl` is the old mid-to-mid convention.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_cells import (  # noqa: E402
    Racer, battery, break_entries, five_second, placebo, run_entries, stat,
)
from gf_mgc_l2 import attach, load_book_5s  # noqa: E402
from gf_mgc_tape import build_tape, eff_ratio, atr as atr_fn, session_of  # noqa: E402

pd.set_option("display.width", 260)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"

IS_END = "2026-08-15"          # last week's sample ended 08-14 inclusive
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
SCALP = dict(stop=1.0, target=1.0, cap_min=120)
R: dict = {}


def line(t: str) -> None:
    print("\n" + "=" * 104 + f"\n{t}\n" + "=" * 104, flush=True)


def regime_with_frozen_cuts(m: pd.DataFrame, cuts: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Label regimes. If `cuts` is given they are USED; otherwise they are computed on this frame.

    Splitting this out of gf_mgc_tape.add_regime is the whole point: the out-of-sample week must be
    labelled with boundaries drawn BEFORE it existed, or the label itself has seen the future.
    """
    m = m.copy()
    m["atr"] = atr_fn(m)
    m["er"] = eff_ratio(m["close"])
    m["session"] = session_of(m.index).values
    m["day"] = m.index.strftime("%Y-%m-%d")
    if cuts is None:
        cuts = {"atr_p33": float(m["atr"].quantile(0.33)), "atr_p67": float(m["atr"].quantile(0.67)),
                "er_p40": float(m["er"].quantile(0.40)), "er_p75": float(m["er"].quantile(0.75))}
    a_lo, a_hi, e_lo, e_hi = cuts["atr_p33"], cuts["atr_p67"], cuts["er_p40"], cuts["er_p75"]
    reg = pd.Series("NORMAL_CHOP", index=m.index)
    reg[(m["atr"] <= a_lo) & (m["er"] <= e_hi)] = "DEAD_CHOP"
    reg[(m["atr"] >= a_hi) & (m["er"] >= e_hi)] = "CLEAN_TREND"
    reg[(m["atr"] >= a_hi) & (m["er"] <= e_lo)] = "VIOLENT_WHIPSAW"
    reg[(m["atr"].between(a_lo, a_hi, inclusive="neither")) & (m["er"] >= e_hi)] = "BUILDING"
    m["regime"] = reg.values
    m.attrs["cuts"] = cuts
    return m, cuts


def gate(m: pd.DataFrame, bk: pd.DataFrame, *, fade: bool = True, double: bool = False,
         look: int = 60, margin: float = 0.10, cool: int = 45) -> pd.DataFrame:
    """The literal section-6.1 spec: break -> book gate -> direction."""
    e = break_entries(m, look=look, margin_atr=margin, cool=cool, fade=fade)
    if e.empty:
        return e
    eb = attach(e, bk)
    if eb.empty:
        return eb
    sel = eb["obstacle"] == 0
    if double:
        sel &= eb["support"] == 0
    return eb[sel].reset_index(drop=True)


def wall(m: pd.DataFrame, bk: pd.DataFrame, **kw) -> pd.DataFrame:
    """The momentum arm: follow a break that ate a DEFENDED level (obstacle > support)."""
    e = break_entries(m, look=kw.get("look", 60), margin_atr=kw.get("margin", 0.10),
                      cool=kw.get("cool", 45), fade=False)
    if e.empty:
        return e
    eb = attach(e, bk)
    return eb[eb["obstacle"] > eb["support"]].reset_index(drop=True) if not eb.empty else eb


def show(tag: str, d: pd.DataFrame) -> dict:
    s = stat(d)
    lo = stat(d[d["side"] > 0]) if not d.empty else stat(d)
    sh = stat(d[d["side"] < 0]) if not d.empty else stat(d)
    print(f"  {tag:<42} n={s['n']:<5} net={s['net']:>+8.0f}  win={s['win']:>5.1f}%  "
          f"$/tr={s['per']:>+7.2f}  days={s['days']:<3}  LONG {lo['n']:>3}/{lo['per']:>+7.2f}  "
          f"SHORT {sh['n']:>3}/{sh['per']:>+7.2f}")
    return {"pooled": s, "long": lo, "short": sh}


def main() -> None:
    m_all, q_all = build_tape()
    print(f"tape: {len(m_all):,} minutes  {m_all['day'].min()} .. {m_all['day'].max()}  "
          f"{m_all['day'].nunique()} days", flush=True)
    print("loading 10-level MGC depth ...", flush=True)
    bk = load_book_5s()
    print(f"book: {len(bk):,} 5s snapshots  {bk.index.min()} .. {bk.index.max()}", flush=True)

    # ── freeze the calibration on the in-sample block, then label everything with it ──
    m_is_raw = m_all[m_all["day"] < IS_END]
    _, cuts = regime_with_frozen_cuts(m_is_raw)
    m, _ = regime_with_frozen_cuts(m_all, cuts)
    print(f"\nFROZEN CUTS (from the 22 in-sample days only): "
          f"ATR p33={cuts['atr_p33']:.3f} p67={cuts['atr_p67']:.3f}  "
          f"ER p40={cuts['er_p40']:.3f} p75={cuts['er_p75']:.3f}")
    live_cuts = {"atr_p33": float(m_all["atr"].quantile(0.33)), "atr_p67": float(m_all["atr"].quantile(0.67)),
                 "er_p40": float(m_all["er"].quantile(0.40)), "er_p75": float(m_all["er"].quantile(0.75))}
    print(f"  (all-29-day cuts, for reference only: ATR p33={live_cuts['atr_p33']:.3f} "
          f"p67={live_cuts['atr_p67']:.3f}  ER p40={live_cuts['er_p40']:.3f} p75={live_cuts['er_p75']:.3f})")
    R["cuts_frozen"], R["cuts_all"] = cuts, live_cuts

    f = five_second(q_all)
    racer = Racer(f)

    is_days = sorted(m[m["day"] < IS_END]["day"].unique())
    oos_days = sorted(m[m["day"] >= IS_END]["day"].unique())
    print(f"\nIN-SAMPLE  {len(is_days)} days  {is_days[0]} .. {is_days[-1]}")
    print(f"OUT-OF-SAMPLE {len(oos_days)} days  {oos_days[0]} .. {oos_days[-1]}   <- did not exist on 08-15")
    R["is_days"], R["oos_days"] = is_days, oos_days

    # ── build every arm once on the whole tape, then slice ──
    arms = {
        "fade_primary  (obstacle==0)":      gate(m, bk, fade=True, double=False),
        "fade_double   (obst==0 & sup==0)": gate(m, bk, fade=True, double=True),
        "wall_go       (obstacle>support)": wall(m, bk),
    }

    line("SELF-CHECK — can this harness reproduce last week's IN-SAMPLE headline?")
    print("  last week (gf_MGC.md sec 6.2/5): fade_primary n=219 +$2,730 · fade_double n=157 +$2,648 "
          "· wall_go n=63 +$746\n")
    R["selfcheck"] = {}
    for tag, e in arms.items():
        d = run_entries(racer, e[e["day"] < IS_END], **CHAND) if not e.empty else pd.DataFrame()
        R["selfcheck"][tag] = show(tag, d)

    line("★★★ THE FORWARD WALK — the same rules, on the 7 days that did not exist when they were written")
    R["oos"], R["oos_battery"] = {}, {}
    oos_tr = {}
    for tag, e in arms.items():
        eo = e[e["day"] >= IS_END] if not e.empty else e
        d = run_entries(racer, eo, **CHAND) if not eo.empty else pd.DataFrame()
        oos_tr[tag] = d
        R["oos"][tag] = show(tag, d)
        if not d.empty:
            byday = d.groupby("day")["true_pnl"].agg(["count", "sum"])
            print(f"       per day: " + "  ".join(f"{k[5:]} {v['sum']:+.0f}({int(v['count'])})"
                                                  for k, v in byday.iterrows()))
            R["oos_battery"][tag] = {"byday": {k: [int(v["count"]), round(float(v["sum"]), 0)]
                                               for k, v in byday.iterrows()},
                                     "strip_best": round(float(d["true_pnl"].sort_values().iloc[:-1].sum()), 0),
                                     "desk_pnl": round(float(d["desk_pnl"].sum()), 0)}

    line("THE CONTROLS ON THE SAME OUT-OF-SAMPLE STAMPS — mirror, and the two constants")
    R["oos_controls"] = {}
    for tag, e in (("fade_primary", arms["fade_primary  (obstacle==0)"]),
                   ("fade_double", arms["fade_double   (obst==0 & sup==0)"])):
        eo = e[e["day"] >= IS_END].copy()
        if eo.empty:
            continue
        mir = eo.copy(); mir["side"] = -mir["side"]
        lng = eo.copy(); lng["side"] = 1
        sht = eo.copy(); sht["side"] = -1
        for lbl, ee in (("MIRROR (follow instead)", mir), ("always LONG at same stamps", lng),
                        ("always SHORT at same stamps", sht)):
            d = run_entries(racer, ee, **CHAND)
            R["oos_controls"][f"{tag} :: {lbl}"] = show(f"{tag} :: {lbl}", d)

    line("OUT-OF-SAMPLE, BY REGIME (labels frozen on the in-sample block) — does the router rule hold?")
    R["oos_regime"] = {}
    for tag, d in oos_tr.items():
        if d.empty:
            continue
        print(f"\n  {tag}")
        g = d.groupby(["regime", d["side"].map({1: "LONG", -1: "SHORT"})])["true_pnl"].agg(
            ["count", "sum", "mean"]).round(2)
        print(g.to_string())
        R["oos_regime"][tag] = {f"{a}|{b}": [int(r["count"]), round(float(r["sum"]), 0),
                                             round(float(r["mean"]), 2)] for (a, b), r in g.iterrows()}

    line("THE COMBINED 29-DAY PICTURE — in-sample + forward walk, one ledger")
    R["combined"], R["combined_battery"] = {}, {}
    for tag, e in arms.items():
        d = run_entries(racer, e, **CHAND) if not e.empty else pd.DataFrame()
        R["combined"][tag] = show(tag, d)
        if not d.empty:
            b = battery(d)
            R["combined_battery"][tag] = b
            print(f"       strip-best-3 {b['strip_best3']:+.0f} · drop-best-day {b['loo_worst']:+.0f} "
                  f"· days green {b['days_green']}% · H1 {b['h1'][1]:+.0f} / H2 {b['h2'][1]:+.0f} "
                  f"· best {b['best_day']} · worst {b['worst_day']}")
            wk = d.copy()
            wk["iso"] = pd.to_datetime(wk["day"]).dt.isocalendar().week
            w = wk.groupby("iso")["true_pnl"].agg(["count", "sum"])
            print(f"       by ISO week: " + "  ".join(f"wk{int(k)} {v['sum']:+.0f}({int(v['count'])})"
                                                      for k, v in w.iterrows()))
            R["combined_battery"][tag]["weeks"] = {int(k): [int(v["count"]), round(float(v["sum"]), 0)]
                                                   for k, v in w.iterrows()}

    line("PLACEBO ON THE FORWARD WALK — same days, same hours, same side mix, random minutes")
    R["oos_placebo"] = {}
    for tag, d in oos_tr.items():
        if d.empty or len(d) < 5:
            print(f"  {tag:<42} too few trades to placebo (n={len(d)})")
            continue
        m_oos = m[m["day"] >= IS_END]
        p = placebo(racer, d, m_oos, n_runs=30, seed=20260825, **CHAND)
        print(f"  {tag:<42} real {p.get('real', 0):+.0f}  placebo mean {p.get('mean', 0):+.0f}  "
              f"beaten {p.get('beaten', '?')}/{p.get('runs', 0)}  pctile {p.get('pctile', 0)}")
        R["oos_placebo"][tag] = p

    with open(f"{OUT}/gf3_mgc_forward.json", "w") as fh:
        json.dump(R, fh, indent=1, default=str)
    print(f"\nwrote {OUT}/gf3_mgc_forward.json")


if __name__ == "__main__":
    main()
