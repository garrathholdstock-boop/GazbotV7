#!/usr/bin/env python3
"""THE EXIT-LADDER PROOF — per gate-family x REGIME RUNG, on the widest tape this desk holds.

Extends scripts/adaptive_exit_bt_ext.py in the three ways the BIG-TREND rung needs:
  1. TAPE = the UNION of the parquet lake's 5s bars (2026-06-19..08-27) and capture.db's own
     5s bars (2026-07-15..08-28). The lake alone stops a day short of this report's week.
  2. ENTRIES = THREE independent pools, not two — V7 shadow, the retired V5 desk's shadow sims,
     and the V5 desk's 574 REAL MNQ fills (an actual-money pool, the strongest OOS leg we own).
  3. The RUNG BOUNDARY is itself swept (ER 0.40/0.45/0.50/0.55), because "BIG-TREND is tiny-n"
     may be a fact about the definition rather than about the tape.

Per winning cell: strip-the-best-3, leave-one-day-out worst, first/second half, per-POOL split,
and a PARAMETER-PLATEAU read (the mean of the immediate grid neighbours). A peak with a dead
plateau is a curve-fit; a plateau is an edge.

Costs: $2.00/point (MNQ), $1.50 per ROUND TRIP per lot, 2 lots. Stop = 1.0x entry ATR and wins
any same-bar race (conservative). Horizon 60 min.

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/exit_ladder_proof.py
"""
from __future__ import annotations
import json, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timezone

import duckdb
import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect

VPP, FEE, HORIZON_MIN, STOP_K = 2.0, 1.5, 60, 1.0
OUT = "/home/alphabot/gazbot7/data/exit_ladder_proof.json"
V5SIM = "/tmp/v5/fut_shadow_sim_trades.parquet"
V5REAL = "/tmp/v5/trades.parquet"
CAP = "/home/alphabot/gazbot7/data/capture.db"

# ───────────────────────── 1. the UNION tape ─────────────────────────
print("loading 5s tape — parquet lake UNION capture.db …")
con = connect(symbol="MNQ")
L = con.execute("SELECT bar_ts, high, low, close FROM bars WHERE timeframe='5s'").df()
con.close()
d = duckdb.connect()
d.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
C = d.execute("SELECT bar_ts, high, low, close FROM c.bars "
              "WHERE symbol='MNQ' AND timeframe='5s'").df()
d.close()
import pandas as pd
B = (pd.concat([L, C]).drop_duplicates(subset="bar_ts", keep="first")
       .sort_values("bar_ts").reset_index(drop=True))
bts = B.bar_ts.values.astype(np.int64)
bh, bl, bc = B.high.values.astype(float), B.low.values.astype(float), B.close.values.astype(float)
print(f"  lake {len(L):,} + capture {len(C):,} → union {len(bts):,} 5s bars  "
      f"{datetime.fromtimestamp(bts[0],timezone.utc):%Y-%m-%d} .. "
      f"{datetime.fromtimestamp(bts[-1],timezone.utc):%Y-%m-%d}")

