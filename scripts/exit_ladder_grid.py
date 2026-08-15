#!/usr/bin/env python3
"""★ THE REGIME-FLEX EXIT LADDER — per gate x rung, proven on the LONGEST window we hold.

The operator's ladder: BIG-TREND (ER>=0.50) ride · MED-TREND (0.30-0.50) · SCALP-CHOP · STAY-OUT.
Every R in it is a GUESS until swept. This sweeps Lot-A x Lot-B over a grid (plus chandelier) for
each gate family x rung and reports the ROBUST optimum, not the peak cell.

★ WHY THIS EXISTS SEPARATELY FROM adaptive_exit_bt.py: that one reads capture.db, whose 5s bars
start 2026-07-15, and scores only V7 shadow entries from 07-16 — which is why the BIG-TREND rung
has always been tiny-n and never provable. This one runs on the full 45-day 5s tape (V5 archive +
lake + hot, 06-19..08-14) and adds the 4,422 MNQ entries from the V5 archive's fut_shadow_sim_trades
(06-29..07-15), which are 13 trading days the V7 board simply does not contain.

Robustness per the standing discipline: parameter PLATEAU (neighbourhood, not peak),
strip-the-best-3-days, leave-one-day-out, and an out-of-sample split (V5 archive vs V7 board).
Costs: $1.50/round-trip, $2.00/point. Stop 1.0xATR. Conservative: stop wins a same-bar race.

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/exit_ladder_grid.py
"""
from __future__ import annotations
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

import duckdb
import numpy as np

VPP, FEE = 2.0, 1.5
HORIZON_MIN = 60
STOP_ATR = 1.0
TAPE = "/home/alphabot/gazbot7/scratchpad/tape5s.npz"
V5 = "/tmp/v5/fut_shadow_sim_trades.parquet"
OUT_JSON = "/home/alphabot/gazbot7/data/exit_ladder_grid.json"

A_RS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
B_RS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
CHANDS = ["tightChand", "wideChand"]
RUNGS = ["BIG-TREND", "MED-TREND", "SCALP-CHOP", "STAY-OUT"]

# V7 shadow board: canonical entry population per gate family
FAM_V7 = {
    "grind (mom)":         ["grind_fast"],
    "thrust/absveto":      ["thrust_loose", "thrust_short_raw"],
    "rgv (fade)":          ["rg_long_fast", "rg_short_025_raw"],
    "capitulation (fade)": ["capit_loose"],
    "exhaustion (fade)":   ["exhaustion_rev"],
}
# V5 archive: the mapping is by MECHANISM (what the strategy was doing), and it is a JUDGEMENT
# CALL — reported as a separate out-of-sample leg, never silently merged into the headline.
FAM_V5 = {
    "thrust/absveto":      ["tw_mnq_thrust_loose", "tw_mnq_thrust_cont", "tw_mnq_thrust_floor00",
                            "tw_mnq_thrust_floor03", "tw_mnq_thrust_floor04", "tw_us_open_surge_cont"],
    "grind (mom)":         ["momentum_shadow", "tw_ride_strength", "trend_donch"],
    "rgv (fade)":          ["dip_loose", "pullback_loose", "dip_loose_absorption", "pullback_quiet"],
    "exhaustion (fade)":   ["passive_chop", "passive_chop_calm", "passive_chop_gated"],
}

# ─────────────────────────────── tape ───────────────────────────────
z = np.load(TAPE)
bts, bh, bl, bc = z["ts"].astype(np.int64), z["h"], z["l"], z["c"]
print(f"tape: {len(bts):,} 5s bars  "
      f"{datetime.fromtimestamp(bts[0], timezone.utc):%Y-%m-%d} .. "
      f"{datetime.fromtimestamp(bts[-1], timezone.utc):%Y-%m-%d}")

# 1-min ER(30) for the rung
mk = {}
for i in range(len(bts)):
    m = int(bts[i]) // 60
    r = mk.get(m)
    if r is None:
        mk[m] = [bh[i], bl[i], bc[i]]
    else:
        r[0] = max(r[0], bh[i]); r[1] = min(r[1], bl[i]); r[2] = bc[i]
mins = sorted(mk)
C = np.array([mk[m][2] for m in mins])
ER = {}
for i, m in enumerate(mins):
    if i >= 30:
        seg = C[i - 30:i + 1]
        path = float(np.abs(np.diff(seg)).sum()) or 1.0
        ER[m] = abs(seg[-1] - seg[0]) / path


