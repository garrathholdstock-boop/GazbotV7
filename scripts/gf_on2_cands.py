#!/usr/bin/env python3
"""OPEN-NEWS greenfield 2026-09-11 — the INVENTED entry signals and their tick-honest backtests.

Every candidate is a pure function day -> list of (sod, direction). The engine does the fills.
Nothing here reads a gate, a shadow row or a prior week's conclusion: the cluster says the ignition
happens in 13:00-15:00Z out of a tape with NO flow footprint and NO amplitude expansion, so every
candidate below has to trigger on PRICE STRUCTURE, which is all that is left.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from gf_on2_engine import WIN_LO, WIN_HI, atr_series, er_series


def _ctx(day):
    """Per-minute context for one day: 1m bars, ATR14, ER20, and index helpers."""
    m1 = day['m1']
    if '_atr' not in day:
        day['_atr'] = atr_series(m1, 14)
        day['_er'] = er_series(m1, 20)
        day['_sod'] = m1.sod.values
    return m1, day['_atr'], day['_er'], day['_sod']


# ──────────────────────────────────────────────────────────────────────────────────────
# A — ORB : break of the 13:00->OR_END opening range
# ──────────────────────────────────────────────────────────────────────────────────────
def orb(day, or_end=13*3600+25*60, one_per_day=True, buf_atr=0.0):
    m1, atr, er, sod = _ctx(day)
    h, l, c = m1.h.values, m1.l.values, m1.c.values
    rsel = (sod >= WIN_LO) & (sod < or_end)
    if rsel.sum() < 5:
        return []
    hi, lo = h[rsel].max(), l[rsel].min()
    out = []
    for i in np.where((sod >= or_end) & (sod < WIN_HI))[0]:
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        b = buf_atr*a
        if c[i] > hi + b:
            out.append((int(sod[i])+60, +1))
        elif c[i] < lo - b:
            out.append((int(sod[i])+60, -1))
        if out and one_per_day:
            break
    return out


# ──────────────────────────────────────────────────────────────────────────────────────
# B — COILPOP : compression first, THEN the break.  The cluster's own definition says the
#     5-minute amplitude before ignition was ordinary-or-small, so require a COIL and trade
#     the escape.  `q` = how tight the trailing 15m range must be vs the day so far.
# ──────────────────────────────────────────────────────────────────────────────────────
def coilpop(day, look=20, coil_q=0.35, one_per_day=True, coil_look=15):
    m1, atr, er, sod = _ctx(day)
    h, l, c = m1.h.values, m1.l.values, m1.c.values
    rng15 = pd.Series(h).rolling(coil_look).max().values - pd.Series(l).rolling(coil_look).min().values
    out = []
    for i in np.where((sod >= WIN_LO+look*60) & (sod < WIN_HI))[0]:
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        prior = rng15[max(0, i-120):i]
        prior = prior[np.isfinite(prior)]
        if len(prior) < 30:
            continue
        if rng15[i-1] > np.quantile(prior, coil_q):     # not coiled -> no trade
            continue
        dh, dl = h[i-look:i].max(), l[i-look:i].min()
        if c[i] > dh:
            out.append((int(sod[i])+60, +1))
        elif c[i] < dl:
            out.append((int(sod[i])+60, -1))
        if out and one_per_day:
            break
    return out


# ──────────────────────────────────────────────────────────────────────────────────────
# C — DONCH : the SAME break with the coil requirement REMOVED. This is B's control: if C
#     earns what B earns, the compression filter is decoration.
# ──────────────────────────────────────────────────────────────────────────────────────
def donch(day, look=20, one_per_day=True):
    return coilpop(day, look=look, coil_q=1.01, one_per_day=one_per_day)


# ──────────────────────────────────────────────────────────────────────────────────────
# D — CLOCK : NO SIGNAL AT ALL. Enter at a fixed second-of-day in the direction of the
#     preceding 5 minutes. The mandatory control — if the clock alone books the money, every
#     candidate above is a clock with extra steps.
# ──────────────────────────────────────────────────────────────────────────────────────
def clockmom(day, at=13*3600+30*60, look=5, sign=+1):
    m1, atr, er, sod = _ctx(day)
    c = m1.c.values
    i = int(np.searchsorted(sod, at, 'left'))
    if i <= look or i >= len(sod) or sod[i] >= WIN_HI:
        return []
    mv = c[i] - c[i-look]
    if mv == 0:
        return []
    return [(int(at), sign*(1 if mv > 0 else -1))]


# ──────────────────────────────────────────────────────────────────────────────────────
# E — VWAPREC : session VWAP reclaim with a momentum confirm.
# ──────────────────────────────────────────────────────────────────────────────────────
def vwaprec(day, look=3, one_per_day=True):
    m1, atr, er, sod = _ctx(day)
    c, v, h, l = m1.c.values, m1.v.values, m1.h.values, m1.l.values
    tp = (h+l+c)/3.0
    sel = sod >= WIN_LO
    cv = np.cumsum(np.where(sel, tp*v, 0.0)); cvv = np.cumsum(np.where(sel, v, 0.0))
    with np.errstate(invalid='ignore', divide='ignore'):
        vwap = np.where(cvv > 0, cv/cvv, np.nan)
    out = []
    for i in np.where((sod >= WIN_LO+10*60) & (sod < WIN_HI))[0]:
        if not np.isfinite(vwap[i]) or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        if c[i] > vwap[i] and c[i-1] <= vwap[i-1] and c[i] - c[i-look] > 0:
            out.append((int(sod[i])+60, +1))
        elif c[i] < vwap[i] and c[i-1] >= vwap[i-1] and c[i] - c[i-look] < 0:
            out.append((int(sod[i])+60, -1))
        if out and one_per_day:
            break
    return out


# ──────────────────────────────────────────────────────────────────────────────────────
# F — FADE : the counter-hypothesis. The window is quiet by construction, so fade the first
#     push of N x ATR off the 13:00 open and expect it back.
# ──────────────────────────────────────────────────────────────────────────────────────
def fadepush(day, k=1.5, one_per_day=True):
    m1, atr, er, sod = _ctx(day)
    c = m1.c.values
    i0 = int(np.searchsorted(sod, WIN_LO, 'left'))
    if i0 >= len(sod):
        return []
    open_px = c[i0]
    out = []
    for i in np.where((sod >= WIN_LO+5*60) & (sod < WIN_HI))[0]:
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        d = c[i] - open_px
        if abs(d) >= k*atr[i]:
            out.append((int(sod[i])+60, -1 if d > 0 else +1))
            if one_per_day:
                break
    return out


# ──────────────────────────────────────────────────────────────────────────────────────
# G — PDBREAK : break of the PREVIOUS day's 13:00-21:00Z (US session) high/low.
# ──────────────────────────────────────────────────────────────────────────────────────
def pdbreak(day, prev, one_per_day=True):
    m1, atr, er, sod = _ctx(day)
    c = m1.c.values
    if prev is None:
        return []
    pm = prev['m1']
    psel = (pm.sod.values >= 13*3600) & (pm.sod.values < 21*3600)
    if psel.sum() < 60:
        return []
    phi, plo = pm.h.values[psel].max(), pm.l.values[psel].min()
    out = []
    for i in np.where((sod >= WIN_LO) & (sod < WIN_HI))[0]:
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        if c[i] > phi:
            out.append((int(sod[i])+60, +1))
        elif c[i] < plo:
            out.append((int(sod[i])+60, -1))
        if out and one_per_day:
            break
    return out
