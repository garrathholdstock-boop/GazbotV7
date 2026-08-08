#!/usr/bin/env python3
"""FULL rehab engine — grind-exit scale-out (two_ratchet / partial / Lot-A scalp).

Tick-honest ($1.50/RT/lot, $2/pt), per-regime, per-time-of-day. Reconstructs every
grind_long SIGNAL (deduped by opened_at) that has capture.db tick coverage, reprices
ALL exit policies counterfactually on the true post-entry tick path, and evaluates each
policy ONLY on its home regime segments. Sweeps the Lot-A scalp R + Lot-B params per
regime and reports the proven plateau vs the operator's guess. Shows every NULL/grave.

READ-ONLY. No live writes, no commits.
"""
from __future__ import annotations
import datetime as dt
import sqlite3
import sys
import collections
import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import archive_data as A
from gazbot7.deciders import Bar, compute_features

VPP, FEE = 2.0, 1.5
STORE = "/home/alphabot/gazbot7/data/gazbot7.db"
PRIMARY = dict(start_k=3.5, lock_r=6.0, lock_k=0.5)     # deployed Lot-B chandelier
RATCHET2 = dict(arm_r=4.0, disarm_r=4.5, b_k=1.25)      # shadow 2nd ratchet
HORIZON_MS = 60 * 60000
STOP_M = 1.0

# ── exits ────────────────────────────────────────────────────────────────────
def ex_lock(fav, atr, start_k, lock_r, lock_k):
    peak = np.maximum.accumulate(fav)
    k = np.where(peak / atr < lock_r, start_k, lock_k)
    thresh = peak - k * atr
    chand = (fav > 0) & (fav <= thresh); stop = fav <= -STOP_M * atr
    fire = chand | stop
    idx = int(np.argmax(fire)) if fire.any() else len(fav) - 1
    return float(fav[idx])

def ex_two_ratchet(fav, atr, *, start_k, lock_r, lock_k, arm_r, disarm_r, b_k):
    peak = np.maximum.accumulate(fav); peak_r = peak / atr
    kp = np.where(peak_r < lock_r, start_k, lock_k); gb_p = kp * atr
    reached_disarm = np.maximum.accumulate((peak_r >= disarm_r).astype(float)) > 0
    b_active = (peak_r >= arm_r) & (~reached_disarm)
    gb_b = np.where(b_active, b_k * atr, np.inf)
    gb = np.minimum(gb_p, gb_b); thresh = peak - gb
    chand = (fav > 0) & (fav <= thresh); stop = fav <= -STOP_M * atr
    fire = chand | stop
    idx = int(np.argmax(fire)) if fire.any() else len(fav) - 1
    return float(fav[idx])

def ex_scalp(fav, atr, target_r, stop_m=STOP_M):
    tgt = fav >= target_r * atr; stop = fav <= -stop_m * atr
    fire = tgt | stop
    idx = int(np.argmax(fire)) if fire.any() else len(fav) - 1
    return float(fav[idx])

def net_usd(pts):  # one lot
    return pts * VPP - FEE

def rmfe(fav, atr):
    sh = np.where(fav <= -atr)[0]
    hz = sh[0] if len(sh) else len(fav) - 1
    m = float(fav[:hz + 1].max())
    return m, m / atr

# ── entry ATR (same as the watch tools) ───────────────────────────────────────
def _atr_at(D, entry_ms):
    entry_sec = entry_ms // 1000
    k = int(np.searchsorted(D.mins, entry_sec - 60, side="right")) - 1
    if k < 6:
        return D.atr_for(entry_ms) or 0.0
    lo = max(0, k - 59)
    bars = [Bar(int(D.mins[j]), float(D.cls[j]), float(D.hh[j]), float(D.ll[j]),
                float(D.cls[j]), float(D.vv[j])) for j in range(lo, k + 1)]
    try:
        return float(compute_features(bars).atr)
    except Exception:
        return D.atr_for(entry_ms) or 0.0

def _iso_to_ms(s):
    return int(dt.datetime.fromisoformat(s).timestamp() * 1000)

