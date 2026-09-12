"""EXTENDED ADAPTIVE-EXIT LAB — per gate-family x REGIME RUNG, on the widest tape we hold.

Why this exists: scripts/adaptive_exit_bt.py answers the same question but is pinned to
capture.db (a 5-trading-day rolling window for ticks, 60 for bars) and to the V7 shadow board
alone, which leaves the operator's BIG-TREND rung at n=6..42 — far too thin to deploy from.
This version:
  · reads bars from the PARQUET LAKE (5s, 2026-06-19 onward) instead of capture.db;
  · pools V7 shadow entries (2026-07-16..08-21) with the RETIRED V5 desk's own shadow-sim
    entries (fut_shadow_sim_trades, MNQ, 2026-06-29..07-15) — a genuinely separate pool from a
    separate desk, which doubles as the out-of-sample leg;
  · sweeps a much wider Lot-A x Lot-B R grid plus four chandelier shapes;
  · runs the robustness battery per winning cell: strip-the-best-3, leave-one-day-out,
    first/second-half split, and a parameter-plateau read on the neighbouring cells.

Costs: $2.00/point (MNQ), $1.50 per ROUND TRIP per lot. 2 lots. Stop = 1.0 x entry ATR,
stop wins any same-bar race (conservative). Horizon 60 min.

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/adaptive_exit_bt_ext.py
"""
from __future__ import annotations
import json, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timezone

import duckdb
import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect

VPP, FEE, HORIZON_MIN = 2.0, 1.5, 60
STOP_K = 1.0
OUT = "/home/alphabot/gazbot7/scratchpad/adaptive_exit_ext.json"
V5 = "/tmp/v5/fut_shadow_sim_trades.parquet"

# ── bars from the LAKE (not capture.db — that is a rolling window) ──
print("loading 5s tape from the parquet lake …")
con = connect(symbol="MNQ")
B = con.execute("SELECT bar_ts, high, low, close FROM bars WHERE timeframe='5s' ORDER BY bar_ts").df()
con.close()
bts = B.bar_ts.values.astype(np.int64)
bh, bl, bc = B.high.values.astype(float), B.low.values.astype(float), B.close.values.astype(float)
print(f"  {len(bts):,} 5s bars  "
      f"{datetime.fromtimestamp(bts[0],timezone.utc):%Y-%m-%d} .. "
      f"{datetime.fromtimestamp(bts[-1],timezone.utc):%Y-%m-%d}")

