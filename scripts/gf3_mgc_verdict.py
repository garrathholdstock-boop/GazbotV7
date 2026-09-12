#!/usr/bin/env python3
"""GF3_MGC VERDICT — the full battery on every surviving arm, 29 days, and the per-cell decision.

    PYTHONPATH=src .venv/bin/python scripts/gf3_mgc_verdict.py

★ WHAT IS BEING DECIDED. Four cells: {MOMENTUM, REVERSION} x {LONG, SHORT}.
    REVERSION-LONG / REVERSION-SHORT  ->  mgc_hole_break_fade  (fade a break into a liquidity hole)
    MOMENTUM-LONG  / MOMENTUM-SHORT   ->  mgc_wall_break_go    (follow a break that ate a defended level)

★ THE FIVE THINGS THAT ARE NEW SINCE THE 08-15 SECTION AND THAT DECIDE THESE VERDICTS:
    1. seven days of genuine FORWARD tape the rules have never seen;
    2. a 320-day YEAR tape on the bare trigger (the book gate cannot reach back that far);
    3. a 278-day PAIRED MGC x MNQ tape - the cross-asset stone, which produced a real VETO;
    4. the side-decay question: the fade's SHORT side fell from +$11.77/tr to +$0.65/tr forward;
    5. the wall arm's spec mismatch - last week's NUMBER (n=63) and last week's SHADOW LINE
       (obstacle > support, n=116) are different populations.

★ EVERY ARM GETS THE SAME BATTERY: strip-best-3/5/10, drop-the-best-day, leave-one-day-out, both
halves, ISO weeks, days green, random-minute placebo, mirror, both constants, and a slippage ladder.
No arm is judged on win% (operator's standing rule, 2026-08-01) - only expectancy and robustness.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_cells import Racer, break_entries, five_second, placebo, run_entries, stat  # noqa: E402
from gf_mgc_l2 import attach, load_book_5s  # noqa: E402
from gf_mgc_tape import VPP, build_tape  # noqa: E402
from gf3_mgc_forward import regime_with_frozen_cuts  # noqa: E402
from gf3_mgc_cross import mnq_minutes, tag_cross, filter_placebo  # noqa: E402

pd.set_option("display.width", 260)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
IS_END = "2026-08-15"
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
R: dict = {}


def line(t: str) -> None:
    print("\n" + "=" * 106 + f"\n{t}\n" + "=" * 106, flush=True)


def full_battery(d: pd.DataFrame) -> dict:
    if d.empty:
        return {}
    v = d["true_pnl"].sort_values()
    byday = d.groupby("day")["true_pnl"].sum()
    days = sorted(d["day"].unique())
    mid = days[len(days) // 2]
    wk = d.copy(); wk["iso"] = pd.to_datetime(wk["day"]).dt.isocalendar().week
    w = wk.groupby("iso")["true_pnl"].sum()
    loo = {dd: float(byday.sum() - byday[dd]) for dd in byday.index}
    return {"n": int(len(v)), "days": int(len(days)), "net": round(float(v.sum()), 0),
            "per": round(float(v.mean()), 2), "win": round(100.0 * float((v > 0).mean()), 1),
            "strip_best_3": round(float(v.iloc[:-3].sum()), 0),
            "strip_best_5": round(float(v.iloc[:-5].sum()), 0),
            "strip_best_10": round(float(v.iloc[:-10].sum()), 0),
            "drop_best_day": round(float(byday.sum() - byday.max()), 0),
            "loo_min": round(min(loo.values()), 0), "loo_all_green": bool(min(loo.values()) > 0),
            "days_green": round(100.0 * float((byday > 0).mean()), 1),
            "best_day": f"{byday.idxmax()} {byday.max():+.0f}",
            "worst_day": f"{byday.idxmin()} {byday.min():+.0f}",
            "h1": round(float(d[d["day"] < mid]["true_pnl"].sum()), 0),
            "h2": round(float(d[d["day"] >= mid]["true_pnl"].sum()), 0),
            "weeks_green": f"{int((w > 0).sum())}/{len(w)}",
            "weeks": {int(k): round(float(x), 0) for k, x in w.items()},
            "IS": round(float(d[d["day"] < IS_END]["true_pnl"].sum()), 0),
            "OOS": round(float(d[d["day"] >= IS_END]["true_pnl"].sum()), 0),
            "slip": {f"+{t}tk": round(float((d["true_pnl"] - t * 0.10 * 2 * VPP).sum()), 0)
                     for t in (1, 2, 3, 4)}}


def report(tag: str, d: pd.DataFrame) -> dict:
    b = full_battery(d)
    if not b:
        print(f"  {tag}: EMPTY")
        return {}
    print(f"\n  ── {tag} ──")
    print(f"     n={b['n']} over {b['days']} days   net {b['net']:+.0f}   ${b['per']:+.2f}/trade   "
          f"win {b['win']}%   IS {b['IS']:+.0f} / FORWARD {b['OOS']:+.0f}")
    print(f"     strip-best 3/5/10: {b['strip_best_3']:+.0f} / {b['strip_best_5']:+.0f} / "
          f"{b['strip_best_10']:+.0f}     drop-best-day {b['drop_best_day']:+.0f}     "
          f"leave-one-day-out worst {b['loo_min']:+.0f} ({'ALL GREEN' if b['loo_all_green'] else 'A DAY FLIPS IT'})")
    print(f"     days green {b['days_green']}%   weeks green {b['weeks_green']}   "
          f"H1 {b['h1']:+.0f} / H2 {b['h2']:+.0f}   best {b['best_day']}   worst {b['worst_day']}")
    print(f"     weeks: " + "  ".join(f"wk{k} {v:+.0f}" for k, v in b["weeks"].items()))
    print(f"     slippage: " + "   ".join(f"{k} {v:+.0f}" for k, v in b["slip"].items()))
    return b


def main() -> None:
    m_all, q = build_tape()
    _, cuts = regime_with_frozen_cuts(m_all[m_all["day"] < IS_END])
    m, _ = regime_with_frozen_cuts(m_all, cuts)
    print("loading depth + MNQ ...", flush=True)
    bk = load_book_5s()
    xn = mnq_minutes("daily")
    racer = Racer(five_second(q))

    e_fade = attach(break_entries(m, look=60, margin_atr=0.10, cool=45, fade=True), bk).reset_index(drop=True)
    e_foll = attach(break_entries(m, look=60, margin_atr=0.10, cool=45, fade=False), bk).reset_index(drop=True)
    e_fade = tag_cross(e_fade, xn)
    e_foll = tag_cross(e_foll, xn)

    arms = {
        "REVERSION  mgc_hole_break_fade  PRIMARY (obstacle==0)": e_fade[e_fade["obstacle"] == 0],
        "REVERSION  mgc_hole_break_fade  DOUBLE-HOLE (obst==0 & sup==0)":
            e_fade[(e_fade["obstacle"] == 0) & (e_fade["support"] == 0)],
        "MOMENTUM   mgc_wall_break_go    SHADOW-LINE (obstacle > support)":
            e_foll[e_foll["obstacle"] > e_foll["support"]],
        "MOMENTUM   mgc_wall_break_go    AS-MEASURED (ratio>1: sup>0 & obst>sup)":
            e_foll[(e_foll["support"] > 0) & (e_foll["obstacle"] > e_foll["support"])],
    }

    line("1. ★★★ THE FULL BATTERY ON EVERY ARM — 29 days, in-sample and forward in one ledger")
    R["arms"] = {}
    traded = {}
    for tag, e in arms.items():
        d = run_entries(racer, e.reset_index(drop=True), **CHAND)
        traded[tag] = d
        R["arms"][tag] = report(tag, d)

    line("2. THE CONTROLS — mirror and the two constants, on each arm's own stamps, 29 days")
    R["controls"] = {}
    for tag, e in arms.items():
        ee = e.reset_index(drop=True)
        row = {}
        for lbl, mk in (("MIRROR", lambda x: x.assign(side=-x["side"])),
                        ("always LONG", lambda x: x.assign(side=1)),
                        ("always SHORT", lambda x: x.assign(side=-1))):
            d = run_entries(racer, mk(ee), **CHAND)
            s = stat(d)
            row[lbl] = s
        base = stat(traded[tag])
        print(f"  {tag[:56]:<56} real {base['per']:>+7.2f} | mirror {row['MIRROR']['per']:>+7.2f} "
              f"| aL {row['always LONG']['per']:>+7.2f} | aS {row['always SHORT']['per']:>+7.2f}")
        R["controls"][tag] = row

    line("3. THE RANDOM-MINUTE PLACEBO — 30 draws, same days, same hours, same side mix")
    R["placebo"] = {}
    for tag, d in traded.items():
        if len(d) < 5:
            continue
        p = placebo(racer, d, m, n_runs=30, seed=20260825, **CHAND)
        verdict = "PASS" if p.get("beaten", 99) <= 3 else ("MARGINAL" if p.get("beaten", 99) <= 10 else "FAIL")
        print(f"  {tag[:60]:<60} real {p.get('real', 0):>+6.0f}  random mean {p.get('mean', 0):>+6.0f}  "
              f"beaten {p.get('beaten')}/{p.get('runs')}  -> {verdict}")
        R["placebo"][tag] = {**p, "verdict": verdict}

    line("4. ★ THE SIDE-DECAY QUESTION — the fade's SHORT side fell away on the forward walk")
    R["side_decay"] = {}
    for tag in list(arms)[:2]:
        d = traded[tag]
        print(f"\n  {tag}")
        for blk, sel in (("IN-SAMPLE 22d", d["day"] < IS_END), ("FORWARD 7d", d["day"] >= IS_END)):
            for sd, nm in ((1, "LONG "), (-1, "SHORT")):
                s = stat(d[sel & (d["side"] == sd)])
                print(f"     {blk:<14} {nm}  n={s['n']:<4} net={s['net']:>+7.0f}  $/tr={s['per']:>+7.2f}  "
                      f"win={s['win']:>5.1f}%")
                R["side_decay"][f"{tag}|{blk}|{nm.strip()}"] = s
        fw = d[d["day"] >= IS_END]
        sh = fw[fw["side"] < 0]
        if not sh.empty:
            bd = sh.groupby("day")["true_pnl"].sum().sort_values()
            print(f"     forward SHORT by day: " + "  ".join(f"{k[5:]} {v:+.0f}" for k, v in bd.items()))
            print(f"     -> drop the single worst forward day and the short side is "
                  f"{float(bd.sum() - bd.min()):+.0f} over {len(sh) - int((sh['day'] == bd.index[0]).sum())} trades")

    line("5. ★★ THE CROSS-ASSET VETO, derived on 278 PAIRED days, applied to the book sample")
    print("  Year tape (n=3800): fading a gold break the Nasdaq CONFIRMS makes -$10.52/tr (placebo")
    print("  pctile 2.5 - significantly WORSE than random); fading one the Nasdaq's drift OPPOSES")
    print("  makes +$5.43/tr (pctile 97.0). Two-sided, well powered. Does it show up on 29 days?\n")
    R["veto"] = {}
    for tag in list(arms)[:2]:
        d = traded[tag]
        for lbl, sel in (("ALL (no veto)", pd.Series(True, index=d.index)),
                         ("VETO when MNQ confirms the break", d["mnq_confirm"] == 0),
                         ("VETO when MNQ drift agrees", d["mnq_agree"] != 1),
                         ("VETO on either", (d["mnq_confirm"] == 0) & (d["mnq_agree"] != 1))):
            s_all, s_o = stat(d[sel]), stat(d[sel & (d["day"] >= IS_END)])
            print(f"  {tag[10:46]:<38} {lbl:<34} 29d n={s_all['n']:<4} {s_all['net']:>+6.0f} "
                  f"({s_all['per']:>+6.2f})  fwd n={s_o['n']:<3} {s_o['net']:>+5.0f} ({s_o['per']:>+6.2f})")
            R["veto"][f"{tag}|{lbl}"] = {"all29": s_all, "forward": s_o}
        p = filter_placebo(d, d["mnq_confirm"] == 0, runs=200)
        if p.get("runs"):
            print(f"  {'':38} filter-placebo of the confirm-veto: keep {p['keep_n']} real {p['real']:+.0f} "
                  f"vs random {p['rand_mean']:+.0f}, beaten {p['beaten']}/{p['runs']} (pctile {p['pctile']})\n")
            R["veto"][f"{tag}|placebo"] = p

    with open(f"{OUT}/gf3_mgc_verdict.json", "w") as fh:
        json.dump(R, fh, indent=1, default=str)
    print(f"\nwrote {OUT}/gf3_mgc_verdict.json")


if __name__ == "__main__":
    main()
