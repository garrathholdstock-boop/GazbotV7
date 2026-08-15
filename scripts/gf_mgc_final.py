#!/usr/bin/env python3
"""GF_MGC FINAL — the two surviving gold cells, taken apart.

    PYTHONPATH=src .venv/bin/python scripts/gf_mgc_final.py

One trigger — a 60-minute level break — and the BOOK decides which of two trades it is:

    VACUUM BREAK   nothing resting in front of the level -> FADE it   (the REVERSION pair)
                   nobody was defending that level, so nobody wanted the price; it comes back.
    WALL BREAK     more size in front of the level than behind it, and it broke ANYWAY
                   -> GO WITH IT   (the MOMENTUM pair). Something ate a defended offer.

That is the 2x2 from a single mechanism rather than four separately-fitted gates, and the sign of
each cell was PREDICTED by the liquidity story before it was priced.

Everything here: MGC $10.00/pt · fee $1.50/RT · BOTH legs cross a ~0.30pt spread · exits raced on
5-second bid/ask bars with every tie resolved AGAINST the trade.
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
    Racer, battery, break_entries, five_second, line, placebo, run_entries, side_split, stat,
)
from gf_mgc_l2 import attach, load_book_5s  # noqa: E402
from gf_mgc_tape import build_tape  # noqa: E402
from gf_mgc_verify import cost_stress, drift_neutral  # noqa: E402

pd.set_option("display.width", 260)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
R: dict = {}


def full_report(name: str, e: pd.DataFrame, racer: Racer, m: pd.DataFrame, *,
                exit_kw: dict, mirror: bool = True) -> pd.DataFrame:
    """Everything the scope demands of a surviving cell, in one block."""
    print("\n" + "#" * 126)
    print(f"# {name}")
    print("#" * 126)
    r = run_entries(racer, e, **exit_kw)
    if r.empty:
        print("  no trades")
        return r
    s = side_split(r)
    print(line("POOLED", stat(r), f"drift-neutral ${drift_neutral(r)}"))
    print(line("  LONG cell", s["LONG"]))
    print(line("  SHORT cell", s["SHORT"]))

    if mirror:
        em = e.copy()
        em["side"] = -em["side"]
        rm = run_entries(racer, em, **exit_kw)
        print(line("  THE MIRROR (same rows, opposite side)", stat(rm)))
        R.setdefault(name, {})["mirror"] = stat(rm)

    print("\n  robustness:")
    for lbl, sub in (("POOLED", r), ("LONG", r[r["side"] > 0]), ("SHORT", r[r["side"] < 0])):
        b = battery(sub)
        print(f"    {lbl}: {stat(sub)}")
        for k, v in b.items():
            print(f"        {k:<14} {v}")
        print(f"        {'cost_stress':<14} {cost_stress(sub)}")
        R.setdefault(name, {}).setdefault("battery", {})[lbl] = {"stat": stat(sub), **b,
                                                                 "cost": cost_stress(sub)}

    print("\n  placebo (same count / days / hours / sides, random minutes, identical exit):")
    for lbl, sub in (("POOLED", r), ("LONG", r[r["side"] > 0]), ("SHORT", r[r["side"] < 0])):
        p = placebo(racer, sub, m, n_runs=30, **exit_kw)
        print(f"    {lbl:<7} {p}")
        R.setdefault(name, {}).setdefault("placebo", {})[lbl] = p

    print("\n  home regime / session:")
    for key in ("regime", "session"):
        rows = [{key: k, "side": sd, **stat(g)}
                for (k, sd), g in r.groupby([key, r["side"].map({1: "LONG", -1: "SHORT"})])]
        t = pd.DataFrame(rows).sort_values(["side", "per"], ascending=[True, False])
        print(f"\n  by {key}:")
        print(t.to_string(index=False))
        R.setdefault(name, {}).setdefault("home", {})[key] = rows

    print("\n  ★ THE EXIT MATRIX (Rule 3 — the entry and the exit are separate questions):")
    grid = []
    fam = [("(a) scalp  tp0.5/sl0.5", dict(stop=0.5, target=0.5, cap_min=120)),
           ("(a) scalp  tp0.75/sl1.0", dict(stop=1.0, target=0.75, cap_min=120)),
           ("(a) scalp  tp1.0/sl1.0", dict(stop=1.0, target=1.0, cap_min=120)),
           ("(a) scalp  tp1.5/sl1.5", dict(stop=1.5, target=1.5, cap_min=120)),
           ("(a) scalp  tp2.0/sl2.0", dict(stop=2.0, target=2.0, cap_min=120)),
           ("(b) chand  stop2/arm2/tr2", dict(stop=2.0, arm=2.0, trail=2.0, cap_min=480)),
           ("(b) chand  stop2.5/arm2/tr2", dict(stop=2.5, arm=2.0, trail=2.0, cap_min=480)),
           ("(b) chand  stop3/arm2/tr2", CHAND),
           ("(b) chand  stop5/arm3/tr3", dict(stop=5.0, arm=3.0, trail=3.0, cap_min=480)),
           ("(d) timecap sl1.5, 60m", dict(stop=1.5, cap_min=60)),
           ("(d) timecap sl1.5, 240m", dict(stop=1.5, cap_min=240)),
           ("(d) timecap sl3.0, 480m", dict(stop=3.0, cap_min=480))]
    for lbl, kw in fam:
        rr = run_entries(racer, e, **kw)
        if rr.empty:
            continue
        ss = side_split(rr)
        grid.append({"exit": lbl, **stat(rr), "LONG$/tr": ss["LONG"]["per"],
                     "SHORT$/tr": ss["SHORT"]["per"], "desk_net": stat(rr, "desk_pnl")["net"],
                     "med_mins": round(float(rr["minutes"].median()), 1)})
    gt = pd.DataFrame(grid)
    print(gt.to_string(index=False))
    # (c) the desk's dual slot
    ra = run_entries(racer, e, stop=1.0, target=1.0, cap_min=120)
    rb = run_entries(racer, e, **CHAND)
    comb = round(float(ra["true_pnl"].sum() + rb["true_pnl"].sum()), 0)
    print(f"  (c) DUAL SLOT  Lot A scalp 1.0R ${stat(ra)['net']:,.0f} + Lot B chandelier "
          f"${stat(rb)['net']:,.0f} = ${comb:,.0f} over {len(ra)} signals "
          f"(${comb / max(len(ra), 1):.2f} per signal, 2 lots)")
    R.setdefault(name, {})["exit_grid"] = grid
    R.setdefault(name, {})["dual"] = {"A": stat(ra), "B": stat(rb), "combined": comb}
    R.setdefault(name, {})["pooled"] = stat(r)
    R.setdefault(name, {})["sides"] = s
    return r


def main() -> None:
    m, q = build_tape()
    racer = Racer(five_second(q))
    print("loading MGC depth ...", flush=True)
    e_all = attach(break_entries(m, fade=True), load_book_5s())
    print(f"{len(e_all)} breaks with a causal book read\n")

    # ── how the book splits the population ──────────────────────────────────────────────────────
    vac = e_all["obstacle"] == 0
    wall = (e_all["ratio"] > 1) & e_all["ratio"].notna()
    mid = ~vac & ~wall
    print(f"POPULATION SPLIT:  vacuum {int(vac.sum())} ({100*vac.mean():.0f}%) · "
          f"wall {int(wall.sum())} ({100*wall.mean():.0f}%) · neither {int(mid.sum())} "
          f"({100*mid.mean():.0f}%)")
    R["split"] = {"vacuum": int(vac.sum()), "wall": int(wall.sum()), "neither": int(mid.sum())}

    # ── THE REVERSION PAIR ──────────────────────────────────────────────────────────────────────
    ev = e_all[vac].reset_index(drop=True)
    rv = full_report("REVERSION PAIR — mgc_vacuum_break_fade  (fade a break into an EMPTY far side)",
                     ev, racer, m, exit_kw=CHAND)

    # ── THE MOMENTUM PAIR ───────────────────────────────────────────────────────────────────────
    ew = e_all[wall].reset_index(drop=True).copy()
    ew["side"] = -ew["side"]          # GO WITH the break, not against it
    rw = full_report("MOMENTUM PAIR — mgc_wall_break_go  (follow a break that ate a DEFENDED level)",
                     ew, racer, m, exit_kw=CHAND)

    # ── the middle bucket, for completeness: neither vacuum nor wall ─────────────────────────────
    en = e_all[mid].reset_index(drop=True)
    rn = run_entries(racer, en, **CHAND)
    rn2 = run_entries(racer, en.assign(side=-en["side"]), **CHAND)
    print("\n" + "=" * 126)
    print("[THE MIDDLE BUCKET] neither a vacuum nor a wall — the book says nothing, so nor should we")
    print("=" * 126)
    print(line("  fade it", stat(rn)))
    print(line("  follow it", stat(rn2)))
    R["middle"] = {"fade": stat(rn), "follow": stat(rn2)}

    # ── the wall threshold plateau ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[PLATEAU] the WALL definition — is +$/tr a plateau or a single lucky cut?")
    print("=" * 126)
    rows = []
    for lbl, mask in (("obstacle > support (ratio>1)", (e_all["ratio"] > 1)),
                      ("obstacle >= support+1", (e_all["obstacle"] >= e_all["support"] + 1)),
                      ("obstacle >= support+2", (e_all["obstacle"] >= e_all["support"] + 2)),
                      ("obstacle >= 3 lots", (e_all["obstacle"] >= 3)),
                      ("obstacle >= 5 lots", (e_all["obstacle"] >= 5)),
                      ("obstacle >= 10 lots", (e_all["obstacle"] >= 10)),
                      ("obstacle>=5 AND ratio>1", (e_all["obstacle"] >= 5) & (e_all["ratio"] > 1)),
                      ("obstacle>=3 AND ratio>1", (e_all["obstacle"] >= 3) & (e_all["ratio"] > 1))):
        sub = e_all[mask.fillna(False)].copy()
        if len(sub) < 10:
            continue
        sub["side"] = -sub["side"]
        rr = run_entries(racer, sub, **CHAND)
        ss = side_split(rr)
        rows.append({"wall rule": lbl, **stat(rr), "LONG$/tr": ss["LONG"]["per"],
                     "SHORT$/tr": ss["SHORT"]["per"]})
    print(pd.DataFrame(rows).to_string(index=False))
    R["wall_plateau"] = rows

    print("\n[PLATEAU] the VACUUM definition:")
    rows = []
    for lbl, mask in (("obstacle == 0", e_all["obstacle"] == 0),
                      ("obstacle < 2", e_all["obstacle"] < 2),
                      ("obstacle < 5", e_all["obstacle"] < 5),
                      ("obstacle < 10", e_all["obstacle"] < 10),
                      ("obstacle==0 AND depletion>0.5",
                       (e_all["obstacle"] == 0) & (e_all["depletion"] > 0.5)),
                      ("obstacle==0 AND US session", (e_all["obstacle"] == 0) & (e_all["session"] == "US"))):
        sub = e_all[mask.fillna(False)]
        if len(sub) < 10:
            continue
        rr = run_entries(racer, sub, **CHAND)
        ss = side_split(rr)
        rows.append({"vacuum rule": lbl, **stat(rr), "LONG$/tr": ss["LONG"]["per"],
                     "SHORT$/tr": ss["SHORT"]["per"]})
    print(pd.DataFrame(rows).to_string(index=False))
    R["vac_plateau"] = rows

    # ── filter placebo on the wall cut ──────────────────────────────────────────────────────────
    print("\n" + "=" * 126)
    print("[FILTER PLACEBO on the WALL cut] keep the same NUMBER of follow-the-break trades at")
    print("    random, 200 times — a filter that wins by dropping losers is beaten by random.")
    print("=" * 126)
    e_follow = e_all.copy()
    e_follow["side"] = -e_follow["side"]
    r_follow_all = run_entries(racer, e_follow, **CHAND)
    rng = np.random.default_rng(20260815)
    keep = wall.reindex(r_follow_all.index).fillna(False).to_numpy()
    real = float(r_follow_all[keep]["true_pnl"].sum())
    k = int(keep.sum())
    draws = [float(r_follow_all["true_pnl"].iloc[rng.choice(len(r_follow_all), size=k, replace=False)].sum())
             for _ in range(200)]
    beaten = sum(1 for x in draws if x >= real)
    print(f"  wall cut: keep n={k}  real ${real:,.0f}  random-keep mean ${np.mean(draws):,.0f}  "
          f"beaten {beaten}/200  pctile {100 * (1 - beaten / 200):.1f}")
    R["wall_filter_placebo"] = {"n": k, "real": round(real, 0),
                                "random_mean": round(float(np.mean(draws)), 0),
                                "beaten": beaten, "runs": 200,
                                "pctile": round(100 * (1 - beaten / 200), 1)}

    # ── trade dumps for the chart + the shadow spec ──────────────────────────────────────────────
    for nm, d in (("vacuum_fade", rv), ("wall_go", rw)):
        if d is not None and not d.empty:
            d.assign(ts=d["ts"].astype(str)).to_json(f"{OUT}/gf_mgc_trades_{nm}.json",
                                                     orient="records")
    json.dump(R, open(f"{OUT}/gf_mgc_final.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/gf_mgc_final.json")


if __name__ == "__main__":
    main()
