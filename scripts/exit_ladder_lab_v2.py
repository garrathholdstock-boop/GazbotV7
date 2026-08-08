#!/usr/bin/env python3
"""REGIME-FLEX EXIT LADDER LAB (v2) — prove the operator's 2026-07-31 exit ladder.

Extends scripts/adaptive_exit_bt.py in the four ways the mid-week first-look could not:

  1. FULL WINDOW.  The first-look read capture.db 5s bars for "07-16..31" — but that run was
     CHOP-DOMINATED and BIG-TREND came out at n=5-25, so the 3.5R+chandelier rung was untested.
     capture.db keeps only ~5 days of TICKS but retains 5s BARS for the whole archive, so this
     runs the entire 2026-07-15..now span (21 trading days, ~3,300 shadow entries).
  2. TIME-OF-DAY.  adaptive_exit_bt computed tod() and never used it. Here every cell is
     (family x rung x ToD) with ON = pre-13:30 UTC, US = 13:30-21:00 UTC.
  3. STAY-OUT IS A REAL RUNG.  Classified per DAY by the deployed untradeable meter
     (src/gazbot7/untradeable.py), not by an ATR proxy.
  4. ROBUSTNESS.  Every winning cell gets leave-one-day-out (worst LOO mean), strip-best-3,
     and walk-forward halves. A cell that only wins on one day is reported as such.

Conservative: same-bar stop-first, 1-ATR stop, $2/pt, $1.50/lot fee, 60-min horizon, 2-lot basis.
READ-ONLY. Writes scratchpad/exit_ladder_v2.json.

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/exit_ladder_lab_v2.py
"""
from __future__ import annotations
import json, os, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.untradeable import compute as untradeable_compute

VPP, FEE, HORIZON_MIN = 2.0, 1.5, 60
STOP_ATR = 1.0
# ★ POISONED-ATR GUARD. shadow_trades.entry_atr contains impossible MNQ values — 25,809.5 /
# 7,351.7 / 1,846.5 points (capit_loose, grind_fast, thrust_loose, chand_k35...). Every R-scaled
# payoff is (R x atr x $2), so ONE of these rows moves a 266-trade cell's mean by four figures:
# the first pass showed capitulation_long/SCALP-CHOP "best" at +$1,115/trade off a 6% win rate.
# MNQ's real 14-min ATR sits ~4-60pt over this archive, so anything outside that is dropped and
# COUNTED (the count is itself a reportable data-quality finding).
ATR_MIN, ATR_MAX = 3.0, 60.0
CAP = "/home/alphabot/gazbot7/data/capture.db"
SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
STORE = "/home/alphabot/gazbot7/data/gazbot7.db"
OUT = "/home/alphabot/gazbot7/scratchpad/exit_ladder_v2.json"
START = "2026-07-15"

# gate family -> canonical shadow entry strategies (side kept separate where the desk runs it two-sided)
FAM = {
    "grind_long":        [("grind_fast", None)],
    "abs_veto_long":     [("abs_veto_55s", "LONG")],
    "abs_veto_short":    [("abs_veto_55s", "SHORT")],
    "thrust_raw":        [("thrust_loose", None), ("thrust_short_raw", None)],
    "rgv_long":          [("rg_long_fast", None)],
    "rgv_short":         [("rg_short_025_raw", None)],
    "capitulation_long": [("capit_loose", None)],
    "exhaustion_short":  [("exhaustion_rev", None)],
}

cap = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
sh = sqlite3.connect(f"file:{SHADOW}?mode=ro", uri=True)

# ── 5s bars for the whole archive ────────────────────────────────────────────
bars = cap.execute(
    "SELECT bar_ts,high,low,close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
    "AND bar_ts>=strftime('%s',?) ORDER BY bar_ts", (START,)).fetchall()
bts = np.array([b[0] for b in bars], dtype=np.int64)
bh = np.array([b[1] for b in bars]); bl = np.array([b[2] for b in bars]); bc = np.array([b[3] for b in bars])
print(f"[tape] {len(bts):,} 5s bars  {datetime.fromtimestamp(bts[0],timezone.utc)} .. "
      f"{datetime.fromtimestamp(bts[-1],timezone.utc)}")

