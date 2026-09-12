#!/usr/bin/env python3
"""GF2 — RULE 3: THE FULL EXIT MATRIX on the level-break trigger, over 184 days.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_exitgrid.py

★ WHY THIS RUN EXISTS. On the year tape the faded break loses -$2.97 a trade but its MEDIAN trade
is +$2.43 and it wins 53.4% of the time. A gate that wins more often than it loses and still bleeds
is not an entry problem, it is an EXIT problem: the chandelier is handing back more on its losers
than it keeps on its winners. The desk has been burned assuming the entry implies the exit, so the
whole matrix gets run rather than one alternative.

Families, per the scope: (a) tight-R scalp swept 0.5-2.0R, (b) wide chandelier swept arm x trail,
(c) the desk's dual slot (Lot A scalp + Lot B chandelier), (d) time caps. Plus the two that gold's
own shape suggests: a BREAK-EVEN-then-trail, and a fixed target with an asymmetric stop.

Everything on the SAME 3,716 entries, so the entry is held constant and only the exit moves.
"""
from __future__ import annotations

import json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from gf2_mgc_histlab import BarRacer, breaks, line, load_clean, run, stat  # noqa: E402

pd.set_option("display.width", 300)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf2"
R: dict = {}


def sides(d):
    return {"LONG": stat(d[d["side"] > 0])["per"], "SHORT": stat(d[d["side"] < 0])["per"]}


