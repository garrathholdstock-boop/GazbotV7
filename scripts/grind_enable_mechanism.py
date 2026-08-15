#!/usr/bin/env python3
"""GRIND — WHICH ENABLE-MECHANISM? (Friday 2026-08-14, Part 2.5 standing lead)

The operator's standing question: what best captures grind's trend-day upside while killing its
chop-churn —
    (a) TREND-DAY-ONLY   (a day-level permission window, decided causally before the day trades)
    (b) ENTRY TREND-CONFIRMATION / VETO   (a per-signal directional confirm inside the gate)
    (c) the "current ER-0.35 floor"

⚠ (c) IS A PHANTOM. `deciders.ER_FLOOR` is `{}` — every ER floor was deleted 2026-08-01, and the
lookup had been broken since the 07-29 dual-slot cutover, so no ER floor has ever blocked a live
grind trade. What is ACTUALLY in force is ATR>=22 (deciders.ATR_FLOOR) plus the router's on/off.
This script therefore scores FOUR arms: the deployed base, (a), (b), (c).

HONEST SHAPE
  · Entries are decided on the 1-min bar exactly as live (gate_grind, slope_min 0.4, fast_slope),
    ATR>=22 applied first (the deployed floor).
  · Exits are repriced TICK-BY-TICK on the real trade ticks, as the LIVE MANAGED two-lot slate:
    Lot A = 2.5R scalp with a 1.0xATR stop, Lot B = loose-then-lock chandelier (3.5 / 6.0R / 0.5)
    with the native 1.0xATR stop. Fee $1.50 per round trip PER LOT ($3.00 for the pair).
  · One position at a time (live behaviour), 180-min hold cap, entry at the first tick after the
    signal bar closes (the bar-label look-ahead trap).
  · Every day-level classifier is built from bars BEFORE the day's first eligible entry, never
    from the day's outcome.

  PYTHONPATH=src:scripts .venv/bin/python scripts/grind_enable_mechanism.py
"""
from __future__ import annotations

import collections
import json
import statistics
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

from gazbot7.deciders import (  # noqa: E402
    Bar,
    Position,
    compute_features,
    exit_chandelier_lock,
    exit_scalp,
    gate_grind,
)
from gazbot7.lake import connect  # noqa: E402

VPP, FEE = 2.0, 1.5          # MNQ $2.00/point · $1.50 per ROUND TRIP per lot
ATR_FLOOR = 22.0             # the deployed grind_long floor (deciders.ATR_FLOOR)
CAP_MIN = 180
SLOPE_MIN, EXT_LO, EXT_HI = 0.4, 0.3, 4.0


def er_of(window):
    cl = [b.close for b in window]
    if len(cl) < 6:
        return 1.0
    tot = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1
    return abs(cl[-1] - cl[0]) / tot


def replay(side, entry_px, atr, ticks):
    """Reprice both live lots tick-by-tick.

    Returns (lotA_pts, lotB_pts, exitA, exitB, mfe_pts, done_ms) where done_ms is when the
    LAST lot closed — the moment the slot is free again (live one-position-at-a-time)."""
    peak = 0.0
    a_done = b_done = None
    a_px = b_px = None
    a_ms = b_ms = None
    for ts, px in ticks:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak:
            peak = fav
        pos = Position(side, entry_px, atr, peak)
        if a_done is None:
            r = exit_scalp(pos, px, target_r=2.5, stop_atr_mult=1.0)
            if r:
                a_done, a_px, a_ms = r, px, ts
        if b_done is None:
            r = (exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
                 or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))
            if r:
                b_done, b_px, b_ms = r, px, ts
        if a_done and b_done:
            break
    last_px, last_ms = ticks[-1][1], ticks[-1][0]
    if a_done is None:
        a_done, a_px, a_ms = "CAP", last_px, last_ms
    if b_done is None:
        b_done, b_px, b_ms = "CAP", last_px, last_ms
    sgn = 1 if side == "LONG" else -1
    return ((a_px - entry_px) * sgn, (b_px - entry_px) * sgn, a_done, b_done, peak,
            max(a_ms, b_ms))


def usd(pts_a, pts_b):
    return (pts_a * VPP - FEE) + (pts_b * VPP - FEE)