# ── per-minute ER(30) — CONTIGUITY-GUARDED (never straddle a weekend/gap) ────
mn = {}
for ts, h, l, c in bars:
    mn[ts // 60] = c
mk = sorted(mn); mcl = [mn[k] for k in mk]
er_at = {}
for i in range(30, len(mk)):
    if mk[i] - mk[i - 30] != 30:      # gap -> no reading rather than a fabricated one
        continue
    seg = mcl[i - 30:i + 1]
    path = sum(abs(seg[j] - seg[j - 1]) for j in range(1, len(seg)))
    er_at[mk[i]] = (abs(seg[-1] - seg[0]) / path) if path > 0 else 0.0

# ── STAY-OUT days from the deployed meter ───────────────────────────────────
def _day_key(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")

days = sorted({_day_key(t) for t in bts})
stayout, day_meter = set(), {}
for d in days:
    ep = int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    try:
        m = untradeable_compute(CAP, STORE, ep, ep + 86400)
    except Exception:
        continue
    day_meter[d] = {"score": m["score"], "verdict": m["verdict"], "roundtrip": m["roundtrip"],
                    "range_pt": m["range_pt"], "net_pt": m["net_pt"], "atr": m["atr"]}
    if m["verdict"] == "STAY-OUT":
        stayout.add(d)
print(f"[meter] STAY-OUT days ({len(stayout)}/{len(days)}): {sorted(stayout)}")


def rung(ts):
    d = _day_key(ts)
    if d in stayout:
        return "STAY-OUT"
    er = er_at.get(ts // 60)
    if er is None:
        return None
    if er >= 0.50: return "BIG-TREND"
    if er >= 0.30: return "MED-TREND"
    return "SCALP-CHOP"


def tod(ts):
    t = datetime.fromtimestamp(ts, timezone.utc)
    return "US" if (t.hour * 60 + t.minute) >= 810 and t.hour < 21 else "ON"


# ── entries ──────────────────────────────────────────────────────────────────
def load_entries():
    out = []
    for fam, specs in FAM.items():
        for strat, side_filter in specs:
            q = ("SELECT strategy,side,entry_ts,entry_price,entry_atr FROM shadow_trades "
                 "WHERE strategy=? AND entry_atr>0 AND entry_ts>=strftime('%s',?)")
            args = [strat, START]
            if side_filter:
                q += " AND side=?"; args.append(side_filter)
            for r in sh.execute(q, args).fetchall():
                out.append((fam,) + tuple(r))
    return out


rows = load_entries()
print(f"[entries] {len(rows):,} shadow entries across {len(FAM)} gate families")


def excursions(side, entry, atr, i0):
    j1 = min(i0 + HORIZON_MIN * 12, len(bts))
    h, l, c = bh[i0:j1], bl[i0:j1], bc[i0:j1]
    if len(h) == 0:
        return None
    if side == "LONG":
        return (h - entry) / atr, (entry - l) / atr, (c - entry) / atr
    return (entry - l) / atr, (h - entry) / atr, (entry - c) / atr


def scalp_r(favcum, stop_idx, target, cf_last):
    """R booked by a fixed target lot. Same-bar stop-first (conservative)."""
    reach = int(np.argmax(favcum >= target)) if (favcum >= target).any() else len(favcum)
    if reach <= stop_idx:
        return target
    if stop_idx < len(favcum):
        return -STOP_ATR
    return max(min(cf_last, target), -STOP_ATR)


def chand_r(fav, cf, stop_idx, start_k, lock_r, lock_k):
    """Threshold-chandelier in R: trail start_k ATR until peak>=lock_r, then lock_k ATR."""
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_idx:
            return -STOP_ATR
        peak = max(peak, fav[i])
        k = lock_k if peak >= lock_r else start_k
        trail = peak - k
        if peak > 0 and trail > 0 and cf[i] <= trail:
            return trail
    return max(min(cf[-1], peak), -STOP_ATR)


# ── the policy grid ─────────────────────────────────────────────────────────
A_RS = [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
B_RS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
SCALP = [(a, b) for a in A_RS for b in B_RS if b > a]
# chandelier lots: (label, start_k, lock_r, lock_k)
CH = {"wide": (3.5, 6.0, 0.5), "mid": (2.0, 4.0, 0.5), "tight": (1.5, 3.0, 0.5)}
# ride policies = Lot A fixed R + Lot B chandelier (the operator's BIG-TREND rung)
RIDE_A = [1.5, 2.0, 2.5, 3.0, 3.5]

# cell -> policy -> list of (day, 2-lot $)
agg = defaultdict(lambda: defaultdict(list))
seen = set()
skipped = 0
bad_atr = defaultdict(int)
for fam, strat, side, ts, ep, atr in rows:
    key = (strat, side, ts)
    if key in seen:
        continue
    if not (ATR_MIN <= atr <= ATR_MAX):
        bad_atr[strat] += 1; continue
    seen.add(key)
    rg = rung(ts)
    if rg is None:
        skipped += 1; continue
    i0 = int(np.searchsorted(bts, ts))
    ex = excursions(side, ep, atr, i0)
    if ex is None:
        skipped += 1; continue
    fav, adv, cf = ex
    favcum = np.maximum.accumulate(fav)
    stop_idx = int(np.argmax(adv >= STOP_ATR)) if (adv >= STOP_ATR).any() else len(fav)
    cfl = cf[-1]
    day = _day_key(ts)

    def lot(rr):
        return (rr * atr * VPP) - FEE

    cells = [(fam, rg, "ALL"), (fam, rg, tod(ts))]
    pol = {}
    for (a, b) in SCALP:
        pol[f"scalp {a}/{b}"] = lot(scalp_r(favcum, stop_idx, a, cfl)) + lot(scalp_r(favcum, stop_idx, b, cfl))
    for lbl, (sk, lr, lk) in CH.items():
        rc = chand_r(fav, cf, stop_idx, sk, lr, lk)
        pol[f"{lbl}Chand x2"] = 2 * lot(rc)
        for a in RIDE_A:
            pol[f"A{a} + {lbl}Chand"] = lot(scalp_r(favcum, stop_idx, a, cfl)) + lot(rc)
    for cell in cells:
        for p, v in pol.items():
            agg[cell][p].append((day, v))

print(f"[grid] {len(SCALP)} scalp combos + {len(CH)*(1+len(RIDE_A))} chandelier policies; "
      f"{len(seen):,} entries repriced, {skipped:,} skipped (no ER / no forward tape)")
print(f"[data-quality] dropped {sum(bad_atr.values())} entries on impossible entry_atr "
      f"(outside {ATR_MIN}-{ATR_MAX}pt): {dict(bad_atr)}")
# how much of the tape is each rung? (the BIG-TREND-is-rare question)
rung_min = defaultdict(int)
for m in er_at:
    d = _day_key(m * 60)
    if d in stayout: rung_min["STAY-OUT"] += 1
    elif er_at[m] >= 0.50: rung_min["BIG-TREND"] += 1
    elif er_at[m] >= 0.30: rung_min["MED-TREND"] += 1
    else: rung_min["SCALP-CHOP"] += 1
tot_min = sum(rung_min.values())
print("[rung tape share] " + "  ".join(f"{k}={v}min ({100*v/tot_min:.1f}%)" for k, v in sorted(rung_min.items())))


def cellstats(vals):
    v = [x for _, x in vals]
    n = len(v); tot = sum(v)
    return dict(n=n, mean=round(tot / n, 1), med=round(float(np.median(v)), 1), tot=round(tot),
                win=round(100 * sum(1 for x in v if x > 0) / n))


def loo_worst(vals):
    """Leave-one-day-out: the WORST mean once any single day is removed."""
    byday = defaultdict(list)
    for d, x in vals:
        byday[d].append(x)
    if len(byday) < 2:
        return None, None
    worst, worstday = None, None
    for d in byday:
        rest = [x for dd, xs in byday.items() if dd != d for x in xs]
        if not rest:
            continue
        m = sum(rest) / len(rest)
        if worst is None or m < worst:
            worst, worstday = round(m, 1), d
    return worst, worstday


def strip3(vals):
    v = sorted(x for _, x in vals)
    return round(sum(v[:-3]), 1) if len(v) > 3 else None


def halves(vals):
    byday = sorted({d for d, _ in vals})
    if len(byday) < 4:
        return None, None
    cut = byday[len(byday) // 2]
    a = [x for d, x in vals if d < cut]; b = [x for d, x in vals if d >= cut]
    if not a or not b:
        return None, None
    return round(sum(a) / len(a), 1), round(sum(b) / len(b), 1)


# ── THE OPERATOR'S LADDER GUESS (2026-07-31) — the thing this lab exists to prove or refute ──
GUESS = {
    "BIG-TREND":  ["A3.0 + wideChand", "A3.5 + wideChand", "A2.5 + wideChand"],
    "MED-TREND":  ["scalp 1.5/2.5"],
    "SCALP-CHOP": ["scalp 1.0/2.0"],
    "STAY-OUT":   [],          # FLAT — the guess is that no exit saves it
}
# extra reference policies the first-look flagged as LEADS to confirm/refute
REF = ["scalp 0.5/1.0", "scalp 0.75/1.0", "scalp 1.5/2.5", "scalp 1.0/2.0", "scalp 2.5/3.5",
       "A2.5 + wideChand", "A3.5 + wideChand", "wideChand x2", "tightChand x2", "midChand x2"]

MIN_N = 12
out = {}
for cell, pols in sorted(agg.items()):
    fam, rg, td = cell
    ranked = []
    for p, vals in pols.items():
        if len(vals) < MIN_N:
            continue
        s = cellstats(vals); s["policy"] = p
        ranked.append(s)
    if not ranked:
        continue
    ranked.sort(key=lambda s: -s["mean"])
    best = ranked[0]
    vals = pols[best["policy"]]
    lw, ld = loo_worst(vals)
    h1, h2 = halves(vals)
    bym = {r["policy"]: r for r in ranked}
    # what the operator's ladder GUESS scores in this cell, and where it ranks
    guess = None
    for g in GUESS.get(rg, []):
        if g in bym:
            guess = {"policy": g, "mean": bym[g]["mean"], "win": bym[g]["win"], "tot": bym[g]["tot"],
                     "rank": 1 + [r["policy"] for r in ranked].index(g), "of": len(ranked)}
            break
    rec = dict(fam=fam, rung=rg, tod=td, n=best["n"], best=best["policy"], mean=best["mean"],
               med=best["med"], tot=best["tot"], win=best["win"], loo_worst=lw, loo_worst_day=ld,
               strip3=strip3(vals), half1=h1, half2=h2, days=len({d for d, _ in vals}),
               guess=guess,
               ref={p: {"mean": bym[p]["mean"], "win": bym[p]["win"]} for p in REF if p in bym},
               top5=[{k: r[k] for k in ("policy", "mean", "med", "tot", "win")} for r in ranked[:5]],
               bottom3=[{k: r[k] for k in ("policy", "mean", "tot", "win")} for r in ranked[-3:]],
               all_neg=all(r["mean"] < 0 for r in ranked))
    out[f"{fam}|{rg}|{td}"] = rec

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump({"cells": out, "day_meter": day_meter, "stayout": sorted(stayout),
           "window": [str(datetime.fromtimestamp(bts[0], timezone.utc)),
                      str(datetime.fromtimestamp(bts[-1], timezone.utc))],
           "n_entries": len(seen)}, open(OUT, "w"), indent=1)

print()
print(f"{'family':19}{'rung':11}{'tod':5}{'n':>5}  {'best exit':22}{'mean$':>8}{'win%':>6}"
      f"{'LOOworst':>10}{'h1':>8}{'h2':>8}")
print("-" * 102)
for fam in FAM:
    for rg in ("BIG-TREND", "MED-TREND", "SCALP-CHOP", "STAY-OUT"):
        for td in ("ALL", "US", "ON"):
            r = out.get(f"{fam}|{rg}|{td}")
            if not r:
                continue
            flag = "  <-- ALL POLICIES NEGATIVE" if r["all_neg"] else ""
            print(f"{fam:19}{rg:11}{td:5}{r['n']:>5}  {r['best']:22}{r['mean']:>+8.1f}{r['win']:>6}"
                  f"{(r['loo_worst'] if r['loo_worst'] is not None else float('nan')):>+10.1f}"
                  f"{(r['half1'] if r['half1'] is not None else float('nan')):>+8.1f}"
                  f"{(r['half2'] if r['half2'] is not None else float('nan')):>+8.1f}{flag}")
print(f"\n-> {OUT}")
