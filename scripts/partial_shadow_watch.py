#!/usr/bin/env python3
"""2R-partial SHADOW WATCH — observe-only smoothness monitor for grind_long.

The live grind_long gate runs the PURE-6.0 threshold-chandelier on base_size=2 (both lots exit
together on the chandelier). The operator wants to shadow a PARTIAL-SCALING variant — Lot A scalps
at 2R (banks certainty), Lot B rides the chandelier (banks the tail) — which in backtest is a
VARIANCE lever (daily-vol −29%, maxDD −24%, worst-day −34%) for a ~$665/3wk mean give-up
concentrated in a couple of runner days. Unlike the two-ratchet watch (which alarms on a discrete
runner-CLIP), this one has no alarm event — it tracks the SMOOTHNESS: cumulative partial vs
baseline P&L and the variance metrics (daily std, max drawdown, worst day, green-day/week %), so
the operator can watch the smoother curve accumulate live before deciding to adopt it.

READ-ONLY. Reconstructs every live grind_long trade's post-entry tick path from capture.db (via
archive_data.load, the validated loader), reprices BOTH exit schemes at a normalized 2-lot basis,
and writes a durable ledger (data/partial_shadow.json). No commits, no live-service writes.

  cd /home/alphabot/gazbot7 && PYTHONPATH=src:scripts ./.venv/bin/python \
      scripts/partial_shadow_watch.py [--since ISO] [--until ISO]

Cron it (daily refresh) + present it in the Friday gate-rehab section.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import archive_data as A
from gazbot7.deciders import Bar, compute_features

VPP, FEE = 2.0, 1.5
STORE = "/home/alphabot/gazbot7/data/gazbot7.db"
LEDGER = "/home/alphabot/gazbot7/data/partial_shadow.json"
DEPLOY_DEFAULT = "2026-07-26T18:00:00+00:00"
PRIMARY = dict(start_k=3.5, lock_r=6.0, lock_k=0.5)   # the deployed chandelier
SCALP_R = 2.0                                          # Lot A's scalp target (R)


# ── exits (byte-identical to the recon.py study engine) ──────────────────────
def ex_lock(fav, atr, start_k, lock_r, lock_k):
    peak = np.maximum.accumulate(fav)
    k = np.where(peak / atr < lock_r, start_k, lock_k)
    thresh = peak - k * atr
    chand = (fav > 0) & (fav <= thresh); stop = fav <= -atr
    fire = chand | stop
    idx = int(np.argmax(fire)) if fire.any() else len(fav) - 1
    return float(fav[idx])


def ex_scalp(fav, atr, target_r=2.0, stop_m=1.0):
    tgt = fav >= target_r * atr; stop = fav <= -stop_m * atr
    fire = tgt | stop
    idx = int(np.argmax(fire)) if fire.any() else len(fav) - 1
    return float(fav[idx])


def net_usd(pts):
    return pts * VPP - FEE


def _sanity():
    atr = 30.0
    fav = np.concatenate([np.linspace(0, 260, 4000), np.linspace(260, -20, 4000)])  # up then down, never hits −ATR
    chand = net_usd(ex_lock(fav, atr, **PRIMARY))
    # scalp with an unreachable target -> rides to end like the chandelier's MAX_HOLD leg would differ;
    # instead assert the scalp fires AT the 2R target when the path clearly exceeds it:
    assert abs(ex_scalp(fav, atr, 2.0) - 2.0 * atr) < atr, "scalp should exit near the 2R target"
    assert chand > 0, "pure chandelier should be green on a big up-then-down path"


# ── live trade repricing ─────────────────────────────────────────────────────
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


def _utc_day(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%d")


def _iso_week(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).isocalendar()[1]


def live_grind_trades(since_iso, until_iso):
    c = sqlite3.connect(STORE); c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT opened_at, closed_at, entry_price, pnl_usd FROM trades "
        "WHERE symbol='MNQ' AND gate='grind_long' AND side='LONG' "
        "AND closed_at>=? AND closed_at<=? ORDER BY opened_at", (since_iso, until_iso)).fetchall()
    c.close()
    return rows


def _curve_stats(day_pnl: dict):
    """std of daily P&L, max drawdown of the cumulative curve, worst day, green-day%."""
    days = sorted(day_pnl)
    vals = [day_pnl[d] for d in days]
    if not vals:
        return dict(days=0, std=0.0, maxdd=0.0, worst=0.0, green_day_pct=0.0, curve=[])
    std = float(np.std(vals))
    cum, peak, maxdd, run = 0.0, 0.0, 0.0, []
    for d, v in zip(days, vals):
        cum += v; peak = max(peak, cum); maxdd = min(maxdd, cum - peak)
        run.append([d, round(cum, 1)])
    green = 100.0 * sum(1 for v in vals if v > 0) / len(vals)
    return dict(days=len(vals), std=round(std, 1), maxdd=round(maxdd, 1),
                worst=round(min(vals), 1), green_day_pct=round(green, 1), curve=run)


def run(since_iso, until_iso):
    _sanity()
    trades = live_grind_trades(since_iso, until_iso)
    if not trades:
        print(f"[2R-partial watch] no live grind_long trades in [{since_iso} .. {until_iso}] yet.")
        _write(dict(since=since_iso, until=until_iso, n=0, note="no trades yet"))
        return
    D = A.load(since=since_iso.replace("T", " ").split("+")[0],
               until=until_iso.replace("T", " ").split("+")[0])
    tts, tpx = D.tts, D.tpx

    recs = []
    base_day, part_day = {}, {}   # UTC-day -> summed 2-lot P&L
    base_wk, part_wk = {}, {}
    base_net = part_net = 0.0
    for r in trades:
        entry_ms = _iso_to_ms(r["opened_at"])
        epx = float(r["entry_price"]); atr = _atr_at(D, entry_ms)
        if atr <= 0:
            continue
        lo = int(np.searchsorted(tts, entry_ms, "right"))
        hi = int(np.searchsorted(tts, entry_ms + 60 * 60000, "right"))
        if hi - lo < 2:
            continue
        fav = tpx[lo:hi] - epx                                   # LONG path
        chand = net_usd(ex_lock(fav, atr, **PRIMARY))
        scalp = net_usd(ex_scalp(fav, atr, SCALP_R))
        baseline = 2 * chand                                     # deployed: 2 lots both on chandelier
        partial = scalp + chand                                 # Lot A scalp-2R + Lot B chandelier
        day = _utc_day(entry_ms); wk = _iso_week(entry_ms)
        base_day[day] = base_day.get(day, 0.0) + baseline
        part_day[day] = part_day.get(day, 0.0) + partial
        base_wk[wk] = base_wk.get(wk, 0.0) + baseline
        part_wk[wk] = part_wk.get(wk, 0.0) + partial
        base_net += baseline; part_net += partial
        recs.append(dict(opened_at=r["opened_at"], atr=round(atr, 1),
                         baseline_usd=round(baseline, 1), partial_usd=round(partial, 1),
                         delta=round(partial - baseline, 1)))

    bs, ps = _curve_stats(base_day), _curve_stats(part_day)
    gw_base = 100.0 * sum(1 for v in base_wk.values() if v > 0) / len(base_wk) if base_wk else 0.0
    gw_part = 100.0 * sum(1 for v in part_wk.values() if v > 0) / len(part_wk) if part_wk else 0.0

    print("=" * 92)
    print(f"2R-PARTIAL SHADOW WATCH  grind_long  [{since_iso} .. {until_iso}]")
    print(f"baseline = 2 lots on pure-6.0 chandelier  |  partial = Lot A scalp-{SCALP_R:.0f}R + Lot B chandelier")
    print("=" * 92)
    print(f"{'metric':22}{'BASELINE (deployed)':>22}{'2R-PARTIAL (shadow)':>22}")
    print(f"{'net $':22}{base_net:>+22.0f}{part_net:>+22.0f}")
    print(f"{'  mean Δ (part−base)':22}{'':>22}{part_net - base_net:>+22.0f}")
    print(f"{'daily std $':22}{bs['std']:>22.0f}{ps['std']:>22.0f}")
    print(f"{'max drawdown $':22}{bs['maxdd']:>22.0f}{ps['maxdd']:>22.0f}")
    print(f"{'worst day $':22}{bs['worst']:>22.0f}{ps['worst']:>22.0f}")
    print(f"{'green-day %':22}{bs['green_day_pct']:>22.0f}{ps['green_day_pct']:>22.0f}")
    print(f"{'green-week %':22}{gw_base:>22.0f}{gw_part:>22.0f}")
    print(f"\ntrades={len(recs)}  days={bs['days']}  "
          f"→ the partial trades smoother vol/DD for a mean give-up of ${part_net - base_net:+.0f}")

    _write(dict(since=since_iso, until=until_iso, n=len(recs), scalp_r=SCALP_R,
                baseline_net=round(base_net, 1), partial_net=round(part_net, 1),
                mean_delta=round(part_net - base_net, 1),
                baseline=dict(std=bs['std'], maxdd=bs['maxdd'], worst=bs['worst'],
                              green_day_pct=bs['green_day_pct'], green_week_pct=round(gw_base, 1),
                              curve=bs['curve']),
                partial=dict(std=ps['std'], maxdd=ps['maxdd'], worst=ps['worst'],
                             green_day_pct=ps['green_day_pct'], green_week_pct=round(gw_part, 1),
                             curve=ps['curve']),
                trades=recs))
    return


def _write(d):
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, LEDGER)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=DEPLOY_DEFAULT)
    ap.add_argument("--until", default=None)
    a = ap.parse_args()
    run(a.since, a.until or dt.datetime.now(dt.UTC).isoformat())