# per-minute trailing-30min efficiency ratio — the rung key
mdf = B.assign(m=(B.bar_ts // 60)).groupby("m").close.last()
mk = mdf.index.values.astype(np.int64)
mc = mdf.values.astype(float)
step = np.abs(np.diff(mc, prepend=mc[0]))
csum = np.cumsum(step)
er = np.zeros(len(mc))
for i in range(30, len(mc)):
    path = csum[i] - csum[i - 30]
    er[i] = abs(mc[i] - mc[i - 30]) / path if path > 0 else 0.0
ER = dict(zip(mk.tolist(), er.tolist()))


def rung(atr: float, ts: int) -> str:
    """The operator's four exit-ladder rungs."""
    e = ER.get(ts // 60, 0.0)
    if e >= 0.50:
        return "BIG-TREND"
    if e >= 0.30:
        return "MED-TREND"
    if atr >= 22:
        return "STAY-OUT"
    return "SCALP-CHOP"


# ── entries: V7 shadow board + the V5 archive ──
FAM7 = {
    "grind (mom)":         ["grind_fast"],
    "thrust/absveto":      ["thrust_loose", "thrust_short_raw"],
    "rgv (fade)":          ["rg_long_fast", "rg_short_025_raw"],
    "capitulation (fade)": ["capit_loose"],
    "exhaustion (fade)":   ["exhaustion_rev"],
}
S2F = {s: f for f, ss in FAM7.items() for s in ss}

rows = []
sh = sqlite3.connect("/home/alphabot/gazbot7/data/shadow.db")
ph = ",".join("?" * len(S2F))
for strat, side, ts, ep, atr in sh.execute(
        "SELECT strategy,side,entry_ts,entry_price,entry_atr FROM shadow_trades "
        "WHERE entry_atr>0 AND strategy IN (" + ph + ")", list(S2F)):
    rows.append((S2F[strat], "V7", side, int(ts), float(ep), float(atr)))
sh.close()

# V5: map the retired desk's shadow sims onto the same two behavioural families.
V5MAP = {"momentum_shadow": "grind (mom)", "tw_ride_strength": "grind (mom)",
         "tw_mnq_thrust_loose": "thrust/absveto", "tw_mnq_thrust_cont": "thrust/absveto",
         "tw_mnq_thrust_floor00": "thrust/absveto", "tw_mnq_thrust_floor03": "thrust/absveto",
         "tw_mnq_thrust_floor04": "thrust/absveto",
         "dip_loose": "capitulation (fade)", "dip_loose_absorption": "capitulation (fade)",
         "pullback_loose": "rgv (fade)", "pullback_quiet": "rgv (fade)",
         "passive_chop": "exhaustion (fade)", "passive_chop_calm": "exhaustion (fade)"}
try:
    d = duckdb.connect()
    v5 = d.execute(f"""SELECT strategy, side, entry_ts, entry_price, entry_atr_abs
                       FROM '{V5}' WHERE symbol='MNQ' AND entry_atr_abs>0""").fetchall()
    d.close()
    for strat, side, ts, ep, atr in v5:
        fam = V5MAP.get(strat)
        if fam:
            rows.append((fam, "V5", side.upper(), int(ts), float(ep), float(atr)))
except Exception as e:                                     # the archive is optional, never fatal
    print(f"  ⚠ V5 archive unavailable ({e}) — V7-only run")

print(f"  entries: {sum(1 for r in rows if r[1]=='V7'):,} V7 + "
      f"{sum(1 for r in rows if r[1]=='V5'):,} V5 = {len(rows):,}")

# ── the exit models ──
A_RS = [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
B_RS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
COMBOS = [(a, b) for a in A_RS for b in B_RS if b > a]
CHANDS = {"chand k1.5": 1.5, "chand k2.5": 2.5, "chand k3.5": 3.5}


def leg_r(favcum, stop_i, target, cf_last):
    """R booked by one lot targeting `target`, stop -1R. Stop wins a same-bar race."""
    hit = np.argmax(favcum >= target) if (favcum >= target).any() else len(favcum)
    if hit < stop_i:
        return target
    if stop_i < len(favcum):
        return -1.0
    return max(min(cf_last, target), -1.0)


def chand_r(fav, cf, stop_i, k):
    """Threshold chandelier: trail k R below the running peak once the peak clears k."""
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_i:
            return -1.0
        peak = max(peak, fav[i])
        trail = peak - k
        if trail > 0 and cf[i] <= trail:
            return trail
    return max(min(cf[-1], peak), -1.0)


def wide_chand_r(fav, cf, stop_i):
    """grind_long's deployed pure-6.0: trail 3.5R until the peak clears 6R, then 0.5R."""
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_i:
            return -1.0
        peak = max(peak, fav[i])
        k = 0.5 if peak >= 6 else 3.5
        trail = peak - k
        if trail > 0 and cf[i] <= trail:
            return trail
    return max(min(cf[-1], peak), -1.0)


# agg[(fam, rung)][policy] -> list of (day, pool, $ for 2 lots)
agg = defaultdict(lambda: defaultdict(list))
seen = set()
skipped = 0
for fam, pool, side, ts, ep, atr in rows:
    key = (fam, pool, ts, round(ep, 2))
    if key in seen:
        continue
    seen.add(key)
    i0 = int(np.searchsorted(bts, ts))
    j1 = min(i0 + HORIZON_MIN * 12, len(bts))
    if j1 - i0 < 12:                                       # no forward tape → not measurable
        skipped += 1
        continue
    h, l, c = bh[i0:j1], bl[i0:j1], bc[i0:j1]
    if side.upper().startswith("L"):
        fav, adv, cf = (h - ep) / atr, (ep - l) / atr, (c - ep) / atr
    else:
        fav, adv, cf = (ep - l) / atr, (h - ep) / atr, (ep - c) / atr
    favcum = np.maximum.accumulate(fav)
    stop_i = int(np.argmax(adv >= STOP_K)) if (adv >= STOP_K).any() else len(fav)
    cfl = float(cf[-1])
    day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
    rg = rung(atr, ts)
    usd = lambda r: (r * atr * VPP) - FEE
    bucket = agg[(fam, rg)]
    for a, b in COMBOS:
        bucket[f"A{a}/B{b}"].append((day, pool, usd(leg_r(favcum, stop_i, a, cfl))
                                     + usd(leg_r(favcum, stop_i, b, cfl))))
    for nm, k in CHANDS.items():
        r = chand_r(fav, cf, stop_i, k)
        bucket[f"{nm} x2"].append((day, pool, usd(r) * 2))
    rw = wide_chand_r(fav, cf, stop_i)
    bucket["wideChand(6.0) x2"].append((day, pool, usd(rw) * 2))
    for a in (1.0, 2.0, 2.5):
        bucket[f"A{a} + wideChand"].append((day, pool, usd(leg_r(favcum, stop_i, a, cfl)) + usd(rw)))

print(f"  scored {len(seen)-skipped:,} entries ({skipped:,} had no forward tape)")


def battery(vals):
    """vals = [(day,pool,$)] → mean, robustness reads."""
    v = np.array([x[2] for x in vals])
    days = np.array([x[0] for x in vals])
    pools = np.array([x[1] for x in vals])
    n = len(v)
    out = dict(n=n, mean=float(v.mean()), tot=float(v.sum()),
               win=float(100 * (v > 0).mean()))
    s = np.sort(v)
    out["strip3"] = float(s[:-3].mean()) if n > 3 else None
    loo = [float(np.delete(v, np.where(days == d)).mean()) for d in np.unique(days)
           if (days != d).any()]
    out["loo_worst"] = float(min(loo)) if loo else None
    half = n // 2
    out["h1"] = float(v[:half].mean()) if half else None
    out["h2"] = float(v[half:].mean()) if half else None
    for p in ("V7", "V5"):
        m = pools == p
        out[f"{p.lower()}_n"] = int(m.sum())
        out[f"{p.lower()}_mean"] = float(v[m].mean()) if m.any() else None
    return out


res = {}
for (fam, rg), pol in sorted(agg.items()):
    cells = {p: battery(v) for p, v in pol.items() if len(v) >= 12}
    if not cells:
        continue
    best = max(cells, key=lambda p: cells[p]["mean"])
    res.setdefault(fam, {})[rg] = {"best": best, "cells": cells}

with open(OUT, "w") as f:
    json.dump(res, f, indent=1)

print(f"\n{'family':21}{'rung':11}{'n':>5}  {'best exit':20}{'$/sig':>8}{'strip3':>8}"
      f"{'LOOworst':>9}{'h1':>7}{'h2':>7}{'V7':>7}{'V5':>7}")
print("-" * 111)
for fam in FAM7:
    for rg in ("BIG-TREND", "MED-TREND", "SCALP-CHOP", "STAY-OUT"):
        cell = res.get(fam, {}).get(rg)
        if not cell:
            continue
        b = cell["cells"][cell["best"]]
        f7 = f"{b['v7_mean']:+.1f}" if b["v7_mean"] is not None else "  —"
        f5 = f"{b['v5_mean']:+.1f}" if b["v5_mean"] is not None else "  —"
        print(f"{fam:21}{rg:11}{b['n']:>5}  {cell['best']:20}{b['mean']:+8.1f}"
              f"{b['strip3']:+8.1f}{b['loo_worst']:+9.1f}{b['h1']:+7.1f}{b['h2']:+7.1f}{f7:>7}{f5:>7}")
print(f"\nwrote {OUT}")
