"""GRADE the LIVE exhaustion_short fade-scalp trial (A@0.5R + B@1.5R, deployed 2026-07-31).

Two halves:
  (1) ACTUAL FILLS — every live exhaustion_short trade, split by the exit config that was
      actually running (pre-trial single-slot -> A@2.5R + wide lock-chandelier default ->
      the 07-31 fade-scalp trial), with the 0.5R/1.5R hit-rate vs stops.
  (2) REPRICE — because the live trial n is tiny, replay EVERY exhaustion entry we have
      (live exhaustion_short signals + the exhaustion_rev shadow board) on the forward 5s
      path under BOTH configs, segmented by regime rung. That is the honest read.

Read-only.  Writes scratchpad/exhaustion_trial.json.
"""
from __future__ import annotations
import sqlite3, json, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import numpy as np

UTC = timezone.utc
VPP, FEE, HORIZON_MIN = 2.0, 1.5, 90
TAPE = "/home/alphabot/gazbot7/scratchpad/tape5s.npz"
STORE = "/home/alphabot/gazbot7/data/gazbot7.db"
SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
TRIAL_START = "2026-07-31T07:55:00"     # operator deploy of the A0.5/B1.5 override

z = np.load(TAPE)
bts, bh, bl, bc = z["ts"], z["h"], z["l"], z["c"]

# 1-min ER(30) + ATR(14) for the regime rung
mk = {}
for i in range(len(bts)):
    m = int(bts[i]) // 60
    r = mk.get(m)
    if r is None:
        mk[m] = [bh[i], bl[i], bc[i]]
    else:
        r[0] = max(r[0], bh[i]); r[1] = min(r[1], bl[i]); r[2] = bc[i]
