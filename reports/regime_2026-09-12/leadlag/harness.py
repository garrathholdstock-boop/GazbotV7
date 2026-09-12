#!/usr/bin/env python3
"""Shared causal-backtest harness for the 2026-09-12 cross-instrument study.

CAUSALITY CONTRACT (the thing two analyses got wrong yesterday, producing t=8.99):
  * a signal measured over the window ending at bar t may only use closes at or before t;
  * the ENTRY fill is the OPEN of bar t+1  (never the close of t, which is simultaneous with the
    signal's own last observation and, given a lag-0 correlation of 0.45, would book part of the
    contemporaneous co-move as if it were a forecast);
  * the EXIT fill is the OPEN of bar t+1+h.
  * signals never cross a session boundary or a contract roll.

COSTS (this desk's measured numbers, not a paper's):
  MNQ  1.25 pt round turn  ($1.50/RT commission = 0.75pt at $2/pt, + one 0.25pt tick crossed)
  MGC  0.45 pt round turn  ($4.50/RT at $10/pt: 0.30pt spread crossed ONCE = $3.00, + $1.50)
"""
import numpy as np, pandas as pd

FRICTION = {'MNQ': 1.25, 'MGC': 0.45}
DOLLARS  = {'MNQ': 2.0,  'MGC': 10.0}

def rolling_sig(close, sday, k):
    """close[t] - close[t-k], NaN when the window crosses a session boundary. Causal at t."""
    c = pd.Series(close)
    s = pd.Series(sday)
    out = c - c.shift(k)
    out[s.values != s.shift(k).values] = np.nan
    return out.values

def fwd_open(open_, sday, off):
    """open of bar t+off, NaN across session boundary."""
    o = pd.Series(open_); s = pd.Series(sday)
    out = o.shift(-off)
    out[s.values != s.shift(-off).values] = np.nan
    return out.values

def trade_pnl(sig, entry_px, exit_px, inst):
    """signed points net of friction; NaN where anything is missing or sig==0."""
    d = np.sign(sig)
    p = d * (exit_px - entry_px) - FRICTION[inst]
    p[(d == 0) | ~np.isfinite(d) | ~np.isfinite(entry_px) | ~np.isfinite(exit_px)] = np.nan
    return p

def day_block_boot(pnl, sday, n_boot=2000, seed=7):
    """Day-block bootstrap of the MEAN. Resamples whole SESSIONS with replacement, which is the
    only honest CI when entries overlap (h up to 60 min at 1-min spacing)."""
    m = np.isfinite(pnl)
    pnl = pnl[m]; sday = sday[m]
    if len(pnl) < 30: return (np.nan, np.nan, np.nan)
    days, inv = np.unique(sday, return_inverse=True)
    sums = np.bincount(inv, weights=pnl); cnts = np.bincount(inv)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(days), size=(n_boot, len(days)))
    bs = sums[idx].sum(1) / np.maximum(cnts[idx].sum(1), 1)
    return (float(pnl.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))

def shuffled_twin(sig, sday, n_rep=20, seed=11):
    """Within-session permutation of the SIGNAL across minutes.
    Keeps the signal's marginal distribution, the session, the entry population size and the
    holding period identical; destroys only the time alignment between signal and future return.
    Strictly better than the addendum's 5-way label permutation, which also changed the entry
    population. Returns a list of n_rep permuted signal vectors."""
    rng = np.random.default_rng(seed)
    s = pd.Series(sday); out = []
    groups = pd.Series(np.arange(len(sig))).groupby(s.values)
    idx_by_day = [g.values for _, g in groups]
    for _ in range(n_rep):
        perm = np.empty(len(sig)); perm[:] = np.nan
        for ix in idx_by_day:
            v = sig[ix].copy(); rng.shuffle(v); perm[ix] = v
        out.append(perm)
    return out