mdf = B.assign(m=(B.bar_ts // 60)).groupby("m").close.last()
mk = mdf.index.values.astype(np.int64); mc = mdf.values.astype(float)
csum = np.cumsum(np.abs(np.diff(mc, prepend=mc[0])))
er = np.zeros(len(mc))
for i in range(30, len(mc)):
    path = csum[i] - csum[i - 30]
    er[i] = abs(mc[i] - mc[i - 30]) / path if path > 0 else 0.0
ER = dict(zip(mk.tolist(), er.tolist()))

# how much of the tape IS each rung? (the honest answer to "why is BIG-TREND tiny-n")
pop = {f"ER>={t:.2f}": float(100 * (er[30:] >= t).mean()) for t in (0.40, 0.45, 0.50, 0.55, 0.60)}
print("  tape-minute population: " + " · ".join(f"{k} {v:.1f}%" for k, v in pop.items()))

def rung(atr, ts, er_hi=0.50, er_mid=0.30):
    e = ER.get(ts // 60, 0.0)
    if e >= er_hi: return "BIG-TREND"
    if e >= er_mid: return "MED-TREND"
    if atr >= 22:   return "STAY-OUT"
    return "SCALP-CHOP"

# ───────────────────────── 2. THREE entry pools ─────────────────────────
FAM7 = {"grind (mom)": ["grind_fast", "sw_grind_A_k10", "sw_grind_A_k20", "sw_grind_B_k10"],
        "thrust/absveto": ["thrust_loose", "thrust_short_raw", "thrust_cont", "abs_veto_55s"],
        "rgv (fade)": ["rg_long_fast", "rg_short_025_raw", "rg_long_fast_v"],
        "capitulation (fade)": ["capit_loose"],
        "exhaustion (fade)": ["exhaustion_rev"]}
S2F = {s: f for f, ss in FAM7.items() for s in ss}
rows = []
sh = sqlite3.connect("/home/alphabot/gazbot7/data/shadow.db")
ph = ",".join("?" * len(S2F))
for st, side, ts, ep, atr in sh.execute(
        "SELECT strategy,side,entry_ts,entry_price,entry_atr FROM shadow_trades "
        "WHERE entry_atr>0 AND strategy IN (" + ph + ")", list(S2F)):
    rows.append((S2F[st], "V7", side, int(ts), float(ep), float(atr)))
sh.close()

V5MAP = {"momentum_shadow": "grind (mom)", "tw_ride_strength": "grind (mom)",
         "trend_donch": "grind (mom)", "orb_shadow": "grind (mom)",
         "orb_shadow_isolated": "grind (mom)",
         "tw_mnq_thrust_loose": "thrust/absveto", "tw_mnq_thrust_cont": "thrust/absveto",
         "tw_mnq_thrust_floor00": "thrust/absveto", "tw_mnq_thrust_floor03": "thrust/absveto",
         "tw_mnq_thrust_floor04": "thrust/absveto", "tw_us_open_surge_cont": "thrust/absveto",
         "dip_loose": "capitulation (fade)", "dip_loose_absorption": "capitulation (fade)",
         "pullback_loose": "rgv (fade)", "pullback_quiet": "rgv (fade)",
         "tw_strength_ceiling_pb": "rgv (fade)",
         "passive_chop": "exhaustion (fade)", "passive_chop_calm": "exhaustion (fade)",
         "passive_chop_gated": "exhaustion (fade)"}
try:
    d = duckdb.connect()
    for st, side, ts, ep, atr in d.execute(
            f"SELECT strategy,side,entry_ts,entry_price,entry_atr_abs FROM '{V5SIM}' "
            f"WHERE symbol='MNQ' AND entry_atr_abs>0").fetchall():
        if V5MAP.get(st):
            rows.append((V5MAP[st], "V5sim", side.upper(), int(ts), float(ep), float(atr)))
    # V5 REAL fills — actual money, the strongest independent pool
    GATEMAP = {"momentum": "grind (mom)", "thrust": "thrust/absveto", "pullback": "rgv (fade)",
               "dip": "capitulation (fade)", "chop": "exhaustion (fade)"}
    for gate, side, oa, ep, natr in d.execute(
            f"SELECT entry_gate, side, opened_at, entry_price, entry_net_atr FROM '{V5REAL}' "
            f"WHERE symbol='MNQ' AND discipline='us_futures_daytrade' AND entry_price>0").fetchall():
        fam = next((f for k, f in GATEMAP.items() if gate and k in str(gate).lower()), None)
        if not fam:
            continue
        ts = int(datetime.fromisoformat(oa).timestamp())
        i0 = int(np.searchsorted(bts, ts))
        if i0 >= len(bts) - 12:
            continue
        # V5 rows carry no absolute ATR: rebuild it from the tape (14x1min true range)
        j = int(np.searchsorted(mk, ts // 60))
        if j < 15:
            continue
        atr = float(np.mean(np.abs(np.diff(mc[j - 15:j]))) * 3.0)   # crude 1m-range proxy
        if atr <= 0:
            continue
        rows.append((fam, "V5real", side.upper(), ts, float(ep), atr))
    d.close()
except Exception as e:
    print(f"  ⚠ V5 archive unavailable ({e}) — V7-only run")
for p in ("V7", "V5sim", "V5real"):
    print(f"  {p:7} entries: {sum(1 for r in rows if r[1]==p):,}")

# ───────────────────────── 3. the exit models ─────────────────────────
A_RS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
B_RS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
COMBOS = [(a, b) for a in A_RS for b in B_RS if b > a]
CHANDS = {"chand k1.5": 1.5, "chand k2.0": 2.0, "chand k2.5": 2.5, "chand k3.5": 3.5}

def leg_r(favcum, stop_i, target, cf_last):
    hit = int(np.argmax(favcum >= target)) if (favcum >= target).any() else len(favcum)
    if hit < stop_i: return target
    if stop_i < len(favcum): return -1.0
    return max(min(cf_last, target), -1.0)

def chand_r(fav, cf, stop_i, k):
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_i: return -1.0
        peak = max(peak, fav[i]); trail = peak - k
        if trail > 0 and cf[i] <= trail: return trail
    return max(min(cf[-1], peak), -1.0)

def wide_chand_r(fav, cf, stop_i):
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_i: return -1.0
        peak = max(peak, fav[i]); k = 0.5 if peak >= 6 else 3.5; trail = peak - k
        if trail > 0 and cf[i] <= trail: return trail
    return max(min(cf[-1], peak), -1.0)

ERHI = [0.40, 0.45, 0.50, 0.55]
agg = {h: defaultdict(lambda: defaultdict(list)) for h in ERHI}
seen, skipped = set(), 0
for fam, pool, side, ts, ep, atr in rows:
    key = (fam, pool, ts, round(ep, 2))
    if key in seen: continue
    seen.add(key)
    i0 = int(np.searchsorted(bts, ts)); j1 = min(i0 + HORIZON_MIN * 12, len(bts))
    if j1 - i0 < 12: skipped += 1; continue
    h, l, c = bh[i0:j1], bl[i0:j1], bc[i0:j1]
    if side.upper().startswith(("L", "B")):
        fav, adv, cf = (h - ep) / atr, (ep - l) / atr, (c - ep) / atr
    else:
        fav, adv, cf = (ep - l) / atr, (h - ep) / atr, (ep - c) / atr
    favcum = np.maximum.accumulate(fav)
    stop_i = int(np.argmax(adv >= STOP_K)) if (adv >= STOP_K).any() else len(fav)
    cfl = float(cf[-1]); day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
    usd = lambda r: (r * atr * VPP) - FEE
    legs = {f"A{a}/B{b}": usd(leg_r(favcum, stop_i, a, cfl)) + usd(leg_r(favcum, stop_i, b, cfl))
            for a, b in COMBOS}
    for nm, k in CHANDS.items():
        legs[f"{nm} x2"] = usd(chand_r(fav, cf, stop_i, k)) * 2
    rw = wide_chand_r(fav, cf, stop_i)
    legs["wideChand(6.0) x2"] = usd(rw) * 2
    for a in (1.0, 1.5, 2.0, 2.5):
        legs[f"A{a} + wideChand"] = usd(leg_r(favcum, stop_i, a, cfl)) + usd(rw)
    for hcut in ERHI:
        bucket = agg[hcut][(fam, rung(atr, ts, hcut))]
        for p, v in legs.items():
            bucket[p].append((day, pool, v))
print(f"  scored {len(seen)-skipped:,} entries ({skipped:,} had no forward tape)")

def battery(vals):
    v = np.array([x[2] for x in vals]); days = np.array([x[0] for x in vals])
    pools = np.array([x[1] for x in vals]); n = len(v)
    s = np.sort(v)
    loo = [float(np.delete(v, np.where(days == dd)).mean()) for dd in np.unique(days) if (days != dd).any()]
    half = n // 2
    out = dict(n=n, mean=float(v.mean()), tot=float(v.sum()), win=float(100*(v > 0).mean()),
               days=int(len(np.unique(days))),
               strip3=float(s[:-3].mean()) if n > 3 else None,
               loo_worst=float(min(loo)) if loo else None,
               h1=float(v[:half].mean()) if half else None,
               h2=float(v[half:].mean()) if half else None)
    for p in ("V7", "V5sim", "V5real"):
        m = pools == p
        out[f"{p}_n"] = int(m.sum()); out[f"{p}_mean"] = float(v[m].mean()) if m.any() else None
    return out

def plateau(cells, best):
    """mean of the immediate A/B grid neighbours of `best` — a peak with a dead plateau is a fit."""
    if not best.startswith("A") or "/B" not in best: return None, 0
    a = float(best[1:best.index("/B")]); b = float(best[best.index("/B")+2:])
    ai, bi = A_RS.index(a), B_RS.index(b)
    ns = []
    for da in (-1, 0, 1):
        for db in (-1, 0, 1):
            if da == 0 and db == 0: continue
            i, j = ai+da, bi+db
            if 0 <= i < len(A_RS) and 0 <= j < len(B_RS) and B_RS[j] > A_RS[i]:
                k = f"A{A_RS[i]}/B{B_RS[j]}"
                if k in cells: ns.append(cells[k]["mean"])
    return (float(np.mean(ns)) if ns else None), len(ns)

res = {}
for hcut in ERHI:
    for (fam, rg), pol in sorted(agg[hcut].items()):
        cells = {p: battery(v) for p, v in pol.items() if len(v) >= 12}
        if not cells: continue
        best = max(cells, key=lambda p: cells[p]["mean"])
        med = float(np.median([c["mean"] for c in cells.values()]))
        pl, npl = plateau(cells, best)
        res.setdefault(str(hcut), {}).setdefault(fam, {})[rg] = {
            "best": best, "median_cell_mean": med, "plateau_mean": pl, "plateau_n": npl,
            "cells": cells}

with open(OUT, "w") as f:
    json.dump({"rung_population_pct": pop, "results": res}, f, indent=1)

for hcut in ERHI:
    tag = "  <- the operator's stated rung" if hcut == 0.50 else ""
    print(f"\n{'='*126}\nBIG-TREND boundary ER >= {hcut:.2f}{tag}\n{'='*126}")
    print(f"{'family':21}{'rung':11}{'n':>5}{'d':>4}  {'best exit':20}{'$/sig':>8}{'median':>8}"
          f"{'plateau':>8}{'strip3':>8}{'LOOwst':>8}{'h1':>7}{'h2':>7}{'V7':>7}{'V5sim':>7}{'V5real':>7}")
    print("-" * 126)
    for fam in FAM7:
        for rg in ("BIG-TREND", "MED-TREND", "SCALP-CHOP", "STAY-OUT"):
            cell = res.get(str(hcut), {}).get(fam, {}).get(rg)
            if not cell: continue
            b = cell["cells"][cell["best"]]
            f = lambda k: f"{b[k]:+.1f}" if b.get(k) is not None else "   —"
            pl = f"{cell['plateau_mean']:+.1f}" if cell["plateau_mean"] is not None else "   —"
            print(f"{fam:21}{rg:11}{b['n']:>5}{b['days']:>4}  {cell['best']:20}{b['mean']:+8.1f}"
                  f"{cell['median_cell_mean']:+8.1f}{pl:>8}{f('strip3'):>8}{f('loo_worst'):>8}"
                  f"{f('h1'):>7}{f('h2'):>7}{f('V7_mean'):>7}{f('V5sim_mean'):>7}{f('V5real_mean'):>7}")
print(f"\nwrote {OUT}")
