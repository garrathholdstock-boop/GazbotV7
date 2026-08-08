#!/usr/bin/env python3
"""LIVE-ENTRY EXIT REPRICE — what the deployed exit ladder cost, on the REAL fills.

exit_ladder_lab_v2.py sweeps exits over the UNGATED shadow entry book. That answers "what exit
suits this signal", but the desk does not trade the ungated book — the router arms and benches, so
the population that actually trades is the LIVE fills. This reprices EVERY real live entry (one row
per ENTRY, lots de-duplicated) on the forward 5s path across the same exit grid, segmented by the
exit-ladder rungs, and reports the deployed ladder's rank against the grid.

Conservative: same-bar stop-first, 1-ATR stop from the ATR read at entry, $2/pt, $1.50/lot fee,
60-min horizon, 2-lot basis. READ-ONLY.

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/live_entry_exit_reprice.py [--since 2026-08-03]
"""
from __future__ import annotations
import argparse, json, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

VPP, FEE, HORIZON_MIN, STOP_ATR = 2.0, 1.5, 60, 1.0
CAP = "/home/alphabot/gazbot7/data/capture.db"
STORE = "/home/alphabot/gazbot7/data/gazbot7.db"

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-08-03")
ap.add_argument("--all", action="store_true", help="whole archive, not just this week")
a = ap.parse_args()
SINCE = "2026-07-15" if a.all else a.since

cap = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
bars = cap.execute("SELECT bar_ts,high,low,close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
                   "AND bar_ts>=strftime('%s','2026-07-15') ORDER BY bar_ts").fetchall()
bts = np.array([b[0] for b in bars], dtype=np.int64)
bh = np.array([b[1] for b in bars]); bl = np.array([b[2] for b in bars]); bc = np.array([b[3] for b in bars])

