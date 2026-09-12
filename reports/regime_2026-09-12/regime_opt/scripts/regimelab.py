#!/usr/bin/env python3
"""regimelab — one audited implementation of the regime-transition backtest.

Everything in this study goes through here so a bug is a bug in one place.

CONTRACT (the method rules from the brief, enforced in code, not in prose):
  * fit_gmm() is only ever handed TRAIN rows. predict() is applied unchanged to VAL/TEST.
  * feature standardisation uses TRAIN mean/sd only.
  * states are named from their own TRAIN feature statistics (mean signed drift), never from
    trade outcome.
  * entry price is ALWAYS open[i+1] - the bar AFTER the bar whose close revealed the state.
  * every rolling statistic is trailing; nothing at bar i uses data after bar i.
  * a trade is only taken if its whole hold fits inside the same CME session (known at entry).
"""
from __future__ import annotations
import numpy as np, pandas as pd, duckdb

GB = "/home/alphabot/gazbot7"
ART = f"{GB}/reports/regime_2026-09-12/regime_opt"
TAPE = f"{ART}/mnq_1min_front.parquet"
VPP = 2.0          # $ per MNQ point
FRICTIONS = (0.75, 1.00, 1.25, 1.50, 2.00)

# ───────────────────────────────── tape ─────────────────────────────────

def load_bars(bar_min: int) -> pd.DataFrame:
    con = duckdb.connect()
    s = bar_min * 60
    g = con.execute(f"""
      select ts - (ts % {s}) as bt,           -- integer floor; DuckDB '/' is FLOAT and ::bigint ROUNDS
             first(open order by ts) as "open", max(high) as high, min(low) as low,
             last(close order by ts) as "close", sum(volume) as volume, count(*) as nmin
      from read_parquet('{TAPE}') group by 1 order by 1""").df()
    con.close()
    g["dt"] = pd.to_datetime(g.bt, unit="s", utc=True)
    g["mod"] = g.dt.dt.hour * 60 + g.dt.dt.minute          # minutes past 00:00 UTC
    # CME session 22:00Z -> 21:00Z. +2h puts 22:00Z into the next calendar day.
    g["sess"] = (g.dt + pd.Timedelta(hours=2)).dt.date
    return g

# ─────────────────────────────── features ───────────────────────────────
# Every one of these is causal at bar i (trailing windows only).

def _atr(g, win=20):
    tr = np.maximum(g.high.values - g.low.values, 0.25)
    return pd.Series(tr).rolling(win, min_periods=5).mean().values

