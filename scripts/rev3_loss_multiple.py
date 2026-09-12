#!/usr/bin/env python3
"""THE REALISED LOSS MULTIPLE — what a shadow arm actually costs once it goes live.

★ WHY (2026-08-30, Rev 3). MONDAY #1's whole kill criterion turns on 1.64x ("a realised loss
multiple above 1.64x makes this a null") and the report quotes a standing 1.1x-3.1x band with NO
source. Both are hypotheticals. This desk has run FOUR gates live alongside a shadow twin on the
same tape, which means the multiple is MEASURABLE — from our own book, not from a rule of thumb.

METHOD. For each live gate that has a shadow mirror, pair every live LOT with the mirror's trade on
the same side whose entry timestamp is within +/-TOL seconds. Score the live lot on pnl_usd (already
net of the $1.50 round trip) and the shadow lot on real_pnl (the tick-repriced honest column, never
ceiling_pnl). The multiple is a $/trade ratio:

    loss multiple = (shadow $/trade)  /  (live $/trade)      when both are the same sign
                  = "the shadow said X, the desk got Y"

Reported per gate with n, and with the LOSER-ONLY multiple beside it, because the criterion the
card states is about losses specifically. ⚠ A/B lots are a SCALE-OUT, not two experiments — the
live side is collapsed to one row per signal (mean of its lots) before pairing, or two lots of one
signal would count as two independent live observations.

  PYTHONPATH=src .venv/bin/python scripts/rev3_loss_multiple.py
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import defaultdict

DB = "/home/alphabot/gazbot7/data/gazbot7.db"
SH = "/home/alphabot/gazbot7/data/shadow.db"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev3_loss_multiple.json"
TOL = 300     # seconds — a 5-minute window; 600s starts pairing different impulses

PAIRS = {
    "capitulation_long": ["capit_live_mirror"],
    "grind_long":        ["cx_grindA_live", "sw_grind_A_k10", "bank20_grindA_ctl"],
    "abs_veto_long":     ["abs_veto_55s"],
    "abs_veto_short":    ["abs_veto_55s", "thrust_short_absveto55"],
}


def main():
    d = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    s = sqlite3.connect(f"file:{SH}?mode=ro", uri=True)

    live = defaultdict(list)
    for gate, side, opened, pnl in d.execute(
            "SELECT gate, side, opened_at, pnl_usd FROM trades "
            "WHERE gate IS NOT NULL AND gate<>'day_rider' AND data_quality IS NULL"):
        base = gate.replace("_A", "").replace("_B", "")
        if base not in PAIRS:
            continue
        ts = int(dt.datetime.fromisoformat(opened).timestamp())
        live[base].append((ts, side, pnl))

    # collapse the A/B scale-out into ONE live observation per signal
    sig = defaultdict(dict)
    for g, rows in live.items():
        for ts, side, pnl in rows:
            key = None
            for k in sig[g]:
                if abs(k - ts) <= 5 and sig[g][k]["side"] == side:
                    key = k
                    break
            if key is None:
                sig[g][ts] = {"side": side, "lots": [pnl]}
            else:
                sig[g][key]["lots"].append(pnl)

    res = {"tol_s": TOL, "note": "live pnl_usd is already net of $1.50/RT; shadow scored on real_pnl",
           "gates": {}}
    for g, arms in PAIRS.items():
        shadow = []
        for a in arms:
            shadow += s.execute(
                "SELECT t.entry_ts, t.side, r.real_pnl, t.strategy FROM shadow_trades t "
                "JOIN shadow_real r ON r.trade_id=t.id "
                "WHERE t.strategy=? AND (t.data_quality IS NULL) AND r.real_pnl IS NOT NULL",
                (a,)).fetchall()
        rows = []
        used = set()
        for ts, v in sorted(sig[g].items()):
            lv = sum(v["lots"]) / len(v["lots"])
            best = None
            for i, (ets, sd, rp, strat) in enumerate(shadow):
                if i in used or sd != v["side"] or abs(ets - ts) > TOL:
                    continue
                if best is None or abs(ets - ts) < abs(shadow[best][0] - ts):
                    best = i
            if best is None:
                continue
            used.add(best)
            rows.append({"ts": dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m-%d %H:%M:%S"),
                         "side": v["side"], "lots": len(v["lots"]),
                         "live": round(lv, 2), "shadow": round(shadow[best][2], 2),
                         "arm": shadow[best][3]})
        if not rows:
            res["gates"][g] = {"n": 0, "note": "no timestamp-matched pairs"}
            continue
        lsum = sum(r["live"] for r in rows)
        ssum = sum(r["shadow"] for r in rows)
        losers = [r for r in rows if r["shadow"] < 0]
        res["gates"][g] = {
            "arms": arms, "n": len(rows),
            "live_per_trade": round(lsum / len(rows), 2),
            "shadow_per_trade": round(ssum / len(rows), 2),
            "live_total": round(lsum, 2), "shadow_total": round(ssum, 2),
            "haircut_usd_per_trade": round((ssum - lsum) / len(rows), 2),
            "loser_n": len(losers),
            "loser_live_per_trade": round(sum(r["live"] for r in losers) / len(losers), 2) if losers else None,
            "loser_shadow_per_trade": round(sum(r["shadow"] for r in losers) / len(losers), 2) if losers else None,
            "loser_multiple": (round(sum(r["live"] for r in losers) / sum(r["shadow"] for r in losers), 3)
                               if losers and sum(r["shadow"] for r in losers) else None),
            "pairs": rows,
        }

    allr = [r for g in res["gates"].values() if g.get("pairs") for r in g["pairs"]]
    los = [r for r in allr if r["shadow"] < 0]
    res["desk"] = {
        "n": len(allr),
        "live_per_trade": round(sum(r["live"] for r in allr) / len(allr), 2) if allr else None,
        "shadow_per_trade": round(sum(r["shadow"] for r in allr) / len(allr), 2) if allr else None,
        "haircut_usd_per_trade": round((sum(r["shadow"] for r in allr) - sum(r["live"] for r in allr)) / len(allr), 2) if allr else None,
        "loser_n": len(los),
        "loser_multiple": round(sum(r["live"] for r in los) / sum(r["shadow"] for r in los), 3) if los and sum(r["shadow"] for r in los) else None,
    }

    json.dump(res, open(OUT, "w"), indent=1)
    for g, v in res["gates"].items():
        if not v.get("n"):
            print(f"{g:20} {v.get('note')}")
            continue
        print(f"{g:20} n={v['n']:3}  live {v['live_per_trade']:>8}/tr  shadow {v['shadow_per_trade']:>8}/tr  "
              f"haircut {v['haircut_usd_per_trade']:>8}/tr  losers n={v['loser_n']:2} "
              f"live {v['loser_live_per_trade']} vs shadow {v['loser_shadow_per_trade']} "
              f"= {v['loser_multiple']}x")
    print("DESK:", res["desk"])
    print("->", OUT)


if __name__ == "__main__":
    main()