def rung(atr, ts):
    er = ER.get(int(ts) // 60, 0.0)
    if er >= 0.50:
        return "BIG-TREND"
    if er >= 0.30:
        return "MED-TREND"
    if atr >= 22:
        return "STAY-OUT"          # violent chop — measured, not traded
    return "SCALP-CHOP"


# ─────────────────────────── exit engines ───────────────────────────
def path_R(side, entry, atr, i0):
    j1 = min(i0 + HORIZON_MIN * 12, len(bts))
    if j1 - i0 < 2:
        return None
    h, l, c = bh[i0:j1], bl[i0:j1], bc[i0:j1]
    if side == "LONG":
        fav, adv, cf = (h - entry) / atr, (entry - l) / atr, (c - entry) / atr
    else:
        fav, adv, cf = (entry - l) / atr, (h - entry) / atr, (entry - c) / atr
    return fav, adv, cf


def lot_R(fav, adv, cf, target):
    """One lot at a fixed R target, 1.0xATR stop. Stop wins a same-bar race (conservative)."""
    favmax = np.maximum.accumulate(fav)
    t_idx = int(np.argmax(favmax >= target)) if (favmax >= target).any() else len(fav)
    s_idx = int(np.argmax(adv >= STOP_ATR)) if (adv >= STOP_ATR).any() else len(fav)
    if s_idx <= t_idx and s_idx < len(fav):
        return -STOP_ATR
    if t_idx < len(fav):
        return target
    return max(min(float(cf[-1]), target), -STOP_ATR)


def lot_chand(fav, adv, cf, mode):
    """Threshold chandelier. tight = trail 1.5R off peak; wide = 3.5R, tightening to 0.5R past 6R."""
    s_idx = int(np.argmax(adv >= STOP_ATR)) if (adv >= STOP_ATR).any() else len(fav)
    peak = 0.0
    for i in range(len(fav)):
        if i >= s_idx:
            return -STOP_ATR
        peak = max(peak, float(fav[i]))
        k = (0.5 if peak >= 6 else 3.5) if mode == "wideChand" else 1.5
        trail = peak - k
        if peak > 0 and trail > 0 and cf[i] <= trail:
            return trail
    return max(min(float(cf[-1]), peak), -STOP_ATR)


def usd(r, atr):
    return r * atr * VPP - FEE


# ─────────────────────────── entries ───────────────────────────
entries = []       # (fam, side, ts, price, atr, src)
sh = sqlite3.connect("/home/alphabot/gazbot7/data/shadow.db")
s2f = {s: f for f, ss in FAM_V7.items() for s in ss}
ph = ",".join("?" * len(s2f))
for strat, side, ts, ep, atr in sh.execute(
        f"SELECT strategy,side,entry_ts,entry_price,entry_atr FROM shadow_trades "
        f"WHERE entry_atr>0 AND strategy IN ({ph})", list(s2f)):
    entries.append((s2f[strat], side, int(ts), float(ep), float(atr), "V7"))
sh.close()
n_v7 = len(entries)

s2f5 = {s: f for f, ss in FAM_V5.items() for s in ss}
con = duckdb.connect()
rows = con.execute(f"""SELECT strategy, side, entry_ts, entry_price, entry_atr_abs
    FROM read_parquet('{V5}') WHERE symbol='MNQ' AND entry_atr_abs>0
      AND strategy IN ({','.join(chr(39)+s+chr(39) for s in s2f5)})""").fetchall()
con.close()
for strat, side, ts, ep, atr in rows:
    entries.append((s2f5[strat], str(side).upper(), int(ts), float(ep), float(atr), "V5"))
print(f"entries: {n_v7:,} V7 board + {len(entries)-n_v7:,} V5 archive = {len(entries):,}")

# ─────────────────────────── the sweep ───────────────────────────
POLICIES = [(f"A{a}/B{b}", a, b) for a in A_RS for b in B_RS if b > a]
POLICIES += [(f"A{a}/{ch}", a, ch) for a in A_RS for ch in CHANDS]
POLICIES += [(f"{ch}x2", ch, ch) for ch in CHANDS]

agg = defaultdict(lambda: defaultdict(list))     # (fam,rung,src) -> policy -> [(day,$)]
seen = set()
for fam, side, ts, ep, atr, src in entries:
    key = (fam, ts, side, round(ep, 2))
    if key in seen:
        continue
    seen.add(key)
    i0 = int(np.searchsorted(bts, ts))
    if i0 >= len(bts) or abs(int(bts[min(i0, len(bts)-1)]) - ts) > 600:
        continue                                  # no tape at this entry
    p = path_R(side, ep, atr, i0)
    if p is None:
        continue
    fav, adv, cf = p
    rg = rung(atr, ts)
    day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
    cache = {}
    for name, a, b in POLICIES:
        ra = cache.get(a) if a in cache else None
        if ra is None:
            ra = lot_chand(fav, adv, cf, a) if isinstance(a, str) else lot_R(fav, adv, cf, a)
            cache[a] = ra
        rb = cache.get(b)
        if rb is None:
            rb = lot_chand(fav, adv, cf, b) if isinstance(b, str) else lot_R(fav, adv, cf, b)
            cache[b] = rb
        agg[(fam, rg, src)][name].append((day, usd(ra, atr) + usd(rb, atr)))

# ─────────────────────────── report ───────────────────────────
def score(vals):
    v = np.array([x[1] for x in vals])
    return dict(n=len(v), net=float(v.sum()), per=float(v.mean()),
                win=float(100 * (v > 0).mean()))


def strip_best3_days(vals):
    d = defaultdict(float)
    for day, x in vals:
        d[day] += x
    s = sorted(d.values(), reverse=True)
    return sum(s[3:]) if len(s) > 3 else 0.0


def loo_worst(vals):
    """Leave-one-day-out: the WORST per-trade the policy drops to when any single day is removed."""
    d = defaultdict(list)
    for day, x in vals:
        d[day].append(x)
    if len(d) < 3:
        return None
    outs = []
    for k in d:
        rest = [x for kk, vv in d.items() if kk != k for x in vv]
        if rest:
            outs.append(np.mean(rest))
    return float(min(outs))


def plateau(pol_stats, name):
    """Neighbourhood mean: a robust optimum sits on a PLATEAU, a fitted one is a lone spike."""
    if not name.startswith("A") or "Chand" in name:
        return None
    try:
        a = float(name.split("/")[0][1:]); b = float(name.split("/B")[1])
    except (IndexError, ValueError):
        return None
    ai, bi = A_RS.index(a), B_RS.index(b)
    nb = []
    for da in (-1, 0, 1):
        for db in (-1, 0, 1):
            i, j = ai + da, bi + db
            if 0 <= i < len(A_RS) and 0 <= j < len(B_RS) and B_RS[j] > A_RS[i]:
                nm = f"A{A_RS[i]}/B{B_RS[j]}"
                if nm in pol_stats:
                    nb.append(pol_stats[nm]["per"])
    return float(np.mean(nb)) if nb else None


# ⚠ MINN=15, not 25: BIG-TREND is only 2.96% of all minutes on this tape, so a 25-row floor
# silently DELETES the very rung this study exists to measure. Thin cells are printed and flagged.
out, MINN = {}, 15
print(f"\n{'family':21}{'rung':11}{'src':4}{'n':>5}  {'best (robust)':17}"
      f"{'$/sig':>8}{'plateau':>9}{'strip3':>9}{'LOOworst':>10}  win%")
print("-" * 106)
for fam in FAM_V7:
    for rg in RUNGS:
        for src in ("V7", "V5"):
            pol = agg.get((fam, rg, src))
            if not pol:
                continue
            st = {p: score(v) for p, v in pol.items()}
            n = st[next(iter(st))]["n"]
            if n < MINN:
                continue
            # ROBUST pick: rank by the plateau (neighbourhood) mean where defined, else own mean
            ranked = sorted(st, key=lambda p: (plateau(st, p) if plateau(st, p) is not None
                                               else st[p]["per"]), reverse=True)
            best = ranked[0]
            pl = plateau(st, best)
            s3 = strip_best3_days(pol[best])
            lw = loo_worst(pol[best])
            print(f"{fam:21}{rg:11}{src:4}{n:>5}  {best:17}{st[best]['per']:>+8.1f}"
                  f"{(pl if pl is not None else float('nan')):>+9.1f}{s3:>+9.0f}"
                  f"{(lw if lw is not None else float('nan')):>+10.1f}  {st[best]['win']:.0f}")
            out.setdefault(fam, {}).setdefault(rg, {})[src] = dict(
                n=n, best=best, per=st[best]["per"], plateau=pl, strip3=s3, loo_worst=lw,
                win=st[best]["win"], top5={p: st[p] for p in ranked[:5]})

json.dump(out, open(OUT_JSON, "w"), indent=1)
print(f"\nwrote {OUT_JSON}")