def build_features(g: pd.DataFrame, names: tuple[str, ...]):
    c = g.close.values; n = len(c)
    atr = _atr(g)
    out, cols = {}, []
    step = np.abs(np.diff(c, prepend=c[0]))
    for L in (2, 4, 8, 12, 16):
        r = np.full(n, np.nan); r[L:] = c[L:] - c[:-L]
        path = pd.Series(step).rolling(L, min_periods=max(2, L // 2)).sum().values
        out[f"d{L}"] = r / np.maximum(atr, 1e-6)                 # signed drift in ATR units
        out[f"er{L}"] = np.abs(r) / np.maximum(path, 1e-6)       # efficiency ratio
    ret1 = np.full(n, np.nan); ret1[1:] = c[1:] - c[:-1]
    rv_s = pd.Series(ret1).rolling(6, min_periods=3).std().values
    rv_l = pd.Series(ret1).rolling(24, min_periods=8).std().values
    out["vr"] = np.log(np.maximum(rv_s, 1e-6) / np.maximum(rv_l, 1e-6))   # vol ratio short/long
    v = g.volume.values.astype(float)
    vm = pd.Series(v).rolling(48, min_periods=12).mean().values
    vs = pd.Series(v).rolling(48, min_periods=12).std().values
    out["vz"] = (v - vm) / np.maximum(vs, 1e-6)                  # volume z-score
    # position in the session range SO FAR (causal cumulative extremes within the session)
    df = pd.DataFrame({"sess": g.sess.values, "h": g.high.values, "l": g.low.values, "c": c})
    hi = df.groupby("sess").h.cummax().values
    lo = df.groupby("sess").l.cummin().values
    out["sp"] = 2 * (c - lo) / np.maximum(hi - lo, 1e-6) - 1.0   # -1 at session low, +1 at high
    out["atr"] = atr
    X = np.column_stack([out[k] for k in names])
    return X, out

FEATURE_SETS = {
    "base":     ("d4", "d8", "er4", "er8"),                      # the incumbent
    "drift":    ("d4", "d8"),
    "drift3":   ("d2", "d4", "d8"),
    "long":     ("d8", "d16", "er8", "er16"),
    "base_vol": ("d4", "d8", "er4", "er8", "vr"),
    "base_vz":  ("d4", "d8", "er4", "er8", "vz"),
    "base_sp":  ("d4", "d8", "er4", "er8", "sp"),
    "full":     ("d4", "d8", "er4", "er8", "vr", "vz", "sp"),
}

# ──────────────────────────────── the GMM ────────────────────────────────

def fit_gmm(X, K, iters=200, seeds=(7, 13, 29, 101), tol=1e-7):
    """Diagonal-covariance Gaussian mixture by EM; best of several starts by log-likelihood."""
    X = X[np.isfinite(X).all(axis=1)]
    best = None
    for seed in seeds:
        rng = np.random.default_rng(seed)
        mu = X[rng.choice(len(X), K, replace=False)].copy()
        sd = np.tile(X.std(axis=0), (K, 1)) + 1e-6
        w = np.ones(K) / K
        prev = -np.inf
        for _ in range(iters):
            lp = np.stack([(-0.5 * (((X - mu[k]) / sd[k]) ** 2).sum(1)
                            - np.log(sd[k]).sum() + np.log(w[k])) for k in range(K)], 1)
            m = lp.max(1, keepdims=True)
            ll = float((m[:, 0] + np.log(np.exp(lp - m).sum(1))).sum())
            r = np.exp(lp - m); r /= r.sum(1, keepdims=True) + 1e-300
            nk = r.sum(0) + 1e-9
            mu = (r.T @ X) / nk[:, None]
            sd = np.sqrt(np.maximum((r.T @ (X ** 2)) / nk[:, None] - mu ** 2, 1e-8))
            w = nk / nk.sum()
            if abs(ll - prev) < tol * abs(prev):
                break
            prev = ll
        if best is None or ll > best[0]:
            best = (ll, mu, sd, w)
    return best[1], best[2], best[3]

def predict(X, mu, sd, w):
    K = len(w)
    lp = np.stack([(-0.5 * (((X - mu[k]) / sd[k]) ** 2).sum(1)
                    - np.log(sd[k]).sum() + np.log(w[k])) for k in range(K)], 1)
    out = np.full(len(X), -1)
    ok = np.isfinite(X).all(axis=1)
    out[ok] = lp[ok].argmax(1)
    return out

# ───────────────────────── the fitted model object ─────────────────────────

class Model:
    """One (bar, states, features) fit. TRAIN-only, then frozen."""

    def __init__(self, bar, K, fset, split=(0.40, 0.30), nside=1, g=None):
        self.bar, self.K, self.fset, self.nside = bar, K, fset, nside
        self.g = load_bars(bar) if g is None else g
        g = self.g
        self.X_raw, self.feat = build_features(g, FEATURE_SETS[fset])
        ss = sorted(g.sess.unique()); n = len(ss)
        i1, i2 = int(n * split[0]), int(n * (split[0] + split[1]))
        self.TR, self.VA, self.TE = set(ss[:i1]), set(ss[i1:i2]), set(ss[i2:])
        self.periods = {"TRAIN": self.TR, "VALIDATE": self.VA, "TEST": self.TE}
        ok = np.isfinite(self.X_raw).all(axis=1)
        trm = g.sess.isin(self.TR).values & ok
        self.mu_z = self.X_raw[trm].mean(0); self.sd_z = self.X_raw[trm].std(0) + 1e-9
        Z = (self.X_raw - self.mu_z) / self.sd_z                  # TRAIN-only standardisation
        self.mu, self.sd, self.w = fit_gmm(Z[trm], K)
        self.state = predict(Z, self.mu, self.sd, self.w)
        # ── name the states from their OWN TRAIN feature statistics (mean signed drift) ──
        dcol = FEATURE_SETS[fset].index("d8") if "d8" in FEATURE_SETS[fset] else 0
        d = self.X_raw[:, dcol]
        stats = {}
        for k in range(K):
            m = trm & (self.state == k)
            stats[k] = (np.nanmean(d[m]) if m.sum() else 0.0, int(m.sum()))
        self.stats = stats
        order = sorted(range(K), key=lambda k: stats[k][0])
        self.name = {k: "CHOP" for k in range(K)}
        for k in order[:nside]:
            self.name[k] = "BEARISH"
        for k in order[-nside:]:
            self.name[k] = "BULLISH"
        self.lab = np.array([self.name.get(s, "NA") if s >= 0 else "NA" for s in self.state])
        self.sign = np.where(self.lab == "BULLISH", 1, np.where(self.lab == "BEARISH", -1, 0))
        # rolling causal Markov transition probability P(prev -> cur), 200 bars of history
        self.tp = self._markov(200)

    def _markov(self, win):
        st = self.state; n = len(st)
        tp = np.full(n, np.nan)
        from collections import deque
        dq = deque()
        cnt = {}
        for i in range(1, n):
            if st[i] >= 0 and st[i - 1] >= 0:
                # probability computed from history STRICTLY BEFORE i
                a, b = st[i - 1], st[i]
                tot = sum(v for (x, _), v in cnt.items() if x == a)
                tp[i] = (cnt.get((a, b), 0) / tot) if tot else np.nan
                dq.append((a, b)); cnt[(a, b)] = cnt.get((a, b), 0) + 1
                if len(dq) > win:
                    o = dq.popleft(); cnt[o] -= 1
                    if cnt[o] == 0:
                        del cnt[o]
        return tp

    def describe(self):
        g, X = self.g, self.X_raw
        trm = g.sess.isin(self.TR).values
        rows = []
        ret = np.full(len(g), np.nan); ret[1:] = g.close.values[1:] - g.close.values[:-1]
        for k in range(self.K):
            m = trm & (self.state == k)
            if not m.sum():
                continue
            r = {"state": k, "name": self.name[k], "share%": round(100 * m.sum() / trm.sum(), 1),
                 "meanret": round(float(np.nanmean(ret[m])), 3),
                 "persist": round(float(np.mean(self.state[1:][m[1:]] == self.state[:-1][m[1:]])), 3)}
            for j, f in enumerate(FEATURE_SETS[self.fset]):
                r[f] = round(float(np.nanmean(X[m, j])), 3)
            rows.append(r)
        return pd.DataFrame(rows)

# ───────────────────────────── trade generation ─────────────────────────────

def signals(M: Model, clean=2, win=None, vz_min=None, tp_min=None):
    """Indices i where a CLEAN transition into a directional state completes at close[i].

    clean = how many prior bars must be free of the target state (0 disables).
    win   = (lo_min, hi_min) UTC minute-of-day window for the ENTRY bar, inclusive-exclusive.
    """
    st, lab = M.state, M.lab
    n = len(st)
    i = np.arange(2, n)
    cur, prv = st[i], st[i - 1]
    ok = (cur >= 0) & (prv >= 0) & (cur != prv)
    ok &= np.isin(lab[i], ("BULLISH", "BEARISH"))
    ok &= lab[i - 1] != lab[i]
    for b in range(1, clean + 1):
        ok &= st[i - b] != cur
    if win is not None:
        mod = M.g["mod"].values[i]                  # window applies to the SIGNAL bar
        ok &= (mod >= win[0]) & (mod < win[1])
    if vz_min is not None:
        ok &= np.nan_to_num(M.feat["vz"][i], nan=-9) >= vz_min
    if tp_min is not None:
        ok &= np.nan_to_num(M.tp[i], nan=-1) >= tp_min
    return i[ok]

def trades(M: Model, idx, hold, friction=1.25, exit_mode="time", hold_cap=None,
           pull=0.0, pull_bars=2, side_override=None):
    """Build the trade table. ENTRY = open[i+1], ALWAYS. Returns DataFrame(sess,i,side,gross,bars,pt).

    exit_mode 'time'   = close of bar i+hold (fixed hold measured from the signal bar)
              'revert' = close of the first bar whose label differs from the entry label,
                         capped at hold_cap bars.
    A trade is only taken when the whole hold fits inside the same CME session - a condition
    that is KNOWN AT ENTRY, so it is a rule, not hindsight.
    """
    g = M.g
    op, cl, hi, lo = g.open.values, g.close.values, g.high.values, g.low.values
    sess = g.sess.values
    lab = M.lab
    atr = M.feat["atr"]
    n = len(g)
    idx = np.asarray(idx)
    if len(idx) == 0:
        return pd.DataFrame(columns=["sess", "i", "side", "gross", "bars", "pt"])
    side_all = M.sign[idx] if side_override is None else np.asarray(side_override)

    if exit_mode == "time" and pull == 0:                      # ── vectorised fast path ──
        ok = (idx + hold < n) & (idx + 1 < n)
        i2 = idx[ok]; sd2 = side_all[ok]
        ok2 = sess[i2] == sess[i2 + hold]
        i2 = i2[ok2]; sd2 = sd2[ok2]
        ok3 = sd2 != 0
        i2 = i2[ok3]; sd2 = sd2[ok3]
        if len(i2) == 0:
            return pd.DataFrame(columns=["sess", "i", "side", "gross", "bars", "pt"])
        gross = sd2 * (cl[i2 + hold] - op[i2 + 1])
        T = pd.DataFrame({"sess": sess[i2], "i": i2, "side": sd2,
                          "gross": gross, "bars": hold})
        T["pt"] = T.gross - friction
        return T

    cap = hold if exit_mode == "time" else (hold_cap or hold)
    rec = []
    for k, i in enumerate(idx):
        if i + cap + 1 >= n or sess[i] != sess[i + cap]:
            continue
        side = int(side_all[k])
        if side == 0:
            continue
        e = i + 1
        px = op[e]
        if pull > 0:                                 # ATR-scaled pullback limit; may never fill
            lim = px - side * pull * atr[i]
            filled = False
            for j in range(e, min(e + pull_bars + 1, n)):
                if sess[j] != sess[i]:
                    break
                if (side > 0 and lo[j] <= lim) or (side < 0 and hi[j] >= lim):
                    filled = True; e = j; px = lim; break
            if not filled:
                continue
        if exit_mode == "time":
            xi = i + hold
        else:
            xi = i + cap
            for j in range(i + 1, i + cap + 1):
                if lab[j] != lab[i]:
                    xi = j; break
        if xi >= n or sess[xi] != sess[i] or xi <= e - 1:
            continue
        rec.append((sess[i], int(i), side, float(side * (cl[xi] - px)), int(xi - i)))
    if not rec:
        return pd.DataFrame(columns=["sess", "i", "side", "gross", "bars", "pt"])
    T = pd.DataFrame(rec, columns=["sess", "i", "side", "gross", "bars"])
    T["pt"] = T.gross - friction
    return T


# ─────────────────────────── scoring & controls ───────────────────────────

def period_stats(T, M, friction=None):
    out = {}
    for p, S in M.periods.items():
        s = T[T.sess.isin(S)]
        if len(s) == 0:
            out[p] = dict(n=0, mean=np.nan, t=np.nan); continue
        pt = s.pt.values if friction is None else s.gross.values - friction
        t = pt.mean() / (pt.std(ddof=1) / np.sqrt(len(pt))) if len(pt) > 2 and pt.std() > 0 else np.nan
        out[p] = dict(n=len(pt), mean=float(pt.mean()), t=float(t))
    return out

def day_block_boot(T, friction=None, draws=2000, seed=5, col="pt"):
    """Bootstrap whole SESSIONS with replacement -> CI on mean points per trade."""
    if len(T) == 0:
        return (np.nan, np.nan, np.nan)
    pt = T.pt.values if friction is None else T.gross.values - friction
    d = pd.DataFrame({"s": T.sess.values, "p": pt})
    groups = [v.values for _, v in d.groupby("s").p]
    rng = np.random.default_rng(seed)
    nd = len(groups)
    means = np.empty(draws)
    for b in range(draws):
        sel = rng.integers(0, nd, nd)
        v = np.concatenate([groups[j] for j in sel])
        means[b] = v.mean()
    return float(np.percentile(means, 2.5)), float(pt.mean()), float(np.percentile(means, 97.5))

def sign_control(T, draws=2000, seed=9, friction=None, block=None):
    """H0: the LABEL carries no direction. Same entries, same holds, random sides.

    This is a sign-permutation null on the realised move. Fine-grained (2^n arrangements)
    unlike the 5-way label permutation, and it holds the entry population fixed.
    """
    if len(T) == 0:
        return dict(mean=np.nan, sd=np.nan, p=np.nan)
    mv = (T.gross.values * T.side.values)            # the raw move, direction stripped
    fr = T.pt.values[0] - T.gross.values[0] if friction is None else -friction
    rng = np.random.default_rng(seed)
    n = len(mv)
    obs = T.pt.mean() if friction is None else (T.gross.values - friction).mean()
    ms = np.empty(draws)
    if block == "day":
        # flip whole SESSIONS together: respects intraday clustering of moves
        codes = pd.factorize(T.sess.values)[0]
        nd = codes.max() + 1
        for b in range(draws):
            s = rng.choice((-1, 1), nd)[codes]
            ms[b] = (s * mv).mean() + fr
    else:
        for b in range(draws):
            s = rng.choice((-1, 1), n)
            ms[b] = (s * mv).mean() + fr
    return dict(mean=float(ms.mean()), sd=float(ms.std(ddof=1)),
                p=float((ms >= obs).mean()), obs=float(obs))

def shift_control(M, sig_kw, trd_kw, shifts=(-40, -30, -20, -10, 10, 20, 30, 40)):
    """H0: the state SEQUENCE is not aligned to price. Rotate labels by whole sessions.

    Preserves state persistence, transition frequency and the diurnal shape of entries;
    destroys only the alignment between a state and the prices it was fitted on.
    """
    g = M.g
    ss = sorted(g.sess.unique())
    pos = {s: k for k, s in enumerate(ss)}
    sidx = np.array([pos[s] for s in g.sess.values])
    out = []
    orig_state, orig_lab, orig_sign, orig_tp = M.state, M.lab, M.sign, M.tp
    try:
        for sh in shifts:
            # map each bar to the bar at the same intra-session slot, sh sessions away
            key = pd.DataFrame({"s": sidx, "r": np.arange(len(g))})
            key["rk"] = key.groupby("s").cumcount()
            tgt = key.copy(); tgt["s"] = (tgt.s + sh) % len(ss)
            m = key.merge(tgt, on=["s", "rk"], how="left", suffixes=("", "_t"))
            src = m["r_t"].values
            good = ~np.isnan(src)
            src = np.where(good, np.nan_to_num(src, nan=0).astype(int), 0)
            M.state = np.where(good, orig_state[src], -1)
            M.lab = np.where(good, orig_lab[src], "NA")
            M.sign = np.where(good, orig_sign[src], 0)
            M.tp = np.where(good, orig_tp[src], np.nan)
            idx = signals(M, **sig_kw)
            T = trades(M, idx, **trd_kw)
            if len(T) >= 30:
                out.append((sh, len(T), float(T.pt.mean())))
    finally:
        M.state, M.lab, M.sign, M.tp = orig_state, orig_lab, orig_sign, orig_tp
    return pd.DataFrame(out, columns=["shift_sess", "n", "mean_pt"])

def random_entry_control(M, T, hold, friction=1.25, draws=400, seed=3):
    """Matched-count random entries in the same sessions, random side, same hold+friction."""
    g = M.g
    cl, op, sess = g.close.values, g.open.values, g.sess.values
    bysess = {}
    for s, sub in pd.DataFrame({"s": sess, "i": np.arange(len(g))}).groupby("s"):
        bysess[s] = sub.i.values
    cnt = T.groupby("sess").size().to_dict()
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    for b in range(draws):
        acc = []
        for s, k in cnt.items():
            pool = bysess.get(s)
            if pool is None or len(pool) < hold + 3:
                continue
            cand = pool[1:len(pool) - hold - 1]
            if len(cand) == 0:
                continue
            pick = rng.choice(cand, min(k, len(cand)), replace=False)
            sd = rng.choice((-1, 1), len(pick))
            acc.append(sd * (cl[pick + hold] - op[pick + 1]) - friction)
        means[b] = np.concatenate(acc).mean() if acc else np.nan
    return dict(mean=float(np.nanmean(means)), sd=float(np.nanstd(means, ddof=1)),
                p=float(np.nanmean(means >= T.pt.mean())))

def buy_hold_control(M, hold, friction=1.25):
    """Always-long, every bar, same hold and friction - the passive benchmark."""
    g = M.g
    cl, op, sess = g.close.values, g.open.values, g.sess.values
    i = np.arange(1, len(g) - hold - 1)
    ok = sess[i] == sess[i + hold]
    i = i[ok]
    pt = (cl[i + hold] - op[i + 1]) - friction
    return dict(n=len(pt), mean=float(pt.mean()))
