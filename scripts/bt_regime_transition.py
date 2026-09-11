#!/usr/bin/env python3
"""REGIME-TRANSITION ENTRY with a fixed long hold — the operator's tunnel theory, respecified.

The tunnel study refuted the BREAK as a directional forecast (continuation 0.50). This tests
something different: wait until the market has ESTABLISHED a new state, enter in that state's
own direction, and hold while it persists. Mesfin (2026) falsified fourteen OHLCV signal
families on MNQ and found a gross edge ceiling of ~1.5pt against ~2pt friction - but two
signals passed at t=5.83 and t=5.15, and BOTH used regime classification with 60-75 minute
holds rather than single-bar prediction. That is the shape tested here.

★ WHY A LONG HOLD IS THE POINT, not a detail. Friction is paid ONCE per trade. A 1.5pt edge
  cannot clear a 2pt cost in five minutes; the same edge compounding over a persistent state
  for an hour can. The escape is duration, not a better predictor.

★ THE HMM IS FITTED ON TRAIN ONLY and applied unchanged to VALIDATE and TEST. Fitting on all
  the data would relabel history with hindsight - the exact artefact sessionmap.py warns about,
  which once manufactured a z=4-6 finding that did not exist in real time.

★ STATES ARE LABELLED BY THEIR OWN STATISTICS, never by outcome. A state is 'bullish drift'
  because its bars rose, not because trades from it made money.
"""
from __future__ import annotations

import argparse, glob
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
VPP = 2.0
FRICTION_PT = 2.0          # Mesfin's convention: ~$4/micro RT, covers spread+fees+slippage