mn = {}
for ts, h, l, c in bars:
    mn[ts // 60] = (h, l, c)
mk = sorted(mn); mh = [mn[k][0] for k in mk]; ml = [mn[k][1] for k in mk]; mc = [mn[k][2] for k in mk]
tr = [0.0] * len(mk)
for i in range(1, len(mk)):
    tr[i] = max(mh[i] - ml[i], abs(mh[i] - mc[i - 1]), abs(ml[i] - mc[i - 1]))
er_at, atr_at = {}, {}
for i in range(30, len(mk)):
    if mk[i] - mk[i - 30] == 30:
        seg = mc[i - 30:i + 1]
        p = sum(abs(seg[j] - seg[j - 1]) for j in range(1, len(seg)))
        er_at[mk[i]] = (abs(seg[-1] - seg[0]) / p) if p > 0 else 0.0
for i in range(14, len(mk)):
    if mk[i] - mk[i - 14] == 14:
        atr_at[mk[i]] = sum(tr[i - 13:i + 1]) / 14


def rung(m):
    e = er_at.get(m)
    if e is None: return None
    return "BIG-TREND" if e >= 0.50 else ("MED-TREND" if e >= 0.30 else "SCALP-CHOP")


# ── live entries, ONE ROW PER ENTRY (the _A/_B lots are the same signal) ────
g = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
rows = g.execute(
    "SELECT opened_at, gate, side, entry_price, pnl_usd FROM trades "
    "WHERE symbol='MNQ' AND closed_at>=? AND gate<>'day_rider_crossdesk' ORDER BY opened_at",
    (SINCE,)).fetchall()
entries, live_by_gate = {}, defaultdict(float)
for o, gate, side, ep, p in rows:
    base = gate.replace("_A", "").replace("_B", "")
    live_by_gate[base] += p
    ts = int(datetime.fromisoformat(o).timestamp())
    key = (base, ts // 60 * 60 if False else ts - (ts % 60), side)   # collapse A/B (same minute)
    if key not in entries:
        entries[key] = (base, side, ep, ts)

A_RS = [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
B_RS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 6.0]
SCALP = [(x, y) for x in A_RS for y in B_RS if y > x]
CH = {"wide": (3.5, 6.0, 0.5), "mid": (2.0, 4.0, 0.5), "tight": (1.5, 3.0, 0.5)}
RIDE_A = [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
# what is ACTUALLY deployed today (data/exit_overrides.json)
DEPLOYED = {"grind_long": "A2.5 + wideChand", "capitulation_long": "A1.5 + tightChand",
            "exhaustion_short": "A0.75 + tightChand", "abs_veto_long": "scalp 1.0/1.5",
            "abs_veto_short": "scalp 1.5/2.5", "rgv_short": "A1.5 + tightChand",
            "nipc_long": "scalp 2.0/2.5", "nipc_short": "scalp 2.0/2.5"}


def scalp_r(favcum, stop_idx, target, cf_last):
    reach = int(np.argmax(favcum >= target)) if (favcum >= target).any() else len(favcum)
    if reach <= stop_idx: return target
    if stop_idx < len(favcum): return -STOP_ATR
    return max(min(cf_last, target), -STOP_ATR)


def chand_r(fav, cf, stop_idx, sk, lr, lk):
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_idx: return -STOP_ATR
        peak = max(peak, fav[i])
        k = lk if peak >= lr else sk
        t = peak - k
        if peak > 0 and t > 0 and cf[i] <= t: return t
    return max(min(cf[-1], peak), -STOP_ATR)


agg = defaultdict(lambda: defaultdict(list))
detail = []
for (base, _, _), (gate, side, ep, ts) in entries.items():
    m = ts - (ts % 60)
    atr = atr_at.get(m // 60)
    rg = rung(m // 60)
    if not atr or atr <= 0 or rg is None:
        continue
    i0 = int(np.searchsorted(bts, ts)); j1 = min(i0 + HORIZON_MIN * 12, len(bts))
    if j1 - i0 < 2:
        continue
    h, l, c = bh[i0:j1], bl[i0:j1], bc[i0:j1]
    if side == "LONG":
        fav, adv, cf = (h - ep) / atr, (ep - l) / atr, (c - ep) / atr
    else:
        fav, adv, cf = (ep - l) / atr, (h - ep) / atr, (ep - c) / atr
    favcum = np.maximum.accumulate(fav)
    stop_idx = int(np.argmax(adv >= STOP_ATR)) if (adv >= STOP_ATR).any() else len(fav)
    cfl = cf[-1]
    lot = lambda rr: (rr * atr * VPP) - FEE
    pol = {}
    for (x, y) in SCALP:
        pol[f"scalp {x}/{y}"] = lot(scalp_r(favcum, stop_idx, x, cfl)) + lot(scalp_r(favcum, stop_idx, y, cfl))
    for lbl, (sk, lr, lk) in CH.items():
        rc = chand_r(fav, cf, stop_idx, sk, lr, lk)
        pol[f"{lbl}Chand x2"] = 2 * lot(rc)
        for x in RIDE_A:
            pol[f"A{x} + {lbl}Chand"] = lot(scalp_r(favcum, stop_idx, x, cfl)) + lot(rc)
    for cell in ((gate, "ALL"), (gate, rg)):
        for p, v in pol.items():
            agg[cell][p].append(v)
    # reachable MFE with the stop respected
    reach_mfe = float(favcum[:stop_idx].max()) if stop_idx > 0 else 0.0
    detail.append(dict(gate=gate, at=datetime.fromtimestamp(ts, timezone.utc).strftime("%m-%d %H:%M"),
                       side=side, atr=round(atr, 1), rung=rg, reach_mfe_R=round(reach_mfe, 2),
                       deployed=round(pol.get(DEPLOYED.get(gate, ""), float("nan")), 1),
                       best=round(max(pol.values()), 1)))

print(f"live entries repriced: {len(detail)}  (window from {SINCE})\n")
print(f"{'gate':19}{'rung':12}{'n':>4}  {'DEPLOYED ladder':20}{'$/entry':>9}  {'GRID BEST':20}{'$/entry':>9}{'rank':>8}")
print("-" * 106)
out = {}
for (gate, rg), pol in sorted(agg.items()):
    ranked = sorted(((sum(v) / len(v), p, len(v)) for p, v in pol.items()), reverse=True)
    n = ranked[0][2]
    if n < 3:
        continue
    dep = DEPLOYED.get(gate)
    dm = sum(pol[dep]) / len(pol[dep]) if dep in pol else None
    rank = 1 + [p for _, p, _ in ranked].index(dep) if dep in pol else None
    bm, bp, _ = ranked[0]
    print(f"{gate:19}{rg:12}{n:>4}  {(dep or '-'):20}{(dm if dm is not None else float('nan')):>+9.1f}  "
          f"{bp:20}{bm:>+9.1f}{(f'{rank}/{len(ranked)}' if rank else '-'):>8}")
    out[f"{gate}|{rg}"] = dict(n=n, deployed=dep, deployed_mean=None if dm is None else round(dm, 1),
                               deployed_rank=rank, of=len(ranked), best=bp, best_mean=round(bm, 1),
                               top5=[{"policy": p, "mean": round(mm, 1)} for mm, p, _ in ranked[:5]])

print("\n=== biggest give-ups: entries whose reachable MFE dwarfed the deployed ladder ===")
print(f"{'gate':19}{'when':13}{'rung':12}{'ATR':>6}{'reachMFE_R':>12}{'deployed$':>11}{'best$':>9}")
rows2 = [d for d in detail if d["deployed"] == d["deployed"]]
for d in sorted(rows2, key=lambda x: -(x["best"] - x["deployed"]))[:18]:
    print(f"{d['gate']:19}{d['at']:13}{d['rung']:12}{d['atr']:>6.1f}{d['reach_mfe_R']:>12.2f}"
          f"{d['deployed']:>+11.1f}{d['best']:>+9.1f}")

json.dump({"cells": out, "detail": detail}, open("/home/alphabot/gazbot7/scratchpad/live_entry_reprice.json", "w"), indent=1)
print("\n-> scratchpad/live_entry_reprice.json")
