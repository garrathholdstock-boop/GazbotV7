#!/usr/bin/env python3
"""
OFI-at-seconds sweep on the MNQ L2 archive (Cont/Kukanov/Stoikov Order Flow Imbalance).

Read-only. NOT for commit. Run with /home/alphabot/gazbot7/.venv/bin/python

Tests whether the net CHANGE in best-bid/ask queue size (OFI), aggregated to 1s
buckets and measured over trailing windows of tens of seconds, PREDICTS forward
mid returns on MNQ -- the one variable/horizon the run-catcher null never measured.

Reports, per horizon h and per OFI variant (L1 vs MLOFI 1-3):
  - contemporaneous R2 (same-bucket, the known-strong / possibly-concurrent effect)
  - PREDICTIVE out-of-sample R2 (train 70% / test 30%), Pearson corr, hit-rate
  - tradeable z-score sweep: n, win%, GROSS $/tr, NET $/tr (2pt round-trip cost),
    split long/short, non-overlapping (cooldown = h).

MNQ: $2/point.
"""
import duckdb
import numpy as np
import pandas as pd

DB = "/home/alphabot/gazbot7/data/depth.db"
SYMBOL = "MNQ"
DOLLARS_PER_POINT = 2.0
COST_POINTS = 2.0          # 2-pt round-trip cost
SESSION_GAP_MS = 3000      # inter-snapshot gap above this => new continuous session
HORIZONS = [5, 15, 30, 60] # seconds
Z_THRESHOLDS = [1.0, 1.5, 2.0, 2.5]
Z_WIN_S = 300             # 5-min rolling z-score window (seconds)
TRAIN_FRAC = 0.70

# ----------------------------------------------------------------------------
# 1. Load book (only cols we need: 3 levels of price+size)
# ----------------------------------------------------------------------------
print("Loading MNQ book from depth.db ...", flush=True)
con = duckdb.connect()
con.execute(f"ATTACH '{DB}' AS d (TYPE sqlite, READ_ONLY)")
cols = ["ts_ms",
        "bid1p", "bid1s", "ask1p", "ask1s",
        "bid2p", "bid2s", "ask2p", "ask2s",
        "bid3p", "bid3s", "ask3p", "ask3s"]
df = con.execute(
    f"SELECT {','.join(cols)} FROM d.depth_snap "
    f"WHERE symbol='{SYMBOL}' ORDER BY ts_ms"
).df()
con.close()
print(f"  rows={len(df):,}  span={pd.to_datetime(df.ts_ms.iloc[0], unit='ms')} "
      f"-> {pd.to_datetime(df.ts_ms.iloc[-1], unit='ms')}", flush=True)

# drop rows with a missing/degenerate top of book
df = df[(df.bid1p > 0) & (df.ask1p > 0) & (df.ask1p >= df.bid1p)].reset_index(drop=True)
df["mid"] = (df.bid1p + df.ask1p) / 2.0

# ----------------------------------------------------------------------------
# 2. Per-snapshot OFI  (Cont/Kukanov/Stoikov)
#    e_n = 1{Pb_n>=Pb_n-1}*qb_n - 1{Pb_n<=Pb_n-1}*qb_n-1
#          - 1{Pa_n<=Pa_n-1}*qa_n + 1{Pa_n>=Pa_n-1}*qa_n-1
# ----------------------------------------------------------------------------
def level_ofi(bp, bs, ap, a_s):
    """Vectorised per-snapshot OFI for one book level; index 0 -> NaN."""
    bp0, bp1 = bp.shift(1), bp
    bs0, bs1 = bs.shift(1), bs
    ap0, ap1 = ap.shift(1), ap
    as0, as1 = a_s.shift(1), a_s
    eb = (bp1 >= bp0).astype(float) * bs1 - (bp1 <= bp0).astype(float) * bs0
    ea = -(ap1 <= ap0).astype(float) * as1 + (ap1 >= ap0).astype(float) * as0
    return eb + ea

# session id: break the tape wherever the snapshot gap is large
dt = df.ts_ms.diff()
df["session"] = (dt > SESSION_GAP_MS).cumsum()

# OFI must be computed WITHIN a session (shift across a gap is meaningless)
e1_parts, eml_parts = [], []
for _, g in df.groupby("session", sort=False):
    e1 = level_ofi(g.bid1p, g.bid1s, g.ask1p, g.ask1s)
    e2 = level_ofi(g.bid2p, g.bid2s, g.ask2p, g.ask2s)
    e3 = level_ofi(g.bid3p, g.bid3s, g.ask3p, g.ask3s)
    e1_parts.append(e1)
    eml_parts.append(e1.add(e2, fill_value=0).add(e3, fill_value=0))
