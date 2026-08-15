#!/usr/bin/env python3
"""OPEN-NEWS greenfield — the survivor's ROUTER, its symmetry, and the 250ms L2 read.

The scope is explicit that the router is part of the deliverable: a gate is never scored blanket
across all tape, it is scored on the regime it would be ARMED for. So this file asks, for POPSAR:

  1. what its HOME REGIME actually is, in the live router's own vocabulary (ER / ATR / session)
  2. what the exact ARM and BENCH rule would be, and what it is worth ON THAT HOME REGIME ONLY
  3. long/short symmetry — does one side carry it
  4. whether the 250ms L2 book (11 days) separates the winners from the losers at the trigger
  5. the concentration honesty check: what is left after the best day, and the best two days, go
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_engine as E  # noqa: E402
import gf_on_popgo as P  # noqa: E402
import gf_on_popsar as SAR  # noqa: E402
import gf_on_sweep as S  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CACHE = "/home/alphabot/gazbot7/data/cache_gf_on"


def main():
    days = E.load_days()
    lo_t, hi_t = E.attach_regimes(days)
    sigs = S.gen_signals(days, P.sig_popgo, dict(k=2.0, close_frac=0.70, max_trades=3))
    base = SAR.run(days, sigs, stop_k=1.0, max_rev=1)
    res = {"atr_terciles": [lo_t, hi_t], "headline": E.score(base)}

    # ── 1/2. the router: sweep the ARM condition in the live router's vocabulary ───────────
    router = {}
    for ermin in (0.0, 0.15, 0.20, 0.25, 0.30, 0.40):
        sel = [t for t in base if not np.isnan(t["er"]) and t["er"] >= ermin]
        router[f"ER>={ermin}"] = E.score(sel)
    for amin in (0, 10, 15, 20, 25, 30):
        sel = [t for t in base if t["atr"] >= amin]
        router[f"ATR>={amin}pt"] = E.score(sel)
    res["router_sweep"] = router
    print("── ROUTER ARM SWEEP (POPSAR, one condition at a time) ──")
    print(E.table(router, "arm condition"))

    combo = {}
    for ermin in (0.0, 0.20, 0.25):
        for amin in (0, 15, 20):
            sel = [t for t in base if t["atr"] >= amin and not np.isnan(t["er"]) and t["er"] >= ermin]
            combo[f"ER>={ermin} & ATR>={amin}"] = E.score(sel)
    res["router_combo"] = combo
    print("\n── ROUTER ARM, TWO CONDITIONS ──")
    print(E.table(combo, "arm condition"))

    HOME = [t for t in base if t["atr"] >= 15 and not np.isnan(t["er"]) and t["er"] >= 0.20]
    BENCH = [t for t in base if t not in HOME]
    res["home"] = {"rule": "ARM 13:30-15:00Z when ATR14(1m) >= 15pt AND ER30 >= 0.20; BENCH otherwise",
                   "on_home": E.score(HOME), "on_benched": E.score(BENCH),
                   "by_regime_home": E.by(HOME, lambda t: t["regime"]),
                   "by_day_home": E.by(HOME, lambda t: t["day"])}
    print(f"\n   HOME  n={res['home']['on_home']['n']} net=${res['home']['on_home']['net']:+.0f} "
          f"$/tr={res['home']['on_home']['per']:+.2f}")
    print(f"   what the bench would have refused: n={res['home']['on_benched']['n']} "
          f"net=${res['home']['on_benched']['net']:+.0f}")

    srt = sorted(HOME, key=lambda t: -t["net"])
    for k in (1, 3, 5):
        res["home"][f"strip_{k}"] = E.score(srt[k:])
    bd = E.by(HOME, lambda t: t["day"])
    worst_days = sorted(bd.items(), key=lambda x: -x[1]["net"])
    res["home"]["strip_best_day"] = E.score([t for t in HOME if t["day"] != worst_days[0][0]])
    res["home"]["strip_best_2_days"] = E.score(
        [t for t in HOME if t["day"] not in {worst_days[0][0], worst_days[1][0]}])
    loo = {d: E.score([t for t in HOME if t["day"] != d]) for d in sorted({t["day"] for t in HOME})}
    res["home"]["loo"] = {"days": len(loo), "min_net": min(v["net"] for v in loo.values()),
                          "n_negative": sum(1 for v in loo.values() if v["net"] < 0)}
    print(f"   strip-1 ${res['home']['strip_1']['net']:+.0f}  strip-3 ${res['home']['strip_3']['net']:+.0f}  "
          f"strip-5 ${res['home']['strip_5']['net']:+.0f}")
    print(f"   strip best DAY ${res['home']['strip_best_day']['net']:+.0f}   "
          f"best TWO days ${res['home']['strip_best_2_days']['net']:+.0f}")
    print(f"   LOO worst ${res['home']['loo']['min_net']:+.0f} "
          f"({res['home']['loo']['n_negative']}/{res['home']['loo']['days']} negative)")

    # ── 3. long/short symmetry ────────────────────────────────────────────────────────────
    res["symmetry"] = {"all": E.by(base, lambda t: "LONG" if t["dir"] > 0 else "SHORT"),
                       "home": E.by(HOME, lambda t: "LONG" if t["dir"] > 0 else "SHORT")}
    print("\n── LONG/SHORT SYMMETRY ──")
    print(E.table(res["symmetry"]["all"], "side (all)"))
    print(E.table(res["symmetry"]["home"], "side (home)"))

    # ── 4. the 250ms L2 read ──────────────────────────────────────────────────────────────
    import duckdb
    con = duckdb.connect()
    con.execute("SET memory_limit='2GB'; SET threads=3")
    bookdays = set(x[0] for x in con.execute(
        f"SELECT DISTINCT d FROM read_parquet('{CACHE}/book_win.parquet')").fetchall())
    withbook = [t for t in base if t["day"] in bookdays]
    print(f"\n── L2 BOOK (capture.db book, 41ms event-driven, L1-3) — {len(bookdays)} days, "
          f"{len(withbook)} of {len(base)} trades ──")
    rows = []
    for t in withbook:
        s0, s1 = t["entry_sod"] - 30, t["entry_sod"]
        r = con.execute(f"""
            SELECT COALESCE(SUM(CASE WHEN side='bid' THEN size END),0),
                   COALESCE(SUM(CASE WHEN side='ask' THEN size END),0)
            FROM read_parquet('{CACHE}/book_win.parquet')
            WHERE d='{t['day']}' AND sod>={s0} AND sod<{s1}""").fetchone()
        bid, ask = float(r[0]), float(r[1])
        if bid + ask <= 0:
            continue
        far = ask if t["dir"] > 0 else bid
        rows.append({**t, "far_share": far / (bid + ask)})
    if rows:
        med = float(np.median([r["far_share"] for r in rows]))
        thin = [r for r in rows if r["far_share"] < med]
        thick = [r for r in rows if r["far_share"] >= med]
        res["book"] = {"days": len(bookdays), "trades": len(rows), "median_far_share": round(med, 3),
                       "far_side_THIN": E.score(thin), "far_side_THICK": E.score(thick),
                       "note": "far side = the side price is about to run INTO. Thin = depleted = "
                               "the book supposedly telegraphing the move."}
        print(f"   median far-side share of L1-3 depth in the 30s before entry: {med:.3f}")
        print(E.table({"far side THIN (depleted)": E.score(thin),
                       "far side THICK": E.score(thick)}, "book state"))
    else:
        res["book"] = {"days": len(bookdays), "trades": 0, "note": "no overlap"}

    json.dump(res, open(f"{SEC}/gf_on_final.json", "w"), indent=1, default=float)
    print(f"\n→ {SEC}/gf_on_final.json")


if __name__ == "__main__":
    main()