mins = sorted(mk)
H = np.array([mk[m][0] for m in mins]); L = np.array([mk[m][1] for m in mins]); C = np.array([mk[m][2] for m in mins])
tr = np.zeros(len(mins))
for i in range(1, len(mins)):
    tr[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
ER, ATR = {}, {}
for i, m in enumerate(mins):
    if i >= 30:
        seg = C[i - 30:i + 1]; path = float(np.abs(np.diff(seg)).sum()) or 1.0
        ER[m] = abs(seg[-1] - seg[0]) / path
    if i >= 14:
        ATR[m] = float(tr[i - 13:i + 1].mean())


def rung(ts):
    er = ER.get(ts // 60, 0.0)
    return "BIG-TREND" if er >= 0.50 else "MED-TREND" if er >= 0.30 else "SCALP-CHOP"


# ────────── (1) actual live fills ──────────
st = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
live = st.execute(
    "SELECT id, side, entry_price, exit_price, opened_at, closed_at, pnl_usd, exit_reason, gate "
    "FROM trades WHERE gate LIKE 'exhaustion_short%' ORDER BY opened_at").fetchall()


def era(opened, gate):
    if opened >= TRIAL_START:
        return "TRIAL A0.5/B1.5"
    if gate.endswith("_A") or gate.endswith("_B"):
        return "DEFAULT A2.5+WIDE"
    return "PRE single-slot"


eras = defaultdict(list)
for r in live:
    eras[era(r[4], r[8])].append(r)

out = {"live": {}}
print("═══ LIVE exhaustion_short — actual fills by exit config ═══")
print(f"{'config':22}{'n':>4}{'net$':>9}{'win%':>6}{'TARGET':>8}{'STOP':>6}{'CHAND':>7}{'other':>7}")
for k in ("PRE single-slot", "DEFAULT A2.5+WIDE", "TRIAL A0.5/B1.5"):
    v = eras.get(k, [])
    if not v:
        continue
    net = sum(x[6] for x in v)
    rc = defaultdict(int)
    for x in v:
        rc[x[7]] += 1
    w = sum(1 for x in v if x[6] > 0)
    out["live"][k] = dict(n=len(v), net=round(net, 1), win=round(100 * w / len(v)), reasons=dict(rc))
    print(f"{k:22}{len(v):>4}{net:>9.1f}{100*w/len(v):>6.0f}{rc.get('TARGET',0):>8}{rc.get('STOP',0):>6}"
          f"{rc.get('CHANDELIER',0):>7}{sum(c for rr,c in rc.items() if rr not in ('TARGET','STOP','CHANDELIER')):>7}")

print("\nTRIAL fills, one line each:")
trial_rows = []
for r in eras.get("TRIAL A0.5/B1.5", []):
    _id, side, ep, xp, op, cl, pnl, rsn, gate = r
    m = int(datetime.fromisoformat(op).timestamp()) // 60
    a = ATR.get(m, 0.0)
    rr = ((ep - xp) / a) if a else 0.0
    trial_rows.append(dict(id=_id, gate=gate, opened=op, entry=ep, exit=xp, pnl=round(pnl, 1),
                           reason=rsn, atr=round(a, 1), R=round(rr, 2), rung=rung(m * 60)))
    print(f"  {gate:20} {op[11:19]}  entry {ep:.2f} -> {xp:.2f}  ATR {a:.1f}pt  = {rr:+.2f}R  "
          f"${pnl:+.1f}  {rsn}  [{rung(m*60)}]")
out["trial_rows"] = trial_rows

# ────────── (2) reprice both configs on every exhaustion entry ──────────
sig = {}
for r in live:
    ts = int(datetime.fromisoformat(r[4]).timestamp())
    sig[ts // 5 * 5] = ("live", r[1], r[2], ts)
sh = sqlite3.connect(f"file:{SHADOW}?mode=ro", uri=True)
for side, ets, ep, eatr in sh.execute(
        "SELECT side, entry_ts, entry_price, entry_atr FROM shadow_trades WHERE strategy='exhaustion_rev' AND entry_atr>0"):
    sig.setdefault(int(ets) // 5 * 5, ("shadow", side, float(ep), int(ets)))
print(f"\nrepriced exhaustion entries: {len(sig)} (live {sum(1 for v in sig.values() if v[0]=='live')} + "
      f"shadow {sum(1 for v in sig.values() if v[0]=='shadow')})")


def path(side, entry, atr, i0):
    j1 = min(i0 + HORIZON_MIN * 12, len(bts))
    h, l, c = bh[i0:j1], bl[i0:j1], bc[i0:j1]
    if len(h) < 12:
        return None
    if side == "LONG":
        return (h - entry) / atr, (entry - l) / atr, (c - entry) / atr
    return (entry - l) / atr, (h - entry) / atr, (entry - c) / atr


def r_scalp(favcum, stop_i, t, cfl):
    hit = int(np.argmax(favcum >= t)) if (favcum >= t).any() else len(favcum)
    if hit < stop_i:
        return t
    if stop_i < len(favcum):
        return -1.0
    return max(min(cfl, t), -1.0)


def r_lock(fav, adv, cf):
    stop_i = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else len(fav)
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_i:
            return -1.0
        peak = max(peak, fav[i])
        if peak > 0:
            k = 3.5 if peak < 6.0 else 0.5
            if cf[i] > 0 and cf[i] <= peak - k:
                return float(cf[i])
    return max(min(float(cf[-1]), peak), -1.0)


buckets = defaultdict(lambda: {"trial": [], "prior": [], "hitA": 0, "hitB": 0, "stop": 0, "n": 0})
for key in sorted(sig):
    src, side, ep, ts = sig[key]
    m = ts // 60
    atr = ATR.get(m, 0.0)
    if atr <= 0:
        continue
    i0 = int(np.searchsorted(bts, ts))
    p = path(side, ep, atr, i0)
    if p is None:
        continue
    fav, adv, cf = p
    favcum = np.maximum.accumulate(fav)
    stop_i = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else len(fav)
    cfl = float(cf[-1])
    usd = lambda rr: rr * atr * VPP - FEE
    trial = usd(r_scalp(favcum, stop_i, 0.5, cfl)) + usd(r_scalp(favcum, stop_i, 1.5, cfl))
    prior = usd(r_scalp(favcum, stop_i, 2.5, cfl)) + usd(r_lock(fav, adv, cf))
    for k in (rung(ts), "ALL"):
        b = buckets[k]
        b["trial"].append(trial); b["prior"].append(prior); b["n"] += 1
        if (favcum >= 0.5).any() and int(np.argmax(favcum >= 0.5)) < stop_i:
            b["hitA"] += 1
        if (favcum >= 1.5).any() and int(np.argmax(favcum >= 1.5)) < stop_i:
            b["hitB"] += 1
        if stop_i < len(favcum) and not ((favcum >= 0.5).any() and int(np.argmax(favcum >= 0.5)) < stop_i):
            b["stop"] += 1

print(f"\n{'rung':13}{'n':>5}{'0.5R hit':>10}{'1.5R hit':>10}{'stop-first':>12}"
      f"{'TRIAL $/sig':>13}{'PRIOR $/sig':>13}{'delta':>9}")
rep = {}
for k in ("ALL", "BIG-TREND", "MED-TREND", "SCALP-CHOP"):
    b = buckets.get(k)
    if not b or not b["n"]:
        continue
    t = sum(b["trial"]) / b["n"]; pr = sum(b["prior"]) / b["n"]
    rep[k] = dict(n=b["n"], hitA=round(100 * b["hitA"] / b["n"]), hitB=round(100 * b["hitB"] / b["n"]),
                  stop=round(100 * b["stop"] / b["n"]), trial_mean=round(t, 2), prior_mean=round(pr, 2),
                  trial_tot=round(sum(b["trial"]), 1), prior_tot=round(sum(b["prior"]), 1),
                  trial_win=round(100 * sum(1 for x in b["trial"] if x > 0) / b["n"]),
                  prior_win=round(100 * sum(1 for x in b["prior"] if x > 0) / b["n"]))
    print(f"{k:13}{b['n']:>5}{rep[k]['hitA']:>9}%{rep[k]['hitB']:>9}%{rep[k]['stop']:>11}%"
          f"{t:>13.2f}{pr:>13.2f}{t-pr:>9.2f}")
out["reprice"] = rep
json.dump(out, open("/home/alphabot/gazbot7/scratchpad/exhaustion_trial.json", "w"), indent=1, default=float)
print("\nwrote scratchpad/exhaustion_trial.json")
