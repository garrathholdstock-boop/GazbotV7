#!/usr/bin/env python3
"""Two-ratchet SHADOW WATCH — observe-only clip detector for grind_long.

The live grind_long gate runs the PURE-6.0 threshold-chandelier (start_k=3.5, lock_r=6.0,
lock_k=0.5) as of the 2026-07-26 deploy. The operator wants to shadow the rejected two-ratchet
variant (arm_r=4.0, disarm_r=4.5, b_k=1.25 on top of the same 6.0 primary) and specifically
WATCH FOR RUNNER-CLIPS — the failure mode the range-only backtest archive could not surface:
on a real trend day the second ratchet banks a trade off a ~4R plateau that then ignites to 6R+,
clipping a true runner (the 17 rMFE>=4R runners carry ~263% of grind's net — they ARE the edge).

This tool is READ-ONLY. For every live grind_long trade since the deploy it reconstructs the
post-entry tick path from capture.db (via archive_data.load, the validated loader), reprices BOTH
exits tick-honestly, computes reachable-MFE, and flags a CLIP when the two-ratchet exits
materially below the live pure-6.0 exit on a trade that reached >=4R. It emits a durable ledger
(data/two_ratchet_shadow.json) and can ping the operator when a clip occurs. No commits, no
live-service writes, no order entry.

  cd /home/alphabot/gazbot7 && PYTHONPATH=src:scripts ./.venv/bin/python \
      scripts/two_ratchet_shadow_watch.py [--since ISO] [--until ISO] [--ping]

Cron it weekly (feeds the Friday gate-rehab section). Default window: since the deploy, to now.
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
LEDGER = "/home/alphabot/gazbot7/data/two_ratchet_shadow.json"
DEPLOY_DEFAULT = "2026-07-26T18:00:00+00:00"   # the 18:07 pure-6.0 deploy; watch forward from here
# Primary (deployed) + shadow second-ratchet params
PRIMARY = dict(start_k=3.5, lock_r=6.0, lock_k=0.5)
RATCHET2 = dict(arm_r=4.0, disarm_r=4.5, b_k=1.25)
CLIP_USD = 20.0          # two-ratchet must be >$20 below pure to count as a material clip
RUNNER_R = 4.0           # a "runner" reaches reachable-MFE >= 4R


# ── exits (byte-identical to the recon.py study engine) ──────────────────────
def ex_lock(fav, atr, start_k, lock_r, lock_k):
    peak = np.maximum.accumulate(fav)
    k = np.where(peak / atr < lock_r, start_k, lock_k)
    thresh = peak - k * atr
    chand = (fav > 0) & (fav <= thresh); stop = fav <= -atr
    fire = chand | stop
    if fire.any():
        idx = int(np.argmax(fire)); isstop = bool(stop[idx] and not chand[idx])
    else:
        idx = len(fav) - 1; isstop = False
    return float(fav[idx]), idx, isstop


def ex_two_ratchet(fav, atr, *, start_k, lock_r, lock_k, arm_r, disarm_r, b_k):
    peak = np.maximum.accumulate(fav)
    peak_r = peak / atr
    kp = np.where(peak_r < lock_r, start_k, lock_k)
    gb_p = kp * atr
    reached_disarm = np.maximum.accumulate((peak_r >= disarm_r).astype(float)) > 0
    b_active = (peak_r >= arm_r) & (~reached_disarm)
    gb_b = np.where(b_active, b_k * atr, np.inf)
    gb = np.minimum(gb_p, gb_b)
    thresh = peak - gb
    chand = (fav > 0) & (fav <= thresh); stop = fav <= -atr
    fire = chand | stop
    if fire.any():
        idx = int(np.argmax(fire)); isstop = bool(stop[idx] and not chand[idx])
    else:
        idx = len(fav) - 1; isstop = False
    return float(fav[idx]), idx, isstop


def net_usd(fav_pts):
    return fav_pts * VPP - FEE


def rmfe(fav, atr):
    sh = np.where(fav <= -atr)[0]
    hz = sh[0] if len(sh) else len(fav) - 1
    m = float(fav[:hz + 1].max())
    return m, m / atr


def _sanity():
    """Assert the composition is correct before trusting any live number."""
    rng = np.linspace(-30, 260, 4000)
    fav = np.concatenate([rng, rng[::-1]]); atr = 30.0
    pure = net_usd(ex_lock(fav, atr, **PRIMARY)[0])
    # empty band -> pure
    a = net_usd(ex_two_ratchet(fav, atr, **PRIMARY, arm_r=4.5, disarm_r=4.0, b_k=1.25)[0])
    # huge b_k -> pure
    b = net_usd(ex_two_ratchet(fav, atr, **PRIMARY, arm_r=4.0, disarm_r=4.5, b_k=99.0)[0])
    assert abs(a - pure) < 1e-6, f"empty-band != pure ({a} vs {pure})"
    assert abs(b - pure) < 1e-6, f"huge-bk != pure ({b} vs {pure})"


# ── live trade repricing ─────────────────────────────────────────────────────
def _atr_at(D, entry_ms):
    """ATR(14) via compute_features on the 60 one-min bars ending just before entry —
    the same ATR the live gate and the study used. Falls back to D.atr_for on any gap."""
    entry_sec = entry_ms // 1000
    k = int(np.searchsorted(D.mins, entry_sec - 60, side="right")) - 1   # last completed bar < entry
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


def live_grind_trades(since_iso, until_iso):
    c = sqlite3.connect(STORE); c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT opened_at, closed_at, side, entry_price, exit_price, pnl_usd, exit_reason "
        "FROM trades WHERE symbol='MNQ' AND gate='grind_long' AND side='LONG' "
        "AND closed_at>=? AND closed_at<=? ORDER BY opened_at",
        (since_iso, until_iso)).fetchall()
    c.close()
    return rows


def run(since_iso, until_iso, do_ping):
    _sanity()
    since_sql = since_iso.replace("T", " ").split("+")[0]
    until_sql = until_iso.replace("T", " ").split("+")[0]
    trades = live_grind_trades(since_iso, until_iso)
    if not trades:
        print(f"[two-ratchet watch] no live grind_long trades in [{since_iso} .. {until_iso}] yet.")
        _write_ledger(dict(since=since_iso, until=until_iso, n=0, note="no trades yet"))
        return

    # Load the live tick/bar window that spans every trade (pad the entry side by 2 min).
    D = A.load(since=since_sql, until=until_sql)
    tts, tpx = D.tts, D.tpx

    recs, clips = [], []
    shadow_net = live_net = recon_pure_net = 0.0
    n_runner = 0
    for r in trades:
        entry_ms = _iso_to_ms(r["opened_at"])
        epx = float(r["entry_price"])
        atr = _atr_at(D, entry_ms)
        if atr <= 0:
            continue
        lo = int(np.searchsorted(tts, entry_ms, "right"))
        hi = int(np.searchsorted(tts, entry_ms + 60 * 60000, "right"))
        if hi - lo < 2:
            continue
        fav = tpx[lo:hi] - epx                       # LONG favourable-excursion path
        pure_pts, _, _ = ex_lock(fav, atr, **PRIMARY)
        tr_pts, _, _ = ex_two_ratchet(fav, atr, **PRIMARY, **RATCHET2)
        rm_pts, rm_r = rmfe(fav, atr)
        pure_usd_recon = net_usd(pure_pts)
        tr_usd = net_usd(tr_pts)
        live_usd = float(r["pnl_usd"])               # the ACTUAL deployed result (pure-6.0 forward)
        is_runner = rm_r >= RUNNER_R
        # a runner-clip = two-ratchet banks a >=4R runner materially below what the pure-6.0
        # PRIMARY would do on the IDENTICAL path (counterfactual, so it's valid even in a
        # validation window where the actual live exit differed).
        clipped = is_runner and (tr_usd < pure_usd_recon - CLIP_USD)
        shadow_net += tr_usd; live_net += live_usd; recon_pure_net += pure_usd_recon
        n_runner += is_runner
        rec = dict(opened_at=r["opened_at"], atr=round(atr, 1), rmfe_R=round(rm_r, 2),
                   live_usd=round(live_usd, 1), shadow_usd=round(tr_usd, 1),
                   recon_pure_usd=round(pure_usd_recon, 1), runner=is_runner, clip=clipped,
                   exit_reason=r["exit_reason"])
        recs.append(rec)
        if clipped:
            clips.append(rec)

    # cross-check: reconstructed pure vs the actual deployed pnl (validates ATR + tick alignment)
    xcheck = round(recon_pure_net - live_net, 1)

    print("=" * 96)
    print(f"TWO-RATCHET SHADOW WATCH  grind_long  [{since_iso} .. {until_iso}]")
    print(f"primary {PRIMARY} | shadow-2nd {RATCHET2} | clip= >${CLIP_USD:.0f} below live & rMFE>={RUNNER_R}R")
    print("=" * 96)
    print(f"{'opened_at':25} {'ATR':>5} {'rMFE_R':>6} {'live$':>7} {'shadow$':>8} {'runner':>7} {'CLIP':>5}")
    for x in recs:
        print(f"{x['opened_at']:25} {x['atr']:>5} {x['rmfe_R']:>6} {x['live_usd']:>+7.0f} "
              f"{x['shadow_usd']:>+8.0f} {str(x['runner']):>7} {('CLIP' if x['clip'] else ''):>5}")
    print("-" * 96)
    print(f"trades={len(recs)}  runners(rMFE>=4R)={n_runner}  RUNNER-CLIPS={len(clips)}")
    print(f"LIVE pure-6.0 net = ${live_net:+.0f}   SHADOW two-ratchet net = ${shadow_net:+.0f}   "
          f"(shadow − live = ${shadow_net - live_net:+.0f})")
    print(f"[cross-check] reconstructed-pure − actual-live = ${xcheck:+.0f} (should be ~0; large = data drift)")
    if clips:
        print("\n⚠ RUNNER-CLIPS — the two-ratchet banked a real >=4R runner early:")
        for x in clips:
            print(f"   {x['opened_at']}  rMFE {x['rmfe_R']}R  live ${x['live_usd']:+.0f} vs shadow "
                  f"${x['shadow_usd']:+.0f}  (gave up ${x['live_usd'] - x['shadow_usd']:+.0f})")

    ledger = dict(since=since_iso, until=until_iso, n=len(recs), runners=n_runner,
                  runner_clips=len(clips), live_net=round(live_net, 1),
                  shadow_net=round(shadow_net, 1), xcheck=xcheck, clips=clips, trades=recs)
    _write_ledger(ledger)

    if do_ping and clips:
        _ping(clips, live_net, shadow_net)
    return ledger


def _write_ledger(d):
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, LEDGER)


def _ping(clips, live_net, shadow_net):
    try:
        from gazbot7.notify import notify
    except Exception:
        return
    lines = [f"Two-ratchet shadow: {len(clips)} RUNNER-CLIP(s) detected on grind_long — "
             "the trend-week failure mode we were watching for."]
    for x in clips:
        lines.append(f"• {x['opened_at']}: reached {x['rmfe_R']}R, live pure-6.0 banked "
                     f"${x['live_usd']:+.0f} but the two-ratchet exited at ${x['shadow_usd']:+.0f} "
                     f"(clipped ${x['live_usd'] - x['shadow_usd']:+.0f}).")
    lines.append(f"Cumulative: live pure-6.0 ${live_net:+.0f} vs shadow two-ratchet ${shadow_net:+.0f}. "
                 "This is exactly why we kept it in shadow, not live.")
    notify("\n".join(lines), critical=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=DEPLOY_DEFAULT)
    ap.add_argument("--until", default=None)
    ap.add_argument("--ping", action="store_true")
    a = ap.parse_args()
    until = a.until or dt.datetime.now(dt.UTC).isoformat()
    run(a.since, until, a.ping)
