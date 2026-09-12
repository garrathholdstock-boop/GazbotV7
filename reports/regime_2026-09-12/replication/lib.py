#!/usr/bin/env python3
"""Shared machinery for the Mesfin (2026) positive-control replication.

★ Every UNSTATED choice in the paper is marked GUESS[n] here and listed in GUESSES.
"""
from __future__ import annotations
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
REP = f"{GB}/reports/regime_2026-09-12/replication"
CANON = f"{REP}/mnq_1min_canon.parquet"
FRICTION = {"paper_2.00pt": 2.00, "desk_1.25pt": 1.25}

GUESSES = {
 "G1": "GMM feature vector — the paper never states it. Used signed drift/ATR (1 and 4 bar), "
       "4-bar efficiency ratio, log(range/ATR) and 50-bar volume z: a DIRECTION axis and an "
       "ACTIVITY axis, the minimum needed to produce states nameable 'Bearish Chop' / "
       "'Active Flow' / 'Bullish Drift'.",
 "G2": "Number of GMM states — unstated. K=3, forced by the paper's own R0/R1/R2 naming.",
 "G3": "Which fitted component is R0/R1/R2 — unstated. Labelled by TRAIN statistics only: "
       "R1='Active Flow' = highest mean activity (range/ATR); of the other two, lower mean "
       "bar return = R0 'Bearish Chop', higher = R2 'Bullish Drift'. Never by outcome.",
 "G4": "Rolling 200-bar Markov transition probability 'to Regime 2' — unstated whether it is "
       "P(1->2) or unconditional P(.->2). Used causal P(1->2) over the trailing 200 bars.",
 "G5": "Volume z-score — unstated whether raw or log volume, and whether the window is "
       "inclusive. Used raw volume, trailing 50 bars INCLUDING the current bar.",
 "G6": "'25-point ATR-scaled pullback' — mechanics entirely unstated. Implemented as a LONG "
       "limit at signal-bar close minus 25 * ATR20/median(ATR20 on TRAIN); fixed-25pt variant "
       "reported as sensitivity.",
 "G7": "Pullback limit lifetime — unstated. Primary: live for the 3 bars after the signal bar; "
       "unfilled = no trade. Sensitivity: live until the horizon.",
 "G8": "'Exit at bar 13' — unstated whether counted from the signal bar or the entry bar. "
       "Primary: 13 bars after the ENTRY bar (=65 min, matching the brief), capped at 16:00 ET.",
 "G9": "Signal A direction — unstated in Sec 5.1, but decision D023 rejects the SHORT confluence "
       "signal, so the surviving one is LONG.",
 "G10": "London B 'clean transition, no R1 contamination in the prior two bars' — primary: "
        "state[i]==R2, state[i-1]==R0, state[i-2]!=R1. Looser variant reported as sensitivity.",
 "G11": "Whether the GMM is fitted on session bars only or the whole tape — unstated. Fitted on "
        "the same session window the signal trades (RTH for A, London for B).",
 "G12": "Walk-forward structure — the paper uses expanding calendar-year windows; this lake is "
        "11 months, so the brief's chronological 40/30/30 session split is used instead.",
}

# ─────────────────────────── tape ───────────────────────────
def load_1min() -> pd.DataFrame:
    df = duckdb.connect().execute(f"select * from read_parquet('{CANON}')").df()
    df["et"] = pd.to_datetime(df.et, utc=True).dt.tz_convert("America/New_York")
    return df


