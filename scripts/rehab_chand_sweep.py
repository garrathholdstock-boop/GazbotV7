"""CHANDELIER (runner give-back) rehab — STAGE 2: regime-segmented parameter sweep.

Replays the WIDE-CHANDELIER users (grind momentum + thrust/absveto momentum) on the extended
V5+V7 5s tape (07-06..07-31), reprices each entry's forward 5s path under a GRID of profit-exit
configs (fixed-R, chandelier-lock start_k x lock_r x lock_k, tightening chandelier, and lock+R-
giveback overlays). The native 1-ATR stop owns the downside (adv>=1R => -1R). Corrected cost
$1.50/RT, $2/pt, 1 lot.

SEGMENTS every score by REGIME (entry 30-min ER: chop<0.30 / build 0.30-0.50 / trend>=0.50)
x TIME-OF-DAY (US post-13:00 UTC vs ON) x ATR band. Never a single blanket cross-tape number.
Robustness on the per-segment winner: strip-best-3, per-ISO-week, leave-one-day-out, OOS
(archive 07-06..15 vs capture 07-16..31).  PYTHONPATH=src .venv/bin/python scripts/rehab_chand_sweep.py
"""
from __future__ import annotations
import sys, json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import Bar, compute_features, gate_thrust, gate_grind  # noqa

VPP, FEE = 2.0, 1.5
HORIZON_MIN, LOOKBACK, COOLDOWN_S = 90, 60, 300
UTC = timezone.utc
OV0 = int(datetime(2026, 7, 16, tzinfo=UTC).timestamp())

z = np.load("/home/alphabot/gazbot7/scratchpad/tape5s.npz")
# materialise ALL arrays to local numpy (NpzFile lazily re-decompresses on every key access)
bts = np.asarray(z["ts"]); bo = np.asarray(z["o"]); bh = np.asarray(z["h"])
bl = np.asarray(z["l"]); bc = np.asarray(z["c"]); bv = np.asarray(z["v"])

# 1-min bars
mk = {}
for i in range(len(bts)):
    m = int(bts[i]) // 60
    r = mk.get(m)
    if r is None:
        mk[m] = [bo[i], bh[i], bl[i], bc[i], bv[i]]
    else:
        r[1] = max(r[1], bh[i]); r[2] = min(r[2], bl[i]); r[3] = bc[i]; r[4] += bv[i]
mins = sorted(mk)
MB = [Bar(m * 60, mk[m][0], mk[m][1], mk[m][2], mk[m][3], mk[m][4]) for m in mins]
mts = np.array([b.ts for b in MB]); mcl = np.array([b.close for b in MB])
mhi = np.array([b.high for b in MB]); mlo = np.array([b.low for b in MB])

# 30-min ER at each minute
er30 = np.zeros(len(MB))
for i in range(30, len(MB)):
    seg = mcl[i - 30:i + 1]; path = float(np.abs(np.diff(seg)).sum()) or 1.0
    er30[i] = abs(seg[-1] - seg[0]) / path
