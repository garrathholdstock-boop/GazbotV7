#!/usr/bin/env python3
"""OPEN-NEWS greenfield 2026-09-11 — the shared TICK-HONEST engine, rebuilt on the FULL parquet lake.

★ COST CONSTANTS ARE ASSERTED AT IMPORT. $1.50 per ROUND TRIP, $2.00 per MNQ point. The two traps
this file exists to make impossible are `FEE, VPP = 5.0, 2.0` and `VPP, FEE = 2.0, 1.5` — which look
identical at a glance and are reversed — plus pricing MNQ with gold's $10 multiplier.

Tape: data/cache_on0911 (built from gazbot7.lake, NOT capture.db which is a 5-day rolling window).
  bars5s.parquet   65 days, full session, 2026-06-19..2026-09-11
  ticks_win.parquet 46 days, 12:00-16:30Z, 30.7M trade ticks
  flow1m.parquet    per-minute net aggressor flow, whole day

simulate() walks REAL TICKS forward one at a time, so a bar that contains both the stop and the
target is never resolved by a "which came first" guess.
"""
from __future__ import annotations
import os, pickle
import numpy as np, pandas as pd

VPP  = 2.0     # MNQ dollars per point        <- MGC is 10.0, never cross them
FEE  = 1.50    # dollars per ROUND TRIP       <- not per side, not $5.00, not $2.00
TICK = 0.25    # MNQ minimum price increment
SLIP = 0.25    # one tick of adverse slippage on entry and on a stop (market orders cross)
assert (VPP, FEE, TICK) == (2.0, 1.50, 0.25), "cost constants tampered with"

C = '/home/alphabot/gazbot7/data/cache_on0911'
PKL = f'{C}/days.pkl'
WIN_LO, WIN_HI = 13*3600, 15*3600      # the OPEN/NEWS clock bucket, seconds-of-day
RUNWAY = 16*3600                        # every trade is flat by 16:00Z