def tape(bar_min):
    con = duckdb.connect()
    files = sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
    rows = [f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume "
            f"from read_parquet('{f}')" for f in files]
    df = con.execute(f"""
     with a as ({' union all '.join(rows)}),
     t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d from a),
     v as (select d,exp,sum(volume) vv from t group by 1,2),
     fr as (select d,exp from (select *,row_number() over
            (partition by d order by vv desc) rn from v) where rn=1)
     select t.ts,t.open,t.high,t.low,t.close,t.volume
     from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts""").df()
    s = bar_min * 60
    df["bt"] = (df.ts // s) * s
    g = df.groupby("bt").agg(open=("open", "first"), high=("high", "max"),
                             low=("low", "min"), close=("close", "last"),
                             volume=("volume", "sum")).reset_index()
    g["dt"] = pd.to_datetime(g.bt, unit="s", utc=True)
    g["mod"] = g.dt.dt.hour*60 + g.dt.dt.minute
    g["sess"] = (g.dt + pd.Timedelta(hours=2)).dt.date
    return g


def features(g):
    """Features chosen to separate DRIFT from CHOP, not loud from quiet.

    The first cut used log(true range) + volume z and produced pure VOLATILITY states - mean
    returns of -2.17/+1.35 against bar ranges of 56/25 points, i.e. direction was noise inside
    every state. That is the existing tunnel model with extra steps. These features are about
    PERSISTENCE instead: where multi-bar price has actually gone, and how efficiently.
    """
    c = g.close.values
    n = len(c)
    ret4 = np.zeros(n); ret4[4:] = c[4:] - c[:-4]          # 4-bar net move
    ret8 = np.zeros(n); ret8[8:] = c[8:] - c[:-8]          # 8-bar net move
    step = np.abs(np.diff(c, prepend=c[0]))
    path4 = pd.Series(step).rolling(4, min_periods=2).sum().values
    path8 = pd.Series(step).rolling(8, min_periods=2).sum().values
    er4 = np.abs(ret4)/np.maximum(path4, 1e-6)             # efficiency: drifting vs churning
    er8 = np.abs(ret8)/np.maximum(path8, 1e-6)
    atr = pd.Series(np.maximum(g.high.values-g.low.values, .25)).rolling(
        20, min_periods=5).mean().values
    # SIGNED and scale-free: the drift in ATR units, so a state means the same thing at any vol
    d4 = ret4/np.maximum(atr, 1e-6)
    d8 = ret8/np.maximum(atr, 1e-6)
    X = np.column_stack([d4, d8, er4, er8])
    return X


def fit_gmm(X, K, iters=120, seed=7):
    """Diagonal-covariance Gaussian mixture by EM. No sklearn on this box."""
    rng = np.random.default_rng(seed)
    X = X[np.isfinite(X).all(axis=1)]
    mu = X[rng.choice(len(X), K, replace=False)].copy()
    sd = np.tile(X.std(axis=0), (K, 1)) + 1e-6
    w = np.ones(K)/K
    for _ in range(iters):
        lp = np.stack([(-0.5*(((X-mu[k])/sd[k])**2).sum(1)
                        - np.log(sd[k]).sum() + np.log(w[k])) for k in range(K)], 1)
        lp -= lp.max(1, keepdims=True)
        r = np.exp(lp); r /= r.sum(1, keepdims=True) + 1e-300
        nk = r.sum(0) + 1e-9
        mu = (r.T @ X)/nk[:, None]
        sd = np.sqrt(np.maximum((r.T @ (X**2))/nk[:, None] - mu**2, 1e-8))
        w = nk/nk.sum()
    return mu, sd, w


def predict(X, mu, sd, w):
    K = len(w)
    lp = np.stack([(-0.5*(((X-mu[k])/sd[k])**2).sum(1)
                    - np.log(sd[k]).sum() + np.log(w[k])) for k in range(K)], 1)
    out = np.full(len(X), -1)
    ok = np.isfinite(X).all(axis=1)
    out[ok] = lp[ok].argmax(1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bar", type=int, default=15, help="bar size, minutes")
    ap.add_argument("--states", type=int, default=3)
    a = ap.parse_args()
    g = tape(a.bar)
    X = features(g)
    g["state"] = -1
    ss = sorted(g.sess.unique()); n = len(ss)
    TR = set(ss[:int(n*.40)]); VA = set(ss[int(n*.40):int(n*.70)]); TE = set(ss[int(n*.70):])
    tr_mask = g.sess.isin(TR).values & np.isfinite(X).all(axis=1)
    mu, sd, w = fit_gmm(X[tr_mask], a.states)
    g["state"] = predict(X, mu, sd, w)

    # ── label states by their OWN statistics on TRAIN, never by trade outcome ──
    lab = {}
    print(f"HMM/GMM fitted on TRAIN only · {a.states} states · {a.bar}-min bars\n")
    print(f"{'state':>6}{'share':>8}{'mean ret':>11}{'drift8/ATR':>12}{'effic8':>10}  label")
    sub = g[g.sess.isin(TR)]
    ret = np.zeros(len(g)); ret[1:] = g.close.values[1:]-g.close.values[:-1]
    g["ret"] = ret
    for k in range(a.states):
        m = sub[sub.state == k]
        if not len(m):
            continue
        mr = g.loc[m.index, "ret"].mean()
        lab[k] = mr
    order = sorted(lab, key=lambda k: lab[k])
    names = {}
    names[order[0]] = "BEARISH"
    names[order[-1]] = "BULLISH"
    for k in order[1:-1]:
        names[k] = "CHOP"
    for k in range(a.states):
        m = sub[sub.state == k]
        if not len(m):
            continue
        print(f"{k:>6}{100*len(m)/len(sub):>7.0f}%{g.loc[m.index,'ret'].mean():>11.2f}"
              f"{np.nanmean(X[m.index,1]):>11.2f}{np.nanmean(X[m.index,3]):>11.2f}"
              f"  {names[k]}")

    st = g.state.values
    close, op = g.close.values, g.open.values
    sess = g.sess.values
    bars_per_hold = {}
    print(f"\n{'hold':>7}{'clean':>7}" + "".join(f"{p:>22}" for p in ("TRAIN", "VALIDATE", "TEST"))
          + f"{'ALL':>16}")
    print(f"{'':>14}" + "".join(f"{'n':>6}{'net pt':>8}{'t':>8}" for _ in range(3))
          + f"{'net pt':>8}{'win%':>8}")
    for hold in (2, 3, 4, 5, 6, 8):
        for clean in (True, False):
            rec = []
            for i in range(3, len(g)-hold-1):
                if sess[i] != sess[i+hold] or sess[i] != sess[i-2]:
                    continue
                cur, prv = st[i], st[i-1]
                if cur < 0 or prv < 0 or cur == prv:
                    continue
                if names.get(cur) not in ("BULLISH", "BEARISH"):
                    continue
                if names.get(prv) == names.get(cur):
                    continue
                if clean and (st[i-1] == cur or st[i-2] == cur):
                    continue          # no contamination by the target state in the prior 2 bars
                side = 1 if names[cur] == "BULLISH" else -1
                e = op[i+1]
                x = close[i+hold]
                rec.append((sess[i], side*(x-e) - FRICTION_PT))
            if len(rec) < 60:
                continue
            R = pd.DataFrame(rec, columns=["sess", "pt"])
            line = f"{hold*a.bar:>5}m{'  yes' if clean else '   no':>9}"
            for P in (TR, VA, TE):
                s2 = R[R.sess.isin(P)]
                if len(s2) < 15:
                    line += f"{len(s2):>6}{'-':>8}{'-':>8}"; continue
                t = s2.pt.mean()/(s2.pt.std(ddof=1)/np.sqrt(len(s2)))
                line += f"{len(s2):>6}{s2.pt.mean():>8.2f}{t:>8.2f}"
            line += f"{R.pt.mean():>8.2f}{100*(R.pt > 0).mean():>7.0f}%"
            print(line)
    print(f"\n  net points AFTER {FRICTION_PT:g}pt friction · entry = next bar open · "
          f"exit = fixed hold, no target, no stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
