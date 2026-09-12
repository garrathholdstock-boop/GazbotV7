"""GF6 — the mechanical gate lab. One trade per episode, a real stop, the full exit matrix.

The map in gf6_mgc_map/us/const works on every minute, so one trending session contributes ~110
overlapping samples of the same event. That is fine for finding WHERE to look and useless for
robustness, because 'strip the best 3 sessions' then removes 330 correlated samples. Here each
firing becomes ONE trade: a position, a stop, an exit, a cooldown.

MECHANICS, and they are deliberately pessimistic:
  entry     the OPEN of the bar AFTER the signal bar   (no left-edge replay)
  slippage  0.10pt = one MGC tick, charged on entry AND exit
  fee       $1.50 per round trip
  stop      S x ATR60, checked against the bar LOW/HIGH, filled at the level
  ties      if a bar touches both the stop and the target, the STOP is taken
  chandelier armed at arm_k x ATR of favourable excursion, then trails trail_k x ATR from the peak
  cap       a hard time cap, flat at the cap bar's close
  cooldown  no re-entry while in a position, and none for `cool` minutes after a flat
"""
from __future__ import annotations
import numpy as np, pandas as pd

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"
VPP, FEE, SLIP = 10.0, 1.50, 0.10          # $/pt, $/round trip, points of slippage PER LEG

def frame(w=30, k=1.0):
    from gf6_mgc_map import load
    d = load()
    d["thr"] = k * d.atr60 * np.sqrt(w / 14)
    d["up"] = d[f"ret{w}"] >= d.thr
    d["dn"] = d[f"ret{w}"] <= -d.thr
    return d

def _exit(o, h, l, c, i, n, side, entry, atr, stop_k, target_r, arm_k, trail_k, cap):
    """Walk the bars forward from i and return (exit_price, bars_held, reason)."""
    stop = entry - side * stop_k * atr
    targ = entry + side * target_r * stop_k * atr if target_r else None
    peak = entry
    armed = False
    end = min(i + cap, n - 1)
    for j in range(i, end + 1):
        hi, lo = h[j], l[j]
        if (side > 0 and lo <= stop) or (side < 0 and hi >= stop):
            # pessimistic tie-break: the stop is checked before the target every bar
            return stop, j - i + 1, ("CHANDELIER" if armed else "STOP")
        if targ is not None and ((side > 0 and hi >= targ) or (side < 0 and lo <= targ)):
            return targ, j - i + 1, "TARGET"
        if arm_k:
            peak = max(peak, hi) if side > 0 else min(peak, lo)
            fav = (peak - entry) * side
            if fav >= arm_k * atr:
                armed = True
            if armed:
                tr = peak - side * trail_k * atr
                stop = max(stop, tr) if side > 0 else min(stop, tr)
    return c[end], end - i + 1, "CAP"


def backtest(d, sess, trig, side, *, stop_k=1.5, target_r=None, arm_k=None, trail_k=None,
             cap=120, cool=30, extra=None):
    rows = []
    for sday, g in d.groupby("sday"):
        g = g.reset_index(drop=True)
        o, h, l, c = g.open.values, g.high.values, g.low.values, g.close.values
        fire = (g.sess.values == sess) & g[trig].values
        if extra is not None:
            fire &= extra(g)
        atr = g.atr60.values
        n = len(g)
        block = -1
        for i in range(n - 2):
            if not fire[i] or i <= block or not np.isfinite(atr[i]) or atr[i] <= 0:
                continue
            e = i + 1                                   # fill at the NEXT bar's open
            entry = o[e]
            xp, held, why = _exit(o, h, l, c, e, n, side, entry, atr[i],
                                  stop_k, target_r, arm_k, trail_k, cap)
            gross = side * (xp - entry) * VPP
            pnl = gross - FEE - 2 * SLIP * VPP
            rows.append(dict(sday=sday, i=i, ts=g.ts.values[i], entry=entry, exitp=xp,
                             held=held, why=why, atr=atr[i], gross=gross, pnl=pnl))
            block = e + held + cool
    return pd.DataFrame(rows)

def summarise(t, label=""):
    if t.empty: return dict(cand=label, n=0)
    by = t.groupby("sday").pnl.sum()
    order = by.sort_values(ascending=False).index
    d = dict(cand=label, n=len(t), days=t.sday.nunique(), net=t.pnl.sum(),
             per=t.pnl.mean(), med=float(t.pnl.median()), win=float((t.pnl > 0).mean()),
             mfe=float(t.gross.max()), worst=float(t.pnl.min()), held=float(t.held.median()))
    v = t.pnl.sort_values()
    d["strip_best1"] = float((t.pnl.sum() - v.iloc[-1]) / (len(v) - 1))
    d["strip_best3"] = float((t.pnl.sum() - v.iloc[-3:].sum()) / (len(v) - 3))
    d["strip_day1"] = float(t[~t.sday.isin(order[:1])].pnl.mean())
    d["strip_day3"] = float(t[~t.sday.isin(order[:3])].pnl.mean())
    return d
