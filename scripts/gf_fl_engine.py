#!/usr/bin/env python3
"""FLOW-LED greenfield — the TICK-HONEST simulator every candidate in this section is scored on.

Not a bar backtest: entries, stops, targets and trails are all resolved against the actual TRADE
TICKS from the parquet lake, one tick at a time, so there is never an ambiguity about whether the
stop or the target came first inside a bar.

THE COST MODEL — the one number this desk keeps getting wrong:
    FEE = $1.50 per ROUND TRIP  (not $5, not $2, not $1.50 a side)
    VPP = $2.00 per MNQ point   (MGC would be $10.00 — not used here)
    plus 1 TICK (0.25pt = $0.50) of adverse slippage on every MARKET fill: the entry, the stop and
    the time/trail exit. Limit-style target fills are given the target price exactly but require the
    tape to TRADE THROUGH it.
So a scratch trade costs $1.50 + $1.00 = $2.50 = 1.25 MNQ points. Nothing here is free.

    from gf_fl_engine import load_day_ticks, simulate
    trades = simulate(signals, stop_pt=..., targ_pt=..., max_hold_min=...)
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

FEE = 1.50        # $ per ROUND TRIP  ← the true venue fee
VPP = 2.00        # $ per MNQ point
TICK = 0.25       # MNQ tick size
SLIP = TICK       # 1 tick adverse on every market fill

_CON = None
_CACHE: dict[str, tuple[np.ndarray, np.ndarray]] = {}
# 28 days of MNQ ticks is ~590MB in RAM. The default keeps 3 days (safe for a one-pass run); a sweep
# sets GF_FL_TICK_CACHE=40 so it does not re-read the same day off parquet 60 times.
_KEEP = int(os.environ.get("GF_FL_TICK_CACHE", "3"))


def _con():
    global _CON
    if _CON is None:
        _CON = connect(symbol="MNQ")
    return _CON


def load_day_ticks(day: str, keep: int = 0):
    """(ts_ms, price) for one UTC day, plus the first 90 min of the next (a trade opened at 23:5x
    must be allowed to resolve). Cache is bounded so 28 days never sit in RAM at once."""
    if day in _CACHE:
        return _CACHE[day]
    rows = _con().execute(f"""
        SELECT ts_ms, price FROM ticks
        WHERE ts_ms >= epoch_ms(TIMESTAMP '{day} 00:00:00')
          AND ts_ms <  epoch_ms(TIMESTAMP '{day} 00:00:00' + INTERVAL 25 HOUR + INTERVAL 30 MINUTE)
        ORDER BY ts_ms""").fetchnumpy()
    ts = rows["ts_ms"].astype("int64")
    px = rows["price"].astype("float64")
    if len(_CACHE) >= (keep or _KEEP):
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[day] = (ts, px)
    return ts, px


def simulate(signals, stop_pt, targ_pt=None, max_hold_min=30, trail_pt=None, trail_arm_pt=None,
             be_at=None, cooldown_min=0):
    """signals: iterable of dicts with ts (minute-close epoch), day, dir (+1/-1) and any extra keys
    (carried through onto the trade row for later slicing).

    Rules, exactly:
      ENTRY  first trade tick STRICTLY AFTER ts, at that price + 1 tick against us.
      STOP   first tick at/through entry -/+ stop_pt, filled at the touched TICK price + 1 tick
             against us (so a gap through the stop is charged the gap, not the ideal).
      TARGET first tick at/through entry +/- targ_pt, filled AT the target (limit).
      TRAIL  once open profit >= trail_arm_pt, a trail_pt giveback from the best tick; market fill.
      BE     once open profit >= be_at, the stop moves to entry (+0), market fill.
      TIME   max_hold_min after entry, market fill at the prevailing tick.
    One position at a time; a signal inside an open trade (or its cooldown) is SKIPPED, and the skip
    is counted so no candidate can quietly claim trades it could not have taken.
    """
    out, skipped = [], 0
    busy_until = -1
    for s in sorted(signals, key=lambda r: r["ts"]):
        if s["ts"] <= busy_until:
            skipped += 1
            continue
        # a signal may carry its OWN ATR-scaled stop/target; signals stay in TIME order either way,
        # so the day-tick cache is never asked to jump backwards (grouping by ATR did, and thrashed)
        _stop = float(s.get("stop_pt") or stop_pt)
        _targ = s.get("targ_pt", targ_pt)
        ts, px = load_day_ticks(s["day"])
        i0 = np.searchsorted(ts, (s["ts"] + 60) * 1000, side="left")   # ts is the minute START
        if i0 >= len(ts):
            skipped += 1
            continue
        d = s["dir"]
        entry = px[i0] + d * SLIP
        end_ms = ts[i0] + max_hold_min * 60_000
        i1 = np.searchsorted(ts, end_ms, side="right")
        seg_p = px[i0 + 1:i1]
        seg_t = ts[i0 + 1:i1]
        if len(seg_p) == 0:
            skipped += 1
            continue

        stop = entry - d * _stop
        exit_px = exit_ts = None
        reason = "TIME"
        run_best = np.maximum.accumulate(seg_p) if d > 0 else np.minimum.accumulate(seg_p)
        prof = d * (run_best - entry)                     # best open profit so far, in points

        hit_stop = (seg_p <= stop) if d > 0 else (seg_p >= stop)
        k_stop = int(np.argmax(hit_stop)) if hit_stop.any() else len(seg_p)
        k_targ = len(seg_p)
        if _targ:
            tgt = entry + d * _targ
            hit_t = (seg_p >= tgt) if d > 0 else (seg_p <= tgt)
            k_targ = int(np.argmax(hit_t)) if hit_t.any() else len(seg_p)
        k_trail = len(seg_p)
        if trail_pt:
            armed = prof >= (trail_arm_pt if trail_arm_pt is not None else trail_pt)
            give = d * (run_best - seg_p)                  # giveback from the best
            hit_tr = armed & (give >= trail_pt)
            k_trail = int(np.argmax(hit_tr)) if hit_tr.any() else len(seg_p)
        k_be = len(seg_p)
        if be_at:
            armed = prof >= be_at
            hit_be = armed & ((seg_p <= entry) if d > 0 else (seg_p >= entry))
            k_be = int(np.argmax(hit_be)) if hit_be.any() else len(seg_p)

        k = min(k_stop, k_targ, k_trail, k_be)
        if k >= len(seg_p):
            exit_px, exit_ts, reason = float(seg_p[-1]) - d * SLIP, int(seg_t[-1]), "TIME"
        elif k == k_stop:
            exit_px, exit_ts, reason = float(seg_p[k]) - d * SLIP, int(seg_t[k]), "STOP"
        elif k == k_targ:
            exit_px, exit_ts, reason = float(entry + d * _targ), int(seg_t[k]), "TARGET"
        elif k == k_trail:
            exit_px, exit_ts, reason = float(seg_p[k]) - d * SLIP, int(seg_t[k]), "TRAIL"
        else:
            exit_px, exit_ts, reason = float(seg_p[k]) - d * SLIP, int(seg_t[k]), "BE"

        pts = d * (exit_px - entry)
        row = dict(s)
        row.update(entry=round(float(entry), 2), exit=round(exit_px, 2), pts=round(float(pts), 2),
                   net=round(float(pts) * VPP - FEE, 2), reason=reason,
                   held_min=round((exit_ts - ts[i0]) / 60000, 1),
                   # ⚠ MFE is capped at the EXIT index, not the end of the hold window. Measuring
                   # run_best[-1] counts favourable movement that happened after we were flat — the
                   # desk has been bitten by exactly that before.
                   mfe=round(float(d * (run_best[min(k, len(run_best) - 1)] - entry)), 2))
        out.append(row)
        busy_until = exit_ts // 1000 + cooldown_min * 60
    return out, skipped


def score(trades, label=""):
    if not trades:
        return {"label": label, "n": 0, "net": 0.0, "win_pct": None, "per_trade": None}
    net = np.array([t["net"] for t in trades])
    return {"label": label, "n": len(trades), "net": round(float(net.sum()), 2),
            "win_pct": round(100 * float((net > 0).mean()), 1),
            "per_trade": round(float(net.mean()), 2),
            "median": round(float(np.median(net)), 2),
            "best": round(float(net.max()), 2), "worst": round(float(net.min()), 2),
            "strip3": round(float(np.sort(net)[:-3].sum()), 2) if len(net) > 3 else None,
            "gross_pts": round(float(sum(t["pts"] for t in trades)), 2)}
