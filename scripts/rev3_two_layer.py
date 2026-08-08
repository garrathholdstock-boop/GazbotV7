#!/usr/bin/env python3
"""REV-3 — DOES GRANULAR (SUB-MINUTE) VISIBILITY PAY, AND WHERE?   MNQ · read-only · PAPER

THE FACT THIS RESTS ON (verified upstream, not re-litigated here).  ``agg.MinuteBars.bars()``
returns only COMPLETED minutes; the forming bar ``_cur`` is never exposed.  The 1-minute bar for
[T, T+60) is finalised when the first 5s bar of the NEXT minute folds — the bar [T+60, T+65),
published at T+65.  So the desk's newest datum is up to **65** seconds old (not 59), and the two
gates carrying the 55s absorption-veto fill at **T+120**.
LIVE PROOF (gazbot7.db, 07-27..08-03, entry second-of-minute): abs_veto 56x at :01 + 25x at :02
of 84 fills = exactly T+65+55.  grind clusters :04-:09 (= T+65) and then spreads, because grind is
a STATE gate that re-fires whenever its slot goes flat.  exhaustion / capitulation are spread flat
across all 60 seconds — they read the 20s TICK footprint and the L1 book, never the bar tape, so
they have NO bar lag to save and are structurally out of scope for a forming-bar fix.

WHAT IS BUILT — two layers, gated per (GATE x REGIME), with a stronger fast-layer filter.
  SLOW layer (unchanged) decides WHETHER: completed 1-min bars, the desk exactly as it runs.
  ESCALATION is computed on SLOW DATA ONLY, so the design is not circular:
        (a) ATR14(1m) >= ATR_MIN pt                              [magnitude]
        (b) ATR14 now >= EXP_MULT x ATR14 five minutes ago        [vol EXPANDING]
        (c) last close within BRK_BUF x ATR of the trailing BRK_N-min high (LONG) / low (SHORT)
    Only the side of the break is armed.
  FAST layer decides WHEN: inside an escalated minute the FORMING bar is folded in and the gate is
    re-tested on every 5s bar close.  Same pattern as deciders.NipcTracker — 1-min ATR/ER for
    context, fine bars for the impulse, ticks for the fill.  ATR stays on COMPLETED bars (the
    NipcTracker discipline); the 'partial ATR' variant is measured only to size the hazard.
  ★ NOISE SUPPRESSION SCALED TO THE EXTRA VISIBILITY (the crux).  Looking 12x more often means
    seeing 12x more wiggles, so the fast trigger carries a PROPORTIONALLY STRONGER confirmation
    than the slow one.  Four independent knobs, all swept:
        pers P   the gate's base condition must hold on P CONSECUTIVE 5s reads
        mag  M   the trigger magnitude must clear the slow threshold x M (ATR-normalised already)
        elap E   the forming bar must be at least E seconds old before it is believed
        flow F   net aggressor flow inside the forming minute must AGREE in sign and clear F
    P=1, M=1.0, E=5, F=0 is the crude 60s->5s swap the operator is ruling out; it is included as
    the control so the cost of NOT filtering is on the table.
  GRANULARITY IS GATED PER CELL, not globally: a (gate, regime) cell is either fast-enabled or it
  is not, and every cell is measured on its own with its own n.

METHOD.  gazbot7.cadence asserted: entries at DECISION_MS=1000 (the desk polls once a second and
cannot fill at a level it never observed); stop/target raced at EXEC_MS=250 over 250ms OHLC
buckets so intra-bucket excursions are not deleted.  Scored on the RACE (target BEFORE stop),
never on MFE.  Sequential, one position per (gate, side) slot.  Fee $1.50/round trip, venue truth.
A bucket touching both levels scores STOP (pessimistic tie).  Every number is a CEILING: live
losses on this desk run 1.1-3.1x modelled.

  PYTHONPATH=src ./.venv/bin/python scripts/rev3_two_layer.py --stage all
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pickle
import sys
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import duckdb
import numpy as np

from gazbot7.cadence import DECISION_MS, EXEC_MS, assert_matches_live
from gazbot7.deciders import Bar, _atr, _vwap, efficiency_ratio

assert_matches_live(DECISION_MS, EXEC_MS)   # a harness that quietly disagrees with the desk fails loudly

SCRATCH = "/tmp/claude-0/-root/882eb15b-b9b1-4c08-9348-cd06bd148585/scratchpad/rev3"
VPP = 2.0
FEE_RT = 1.50
TICK = 0.25
LOOKBACK = 60          # RunConfig.bar_lookback
MAX_HOLD_S = 120 * 60  # RunConfig.max_hold_minutes
STOP_NEW_BEFORE_END_S = 15 * 60

DAYS = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03"]

# ── escalation defaults (all SLOW-computable) ─────────────────────────────────────────────
ESC = dict(atr_min=10.0, exp_mult=1.10, exp_lag=5, brk_n=20, brk_buf=0.25)

# ── the live gate configs, lifted verbatim from slot_strategy.tournament_slots ─────────────
GATES = {
    # tag: (kind, side, thresholds..., exit A/B in R)
    "abs_veto_long":  dict(kind="thrust", side="LONG",  thr=1.5, amp=0.0004, a_r=1.0, b_r=1.5, veto=True),
    "abs_veto_short": dict(kind="thrust", side="SHORT", thr=1.5, amp=0.0004, a_r=1.5, b_r=2.5, veto=True),
    "grind_long":     dict(kind="grind",  side="LONG",  slope_min=0.4, ext_lo=0.3, ext_hi=2.0,
                           a_r=2.5, b_r=2.5, veto=False),
    "rgv_short":      dict(kind="rgv",    side="SHORT", ext_min=1.5, turn=0.25, atr_min=20.0,
                           fast_slope=False, flow_min=None, a_r=1.5, b_r=1.5, veto=False),
    "rgv_long":       dict(kind="rgv",    side="LONG",  ext_min=3.0, turn=0.50, atr_min=13.0,
                           fast_slope=True, flow_min=50.0, net30_floor=-125.0,
                           a_r=1.5, b_r=1.5, veto=False),
}
NEAR = 0.70   # escalation clause 2: the SLOW gate is within this fraction of firing on closed bars.
              # Needed so the FADERS get a fair test — a range-break escalation is directionally
              # wrong for a gate whose setup IS an over-extension, so testing faders only through a
              # momentum-shaped trigger would rig the matrix in favour of the operator's prior.
ATR_SPLIT, LO_A_USD, LO_B_R, LO_B_FLOOR_USD = 22.0, 40.0, 1.75, 60.0
VETO_SECS, VETO_MAX_SECS, VETO_FLOW_MIN = 55, 75, 50.0

REGIMES = ["TREND_ALIGNED", "TREND_COUNTER", "WHIPSAW", "CHOP", "DEAD_CHOP"]

# ── the fast-layer confirmation filter ────────────────────────────────────────────────────
CRUDE = dict(pers=1, mag=1.00, elap=5, flow=0.0)      # the flat 60s->5s swap (the control)
BASE = dict(pers=2, mag=1.15, elap=15, flow=0.0)      # the "proportionally stronger" starting point


# ══════════════════════════════════════════════════════════════════════════════════════════
# STAGE 1 — per-day checkpoint table (one row per 5s bar close), cached
# ══════════════════════════════════════════════════════════════════════════════════════════
def paris_window(day: str):
    d = dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return int((d - dt.timedelta(hours=2)).timestamp()), int((d + dt.timedelta(hours=21)).timestamp())


def _load(t0, t1):
    con = duckdb.connect()
    bars = con.execute(f"SELECT bar_ts,open,high,low,close,volume FROM '{SCRATCH}/bars5s.parquet' "
                       f"WHERE bar_ts>=? AND bar_ts<? ORDER BY bar_ts", [t0 - 5 * 3600, t1]).fetchall()
    tk = con.execute(f"SELECT ts_ms,price,size,aggressor FROM '{SCRATCH}/ticks.parquet' "
                     f"WHERE ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
                     [(t0 - 5 * 3600) * 1000, t1 * 1000]).fetchall()
    con.close()
    return bars, tk


def _tick_idx(tk, t_lo, t_hi):
    """1s DECISION snapshots (last print per second = what a 1s poll sees), 250ms EXEC OHLC
    buckets as dense numpy arrays (index = bucket since t_lo), and 1s signed aggressor flow."""
    n_sec = t_hi - t_lo + 2
    dec = np.full(n_sec, np.nan)
    flow = np.zeros(n_sec)
    nb = n_sec * (1000 // EXEC_MS) + 4
    ehi = np.full(nb, np.nan)
    elo = np.full(nb, np.nan)
    for ts, px, sz, agg in tk:
        s = ts // 1000 - t_lo
        if s < 0 or s >= n_sec:
            continue
        dec[s] = px
        if agg == "buy":
            flow[s] += sz
        elif agg == "sell":
            flow[s] -= sz
        k = (ts - t_lo * 1000) // EXEC_MS
        if 0 <= k < nb:
            if np.isnan(ehi[k]) or px > ehi[k]:
                ehi[k] = px
            if np.isnan(elo[k]) or px < elo[k]:
                elo[k] = px
    # carry the last observed print forward for the 1s decision view
    for i in range(1, n_sec):
        if np.isnan(dec[i]):
            dec[i] = dec[i - 1]
    return dec, ehi, elo, flow


def build_day(day: str):
    cache = f"{SCRATCH}/ck_{day}.pkl"
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return pickle.load(f)
    t0, t1 = paris_window(day)
    bars, tk = _load(t0, t1)
    t_lo = t0 - 5 * 3600
    dec, ehi, elo, flow = _tick_idx(tk, t_lo, t1)

    closed: deque = deque(maxlen=LOOKBACK)
    cur = None
    rows = []          # per checkpoint
    mcache = None      # per-minute invariants

    def minute_cache():
        b = list(closed)
        cl = [x.close for x in b]
        trs = []
        for i in range(1, len(b)):
            hl = b[i].high - b[i].low
            trs.append(max(hl, abs(b[i].high - b[i - 1].close), abs(b[i].low - b[i - 1].close))
                       if (b[i].ts - b[i - 1].ts) <= 90 else hl)
        atr = sum(trs[-14:]) / len(trs[-14:]) if trs else 0.0
        atr_prev = _atr(b[:-ESC["exp_lag"]]) if len(b) > ESC["exp_lag"] + 2 else 0.0
        num = sum(((x.high + x.low + x.close) / 3) * x.volume for x in b)
        den = sum(x.volume for x in b)
        h = len(b) // 2
        vw_half = _vwap(b[:h]) if h >= 1 else 0.0
        rec = b[-11:]
        rnum = sum(((x.high + x.low + x.close) / 3) * x.volume for x in rec)
        rden = sum(x.volume for x in rec)
        rec_half = b[-11:-5]
        vwr_half = _vwap(rec_half) if rec_half else 0.0
        w = list(b)[-ESC["brk_n"]:-1]
        er30 = efficiency_ratio(b, 30)
        er15 = efficiency_ratio(b, 15)
        return dict(bars=b, trs=trs, atr=atr, atr_prev=atr_prev, num=num, den=den, vw_half=vw_half,
                    rnum=rnum, rden=rden, vwr_half=vwr_half,
                    hi=max(x.high for x in w) if w else 0.0, lo=min(x.low for x in w) if w else 0.0,
                    er30=er30, er15=er15, net30=cl[-1] - cl[-31] if len(cl) >= 31 else 0.0,
                    c5=cl[-5] if len(cl) >= 5 else cl[0], c2=cl[-2] if len(cl) >= 2 else cl[0],
                    c6=cl[-6] if len(cl) >= 6 else cl[0], c3=cl[-3] if len(cl) >= 3 else cl[0],
                    last=cl[-1], vols=[x.volume for x in b[-5:]],
                    net30w=cl[-1] - cl[-30] if len(cl) >= 30 else 0.0)

    def feats(mc, px, fh, fl, fv, elapsed, tp_v):
        """FAST features with the forming bar folded in.  ATR from COMPLETED bars only."""
        atr = mc["atr"]
        vwap = (mc["num"] + tp_v) / (mc["den"] + fv) if (mc["den"] + fv) > 0 else px
        slope = (vwap - mc["vw_half"]) / atr if atr > 0 else 0.0
        ext = (px - vwap) / atr if atr > 0 else 0.0
        net5 = (px - mc["c5"]) / atr if atr > 0 else 0.0      # forming bar is bars[-1] -> bars[-6]=closed[-5]
        net2 = (px - mc["c2"]) / atr if atr > 0 else 0.0
        rvw = (mc["rnum"] + tp_v) / (mc["rden"] + fv) if (mc["rden"] + fv) > 0 else px
        sf = (rvw - mc["vwr_half"]) / atr if atr > 0 else 0.0
        vn = fv * (60.0 / max(elapsed, 5.0))
        pv = mc["vols"]
        surge = bool(pv) and vn >= 1.5 * (sum(pv) / len(pv))
        # partial-ATR variant: forming bar's own TR enters the ATR window
        tr_f = max(fh - fl, abs(fh - mc["last"]), abs(fl - mc["last"]))
        tp = mc["trs"][-13:] + [tr_f]
        atr_p = sum(tp) / len(tp)
        return dict(price=px, atr=atr, atr_p=atr_p, atr_pct=atr / px if px else 0.0,
                    slope=slope, slope_fast=sf, ext=ext, net5=net5, net2=net2, surge=surge)

    for bar_ts, o, h, l, c, v in bars:
        m = (bar_ts // 60) * 60
        if cur is None or m > cur["min"]:
            if cur is not None:
                closed.append(Bar(cur["min"], cur["o"], cur["h"], cur["l"], cur["c"], cur["v"]))
                mcache = None
            cur = dict(min=m, o=o, h=h, l=l, c=c, v=v)
            just_closed = True
        else:
            cur["h"] = max(cur["h"], h)
            cur["l"] = min(cur["l"], l)
            cur["c"] = c
            cur["v"] += v
            just_closed = False
        u = bar_ts + 5
        if u < t0 or u > t1 or len(closed) < LOOKBACK:
            continue
        if mcache is None:
            mcache = minute_cache()
        mc = mcache
        elapsed = u - cur["min"]
        tp_v = ((cur["h"] + cur["l"] + cur["c"]) / 3) * cur["v"]
        px_tick = dec[u - t_lo]
        if np.isnan(px_tick):
            continue
        ff = feats(mc, cur["c"], cur["h"], cur["l"], cur["v"], elapsed, tp_v)
        # SLOW features = the closed-bar-only read (byte-equivalent to compute_features(bars))
        b = mc["bars"]
        sl_px = mc["last"]
        vwap_s = mc["num"] / mc["den"] if mc["den"] > 0 else sl_px
        atr = mc["atr"]
        rec = b[-12:]
        hh = len(rec) // 2
        slope_fast_s = (_vwap(rec) - _vwap(rec[:hh])) / atr if atr > 0 else 0.0
        pv = [x.volume for x in b[-6:-1]]
        slow = dict(price=sl_px, atr=atr, atr_pct=atr / sl_px if sl_px else 0.0,
                    slope=(vwap_s - mc["vw_half"]) / atr if atr > 0 else 0.0,
                    slope_fast=slope_fast_s,
                    ext=(sl_px - vwap_s) / atr if atr > 0 else 0.0,
                    net5=(sl_px - mc["c6"]) / atr if atr > 0 else 0.0,
                    net2=(sl_px - mc["c3"]) / atr if atr > 0 else 0.0,
                    surge=bool(pv) and b[-1].volume >= 1.5 * (sum(pv) / len(pv)))
        # escalation (SLOW only)
        arm = set()
        if atr >= ESC["atr_min"] and mc["atr_prev"] > 0 and atr >= ESC["exp_mult"] * mc["atr_prev"]:
            if mc["last"] >= mc["hi"] - ESC["brk_buf"] * atr:
                arm.add("LONG")
            if mc["last"] <= mc["lo"] + ESC["brk_buf"] * atr:
                arm.add("SHORT")
        # regime (side-independent part)
        er30, er15, net30w = mc["er30"], mc["er15"], mc["net30w"]
        if er30 >= 0.15 and abs(net30w) >= 30.0:
            base_reg = "TREND_UP" if net30w > 0 else "TREND_DOWN"
        elif atr >= 25.0:
            base_reg = "WHIPSAW"
        elif atr < 18.0 and er15 < 0.35:
            base_reg = "DEAD_CHOP"
        else:
            base_reg = "CHOP"
        # tape_net: trailing-60s net aggressor flow (capture.recent_tape) and forming-minute flow
        i = u - t_lo
        tape_net = float(flow[max(0, i - 60):i].sum())
        form_flow = float(flow[max(0, cur["min"] - t_lo):i].sum())
        rows.append((u, elapsed, just_closed, px_tick, base_reg, tuple(sorted(arm)),
                     atr, mc["atr_prev"], er30, er15, net30w, mc["net30"], tape_net, form_flow,
                     slow, ff))
    data = dict(day=day, t0=t0, t1=t1, t_lo=t_lo, rows=rows, dec=dec, ehi=ehi, elo=elo, flow=flow)
    with open(cache, "wb") as f:
        pickle.dump(data, f, protocol=4)
    return data


# ══════════════════════════════════════════════════════════════════════════════════════════
# STAGE 2 — gate conditions on a feature dict
# ══════════════════════════════════════════════════════════════════════════════════════════
def gate_margin(tag: str, f: dict, tape_net: float, net30: float):
    """(fires_base, margin) for this gate on this feature read.  margin = trigger / threshold,
    so the magnitude filter M is just `margin >= M`.  Mirrors deciders exactly otherwise."""
    g = GATES[tag]
    k = g["kind"]
    if k == "thrust":
        net = f["net5"]
        if f["atr_pct"] < g["amp"] or not f["surge"]:
            return False, 0.0
        if (net > 0) != (g["side"] == "LONG"):
            return False, 0.0
        return abs(net) >= g["thr"], abs(net) / g["thr"]
    if k == "grind":
        if not (g["ext_lo"] <= f["ext"] <= g["ext_hi"]):
            return False, 0.0
        if tape_net < 0.0:
            return False, 0.0
        s = f["slope_fast"]
        if s <= 0:
            return False, 0.0
        return s >= g["slope_min"], s / g["slope_min"]
    if k == "rgv":
        if f["atr_pct"] > 0.09:
            return False, 0.0
        slope = f["slope_fast"] if g["fast_slope"] else f["slope"]
        if abs(slope) > 1.0 or f["atr"] < g["atr_min"]:
            return False, 0.0
        turn = f["net5"]
        if g["side"] == "SHORT":
            if f["ext"] < g["ext_min"] or turn >= 0:
                return False, 0.0
            if g["flow_min"] is not None and tape_net > -g["flow_min"]:
                return False, 0.0
            return -turn >= g["turn"], -turn / g["turn"]
        if f["ext"] > -g["ext_min"] or turn <= 0:
            return False, 0.0
        if g["flow_min"] is not None and tape_net < g["flow_min"]:
            return False, 0.0
        if g.get("net30_floor") is not None and net30 < g["net30_floor"]:
            return False, 0.0
        return turn >= g["turn"], turn / g["turn"]
    return False, 0.0


def regime_for(tag: str, base_reg: str) -> str:
    side = GATES[tag]["side"]
    if base_reg in ("TREND_UP", "TREND_DOWN"):
        aligned = (base_reg == "TREND_UP") == (side == "LONG")
        return "TREND_ALIGNED" if aligned else "TREND_COUNTER"
    return base_reg


# ══════════════════════════════════════════════════════════════════════════════════════════
# STAGE 3 — the race and the sequential sim
# ══════════════════════════════════════════════════════════════════════════════════════════
def race(d, side, entry_px, entry_sec, stop_pt, tgt_pt, end_sec, slip=0.0):
    """250ms OHLC buckets, target-vs-stop ORDERING.  Both in one bucket -> STOP (pessimistic)."""
    t_lo = d["t_lo"]
    k0 = ((entry_sec + 1) - t_lo) * (1000 // EXEC_MS)
    k1 = (end_sec - t_lo) * (1000 // EXEC_MS)
    hi = d["ehi"][k0:k1]
    lo = d["elo"][k0:k1]
    if hi.size == 0:
        return "TIMEOUT", entry_px, end_sec
    if side == "LONG":
        stop, tgt = entry_px - stop_pt, entry_px + tgt_pt
        hs, ht = lo <= stop, hi >= tgt
    else:
        stop, tgt = entry_px + stop_pt, entry_px - tgt_pt
        hs, ht = hi >= stop, lo <= tgt
    hs = np.nan_to_num(hs, nan=False).astype(bool)
    ht = np.nan_to_num(ht, nan=False).astype(bool)
    any_s, any_t = hs.any(), ht.any()
    is_ = int(np.argmax(hs)) if any_s else 10 ** 9
    it = int(np.argmax(ht)) if any_t else 10 ** 9
    if is_ == 10 ** 9 and it == 10 ** 9:
        v = hi[~np.isnan(hi)]
        return "TIMEOUT", float(v[-1]) if v.size else entry_px, end_sec
    if is_ <= it:
        px = stop - slip * TICK if side == "LONG" else stop + slip * TICK
        return "STOP", px, entry_sec + 1 + is_ * EXEC_MS // 1000
    return "TARGET", tgt, entry_sec + 1 + it * EXEC_MS // 1000


def targets_for(tag, atr):
    g = GATES[tag]
    if atr < ATR_SPLIT:      # the 2026-08-02 quiet-tape clip (live for every gate in the file)
        return LO_A_USD / VPP, max(LO_B_R * atr, LO_B_FLOOR_USD / VPP)
    return g["a_r"] * atr, g["b_r"] * atr


def simulate(d, tag, *, fast_cells: set, filt: dict, slow_on=True, slip=0.0,
             atr_mode="slow", use_veto=None, collect=False):
    """One (gate) slot, sequential.  fast_cells = the set of regimes in which the FAST layer is
    allowed to act.  slow_on=False measures the fast layer alone (a diagnostic, never a build)."""
    g = GATES[tag]
    side = g["side"]
    veto = g["veto"] if use_veto is None else use_veto
    t1, t_lo = d["t1"], d["t_lo"]
    stop_new = t1 - STOP_NEW_BEFORE_END_S
    busy_until = -1
    run = 0                    # consecutive fast base-condition reads
    pending = None             # (armed_sec, price, atr, kind) for the 55s veto
    trades, fires = [], []

    def fill(sec, px, atr, kind, elapsed, reg):
        nonlocal busy_until
        entry = px + (slip * TICK if side == "LONG" else -slip * TICK)
        a_pt, b_pt = targets_for(tag, atr)
        end = min(sec + MAX_HOLD_S, t1)
        lots, last = [], sec
        for lab, tgt in (("A", a_pt), ("B", b_pt)):
            r, xp, xs = race(d, side, entry, sec, atr, tgt, end, slip)
            dd = (xp - entry) if side == "LONG" else (entry - xp)
            lots.append((lab, r, round(xp, 2), xs, round(dd * VPP - FEE_RT, 2)))
            last = max(last, xs)
        busy_until = last
        trades.append(dict(sec=sec, kind=kind, elapsed=elapsed, regime=reg, entry=round(entry, 2),
                           atr=round(atr, 2), lots=lots, pnl=round(sum(l[4] for l in lots), 2)))

    for (u, elapsed, just_closed, px_tick, base_reg, arm, atr, atr_prev, er30, er15, net30w,
         net30, tape_net, form_flow, slow, ff) in d["rows"]:
        reg = regime_for(tag, base_reg)
        # ── the 55s absorption veto, faithful to tournament.run ──
        if pending is not None:
            asec, apx, aatr, akind, areg = pending
            age = u - asec
            if age >= VETO_SECS:
                pending = None
                if age <= VETO_MAX_SECS:
                    i0, i1 = asec - t_lo, u - t_lo
                    net = float(d["flow"][i0:i1].sum())
                    dpx = float(d["dec"][i1] - d["dec"][i0])
                    absorbed = (net >= VETO_FLOW_MIN and dpx <= 0) if side == "LONG" \
                        else (net <= -VETO_FLOW_MIN and dpx >= 0)
                    if not absorbed and busy_until < u and u < stop_new:
                        fill(u, float(d["dec"][i1]), aatr, akind, elapsed, areg)
        # ── FAST layer ──
        f = dict(ff)
        if atr_mode == "partial" and ff["atr_p"] > 0:
            s = ff["atr"] / ff["atr_p"]
            f.update(atr=ff["atr_p"], atr_pct=ff["atr_p"] / ff["price"] if ff["price"] else 0.0,
                     slope=ff["slope"] * s, slope_fast=ff["slope_fast"] * s, ext=ff["ext"] * s,
                     net5=ff["net5"] * s, net2=ff["net2"] * s)
        base_fires, margin = gate_margin(tag, f, tape_net, net30)
        run = run + 1 if base_fires else 0
        # ── ESCALATION, computed on SLOW data only (no forming bar anywhere in it) ──
        #   (a) magnitude + (b) vol EXPANDING, and then EITHER (c1) a range break on the closed
        #   bars OR (c2) the slow gate already within NEAR of firing.  (c2) exists so a FADER,
        #   whose setup is an over-extension rather than a break, is not tested through a
        #   momentum-shaped trigger it can never satisfy.
        esc = False
        if atr >= ESC["atr_min"] and atr_prev > 0 and atr >= ESC["exp_mult"] * atr_prev:
            sb0, sm0 = gate_margin(tag, slow, tape_net, net30)
            esc = (side in arm) or (sm0 >= NEAR)
        if (esc and reg in fast_cells and base_fires and busy_until < u and u < stop_new
                and pending is None and elapsed >= filt["elap"] and run >= filt["pers"]
                and margin >= filt["mag"]):
            ok_flow = True
            if filt["flow"] > 0:
                ok_flow = (form_flow >= filt["flow"]) if side == "LONG" else (form_flow <= -filt["flow"])
            if ok_flow:
                if collect:
                    fires.append((u, "fast", px_tick, atr, reg, elapsed))
                fill(u, px_tick, f["atr"], "fast", elapsed, reg)
                continue
        # ── SLOW layer: fires the instant the minute finalises (u == T+65) ──
        if just_closed and slow_on and busy_until < u and u < stop_new and pending is None:
            sb, _ = gate_margin(tag, slow, tape_net, net30)
            if sb:
                if collect:
                    fires.append((u, "slow", px_tick, atr, reg, 65.0))
                if veto:
                    pending = (u, px_tick, atr, "slow", reg)
                else:
                    fill(u, px_tick, atr, "slow", 65.0, reg)
    return trades, fires


# ══════════════════════════════════════════════════════════════════════════════════════════
def agg(trades):
    n = len(trades)
    return dict(n=n, pnl=round(sum(t["pnl"] for t in trades), 2),
                n_fast=sum(1 for t in trades if t["kind"] == "fast"),
                pnl_fast=round(sum(t["pnl"] for t in trades if t["kind"] == "fast"), 2),
                n_slow=sum(1 for t in trades if t["kind"] == "slow"),
                pnl_slow=round(sum(t["pnl"] for t in trades if t["kind"] == "slow"), 2))


def day_regime_label(d):
    rows = d["rows"]
    cl = [r[14]["price"] for r in rows if r[2]]
    if len(cl) < 60:
        return dict(label="?", day_er=0, range_pt=0, net_pt=0)
    path = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1.0
    er = abs(cl[-1] - cl[0]) / path
    rng = max(cl) - min(cl)
    net = cl[-1] - cl[0]
    # DIRECTIONAL EFFICIENCY, not a 1380-close Kaufman ER (which is ~0 on every day by construction):
    # how much of the day's range the day actually WENT.  >= 0.50 = a day that trended.
    de = abs(net) / rng if rng else 0.0
    return dict(label="TREND" if de >= 0.65 else "CHOP", dir_eff=round(de, 3),
                day_er=round(er, 4), range_pt=round(rng, 1), net_pt=round(net, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all")
    ap.add_argument("--days", nargs="*", default=DAYS)
    ap.add_argument("--out", default=f"{SCRATCH}/rev3_results.json")
    a = ap.parse_args()

    data = {}
    for day in a.days:
        data[day] = build_day(day)
        print(f"built {day}: {len(data[day]['rows'])} checkpoints", flush=True)

    res = {"cadence": f"entries {DECISION_MS}ms / exits {EXEC_MS}ms", "fee_rt": FEE_RT,
           "days": {d: day_regime_label(data[d]) for d in a.days}, "stages": {}}

    ALL = set(REGIMES)
    # ── A. headline: baseline vs crude swap vs filtered, fast enabled EVERYWHERE ──
    A = {}
    for tag in GATES:
        for name, cells, filt in (("slow_only", set(), BASE),
                                  ("crude_all", ALL, CRUDE),
                                  ("filtered_all", ALL, BASE)):
            tot = []
            per = {}
            for day in a.days:
                tr, _ = simulate(data[day], tag, fast_cells=cells, filt=filt)
                per[day] = agg(tr)
                tot += tr
            A[f"{tag}|{name}"] = dict(total=agg(tot), per_day=per)
        print(f"A done {tag}", flush=True)
    res["stages"]["A"] = A

    # ── B. the MATRIX: fast enabled in exactly one (gate, regime) cell ──
    B = {}
    for tag in GATES:
        base = {}
        for day in a.days:
            tr, _ = simulate(data[day], tag, fast_cells=set(), filt=BASE)
            base[day] = agg(tr)
        for reg in REGIMES:
            per = {}
            for day in a.days:
                tr, _ = simulate(data[day], tag, fast_cells={reg}, filt=BASE)
                per[day] = agg(tr)
            B[f"{tag}|{reg}"] = dict(
                per_day={d: dict(base=base[d], cell=per[d]) for d in a.days},
                delta=round(sum(per[d]["pnl"] - base[d]["pnl"] for d in a.days), 2),
                n_fast=sum(per[d]["n_fast"] for d in a.days),
                n_base=sum(base[d]["n"] for d in a.days),
                n_cell=sum(per[d]["n"] for d in a.days))
        print(f"B done {tag}", flush=True)
    res["stages"]["B"] = B

    # ── C. filter sweep on every cell that showed promise, plus the two operator priors ──
    C = {}
    grid = [dict(pers=p, mag=m, elap=e, flow=fl)
            for p in (1, 2, 3, 4) for m in (1.0, 1.15, 1.3, 1.5)
            for e in (5, 15, 25, 35) for fl in (0.0, 50.0)]
    sweep_cells = [(tag, reg) for tag in GATES for reg in ("TREND_ALIGNED", "CHOP", "WHIPSAW")]
    for tag, reg in sweep_cells:
        base = {d: agg(simulate(data[d], tag, fast_cells=set(), filt=BASE)[0]) for d in a.days}
        rowsC = []
        for filt in grid:
            per = {d: agg(simulate(data[d], tag, fast_cells={reg}, filt=filt)[0]) for d in a.days}
            rowsC.append(dict(filt=filt,
                              delta=round(sum(per[d]["pnl"] - base[d]["pnl"] for d in a.days), 2),
                              n_fast=sum(per[d]["n_fast"] for d in a.days),
                              per_day={d: round(per[d]["pnl"] - base[d]["pnl"], 2) for d in a.days}))
        C[f"{tag}|{reg}"] = dict(base_total=round(sum(base[d]["pnl"] for d in a.days), 2), rows=rowsC)
        print(f"C done {tag}|{reg}", flush=True)
    res["stages"]["C"] = C

    with open(a.out, "w") as f:
        json.dump(res, f)
    print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