def bars(df1m: pd.DataFrame, minutes: int, lo_min: int, hi_min: int) -> pd.DataFrame:
    """Aggregate to `minutes` bars INSIDE the ET clock window [lo_min, hi_min) and inside one
    ET calendar date.  ★ DST: everything is done on tz-aware America/New_York wall-clock
    minutes, so 03:00-08:30 ET is 03:00-08:30 ET in both EST and EDT."""
    d = df1m.copy()
    d["m"] = d.et.dt.hour * 60 + d.et.dt.minute
    d = d[(d.m >= lo_min) & (d.m < hi_min)].copy()
    d["sess"] = d.et.dt.date
    d["slot"] = ((d.m - lo_min) // minutes).astype(int)
    g = d.groupby(["sess", "slot"]).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"), n=("close", "size"),
        m=("m", "first"), ts=("ts", "first")).reset_index()
    g = g[g.n >= max(1, minutes // 2)].reset_index(drop=True)   # drop stub bars
    g = g.sort_values(["sess", "slot"]).reset_index(drop=True)
    return g


# ─────────────────────── features / GMM ───────────────────────
def features(g: pd.DataFrame, volwin: int = 50, atrwin: int = 20):
    """GUESS[G1]. Causal, scale-free. Rolling stats are reset-free across sessions by design
    (the paper gives no session-reset rule); the first bars of a session therefore inherit the
    tail of the previous session's window, exactly as a rolling indicator would live."""
    c = g.close.values.astype(float)
    o = g.open.values.astype(float)
    hi = g.high.values.astype(float); lo = g.low.values.astype(float)
    n = len(c)
    tr = np.maximum(hi - lo, 0.25)
    atr = pd.Series(tr).rolling(atrwin, min_periods=5).mean().values
    r1 = np.zeros(n); r1[1:] = c[1:] - c[:-1]
    r4 = np.zeros(n); r4[4:] = c[4:] - c[:-4]
    step = np.abs(np.diff(c, prepend=c[0]))
    path4 = pd.Series(step).rolling(4, min_periods=2).sum().values
    er4 = np.abs(r4) / np.maximum(path4, 1e-6)
    v = g.volume.values.astype(float)
    vm = pd.Series(v).rolling(volwin, min_periods=10).mean().values
    vs = pd.Series(v).rolling(volwin, min_periods=10).std(ddof=1).values
    vz = (v - vm) / np.maximum(vs, 1e-9)                      # GUESS[G5]
    X = np.column_stack([
        r1 / np.maximum(atr, 1e-6),          # short signed drift
        r4 / np.maximum(atr, 1e-6),          # medium signed drift
        er4,                                 # efficiency
        np.log(tr / np.maximum(atr, 1e-6)),  # activity (range)
        vz,                                  # activity (volume)
    ])
    return X, atr, vz


def fit_gmm(X, K=3, iters=200, seed=7):
    """Diagonal-covariance Gaussian mixture by EM (no sklearn on this box).
    Standardised internally so no feature dominates the distance."""
    rng = np.random.default_rng(seed)
    X = X[np.isfinite(X).all(axis=1)]
    mx, sx = X.mean(0), X.std(0) + 1e-9
    Z = (X - mx) / sx
    mu = Z[rng.choice(len(Z), K, replace=False)].copy()
    sd = np.tile(Z.std(axis=0), (K, 1)) + 1e-6
    w = np.ones(K) / K
    for _ in range(iters):
        lp = np.stack([(-0.5 * (((Z - mu[k]) / sd[k]) ** 2).sum(1)
                        - np.log(sd[k]).sum() + np.log(w[k])) for k in range(K)], 1)
        lp -= lp.max(1, keepdims=True)
        r = np.exp(lp); r /= r.sum(1, keepdims=True) + 1e-300
        nk = r.sum(0) + 1e-9
        mu = (r.T @ Z) / nk[:, None]
        sd = np.sqrt(np.maximum((r.T @ (Z ** 2)) / nk[:, None] - mu ** 2, 1e-8))
        w = nk / nk.sum()
    return {"mu": mu, "sd": sd, "w": w, "mx": mx, "sx": sx}


def predict(X, M):
    Z = (X - M["mx"]) / M["sx"]
    mu, sd, w = M["mu"], M["sd"], M["w"]
    K = len(w)
    lp = np.stack([(-0.5 * (((Z - mu[k]) / sd[k]) ** 2).sum(1)
                    - np.log(sd[k]).sum() + np.log(w[k])) for k in range(K)], 1)
    out = np.full(len(X), -1)
    ok = np.isfinite(X).all(axis=1)
    out[ok] = lp[ok].argmax(1)
    return out


def name_states(g, X, state, train_mask):
    """GUESS[G3]. Label by TRAIN statistics only — activity picks R1, then mean return
    splits R0 from R2.  Returns {component -> 0|1|2} in the paper's R-numbering."""
    ret = np.zeros(len(g)); ret[1:] = g.close.values[1:] - g.close.values[:-1]
    stats = {}
    for k in sorted(set(state[train_mask & (state >= 0)])):
        m = train_mask & (state == k)
        stats[k] = dict(n=int(m.sum()), share=m.sum() / max(train_mask.sum(), 1),
                        mean_ret=float(np.nanmean(ret[m])),
                        act_range=float(np.nanmean(X[m, 3])),
                        act_vol=float(np.nanmean(X[m, 4])),
                        eff=float(np.nanmean(X[m, 2])),
                        drift4=float(np.nanmean(X[m, 1])))
    act = {k: s["act_range"] + s["act_vol"] for k, s in stats.items()}
    r1 = max(act, key=act.get)                       # 'Active Flow'
    rest = sorted([k for k in stats if k != r1], key=lambda k: stats[k]["mean_ret"])
    mapping = {rest[0]: 0, r1: 1, rest[-1]: 2}       # R0 bearish chop, R1 active flow, R2 bullish
    return mapping, stats


# ─────────────────────── stats helpers ───────────────────────
def tstat(x):
    x = np.asarray(x, float)
    if len(x) < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


def day_block_bootstrap(trades: pd.DataFrame, col="pt", draws=2000, seed=3):
    """Resample SESSIONS with replacement — the addendum's test (c). Returns (lo, hi, p_le_0)."""
    if trades is None or len(trades) == 0:
        return (float("nan"),) * 3
    rng = np.random.default_rng(seed)
    sess = trades.sess.values
    uniq, inv = np.unique(sess, return_inverse=True)
    by = [trades[col].values[inv == i] for i in range(len(uniq))]
    means = np.empty(draws)
    for d in range(draws):
        pick = rng.integers(0, len(uniq), len(uniq))
        vals = np.concatenate([by[i] for i in pick])
        means[d] = vals.mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), float((means <= 0).mean())


def fmt(v, w=8, p=2):
    return f"{'-':>{w}}" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:>{w}.{p}f}"


def splits(sessions):
    ss = sorted(set(sessions)); n = len(ss)
    return (set(ss[:int(n*.40)]), set(ss[int(n*.40):int(n*.70)]), set(ss[int(n*.70):]))
