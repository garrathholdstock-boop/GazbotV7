#!/usr/bin/env python3
"""REV-3 — DOES gate_thrust(fast=True) CLOSE THE 6.2-MINUTE ARRIVAL LAG?   MNQ · read-only · PAPER

WHY THIS QUESTION.  The two-layer resolution study (rev3_two_layer_resolution.html) came back
DO-NOT-BUILD but produced the finding that motivates this one: the desk arrives a median +6.2
minutes into a big run, while the bar-close staleness it was attacking is only 65 seconds.  The
300 seconds live in the GATE'S OWN LOOKBACK — deciders.compute_features defines

    net_atr_5 = (close - close[-6]) / atr      a 5-bar span = 300s of measurement window
    net_atr_2 = (close - close[-3]) / atr      a 2-bar span = 120s

and gate_thrust already ships `fast=True`, which swaps one for the other.  CLOSED BARS ONLY —
no forming bar, no new state, no new failure surface.  That is the whole change under test.

ARMS (thrust family only; `fast` is a parameter of gate_thrust, so grind / rgv / the footprint
gates are structurally out of scope).
    slow          net_atr_5 >= thr                     the live desk, the control
    fast          net_atr_2 >= thr                     the literal fast=True swap (REPLACES)
    union         fires on whichever of the two trips first (a superset, not the parameter)
    trend_fast    net_atr_2 when the SLOW layer says confirmed-aligned-trend, else net_atr_5
                  — "the slow layer decides WHETHER, the shorter window decides WHEN"
    trend_only    net_atr_2 AND confirmed-aligned-trend; stands down everywhere else

Regime is computed on CLOSED bars only (er30>=0.15 & |net30|>=30, split by alignment to the
gate's side) so the trend gate is not circular.

METHOD, the desk's non-negotiables.  gazbot7.cadence.assert_matches_live(1000, 250): entries at
DECISION_MS=1000 (the desk polls once a second and cannot fill at a level it never observed),
stop/target raced at EXEC_MS=250 over 250ms OHLC buckets.  Scored on the RACE (target BEFORE
stop), never MFE; a bucket touching both scores STOP.  Sequential, ONE position per gate slot.
Fee $1.50/round trip.  The live 55s absorption veto and the live dual-lot exits from
data/exit_overrides.json.  Halt-aware ATR (deciders._atr).  Every number is a CEILING.

  PYTHONPATH=src ./.venv/bin/python scripts/rev3_fast_thrust.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb
import numpy as np

import rev3_two_layer as R
from gazbot7.cadence import DECISION_MS, EXEC_MS, assert_matches_live

assert_matches_live(DECISION_MS, EXEC_MS)

TAGS = ["abs_veto_long", "abs_veto_short"]
DAYS = R.DAYS
TREND_DAYS = ["2026-07-29", "2026-07-30"]
OUT = f"{R.SCRATCH}/rev3_fast_thrust.json"


# ══════════════════════════════════════════════════════════════════════════════
# the trigger — everything else about the gate is untouched
# ══════════════════════════════════════════════════════════════════════════════
def thrust_fires(tag, f, arm, thr, aligned):
    """(fires, margin, which) on a CLOSED-bar feature read.  `f` is build_day's `slow` dict.
    Mirrors deciders.gate_thrust exactly except for which net_atr feeds the comparison."""
    g = R.GATES[tag]
    if f["atr_pct"] < g["amp"] or not f["surge"]:
        return False, 0.0, None
    n5, n2 = f["net5"], f["net2"]
    want_long = g["side"] == "LONG"

    def ok(n):
        return ((n > 0) == want_long) and abs(n) >= thr

    if arm == "slow":
        return (ok(n5), abs(n5) / thr, "slow") if ok(n5) else (False, 0.0, None)
    if arm == "fast":
        return (True, abs(n2) / thr, "fast") if ok(n2) else (False, 0.0, None)
    if arm == "union":
        if ok(n2):
            return True, abs(n2) / thr, "fast"
        if ok(n5):
            return True, abs(n5) / thr, "slow"
        return False, 0.0, None
    if arm == "trend_fast":
        if aligned:
            return (True, abs(n2) / thr, "fast") if ok(n2) else (False, 0.0, None)
        return (True, abs(n5) / thr, "slow") if ok(n5) else (False, 0.0, None)
    if arm == "trend_union":
        if aligned:
            if ok(n2):
                return True, abs(n2) / thr, "fast"
        return (True, abs(n5) / thr, "slow") if ok(n5) else (False, 0.0, None)
    if arm == "trend_only":
        if aligned and ok(n2):
            return True, abs(n2) / thr, "fast"
        return False, 0.0, None
    raise ValueError(arm)


# ══════════════════════════════════════════════════════════════════════════════
# the sim — closed bars only, sequential, one position per slot
# ══════════════════════════════════════════════════════════════════════════════
def simulate(d, tag, arm, *, thr=1.5, slip=0.0, block=True, veto_mode="live"):
    """block=False lifts the one-position-per-slot rule; used ONLY for the signal-quality
    diagnostic (does the net_atr_2 SIGNAL earn, independent of which slot was free).
    veto_mode: "live" = the 55s absorption veto as it runs; "off" = no wait at all;
    "chop_only" = wait only when NOT in a confirmed aligned trend (the arrival census says the
    wait, not the window, is what costs the minutes, so this is the cheap alternative build)."""
    g = R.GATES[tag]
    side = g["side"]
    t1, t_lo = d["t1"], d["t_lo"]
    stop_new = t1 - R.STOP_NEW_BEFORE_END_S
    busy_until = -1
    pending = None
    trades = []

    def fill(sec, px, atr, which, reg, sig_sec):
        nonlocal busy_until
        entry = px + (slip * R.TICK if side == "LONG" else -slip * R.TICK)
        a_pt, b_pt = R.targets_for(tag, atr)
        end = min(sec + R.MAX_HOLD_S, t1)
        lots, last = [], sec
        for lab, tgt in (("A", a_pt), ("B", b_pt)):
            r, xp, xs = R.race(d, side, entry, sec, atr, tgt, end, slip)
            dd = (xp - entry) if side == "LONG" else (entry - xp)
            lots.append((lab, r, round(xp, 2), xs, round(dd * R.VPP - R.FEE_RT, 2)))
            last = max(last, xs)
        if block:
            busy_until = last
        trades.append(dict(sec=sec, sig_sec=sig_sec, which=which, regime=reg, entry=round(entry, 2),
                           atr=round(atr, 2), lots=lots, exit_sec=last,
                           pnl=round(sum(l[4] for l in lots), 2)))

    for (u, elapsed, just_closed, px_tick, base_reg, arm_esc, atr, atr_prev, er30, er15, net30w,
         net30, tape_net, form_flow, slow, ff) in d["rows"]:
        # ── the live 55s absorption veto, faithful to tournament.run ──
        if pending is not None:
            asec, apx, aatr, awhich, areg = pending
            age = u - asec
            if age >= R.VETO_SECS:
                pending = None
                if age <= R.VETO_MAX_SECS:
                    i0, i1 = asec - t_lo, u - t_lo
                    net = float(d["flow"][i0:i1].sum())
                    dpx = float(d["dec"][i1] - d["dec"][i0])
                    absorbed = (net >= R.VETO_FLOW_MIN and dpx <= 0) if side == "LONG" \
                        else (net <= -R.VETO_FLOW_MIN and dpx >= 0)
                    if not absorbed and (not block or busy_until < u) and u < stop_new:
                        fill(u, float(d["dec"][i1]), aatr, awhich, areg, asec)
        if not just_closed:
            continue
        if pending is not None or (block and busy_until >= u) or u >= stop_new:
            continue
        reg = R.regime_for(tag, base_reg)
        fires, _margin, which = thrust_fires(tag, slow, arm, thr, reg == "TREND_ALIGNED")
        if not fires:
            continue
        wait = g["veto"] and (veto_mode == "live"
                              or (veto_mode == "chop_only" and reg != "TREND_ALIGNED"))
        if wait:
            pending = (u, px_tick, atr, which, reg)
        else:
            fill(u, float(px_tick), atr, which, reg, u)
    return trades


def agg(trades):
    return dict(n=len(trades), pnl=round(sum(t["pnl"] for t in trades), 2),
                n_fast=sum(1 for t in trades if t["which"] == "fast"),
                pnl_fast=round(sum(t["pnl"] for t in trades if t["which"] == "fast"), 2),
                n_slow=sum(1 for t in trades if t["which"] == "slow"),
                pnl_slow=round(sum(t["pnl"] for t in trades if t["which"] == "slow"), 2))


# ══════════════════════════════════════════════════════════════════════════════
def signals(d, tag, arm, thr=1.5):
    """Every CLOSED-BAR signal instant, no slot blocking, no veto — the raw trigger stream.
    `arm` may be a thrust arm or "grind" (which routes to rev3_two_layer.gate_margin, i.e.
    gate_grind's own condition: ext band + tape_net>0 + vwap_slope_fast >= slope_min).
    Returns [(sig_sec, which, price, atr, regime)]."""
    out = []
    for r in d["rows"]:
        if not r[2]:                      # just_closed only — CLOSED bars, the whole point
            continue
        u, px_tick, base_reg, atr = r[0], r[3], r[4], r[6]
        tape_net, net30, slow = r[12], r[11], r[14]
        reg = R.regime_for(tag, base_reg)
        if arm == "grind":
            fires, _m = R.gate_margin(tag, slow, tape_net, net30)
            which = "grind"
        else:
            fires, _m, which = thrust_fires(tag, slow, arm, thr, reg == "TREND_ALIGNED")
        if fires:
            out.append((u, which, float(px_tick), atr, reg))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# ARRIVAL CENSUS — the operator's question, decomposed
#
#   arrival = (time for the WINDOW to register the move)
#           + (bar-boundary quantisation, <=65s, established upstream)
#           + (the CONFIRMATION WAIT: abs_veto's 55s absorption veto, and its RE-WAIT
#              whenever a signal is vetoed and the gate has to wait for the next one)
#
# The premise under test is that the first term dominates.  The operator's counter-observation
# is that grind reads a 720s window (2.4x LONGER than thrust's 300s) with NO wait and arrives at
# about the same time — which, if true, says the wait and the quantisation are the binding
# constraint and a shorter window cannot buy the 6.2 minutes.  So every lane below reports its
# SIGNAL instant and its FILL instant separately, and the veto is switched on and off.
# ══════════════════════════════════════════════════════════════════════════════
LANES = [
    # (label, tag, arm, veto?)   -- the four thrust lanes plus grind
    ("abs_veto net_atr_5 +55s veto  (LIVE)", "thrust", "slow", True),
    ("abs_veto net_atr_2 +55s veto  (fast)", "thrust", "fast", True),
    ("abs_veto net_atr_5, veto OFF", "thrust", "slow", False),
    ("abs_veto net_atr_2, veto OFF", "thrust", "fast", False),
    ("grind_long  vwap_slope_fast(720s), no wait", "grind", "grind", False),
]


def veto_absorbed(d, side, asec, usec):
    t_lo = d["t_lo"]
    i0, i1 = asec - t_lo, usec - t_lo
    net = float(d["flow"][i0:i1].sum())
    dpx = float(d["dec"][i1] - d["dec"][i0])
    return (net >= R.VETO_FLOW_MIN and dpx <= 0) if side == "LONG" \
        else (net <= -R.VETO_FLOW_MIN and dpx >= 0)


def first_fill(d, sigs, side, veto, after, before):
    """Walk the signal stream from `after`; return (sig_sec, fill_sec, fill_px) for the first
    signal that actually becomes a FILL.  With the veto on, a signal that is absorbed does not
    fill and the gate must wait for the NEXT signal — that re-wait is part of the arrival cost
    and is exactly what a raw signal-time comparison hides."""
    t_lo = d["t_lo"]
    for (s, which, px, atr, reg) in sigs:
        if s < after or s > before:
            continue
        if not veto:
            return s, s, px
        u = s + R.VETO_SECS
        i1 = u - t_lo
        if i1 >= len(d["dec"]) or np.isnan(d["dec"][i1]):
            continue
        if veto_absorbed(d, side, s, u):
            continue
        return s, u, float(d["dec"][i1])
    return None, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="*", default=DAYS)
    a = ap.parse_args()

    data = {day: R.build_day(day) for day in a.days}
    daylab = {d: R.day_regime_label(data[d]) for d in a.days}
    res = dict(cadence=f"entries {DECISION_MS}ms / exits {EXEC_MS}ms", fee_rt=R.FEE_RT,
               days=daylab, arms={}, sweep={}, arrival={}, kill={}, pop={})

    ARMS = ["slow", "fast", "union", "trend_fast", "trend_union", "trend_only"]

    # ── 1. headline: per-arm, per-gate, per-day sequential book ────────────────
    for arm in ARMS:
        for tag in TAGS:
            per = {}
            for day in a.days:
                tr = simulate(data[day], tag, arm)
                per[day] = agg(tr)
                per[day]["trades"] = [dict(sec=t["sec"], which=t["which"], regime=t["regime"],
                                           entry=t["entry"], pnl=t["pnl"],
                                           res=[l[1] for l in t["lots"]]) for t in tr]
            res["arms"][f"{tag}|{arm}"] = per
        print(f"arm {arm} done", flush=True)

    # ── 2. threshold plateau on the fast trigger (a 2-bar window at the 5-bar
    #      threshold is a different animal, so the threshold must be swept) ────
    for arm in ("fast", "trend_fast", "trend_only", "union"):
        for tag in TAGS:
            rows = []
            for thr in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5):
                per = {d: agg(simulate(data[d], tag, arm, thr=thr)) for d in a.days}
                rows.append(dict(thr=thr, pnl=round(sum(per[d]["pnl"] for d in a.days), 2),
                                 n=sum(per[d]["n"] for d in a.days),
                                 per_day={d: per[d]["pnl"] for d in a.days}))
            res["sweep"][f"{tag}|{arm}"] = rows
        print(f"sweep {arm} done", flush=True)

    # ── 3. slippage stress on every arm ───────────────────────────────────────
    for arm in ARMS:
        for tag in TAGS:
            per = {d: agg(simulate(data[d], tag, arm, slip=1.0)) for d in a.days}
            res["kill"][f"slip1|{tag}|{arm}"] = dict(
                pnl=round(sum(per[d]["pnl"] for d in a.days), 2),
                n=sum(per[d]["n"] for d in a.days))

    # ── 4. signal-quality diagnostic: unblocked populations ───────────────────
    #      Does the net_atr_2 SIGNAL earn on its own, or is any delta just the slot
    #      being occupied at different moments (the error that killed the last study)?
    for arm in ARMS:
        for tag in TAGS:
            tr = []
            for day in a.days:
                tr += simulate(data[day], tag, arm, block=False)
            res["pop"][f"{tag}|{arm}"] = dict(
                n=len(tr), pnl=round(sum(t["pnl"] for t in tr), 2),
                per_tr=round(sum(t["pnl"] for t in tr) / len(tr), 2) if tr else 0.0,
                win=round(100 * sum(1 for t in tr if t["pnl"] > 0) / len(tr), 1) if tr else 0.0)
    print("pop done", flush=True)

    # ── 5. ARRIVAL CENSUS on the two trend days (the headline number) ─────────
    #      Runs are run_census's own definition, reused verbatim from rev3_lagcost.
    import rev3_lagcost as L
    typ, thr_run, runs = L.census_runs()
    arr_rows = []
    for day in a.days:
        d = data[day]
        sig = {}
        for lab, kind, arm, veto in LANES:
            for tag in (TAGS + ["grind_long"]):
                if kind == "grind" and tag != "grind_long":
                    continue
                if kind == "thrust" and tag == "grind_long":
                    continue
                sig[(lab, tag)] = signals(d, tag, arm)
        for start, mv in runs:
            if not (d["t0"] <= start < d["t1"]):
                continue
            side = "LONG" if mv > 0 else "SHORT"
            rec = dict(day=day, start=start,
                       t=dt.datetime.fromtimestamp(start, dt.UTC).strftime("%m-%d %H:%M"),
                       dir="UP" if mv > 0 else "DN", move=round(mv, 1),
                       ceil=round(abs(mv) * R.VPP, 0), lanes={})
            for lab, kind, arm, veto in LANES:
                for tag in (TAGS + ["grind_long"]):
                    if (lab, tag) not in sig:
                        continue
                    if R.GATES[tag]["side"] != side:
                        continue
                    s, fsec, fpx = first_fill(d, sig[(lab, tag)], side, veto,
                                              start - 300, start + 900)
                    rec["lanes"][f"{lab}|{tag}"] = dict(
                        sig=s, fill=fsec, px=fpx,
                        sig_min=round((s - start) / 60.0, 2) if s else None,
                        fill_min=round((fsec - start) / 60.0, 2) if fsec else None)
            if rec["lanes"]:
                arr_rows.append(rec)
    res["arrival"] = dict(typ=typ, thr=thr_run, rows=arr_rows)
    print(f"arrival done: {len(arr_rows)} run rows", flush=True)

    with open(OUT, "w") as f:
        json.dump(res, f)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
