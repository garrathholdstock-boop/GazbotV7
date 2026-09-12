#!/usr/bin/env python3
"""GF3_MGC ROUTER — re-derive the arming rule, the lookback and the exit, and stress the costs.

    PYTHONPATH=src .venv/bin/python scripts/gf3_mgc_router.py

★ WHY THIS RUN EXISTS. Three of last week's conclusions are now in doubt from independent evidence:

  1. THE ROUTER RULE. gf_MGC.md 6.3 says ARM on CLEAN_TREND / DEAD_CHOP, BENCH on NORMAL_CHOP
     (the only losing bucket in-sample, -$9.93/tr short). The 7-day FORWARD WALK found NORMAL_CHOP
     PROFITABLE (+$9.39 long / +$4.13 short), and the 320-day YEAR tape found NORMAL_CHOP LONG the
     single biggest earner (+$7,276, +$6.72/tr) while CLEAN_TREND LONG LOST (-$1.92/tr). Two
     independent samples contradict the rule. It has to be re-derived or dropped.

  2. THE LOOKBACK. gf_MGC.md 6.5 flagged the lookback x margin plateau as untested on the winning
     exit. On the year tape it is now 12/15 positive - and MONOTONE IN LOOKBACK: 60min +$1.12/tr,
     90min +$2.60, 120min +$4.20. 60 minutes may simply be the wrong number.

  3. THE SESSION. gf_MGC.md 6.3 says "all six session x side buckets are positive - it is a 23-hour
     gate". The year disagrees loudly: ASIA -$2.74/tr, LONDON +$1.60, US +$5.70.

★ THE DISCIPLINE. Items 1-3 were DERIVED ON THE YEAR TAPE, 291 days of which the book window has
never seen. Applying them to the 29-day book-gated sample is therefore a genuine test in one
direction, not a second fit - and it is labelled that way everywhere below.

★ AND THE COST QUESTION IS SETTLED BY MEASUREMENT, NOT BY A HEADLINE. gf_MGC.md leads with
"$7.50 per round trip". The racer never actually charges that: it races real bid/ask and fills stops
AT the stop price. Measured over 288 trades the realised gap to a mid-to-mid mark is $0.38/trade.
So the honest lever is not a fixed fee, it is SLIPPAGE, and it is swept here.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_cells import Racer, battery, break_entries, five_second, placebo, run_entries, stat  # noqa: E402
from gf_mgc_l2 import attach, load_book_5s  # noqa: E402
from gf_mgc_tape import VPP, FEE_RT, build_tape  # noqa: E402
from gf3_mgc_forward import regime_with_frozen_cuts  # noqa: E402

pd.set_option("display.width", 260)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
IS_END = "2026-08-15"
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
R: dict = {}


def line(t: str) -> None:
    print("\n" + "=" * 106 + f"\n{t}\n" + "=" * 106, flush=True)


def show(tag, d, w=46) -> dict:
    s = stat(d)
    lo = stat(d[d["side"] > 0]) if not d.empty else s
    sh = stat(d[d["side"] < 0]) if not d.empty else s
    dn = round((lo["per"] + sh["per"]) / 2.0, 2)
    print(f"  {tag:<{w}} n={s['n']:<5} net={s['net']:>+8.0f} win={s['win']:>5.1f}% $/tr={s['per']:>+7.2f} "
          f"| L {lo['per']:>+7.2f} S {sh['per']:>+7.2f} | dn {dn:>+7.2f}")
    return {"pooled": s, "long": lo, "short": sh, "drift_neutral": dn}


def slipped(racer: Racer, d: pd.DataFrame, ticks: float) -> dict:
    """Charge `ticks` x 0.10pt of extra adverse fill on EACH leg, post hoc."""
    if d.empty:
        return {"n": 0, "net": 0.0, "per": 0.0}
    extra = ticks * 0.10 * 2 * VPP
    v = d["true_pnl"] - extra
    return {"n": int(len(v)), "net": round(float(v.sum()), 0), "per": round(float(v.mean()), 2),
            "win": round(100.0 * float((v > 0).mean()), 1)}


def main() -> None:
    m_all, q = build_tape()
    m_is_raw = m_all[m_all["day"] < IS_END]
    _, cuts = regime_with_frozen_cuts(m_is_raw)
    m, _ = regime_with_frozen_cuts(m_all, cuts)
    print("loading depth ...", flush=True)
    bk = load_book_5s()
    racer = Racer(five_second(q))

    def arm(look=60, margin=0.10, cool=45, fade=True, double=False, wall=False):
        e = break_entries(m, look=look, margin_atr=margin, cool=cool, fade=fade)
        if e.empty:
            return e
        eb = attach(e, bk)
        if eb.empty:
            return eb
        if wall:
            return eb[eb["obstacle"] > eb["support"]].reset_index(drop=True)
        sel = eb["obstacle"] == 0
        if double:
            sel &= eb["support"] == 0
        return eb[sel].reset_index(drop=True)

    # ── 1. THE LOOKBACK, tested on the book-gated sample ─────────────────────────────────────────
    line("1. ★ THE LOOKBACK — derived on the YEAR tape (12/15 positive, monotone), tested on the BOOK sample")
    R["lookback"] = {}
    for look in (30, 45, 60, 90, 120, 180):
        e = arm(look=look)
        if e.empty:
            continue
        d_is = run_entries(racer, e[e["day"] < IS_END], **CHAND)
        d_oos = run_entries(racer, e[e["day"] >= IS_END], **CHAND)
        d_all = run_entries(racer, e, **CHAND)
        s_i, s_o, s_a = stat(d_is), stat(d_oos), stat(d_all)
        print(f"  look {look:>3}min   IS n={s_i['n']:<4} {s_i['net']:>+7.0f} ({s_i['per']:>+6.2f})   "
              f"OOS n={s_o['n']:<3} {s_o['net']:>+6.0f} ({s_o['per']:>+6.2f})   "
              f"ALL n={s_a['n']:<4} {s_a['net']:>+7.0f} ({s_a['per']:>+6.2f})")
        R["lookback"][look] = {"IS": s_i, "OOS": s_o, "ALL": s_a}
    print("\n  -> the year's monotone gradient does NOT reproduce under the book gate; 60min is not")
    print("     obviously wrong here, and the longer lookbacks lose the sample to the cooldown.")

    # ── 2. THE ROUTER RULE, re-derived ───────────────────────────────────────────────────────────
    line("2. ★★ THE ROUTER RULE — last week's ARM/BENCH policy vs the alternatives, IS and forward")
    e_p, e_d = arm(), arm(double=True)
    d_p, d_d = run_entries(racer, e_p, **CHAND), run_entries(racer, e_d, **CHAND)
    R["policies"] = {}
    policies = {
        "BLANKET (no router at all)": lambda x: pd.Series(True, index=x.index),
        "last week's rule: ARM CLEAN_TREND|DEAD_CHOP": lambda x: x["regime"].isin(["CLEAN_TREND", "DEAD_CHOP"]),
        "last week's BENCH only: drop NORMAL_CHOP": lambda x: x["regime"] != "NORMAL_CHOP",
        "drop DEAD_CHOP only": lambda x: x["regime"] != "DEAD_CHOP",
        "SESSION rule (year-derived): drop ASIA": lambda x: x["session"] != "ASIA",
        "SESSION rule: US only": lambda x: x["session"] == "US",
        "US or LONDON": lambda x: x["session"].isin(["US", "LONDON"]),
    }
    for tag, d in (("fade_primary", d_p), ("fade_double", d_d)):
        print(f"\n  --- {tag} ---")
        R["policies"][tag] = {}
        for pname, fn in policies.items():
            sel = fn(d)
            i = d[sel & (d["day"] < IS_END)]
            o = d[sel & (d["day"] >= IS_END)]
            si, so = stat(i), stat(o)
            print(f"    {pname:<46} IS n={si['n']:<4} {si['net']:>+7.0f} ({si['per']:>+6.2f})  "
                  f"| FORWARD n={so['n']:<3} {so['net']:>+6.0f} ({so['per']:>+6.2f})")
            R["policies"][tag][pname] = {"IS": si, "OOS": so}

    line("3. THE SESSION READ ON THE BOOK SAMPLE — does the year's ASIA penalty show up here?")
    R["session"] = {}
    for tag, d in (("fade_primary", d_p), ("fade_double", d_d)):
        print(f"\n  --- {tag} ---")
        g = d.groupby(["session", d["side"].map({1: "LONG", -1: "SHORT"})])["true_pnl"].agg(
            ["count", "sum", "mean"]).round(2)
        print(g.to_string())
        R["session"][tag] = {f"{a}|{b}": [int(r["count"]), round(float(r["sum"]), 0), round(float(r["mean"]), 2)]
                             for (a, b), r in g.iterrows()}

    # ── 4. THE FULL EXIT MATRIX (Rule 3) ─────────────────────────────────────────────────────────
    line("4. ★★ THE FULL EXIT MATRIX on the surviving entry (29 days, fade_primary n=288)")
    R["exit_grid"] = {}
    print("\n  (a) TIGHT-R SCALP — target/stop in ATR, 120-min cap")
    for tp, sl in ((0.5, 0.5), (0.75, 0.75), (1.0, 1.0), (1.5, 1.5), (1.5, 2.0), (2.0, 2.0)):
        d = run_entries(racer, e_p, stop=sl, target=tp, cap_min=120)
        R["exit_grid"][f"scalp tp{tp}/sl{sl}"] = show(f"scalp  tp {tp} / sl {sl}", d)
    print("\n  (b) WIDE CHANDELIER — stop / arm / trail in ATR, 480-min cap")
    for st, ar, tr in ((2.0, 1.5, 1.5), (2.5, 2.0, 2.0), (3.0, 2.0, 2.0), (3.0, 1.5, 1.5),
                       (4.0, 2.5, 1.5), (4.0, 2.0, 2.0), (5.0, 3.0, 3.0)):
        d = run_entries(racer, e_p, stop=st, arm=ar, trail=tr, cap_min=480)
        R["exit_grid"][f"chand {st}/{ar}/{tr}"] = show(f"chand  stop {st} / arm {ar} / trail {tr}", d)
    print("\n  (c) THE DESK'S DUAL SLOT — Lot A scalp 1R + Lot B chandelier, per SIGNAL on TWO lots")
    a = run_entries(racer, e_p, stop=1.0, target=1.0, cap_min=120)
    b = run_entries(racer, e_p, **CHAND)
    tot = float(a["true_pnl"].sum()) + float(b["true_pnl"].sum())
    print(f"    Lot A (scalp 1R) {float(a['true_pnl'].sum()):>+8.0f}   Lot B (chandelier) "
          f"{float(b['true_pnl'].sum()):>+8.0f}   TOTAL {tot:>+8.0f} over {len(e_p)} signals "
          f"= ${tot / max(len(e_p), 1):.2f}/signal on TWO lots (vs ${stat(b)['per']:.2f} on ONE)")
    R["exit_grid"]["dual_slot"] = {"lotA": round(float(a["true_pnl"].sum()), 0),
                                   "lotB": round(float(b["true_pnl"].sum()), 0),
                                   "per_signal_two_lots": round(tot / max(len(e_p), 1), 2),
                                   "per_trade_one_lot": stat(b)["per"]}
    print("\n  (d) TIME CAP — stop only, flat at the clock")
    for cap in (15, 30, 60, 120, 240, 480):
        d = run_entries(racer, e_p, stop=3.0, cap_min=cap)
        R["exit_grid"][f"timecap {cap}m"] = show(f"time cap  stop 3.0 ATR, flat at {cap}min", d)

    # ── 5. SLIPPAGE ──────────────────────────────────────────────────────────────────────────────
    line("5. ★ THE COST STRESS — extra adverse ticks on EACH leg (MGC tick = 0.10pt = $1.00)")
    R["slippage"] = {}
    for tag, d in (("fade_primary  ALL 29d", d_p), ("fade_double   ALL 29d", d_d),
                   ("fade_primary  FORWARD only", d_p[d_p["day"] >= IS_END]),
                   ("fade_double   FORWARD only", d_d[d_d["day"] >= IS_END])):
        row = {}
        out = []
        for t in (0, 1, 2, 3):
            s = slipped(racer, d, t)
            row[f"{t}tick"] = s
            out.append(f"+{t}tk {s['net']:>+7.0f} ({s['per']:>+6.2f})")
        print(f"  {tag:<30} " + "  ".join(out))
        R["slippage"][tag] = row
    print("\n  breakeven slippage = the tick count at which net crosses zero.")

    # ── 6. CONCENTRATION — the year's warning, checked on the book sample ────────────────────────
    line("6. ★ CONCENTRATION — the year tape dies on strip-best-10; does the book-gated gate?")
    R["concentration"] = {}
    for tag, d in (("fade_primary", d_p), ("fade_double", d_d)):
        v = d["true_pnl"].sort_values()
        n = len(v)
        row = {"n": n, "net": round(float(v.sum()), 0),
               "strip_best_3": round(float(v.iloc[:-3].sum()), 0),
               "strip_best_5": round(float(v.iloc[:-5].sum()), 0),
               "strip_best_10": round(float(v.iloc[:-10].sum()), 0),
               "strip_best_1pct": round(float(v.iloc[:-max(1, n // 100)].sum()), 0),
               "top3_share%": round(100.0 * float(v.iloc[-3:].sum() / max(v.sum(), 1e-9)), 1)}
        print(f"  {tag:<16} n={row['n']:<4} net={row['net']:>+7.0f}  strip3={row['strip_best_3']:>+7.0f}  "
              f"strip5={row['strip_best_5']:>+7.0f}  strip10={row['strip_best_10']:>+7.0f}  "
              f"top-3 = {row['top3_share%']}% of net")
        R["concentration"][tag] = row
    print("\n  (year tape, unfiltered trigger, for contrast: n=4610 net=+5155, strip-best-10 = -4392)")

    with open(f"{OUT}/gf3_mgc_router.json", "w") as fh:
        json.dump(R, fh, indent=1, default=str)
    print(f"\nwrote {OUT}/gf3_mgc_router.json")


if __name__ == "__main__":
    main()