df["ofi_l1"] = pd.concat(e1_parts)
df["ofi_ml"] = pd.concat(eml_parts)
# first snapshot of each session has no predecessor -> OFI undefined -> 0 (no info)
df[["ofi_l1", "ofi_ml"]] = df[["ofi_l1", "ofi_ml"]].fillna(0.0)

# ----------------------------------------------------------------------------
# 3. Aggregate to 1-second buckets, per session.
#    OFI_t = sum of per-snapshot e over the bucket ; mid_t = last mid in bucket.
#    Reindex to a dense 1s grid inside each session (missing sec -> OFI 0, mid ffill).
# ----------------------------------------------------------------------------
df["sec"] = (df.ts_ms // 1000).astype(np.int64)

secframes = []
for sess, g in df.groupby("session", sort=False):
    agg = g.groupby("sec").agg(ofi_l1=("ofi_l1", "sum"),
                               ofi_ml=("ofi_ml", "sum"),
                               mid=("mid", "last"))
    full = np.arange(agg.index.min(), agg.index.max() + 1)
    agg = agg.reindex(full)
    agg["ofi_l1"] = agg["ofi_l1"].fillna(0.0)
    agg["ofi_ml"] = agg["ofi_ml"].fillna(0.0)
    agg["mid"] = agg["mid"].ffill()
    agg["session"] = sess
    secframes.append(agg)
S = pd.concat(secframes)
S = S.dropna(subset=["mid"]).reset_index().rename(columns={"index": "sec"})
print(f"  1-second buckets: {len(S):,}   sessions: {S.session.nunique():,}", flush=True)

# ----------------------------------------------------------------------------
# helpers: within-session trailing sum and forward return, edge-honest
# ----------------------------------------------------------------------------
def trailing_sum(col, w):
    """Rolling sum of `col` over the trailing w seconds, within session; NaN near left edge."""
    out = S.groupby("session")[col].transform(
        lambda s: s.rolling(w, min_periods=w).sum())
    return out

def forward_ret(h):
    """mid[t+h] - mid[t] within session; NaN near right edge."""
    fwd = S.groupby("session")["mid"].shift(-h)
    return fwd - S["mid"]

def oos_regression(x, y):
    """OLS y~x, train first 70% test last 30%. Returns (oos_R2, corr_test, hit_test, n_test)."""
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < 200:
        return np.nan, np.nan, np.nan, 0
    k = int(n * TRAIN_FRAC)
    xtr, ytr, xte, yte = x[:k], y[:k], x[k:], y[k:]
    if xtr.std() == 0 or len(xte) < 50:
        return np.nan, np.nan, np.nan, len(xte)
    b1 = np.cov(xtr, ytr, bias=True)[0, 1] / np.var(xtr)
    b0 = ytr.mean() - b1 * xtr.mean()
    pred = b0 + b1 * xte
    ss_res = np.sum((yte - pred) ** 2)
    ss_tot = np.sum((yte - yte.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    corr = np.corrcoef(xte, yte)[0, 1] if xte.std() > 0 and yte.std() > 0 else np.nan
    # directional hit-rate: does sign(feature) match sign(forward return)?
    nz = xte != 0
    hit = np.mean(np.sign(xte[nz]) == np.sign(yte[nz])) if nz.sum() else np.nan
    return r2, corr, hit, len(xte)

def contemp_r2(ofi_col):
    """Same-bucket: price change ACROSS bucket t (mid[t]-mid[t-1]) vs OFI_t (full-sample R2).
    OFI_t aggregates book changes that OCCURRED during bucket t, so the contemporaneous
    price move is the backward diff, not the forward one."""
    y = S.groupby("session")["mid"].diff()   # mid[t]-mid[t-1], within session
    x = S[ofi_col]
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m].values, y[m].values
    if x.std() == 0:
        return np.nan
    c = np.corrcoef(x, y)[0, 1]
    return c ** 2

# ----------------------------------------------------------------------------
# 4. Tradeable z-score sweep (non-overlapping, cooldown = h)
# ----------------------------------------------------------------------------
def zscore(col):
    def _z(s):
        mu = s.rolling(Z_WIN_S, min_periods=Z_WIN_S).mean()
        sd = s.rolling(Z_WIN_S, min_periods=Z_WIN_S).std()
        return (s - mu) / sd
    return S.groupby("session")[col].transform(_z)

def trade_sweep(ofi_col, h, thr):
    """Non-overlapping entries when |z|>thr, hold h sec, exit mid. Returns per-side stats."""
    z = zscore(ofi_col).values
    mid = S["mid"].values
    sess = S["session"].values
    fwd = forward_ret(h).values  # mid[t+h]-mid[t], within-session, NaN at right edge
    n = len(S)
    res = {"long": [], "short": []}
    cooldown_until = -1
    for i in range(n):
        if i < cooldown_until:
            continue
        zi = z[i]
        if not np.isfinite(zi) or abs(zi) < thr:
            continue
        f = fwd[i]
        if not np.isfinite(f):
            continue
        side = "long" if zi > 0 else "short"
        pnl_pts = f if side == "long" else -f
        res[side].append(pnl_pts)
        cooldown_until = i + h
    out = {}
    for side, arr in res.items():
        a = np.array(arr)
        if len(a) == 0:
            out[side] = dict(n=0, win=np.nan, gross=np.nan, net=np.nan)
            continue
        gross = a.mean() * DOLLARS_PER_POINT
        net = (a.mean() - COST_POINTS) * DOLLARS_PER_POINT
        out[side] = dict(n=len(a), win=float((a > 0).mean() * 100),
                         gross=float(gross), net=float(net))
    return out

# ----------------------------------------------------------------------------
# RUN
# ----------------------------------------------------------------------------
variants = [("L1-OFI", "ofi_l1"), ("MLOFI(1-3)", "ofi_ml")]

print("\n" + "=" * 100)
print("CONTEMPORANEOUS vs PREDICTIVE (OOS) -- OFI at seconds horizons, MNQ")
print("=" * 100)
predictive = {}
for vname, vcol in variants:
    cr2 = contemp_r2(vcol)
    print(f"\n### {vname}   contemporaneous R2 (same-bucket 1s) = {cr2:.5f}")
    print(f"{'horizon':>8} | {'predOOS_R2':>11} | {'corr':>8} | {'hit%':>7} | {'n_test':>9}")
    print("-" * 55)
    for h in HORIZONS:
        x = trailing_sum(vcol, h).values      # OFI over [t-h, t]
        y = forward_ret(h).values             # return over [t, t+h]
        r2, corr, hit, nte = oos_regression(x, y)
        predictive[(vname, h)] = (r2, corr, hit)
        hs = f"{hit*100:.1f}" if np.isfinite(hit) else "  nan"
        print(f"{str(h)+'s':>8} | {r2:>11.5f} | {corr:>8.4f} | {hs:>7} | {nte:>9,}")

print("\n" + "=" * 100)
print("TRADEABLE z-score sweep -- non-overlapping (cooldown=h), MNQ $2/pt, cost=2pt=$4/rt")
print("=" * 100)
# collect all cells for strip-best
best_cells = []
for vname, vcol in variants:
    print(f"\n### {vname}")
    print(f"{'h':>4} {'thr':>4} {'side':>6} {'n':>6} {'win%':>6} {'gross$':>9} {'net$':>9}")
    print("-" * 52)
    for h in HORIZONS:
        for thr in Z_THRESHOLDS:
            st = trade_sweep(vcol, h, thr)
            for side in ("long", "short"):
                d = st[side]
                if d["n"] == 0:
                    continue
                print(f"{str(h)+'s':>4} {thr:>4} {side:>6} {d['n']:>6} "
                      f"{d['win']:>6.1f} {d['gross']:>9.2f} {d['net']:>9.2f}")
                best_cells.append((vname, h, thr, side, d))

# strip-best on any positive cell
print("\n" + "=" * 100)
print("STRIP-BEST: positive cells")
print("=" * 100)
pos_gross = [c for c in best_cells if np.isfinite(c[4]["gross"]) and c[4]["gross"] > 0 and c[4]["n"] >= 30]
pos_net = [c for c in best_cells if np.isfinite(c[4]["net"]) and c[4]["net"] > 0 and c[4]["n"] >= 30]
pos_gross.sort(key=lambda c: c[4]["gross"], reverse=True)
pos_net.sort(key=lambda c: c[4]["net"], reverse=True)
print(f"\nGROSS-positive cells (n>=30): {len(pos_gross)}")
for c in pos_gross[:12]:
    v, h, thr, side, d = c
    print(f"  {v:>11} h={h}s thr={thr} {side:>5} n={d['n']:>5} win={d['win']:.1f}% "
          f"gross=${d['gross']:.2f} net=${d['net']:.2f}")
print(f"\nNET-positive cells (n>=30, clears 2pt cost): {len(pos_net)}")
for c in pos_net[:12]:
    v, h, thr, side, d = c
    print(f"  {v:>11} h={h}s thr={thr} {side:>5} n={d['n']:>5} win={d['win']:.1f}% "
          f"gross=${d['gross']:.2f} net=${d['net']:.2f}")

print("\nDONE.")