def _regime(atr, er, net30, us):
    """Coarse regime key on ATR level + ER + directional net30 (+ time-of-day carried separately)."""
    er = er if er is not None else 0.0
    net30 = net30 if net30 is not None else 0.0
    if er >= 0.5 and net30 > 0:
        return "clean-trend-up"
    if er >= 0.5 and net30 <= 0:
        return "clean-trend-down"   # grind is LONG; a strong down ER = counter
    if 0.3 <= er < 0.5:
        return "building"
    # er < 0.3 -> chop; split by ATR
    if atr >= 28:
        return "violent-whipsaw"
    return "dead/normal-chop"

# ── load signals ──────────────────────────────────────────────────────────────
def load_signals():
    c = sqlite3.connect(STORE); c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT opened_at, gate, side, qty, entry_price, exit_price, pnl_usd, exit_reason "
        "FROM trades WHERE symbol='MNQ' AND gate LIKE 'grind%' AND side='LONG' "
        "AND opened_at>='2026-07-23T22:00' ORDER BY opened_at").fetchall()
    c.close()
    sig = collections.OrderedDict()
    for r in rows:
        sig.setdefault(r["opened_at"][:19], []).append(r)
    return sig

def main():
    sig = load_signals()
    D = A.load(since="2026-07-23 22:00:00", until="2026-07-31 21:00:00")
    tts, tpx = D.tts, D.tpx
    print(f"# tape span {D.span}  n_ticks={D.n_ticks:,}  cutover={D.cutover}")
    print(f"# {len(sig)} unique grind_long signals in coverage\n")

    recs = []
    for k, grp in sig.items():
        r0 = grp[0]
        entry_ms = _iso_to_ms(r0["opened_at"])
        epx = float(r0["entry_price"]); atr = _atr_at(D, entry_ms)
        if atr <= 0:
            continue
        lo = int(np.searchsorted(tts, entry_ms, "right"))
        hi = int(np.searchsorted(tts, entry_ms + HORIZON_MS, "right"))
        if hi - lo < 2:
            continue
        fav = tpx[lo:hi] - epx
        rm_pts, rm_r = rmfe(fav, atr)
        er = D.er_for(entry_ms); net30 = D.net30_for(entry_ms)
        d = dt.datetime.fromtimestamp(entry_ms / 1000, dt.UTC)
        us = (d.hour, d.minute) >= (13, 30) and d.hour < 20
        regime = _regime(atr, er, net30, us)
        # live actual (normalized to base_size=1 per lot)
        live_lots = []
        for r in grp:
            q = float(r["qty"]) or 1.0
            live_lots.append(float(r["pnl_usd"]) / q)   # per-lot live
        recs.append(dict(
            ts=r0["opened_at"], day=d.strftime("%Y-%m-%d"), hour=d.hour, us=us,
            wk=d.isocalendar()[1], atr=atr, er=er, net30=net30, regime=regime,
            rm_r=rm_r, fav=fav, gates=[r["gate"] for r in grp],
            live_lots=live_lots, live_reasons=[r["exit_reason"] for r in grp],
            live_qty=[float(r["qty"]) for r in grp],
            live_raw_pnl=[float(r["pnl_usd"]) for r in grp]))
    return recs

if __name__ == "__main__":
    recs = main()
    import pickle
    with open("/tmp/claude-0/-root/0bb3b1b0-e3be-4607-baa9-5ed673420d95/scratchpad/grind_recs.pkl", "wb") as f:
        # strip fav arrays for pickle size? keep them - needed downstream
        pickle.dump(recs, f)
    print(f"saved {len(recs)} recs")
    # quick regime census
    byr = collections.Counter(r["regime"] for r in recs)
    print("regime census:", dict(byr))
    print("US-session:", sum(1 for r in recs if r["us"]), " overnight:", sum(1 for r in recs if not r["us"]))
    print("ATR range:", round(min(r["atr"] for r in recs),1), "-", round(max(r["atr"] for r in recs),1))
    print("rMFE_R distribution:", sorted(round(r["rm_r"],1) for r in recs))