def _m1(g):
    """1-minute bars from the 5s tape (the census's finest common timeframe is 5s; signals read 1m)."""
    m = (g.sod.values // 60)
    df = pd.DataFrame({'m': m, 'o': g.open.values, 'h': g.high.values,
                       'l': g.low.values, 'c': g.close.values, 'v': g.volume.values})
    gr = df.groupby('m', sort=True)
    return pd.DataFrame({'sod': gr['m'].first().values*60, 'o': gr['o'].first().values,
                         'h': gr['h'].max().values, 'l': gr['l'].min().values,
                         'c': gr['c'].last().values, 'v': gr['v'].sum().values})


def load_days(force=False):
    if os.path.exists(PKL) and not force:
        with open(PKL, 'rb') as f:
            return pickle.load(f)
    import duckdb
    con = duckdb.connect(); con.execute("SET memory_limit='2GB'; SET threads=3")
    bars = con.execute(f"SELECT d, sod, open, high, low, close, volume FROM read_parquet('{C}/bars5s.parquet') ORDER BY d, sod").fetchdf()
    days = {}
    for d, g in bars.groupby('d', sort=True):
        days[d] = {'b5': g.reset_index(drop=True), 'm1': _m1(g)}
    tk = con.execute(f"SELECT d, sod, price, size, agg FROM read_parquet('{C}/ticks_win.parquet') ORDER BY d, sod").fetchdf()
    for d, g in tk.groupby('d', sort=True):
        if d in days:
            days[d]['tk_sod'] = g.sod.values.astype(np.int32)
            days[d]['tk_px'] = g.price.values.astype(np.float64)
    for d in days:
        days[d].setdefault('tk_sod', np.zeros(0, np.int32))
        days[d].setdefault('tk_px', np.zeros(0))
    with open(PKL, 'wb') as f:
        pickle.dump(days, f, protocol=4)
    return days


def atr_series(m1, n=14):
    h, l, c = m1.h.values, m1.l.values, m1.c.values
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h-l, np.maximum(np.abs(h-pc), np.abs(l-pc)))
    return pd.Series(tr).rolling(n, min_periods=max(3, n//3)).mean().values


def er_series(m1, n=20):
    """Kaufman efficiency ratio on 1-min closes: |net| / sum|step| over n minutes."""
    c = m1.c.values
    net = np.abs(pd.Series(c).diff(n).values)
    gross = pd.Series(np.abs(np.r_[0, np.diff(c)])).rolling(n).sum().values
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.where(gross > 0, net/gross, np.nan)


def simulate(day, sod, direction, stop_pts, target_pts=None, trail_k=None, atr=None,
             time_stop=None, be_at=None, runway=RUNWAY):
    """Walk REAL TICKS from the first tick at/after `sod`. direction +1 long, -1 short.

    entry  = next tick price + one tick of adverse slippage
    stop   = stop_pts away, filled at the level + one tick adverse (market stop)
    target = target_pts away, filled AT the level (limit, needs a tick at or through)
    trail  = chandelier at trail_k * atr from the best price seen, ratchet only
    exits at `runway` (16:00Z) on the last tick otherwise.
    Returns dict or None if there is no tape.
    """
    ts, px = day['tk_sod'], day['tk_px']
    i0 = np.searchsorted(ts, sod, 'left')
    if i0 >= len(ts):
        return None
    entry = px[i0] + direction*SLIP
    stop = entry - direction*stop_pts
    tgt = entry + direction*target_pts if target_pts else None
    best = entry
    end = np.searchsorted(ts, runway, 'left')
    exit_px, exit_sod, why = None, None, 'RUNWAY'
    for i in range(i0+1, end):
        p = px[i]
        if direction > 0:
            best = max(best, p)
            if trail_k and atr:
                stop = max(stop, best - trail_k*atr)
            if be_at and best - entry >= be_at:
                stop = max(stop, entry)
            if p <= stop:
                exit_px, exit_sod, why = stop - SLIP, ts[i], 'STOP'; break
            if tgt and p >= tgt:
                exit_px, exit_sod, why = tgt, ts[i], 'TARGET'; break
        else:
            best = min(best, p)
            if trail_k and atr:
                stop = min(stop, best + trail_k*atr)
            if be_at and entry - best >= be_at:
                stop = min(stop, entry)
            if p >= stop:
                exit_px, exit_sod, why = stop + SLIP, ts[i], 'STOP'; break
            if tgt and p <= tgt:
                exit_px, exit_sod, why = tgt, ts[i], 'TARGET'; break
        if time_stop and ts[i] - sod >= time_stop:
            exit_px, exit_sod, why = p, ts[i], 'TIME'; break
    if exit_px is None:
        j = min(end, len(ts)) - 1
        if j <= i0:
            return None
        exit_px, exit_sod, why = px[j], ts[j], 'RUNWAY'
    pts = direction*(exit_px - entry)
    mfe = direction*(best - entry)
    return {'d': day.get('_d'), 'sod': int(sod), 'dir': int(direction), 'entry': float(entry),
            'exit': float(exit_px), 'exit_sod': int(exit_sod), 'why': why,
            'pts': float(pts), 'mfe': float(mfe), 'net': float(pts*VPP - FEE),
            'stop_pts': float(stop_pts), 'held_s': int(exit_sod - sod)}


def score(trades):
    if not trades:
        return {'n': 0, 'net': 0.0, 'win': 0.0, 'per': 0.0, 'gross': 0.0, 'pts': 0.0}
    net = [t['net'] for t in trades]
    return {'n': len(trades), 'net': round(sum(net), 2),
            'win': round(100*sum(1 for x in net if x > 0)/len(net), 1),
            'per': round(sum(net)/len(net), 2),
            'gross': round(sum(t['pts'] for t in trades)*VPP, 2),
            'pts': round(sum(t['pts'] for t in trades), 1)}


def fmt(name, s, extra=''):
    return f"{name:<30}n={s['n']:>4}  net=${s['net']:>9,.2f}  win={s['win']:>5.1f}%  $/trade={s['per']:>8.2f}  {extra}"