ER_AT = {int(mts[i]) // 60: float(er30[i]) for i in range(len(MB))}

def paris_day(ts):
    d = datetime.fromtimestamp(ts, UTC)
    if d.hour >= 22:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")
def regime(ts):
    er = ER_AT.get(ts // 60, 0.0)
    return "trend" if er >= 0.50 else "build" if er >= 0.30 else "chop"
def tod(ts):
    return "US" if 13 <= datetime.fromtimestamp(ts, UTC).hour < 21 else "ON"
def atrb(a):
    return "hiATR" if a >= 30 else "midATR" if a >= 18 else "loATR"
def isowk(ts):
    return "W%d" % datetime.fromtimestamp(ts, UTC).isocalendar()[1]

# ── replay the wide-chandelier-user momentum gates ──
GATES = {
    "grind": lambda f: gate_grind(f, slope_min=0.4, fast_slope=True, tape_net=0.0),
    "thrust/absveto": lambda f: gate_thrust(f, thr=1.5, amp_floor=0.0004),
}
entries = []
last_fire = {}
for i in range(LOOKBACK, len(MB)):
    win = MB[i - LOOKBACK + 1:i + 1]
    f = compute_features(win)
    if f.atr <= 0:
        continue
    ts = int(MB[i].ts) + 60
    for fam, fn in GATES.items():
        if ts - last_fire.get(fam, -10**9) < COOLDOWN_S:
            continue
        e = fn(f)
        if e is None:
            continue
        last_fire[fam] = ts
        entries.append((fam, e.side, ts, float(MB[i].close), float(f.atr)))
print(f"replayed momentum entries: {len(entries)}  " +
      "  ".join(f"{fam}={sum(1 for e in entries if e[0]==fam)}" for fam in GATES))

# ── forward-path repricing helpers (R units) ──
def path(side, entry, atr, i0):
    j1 = min(i0 + HORIZON_MIN * 12, len(bts))
    h, l, c = bh[i0:j1], bl[i0:j1], bc[i0:j1]
    if len(h) < 12:
        return None
    if side == "LONG":
        fav = (h - entry) / atr; adv = (entry - l) / atr; cf = (c - entry) / atr
    else:
        fav = (entry - l) / atr; adv = (h - entry) / atr; cf = (entry - c) / atr
    return fav, adv, cf

def r_fixed(fav, adv, cf, target):
    favcum = np.maximum.accumulate(fav)
    hit = int(np.argmax(favcum >= target)) if (favcum >= target).any() else len(fav)
    stop_i = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else len(fav)
    if hit < stop_i:
        return target
    if stop_i < len(fav):
        return -1.0
    return max(min(float(cf[-1]), target), -1.0)

def r_lock(fav, adv, cf, start_k, lock_r, lock_k, gb_r=None):
    """chandelier-lock; optional gb_r = hard R-giveback overlay (cut if retrace gb_r from peak)."""
    stop_i = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else len(fav)
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_i:
            return -1.0
        peak = max(peak, fav[i])
        if peak > 0:
            k = start_k if peak < lock_r else lock_k
            if gb_r is not None:
                k = min(k, gb_r)
            if cf[i] > 0 and cf[i] <= peak - k:
                return float(cf[i])
    return max(min(float(cf[-1]), peak), -1.0)

def r_tight(fav, adv, cf, start_k, tighten, min_k):
    stop_i = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else len(fav)
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_i:
            return -1.0
        peak = max(peak, fav[i])
        if peak > 0:
            k = max(min_k, start_k - tighten * peak)
            if cf[i] > 0 and cf[i] <= peak - k:
                return float(cf[i])
    return max(min(float(cf[-1]), peak), -1.0)

# ── config grid ──
CFG = {}
for t in (1.5, 2.0, 2.5, 3.0):
    CFG[f"fix{t}"] = ("fixed", t)
for sk in (2.0, 2.5, 3.0, 3.5):
    for lr in (2.0, 2.5, 3.0, 4.0, 6.0):
        for lk in (0.5, 0.75):
            CFG[f"L{sk}/{lr}/{lk}"] = ("lock", sk, lr, lk, None)
# lock + hard R-giveback overlay (cap the wide-trail tail)
for sk in (3.0, 3.5):
    for gb in (1.0, 1.5, 2.0):
        CFG[f"L{sk}/6.0/0.5+gb{gb}"] = ("lock", sk, 6.0, 0.5, gb)
for sk in (2.0, 3.0, 3.5):
    CFG[f"T{sk}"] = ("tight", sk, 0.75, 0.5)
INCUMBENT = "L3.5/6.0/0.5"

def score_cfg(fav, adv, cf, spec):
    kind = spec[0]
    if kind == "fixed":
        r = r_fixed(fav, adv, cf, spec[1])
    elif kind == "lock":
        r = r_lock(fav, adv, cf, spec[1], spec[2], spec[3], spec[4])
    else:
        r = r_tight(fav, adv, cf, spec[1], spec[2], spec[3])
    return r

# ── build per-entry results ──
rows = []
for fam, side, ts, ep, atr in entries:
    i0 = int(np.searchsorted(bts, ts))
    if i0 >= len(bts):
        continue
    pp = path(side, ep, atr, i0)
    if pp is None:
        continue
    fav, adv, cf = pp
    rmfe = float(np.maximum.accumulate(fav)[-1])
    d = dict(fam=fam, ts=ts, atr=atr, day=paris_day(ts), reg=regime(ts), tod=tod(ts),
             atrb=atrb(atr), wk=isowk(ts), oos=(ts < OV0), rmfe=rmfe, r={})
    for name, spec in CFG.items():
        d["r"][name] = score_cfg(fav, adv, cf, spec) * atr * VPP - FEE
    rows.append(d)
print(f"repriced entries: {len(rows)}")

# ── aggregation ──
def agg(vals):
    n = len(vals)
    return None if not n else dict(n=n, tot=round(sum(vals), 1), mean=round(sum(vals) / n, 2),
                                   win=round(100 * sum(1 for v in vals if v > 0) / n))

def robust(sub, name):
    v = [r["r"][name] for r in sub]
    days = sorted({r["day"] for r in sub})
    loo = [sum(r["r"][name] for r in sub if r["day"] != d) / max(1, len([1 for r in sub if r["day"] != d])) for d in days]
    strip3 = sorted(v)[:-3]
    wks = sorted({r["wk"] for r in sub})
    perwk = {w: round(sum(r["r"][name] for r in sub if r["wk"] == w), 1) for w in wks}
    return dict(mean=round(sum(v) / len(v), 2), tot=round(sum(v), 1),
                strip3_mean=round(sum(strip3) / len(strip3), 2) if strip3 else None,
                loo_worst=round(min(loo), 2) if loo else None,
                perwk=perwk, wk_green=sum(1 for x in perwk.values() if x > 0), wk_n=len(wks))

OUT = {"meta": dict(n_entries=len(rows), tape="2026-07-06..07-31", incumbent=INCUMBENT,
                    n_cfg=len(CFG)), "cells": {}}

def seg_report(label, subfilter):
    out = {}
    for fam in ("grind", "thrust/absveto"):
        for reg in ("chop", "build", "trend"):
            sub = [r for r in rows if r["fam"] == fam and r["reg"] == reg and subfilter(r)]
            if len(sub) < 12:
                out[f"{fam}|{reg}"] = dict(n=len(sub), thin=True)
                continue
            means = {c: sum(r["r"][c] for r in sub) / len(sub) for c in CFG}
            best = max(CFG, key=lambda c: means[c])
            top = sorted(CFG, key=lambda c: -means[c])[:6]
            out[f"{fam}|{reg}"] = dict(
                n=len(sub), rmfe_med=round(float(np.median([r["rmfe"] for r in sub])), 2),
                rmfe_p90=round(float(np.percentile([r["rmfe"] for r in sub], 90)), 2),
                incumbent=agg([r["r"][INCUMBENT] for r in sub]),
                best=best, best_stats=robust(sub, best),
                top=[(c, round(means[c], 2)) for c in top],
                tod={t: agg([r["r"][best] for r in sub if r["tod"] == t]) for t in ("US", "ON")},
            )
    return out

OUT["cells"]["ALL"] = seg_report("all", lambda r: True)
OUT["cells"]["US"] = seg_report("US", lambda r: r["tod"] == "US")
OUT["cells"]["ON"] = seg_report("ON", lambda r: r["tod"] == "ON")

# OOS split on the incumbent vs a couple of candidates, per fam|reg
CANDS = [INCUMBENT, "L3.0/2.5/0.5", "L2.5/2.5/0.5", "L3.5/3.0/0.5", "L3.5/6.0/0.5+gb1.5", "fix2.0", "fix2.5"]
oos_tbl = {}
for fam in ("grind", "thrust/absveto"):
    for reg in ("chop", "build", "trend"):
        sub = [r for r in rows if r["fam"] == fam and r["reg"] == reg]
        if len(sub) < 12:
            continue
        io = [r for r in sub if not r["oos"]]; oo = [r for r in sub if r["oos"]]
        oos_tbl[f"{fam}|{reg}"] = {c: dict(IS=agg([r["r"][c] for r in io]), OOS=agg([r["r"][c] for r in oo])) for c in CANDS}
OUT["oos"] = oos_tbl
OUT["cands"] = CANDS

json.dump(OUT, open("/home/alphabot/gazbot7/scratchpad/rehab_chand_sweep.json", "w"), indent=1, default=float)

# ── console ──
def show(tag):
    print(f"\n########## SEGMENT SET: {tag} ##########")
    for k, c in OUT["cells"][tag].items():
        if c.get("thin"):
            print(f"{k:22} n={c['n']:>3}  THIN"); continue
        inc = c["incumbent"]; b = c["best_stats"]
        print(f"\n{k:22} n={c['n']:>3}  rmfe med={c['rmfe_med']} p90={c['rmfe_p90']}")
        print(f"   incumbent {INCUMBENT}: {inc['mean']:+.1f}/sig  tot {inc['tot']:+.0f}  win{inc['win']}%")
        print(f"   BEST {c['best']:20}: {b['mean']:+.1f}/sig  tot {b['tot']:+.0f}  strip3 {b['strip3_mean']:+.1f}  loo_worst {b['loo_worst']:+.1f}  wk_green {b['wk_green']}/{b['wk_n']}")
        print(f"     perwk {b['perwk']}")
        print(f"     top6: " + "  ".join(f"{n}:{m:+.1f}" for n, m in c["top"]))
        print(f"     best by tod: " + "  ".join(f"{t}:{(s['mean'] if s else 0):+.1f}(n{s['n'] if s else 0})" for t, s in c["tod"].items()))
for tag in ("ALL", "US", "ON"):
    show(tag)

print("\n########## OOS split (IS=capture 07-16.., OOS=archive 07-06..15) ##########")
for k, d in OUT["oos"].items():
    print(f"\n{k}:")
    for c in CANDS:
        IS = d[c]["IS"]; OO = d[c]["OOS"]
        print(f"   {c:22} IS {(IS['mean'] if IS else 0):+.1f}/sig(n{IS['n'] if IS else 0})   OOS {(OO['mean'] if OO else 0):+.1f}/sig(n{OO['n'] if OO else 0})")
print("\nwrote scratchpad/rehab_chand_sweep.json")
