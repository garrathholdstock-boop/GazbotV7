#!/usr/bin/env python3
"""EXHAUSTIVE SPECIFICATION SEARCH over every choice Mesfin (2026) leaves unstated.

Design that makes it affordable:
  * a CELL is a boolean MASK over bars (which bars are signals) x an EXECUTION VARIANT.
  * for each execution variant we precompute ret_all[i] = the net points that variant would
    return if bar i were a signal — for EVERY bar. Scoring a cell is then a masked mean.
  * the SAME-ENTRY CONTROL is closed-form off ret_all restricted to the cell's own sessions.
  * the SEARCH CHARGE re-scores every cell against a session-permuted ret_all, so the whole
    search is repeated under the null at negligible cost, and we can ask what the BEST OF N
    constructions is worth by chance.
"""
from __future__ import annotations
import sys, itertools, numpy as np, pandas as pd, duckdb
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import load_1min, bars, fit_gmm, predict, tstat, splits, REP

F = 1.25
FEATS = ["F1dir", "F2diract", "F3desk", "F4ret", "F5vol", "F6full", "F7raw"]
KS = [3, 4, 5, 6]
LABELS = ["Lret_mid", "Lret_top3", "Lact", "Ldrift"]
SEEDS = [1, 3, 7, 11, 23]


# ───────────────────────── tapes ─────────────────────────
def holdout_1min():
    """NQ Sep-2025 expiry, 2025-06-18 -> 2025-09-11: entirely BEFORE the lake starts.
    NQ and MNQ quote the same index level (only the multiplier differs), so points are
    directly comparable. This period took no part in any fit or any search."""
    f = "/home/alphabot/gazbot7/data/driftlab/NQ_202509.parquet"
    d = duckdb.connect().execute(f"select ts,open,high,low,close,volume from read_parquet('{f}') order by ts").df()
    d["et"] = pd.to_datetime(d.ts, unit="s", utc=True).dt.tz_convert("America/New_York")
    return d


# ───────────────────── feature menu ─────────────────────
def featspec(g, which):
    c = g.close.values.astype(float); hi = g.high.values.astype(float)
    lo = g.low.values.astype(float); v = g.volume.values.astype(float)
    n = len(c); tr = np.maximum(hi - lo, .25)
    atr = np.maximum(pd.Series(tr).rolling(20, min_periods=5).mean().values, 1e-6)
    def ret(k):
        r = np.zeros(n); r[k:] = c[k:] - c[:-k]; return r
    step = np.abs(np.diff(c, prepend=c[0]))
    def er(k):
        p = pd.Series(step).rolling(k, min_periods=2).sum().values
        return np.abs(ret(k)) / np.maximum(p, 1e-6)
    vm = pd.Series(v).rolling(50, min_periods=10).mean().values
    vs = pd.Series(v).rolling(50, min_periods=10).std(ddof=1).values
    vz = (v - vm) / np.maximum(vs, 1e-9)
    M = {
        "F1dir":    [ret(1)/atr, ret(4)/atr, er(4)],
        "F2diract": [ret(1)/atr, ret(4)/atr, er(4), np.log(tr/atr), vz],
        "F3desk":   [ret(4)/atr, ret(8)/atr, er(4), er(8)],
        "F4ret":    [ret(1)/atr, ret(2)/atr, ret(4)/atr],
        "F5vol":    [ret(1)/atr, np.log(tr/atr), vz],
        "F6full":   [ret(1)/atr, ret(4)/atr, er(4), er(8), np.log(tr/atr), vz],
        "F7raw":    [ret(1), ret(4), tr, np.log(np.maximum(v, 1))],
    }
    return np.column_stack(M[which]), atr, vz