def main():
    con = connect()
    print("loading MNQ bars + ticks from the lake …", file=sys.stderr)
    # ★ 1-min bars are built from the 5s stream: the lake's native '1m' rows are V5-only and stop
    # 2026-07-15, while 5s runs to today. Integer division (bar_ts//60) — `(bar_ts/60)*60` is a
    # float NO-OP in DuckDB and silently reads 5s bars as 1m (the 08-07 instrument failure).
    bars = con.execute(
        "SELECT (bar_ts//60)*60 AS m, arg_min(open, bar_ts) o, max(high) h, min(low) l, "
        "arg_max(close, bar_ts) c, sum(volume) v FROM bars "
        "WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1 ORDER BY 1").fetchall()
    tickdays = con.execute(
        "SELECT strftime(to_timestamp(ts_ms/1000),'%Y-%m-%d') d, count(*) FROM ticks "
        "WHERE symbol='MNQ' GROUP BY 1 ORDER BY 1").fetchall()
    tick_days = {d for d, _ in tickdays}
    print(f"bars={len(bars)}  tick-days={len(tick_days)}", file=sys.stderr)

    import datetime as dt
    days: dict[str, list[Bar]] = collections.OrderedDict()
    for ts, o, h, lo, c, v in bars:
        d = dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        days.setdefault(d, []).append(Bar(ts, o, h, lo, c, v))

    trades = []
    for d, bs in days.items():
        if d not in tick_days:
            continue
        t0, t1 = bs[0].ts * 1000, (bs[-1].ts + CAP_MIN * 60) * 1000
        ticks_all = con.execute(
            "SELECT ts_ms, price FROM ticks WHERE symbol='MNQ' AND ts_ms>=? AND ts_ms<=? ORDER BY ts_ms",
            [t0, t1]).fetchall()
        if len(ticks_all) < 100:
            continue
        tms = [t[0] for t in ticks_all]
        import bisect
        next_ok = 0
        for i in range(len(bs)):
            w = bs[max(0, i - 59):i + 1]
            if len(w) < 20:
                continue
            f = compute_features(w)
            e = gate_grind(f, tape_net=0.0, slope_min=SLOPE_MIN, ext_lo=EXT_LO,
                           ext_hi=EXT_HI, fast_slope=True)
            if e is None or e.side != "LONG":
                continue
            if f.atr < ATR_FLOOR:
                continue
            dms = (bs[i].ts + 60) * 1000
            if dms <= next_ok:
                continue
            j = bisect.bisect_right(tms, dms)
            k = bisect.bisect_right(tms, dms + CAP_MIN * 60000)
            seg = ticks_all[j:k]
            if len(seg) < 5:
                continue
            epx = seg[0][1]
            pa, pb, xa, xb, mfe, done_ms = replay("LONG", epx, f.atr, seg[1:])
            w30 = bs[max(0, i - 30):i + 1]
            w15 = bs[max(0, i - 15):i + 1]
            trades.append(dict(
                day=d, ts=bs[i].ts, hour=dt.datetime.utcfromtimestamp(bs[i].ts).hour,
                atr=f.atr, ext=f.ext_atr, slope=f.vwap_slope_fast, slope60=f.vwap_slope_atr,
                er30=er_of(w30), er15=er_of(w15),
                net30=bs[i].close - w30[0].close, net15=bs[i].close - w15[0].close,
                hi60=max(b.high for b in w), lo60=min(b.low for b in w), px=bs[i].close,
                pa=pa, pb=pb, xa=xa, xb=xb, mfe_r=mfe / f.atr if f.atr else 0.0,
                usd=usd(pa, pb)))
            next_ok = done_ms      # one position at a time: blocked until the LAST lot closes
        print(f"  {d}: {sum(1 for t in trades if t['day']==d)} grind fires", file=sys.stderr)

    json.dump(trades, open("/tmp/grind_trades.json", "w"))
    print(f"\nTOTAL grind_long fires (ATR>={ATR_FLOOR}): {len(trades)}  over "
          f"{len({t['day'] for t in trades})} tick-days")
    net = sum(t["usd"] for t in trades)
    print(f"BASE (deployed: ATR>=22, no ER floor, no confirm): net ${net:,.2f}")


if __name__ == "__main__":
    main()