def main():
    m = load_clean()
    racer = BarRacer(m)
    ef = breaks(m, fade=True)
    ec = ef.copy(); ec["side"] = -ec["side"]
    print(f"entries held constant: {len(ef)} breaks over {m['day'].nunique()} days\n")

    fam = []
    for r_ in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
        fam.append((f"(a) scalp  tp{r_}R / sl1.0R", dict(stop=1.0, target=r_, cap_min=480)))
    for r_ in (0.5, 1.0, 1.5, 2.0):
        fam.append((f"(a) scalp  tp{r_}R / sl{r_}R", dict(stop=r_, target=r_, cap_min=480)))
    for st, ar, tr in ((2.0, 1.0, 1.0), (2.0, 2.0, 2.0), (3.0, 1.5, 1.5), (3.0, 2.0, 2.0),
                       (3.0, 3.0, 3.0), (5.0, 2.0, 2.0), (5.0, 3.0, 3.0), (5.0, 5.0, 5.0)):
        fam.append((f"(b) chand  sl{st}/arm{ar}/tr{tr}", dict(stop=st, arm=ar, trail=tr, cap_min=480)))
    for cap in (15, 30, 60, 120, 240, 480):
        fam.append((f"(d) timecap sl2.0R, {cap}m", dict(stop=2.0, cap_min=cap)))
    fam.append(("(e) no stop at all, EOD flat", dict(stop=99.0, cap_min=480)))

    print("=" * 150)
    print("THE EXIT MATRIX — same entries, only the exit moves.  FADE (reversion) side")
    print("=" * 150)
    rows = []
    for lbl, kw in fam:
        r = run(racer, ef, **kw)
        if r.empty:
            continue
        s = stat(r); sd = sides(r)
        rows.append({"exit": lbl, **s, "LONG$/tr": sd["LONG"], "SHORT$/tr": sd["SHORT"],
                     "med_min": int(r["minutes"].median()),
                     "mfe/mae": f"{r['mfe_pt'].median():.2f}/{r['mae_pt'].median():.2f}",
                     "stop%": round(100 * (r["reason"] == "STOP").mean(), 1)})
    t = pd.DataFrame(rows).sort_values("per", ascending=False)
    print(t.to_string(index=False))
    R["fade_grid"] = rows

    print("\n" + "=" * 150)
    print("THE SAME MATRIX — FOLLOW (momentum) side")
    print("=" * 150)
    rows2 = []
    for lbl, kw in fam:
        r = run(racer, ec, **kw)
        if r.empty:
            continue
        s = stat(r); sd = sides(r)
        rows2.append({"exit": lbl, **s, "LONG$/tr": sd["LONG"], "SHORT$/tr": sd["SHORT"],
                      "med_min": int(r["minutes"].median()),
                      "stop%": round(100 * (r["reason"] == "STOP").mean(), 1)})
    t2 = pd.DataFrame(rows2).sort_values("per", ascending=False)
    print(t2.to_string(index=False))
    R["follow_grid"] = rows2

    # ── (c) the desk's dual slot on the best of each family ────────────────────────────────────
    print("\n" + "=" * 150)
    print("(c) THE DESK'S DUAL SLOT — Lot A scalp + Lot B chandelier, on the same signal")
    print("=" * 150)
    best_scalp = max([r for r in rows if r["exit"].startswith("(a)")], key=lambda r: r["per"])
    best_chand = max([r for r in rows if r["exit"].startswith("(b)")], key=lambda r: r["per"])
    kwA = dict([f for f in fam if f[0] == best_scalp["exit"]][0][1])
    kwB = dict([f for f in fam if f[0] == best_chand["exit"]][0][1])
    ra, rb = run(racer, ef, **kwA), run(racer, ef, **kwB)
    comb = float(ra["true_pnl"].sum() + rb["true_pnl"].sum())
    print(f"  Lot A = {best_scalp['exit']}  ${stat(ra)['net']:,.0f} ({stat(ra)['per']:+.2f}/lot)")
    print(f"  Lot B = {best_chand['exit']}  ${stat(rb)['net']:,.0f} ({stat(rb)['per']:+.2f}/lot)")
    print(f"  COMBINED over {len(ra)} signals: ${comb:,.0f}  = ${comb/max(len(ra),1):+.2f} per SIGNAL (2 lots)")
    R["dual"] = {"A": best_scalp["exit"], "B": best_chand["exit"], "A_net": stat(ra)["net"],
                 "B_net": stat(rb)["net"], "combined": round(comb, 0)}

    # ── the excursion statistic: what was actually available? ──────────────────────────────────
    print("\n" + "=" * 150)
    print("THE KILLER STATISTIC — what the trade was ever WORTH, in ATR, before costs")
    print("=" * 150)
    r = run(racer, ef, stop=99.0, cap_min=480)
    r["mfe_R"] = r["mfe_pt"] / r["atr"]; r["mae_R"] = r["mae_pt"] / r["atr"]
    print(f"  with NO stop and flat at the day's end, n={len(r)}:")
    for q in (0.25, 0.5, 0.75, 0.9):
        print(f"    MFE p{int(q*100)} {r['mfe_R'].quantile(q):.2f} R      "
              f"MAE p{int((1-q)*100)} {r['mae_R'].quantile(1-q):.2f} R")
    cost_R = (0.30 * 2 * 10 + 1.5) / (r["atr"].median() * 10)
    print(f"  median ATR {r['atr'].median():.2f} pt = ${r['atr'].median()*10:.2f} per R")
    print(f"  ★ THE COST FLOOR: $7.50 round trip = {cost_R:.2f} R. A trade must clear that before")
    print(f"    it earns anything, and the median MFE is only {r['mfe_R'].median():.2f} R.")
    print(f"  share of trades whose BEST moment never cleared the cost: "
          f"{100*(r['mfe_R'] < cost_R).mean():.1f}%")
    R["excursion"] = {"mfe_p50": round(float(r["mfe_R"].median()), 3),
                      "mfe_p75": round(float(r["mfe_R"].quantile(.75)), 3),
                      "mfe_p90": round(float(r["mfe_R"].quantile(.90)), 3),
                      "mae_p50": round(float(r["mae_R"].median()), 3),
                      "cost_R": round(float(cost_R), 3),
                      "never_cleared_cost%": round(100 * float((r["mfe_R"] < cost_R).mean()), 1),
                      "atr_med_pt": round(float(r["atr"].median()), 3)}

    json.dump(R, open(f"{OUT}/exitgrid.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/exitgrid.json")


if __name__ == "__main__":
    main()