def make_map(g, act_arr, drift_arr, st, trmask, K, rule):
    c = g.close.values
    r = np.zeros(len(g)); r[1:] = c[1:] - c[:-1]
    ks = sorted(set(st[trmask & (st >= 0)]))
    if len(ks) < 3:
        return None
    mr = {k: float(np.nanmean(r[trmask & (st == k)])) for k in ks}
    sh = {k: float((trmask & (st == k)).sum()) for k in ks}
    act = {k: float(np.nanmean(act_arr[trmask & (st == k)])) for k in ks}
    dr = {k: float(np.nanmean(drift_arr[trmask & (st == k)])) for k in ks}
    if rule == "Lret_mid":
        o = sorted(ks, key=lambda k: mr[k]); mp = {o[0]: 0, o[-1]: 2}
        for k in o[1:-1]: mp[k] = 1
    elif rule == "Lret_top3":
        top = sorted(ks, key=lambda k: -sh[k])[:3]
        o = sorted(top, key=lambda k: mr[k]); mp = {o[0]: 0, o[1]: 1, o[2]: 2}
    elif rule == "Lact":
        a1 = max(act, key=act.get)
        rest = sorted([k for k in ks if k != a1], key=lambda k: mr[k])
        mp = {rest[0]: 0, a1: 1, rest[-1]: 2}
    elif rule == "Ldrift":
        o = sorted(ks, key=lambda k: dr[k]); mp = {o[0]: 0, o[-1]: 2}
        for k in o[1:-1]: mp[k] = 1
    else:
        raise ValueError(rule)
    return mp


def to_R(st, mp):
    R = np.full(len(st), -1)
    for k, v in mp.items():
        R[st == k] = v
    return R


# ───────────────────── execution variants ─────────────────────
def ret_all_simple(g, hold, delay=0):
    """entry = open of bar i+1+delay, exit = close of bar i+hold+delay. gross - F."""
    sess = g.sess.values; op = g.open.values; cl = g.close.values
    n = len(g); out = np.full(n, np.nan)
    e = np.arange(n) + 1 + delay; x = np.arange(n) + hold + delay
    ok = (x < n) & (e < n)
    idx = np.where(ok)[0]
    good = (sess[e[idx]] == sess[idx]) & (sess[x[idx]] == sess[idx])
    idx = idx[good]
    out[idx] = cl[x[idx]] - op[e[idx]] - F
    return out


def ret_all_pullback(g, atr, atr_ref, hold, mode, life, anchor):
    """LONG limit at close - d. d = 25 (fix) or 25*ATR/ATR_ref (atr). Filled if any of the next
    `life` bars trades <= limit. Exit `hold` bars after the ENTRY bar or the SIGNAL bar."""
    sess = g.sess.values; op = g.open.values; cl = g.close.values; lo = g.low.values
    n = len(g); out = np.full(n, np.nan)
    d = np.full(n, 25.0) if mode == "fix25" else 25.0 * atr / atr_ref
    lim = cl - d
    e = np.full(n, -1)
    for j in range(1, life + 1):
        idx = np.arange(n - j)
        cand = (e[idx] < 0) & (sess[idx + j] == sess[idx]) & (lo[idx + j] <= lim[idx])
        e[idx[cand]] = idx[cand] + j
    ok = e > 0
    idx = np.where(ok)[0]
    base = (e[idx] if anchor == "entry" else idx)
    x = base + hold
    good = (x < n)
    idx = idx[good]; x = x[good]
    same = sess[x] == sess[idx]
    # cap at the session's last bar rather than dropping
    last = pd.Series(np.arange(n)).groupby(g.sess.values).transform("max").values
    x = np.where(same, x, last[idx])
    keep = x > e[idx]
    idx = idx[keep]; x = x[keep]
    px = np.minimum(lim[idx], op[e[idx]])
    out[idx] = cl[x] - px - F
    return out


# ───────────────────── scoring ─────────────────────
def score(mask, ret, sess, sess_codes, nsess):
    m = mask & np.isfinite(ret)
    n = int(m.sum())
    if n < 25:
        return None
    v = ret[m]; sc = sess_codes[m]
    mean = float(v.mean()); t = tstat(v)
    # session-clustered t (the day-block bootstrap's analytic twin)
    dfm = pd.DataFrame({"s": sc, "v": v})
    gsum = dfm.groupby("s").v.sum().values
    k = len(gsum)
    if k > 1:
        se_cl = np.sqrt(((gsum - n * mean / k) ** 2).sum()) / n
        t_cl = mean / se_cl if se_cl > 0 else np.nan
    else:
        t_cl = np.nan
    return n, mean, t, t_cl, sc


def control_closed_form(cell_sess_counts, valid_by_sess_stats, n):
    """same-entry control: k_s draws from session s's own valid bars, same execution."""
    num = 0.0; var = 0.0
    for s, k in cell_sess_counts.items():
        mu, sd, cnt = valid_by_sess_stats.get(s, (np.nan,) * 3)
        if not np.isfinite(mu):
            continue
        num += k * mu; var += k * (sd ** 2)
    cm = num / n; csd = np.sqrt(var) / n
    return cm, csd
