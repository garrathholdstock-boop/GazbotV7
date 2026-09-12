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
# ★2026-09-12 --friction and --shuffle added. THIS DESK'S MEASURED COST IS NOT MESFIN'S ASSUMPTION:
# $1.50/RT = 0.75pt, plus the 0.25pt tick crossed once on entry = ~1.00-1.25pt, not 2.0. A cell can
# only claim that difference if it ALSO beats its own shuffled twin - the 2026-09-11 control that
# killed the first version of this study (shuffled labels scored the same as the real ones).


def tape(bar_min, source="mnq_backfill"):
    """Minute bars -> bar_min bars. TWO SOURCES, and they are not interchangeable.

    ★2026-09-12 `nq_lake` is the MULTI-REGIME tape: 3,666,547 NQ 1-min bars, 2015-01-02 ->
      2025-07-25, day-partitioned under data/tape/bars/NQ/. It is a continuous series already, so
      there is no front-month pick to make. NQ and MNQ track the same index at the same 0.25 tick,
      so POINTS carry across; DOLLARS do not (NQ $20/pt, MNQ $2/pt) and nothing here prices dollars.
    ⚠ THE PRICE LEVEL MOVES 7x ACROSS THIS TAPE (3,862 -> 23,435). Friction is fixed in points
      (~1.25) but the EDGE scales with level, so a pooled points-P&L silently weights 2024-25 far
      above 2015-16. Every result must be read per era, and the ATR column is the scale-free one.
    """
    con = duckdb.connect()
    if source == "mgc_front":
        # ★ The CORRECTED front-month gold minute tape (rebuilt 2026-09-12). NEVER use
        # data/tape/bars/MGC/backfill_1min.parquet: 22.46% of its bars are a dying contract, a
        # median 30.1 points ($301 a lot) from where gold actually was.
        df = con.execute("""
          select ts, open, high, low, close, volume from read_parquet(
            '/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag/front_MGC_1min.parquet')
          order by ts""").df()
    elif source == "gc_daily":
        # ⚠ DAILY bars, 2000-08-30 -> 2026-09-11. A hold here is HELD OVERNIGHT, which this desk
        # does not do ("NEVER HOLD OVERNIGHT. EVER."). It is run to learn whether the effect exists
        # at a horizon where cost cannot bind, NOT as a candidate.
        df = con.execute("""
          select bar_ts ts, open, high, low, close, volume
          from read_parquet('/home/alphabot/gazbot7/data/tape/bars/GC/*.parquet')
          where timeframe='1day' order by bar_ts""").df()
    elif source == "nq_lake":
        df = con.execute("""
          select bar_ts ts, open, high, low, close, volume
          from read_parquet('/home/alphabot/gazbot7/data/tape/bars/NQ/*.parquet')
          where timeframe='1min' order by bar_ts""").df()
    else:
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
    ap.add_argument("--friction", type=float, default=FRICTION_PT,
                    help="points per round trip. 2.0 = the paper's; ~1.25 = this desk's measured")
    ap.add_argument("--source", default="mnq_backfill", choices=["mnq_backfill", "nq_lake", "mgc_front", "gc_daily"])
    ap.add_argument("--overnight", action="store_true",
                    help="allow a hold to span sessions — ONLY for the daily tape")
    ap.add_argument("--zscore", action="store_true", help="standardise features on TRAIN")
    ap.add_argument("--by-era", action="store_true", help="report per calendar year as well")
    ap.add_argument("--shuffle", type=int, default=0,
                    help="draws of the permuted-label control (0 = skip)")
    a = ap.parse_args()
    g = tape(a.bar, a.source)
    X = features(g)
    Xraw = X.copy()
    g["state"] = -1
    ss = sorted(g.sess.unique()); n = len(ss)
    TR = set(ss[:int(n*.40)]); VA = set(ss[int(n*.40):int(n*.70)]); TE = set(ss[int(n*.70):])
    tr_mask = g.sess.isin(TR).values & np.isfinite(X).all(axis=1)
    if a.zscore:
        # ★2026-09-12 STANDARDISE ON TRAIN ONLY. The raw features are on two scales — signed drift
        # in ATR units (±several) and efficiency ratios in [0,1] — and a diagonal-covariance mixture
        # weights whichever happens to be wider. On 11 months of MNQ that was drift; on 10.5 years of
        # NQ it was EFFICIENCY, which produced perfectly persistent states whose "bullish" and
        # "bearish" both drifted UP. Scaling is not cosmetic here; it decides what a state MEANS.
        mu_tr = np.nanmean(X[tr_mask], axis=0)
        sd_tr = np.nanstd(X[tr_mask], axis=0) + 1e-9
        X = (X - mu_tr) / sd_tr
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

    # ── ★★ THE DEGENERATE-LABEL GUARD (banked 2026-09-12: 8 of 72 fitted models produced states
    #    whose BULLISH and BEARISH differed in 8-bar drift by <0.5 ATR, because the mixture had
    #    clustered on efficiency instead of direction. They traded a direction label carrying no
    #    direction and reported like any other cell. CHECK d8_gap BEFORE BELIEVING A STATE NAME.)
    d8_raw = {k: np.nanmean(Xraw[sub[sub.state == k].index, 1]) for k in range(a.states)
              if len(sub[sub.state == k])}
    bull = [k for k in names if names[k] == "BULLISH"]
    bear = [k for k in names if names[k] == "BEARISH"]
    d8_gap = (d8_raw.get(bull[0], np.nan) - d8_raw.get(bear[0], np.nan)) if bull and bear else np.nan
    print(f"\n  d8_gap = {d8_gap:.2f} ATR between BULLISH and BEARISH", end="  ")
    if not np.isfinite(d8_gap) or abs(d8_gap) < 0.5:
        print("→ ⛔ DEGENERATE: these states do not carry direction. The cells below are noise.")
    else:
        print("→ ok, the states are directional")

    st = g.state.values
    close, op = g.close.values, g.open.values
    sess = g.sess.values

    def run(names_map, fric):
        """Every (hold, clean) cell for one label assignment. Returns {(hold,clean): (n, mean)}."""
        out = {}
        for hold in (2, 3, 4, 5, 6, 8):
            for clean in (True, False):
                rec = []
                for i in range(3, len(g)-hold-1):
                    if not a.overnight and (sess[i] != sess[i+hold] or sess[i] != sess[i-2]):
                        continue
                    cur, prv = st[i], st[i-1]
                    if cur < 0 or prv < 0 or cur == prv:
                        continue
                    if names_map.get(cur) not in ("BULLISH", "BEARISH"):
                        continue
                    if names_map.get(prv) == names_map.get(cur):
                        continue
                    if clean and (st[i-1] == cur or st[i-2] == cur):
                        continue      # no contamination by the target state in the prior 2 bars
                    side = 1 if names_map[cur] == "BULLISH" else -1
                    rec.append((sess[i], side, close[i+hold]-op[i+1]))
                if not rec:
                    out[(hold, clean)] = None
                    continue
                R = pd.DataFrame(rec, columns=["sess", "side", "mv"])
                R["gross"] = R.side*R.mv
                R["pt"] = R.gross - fric          # the real arm
                R["flip"] = -R.gross - fric       # ★ SIGN-FLIP CONTROL: identical bars, identical
                R["yr"] = pd.to_datetime(R.sess.astype(str)).dt.year   # count, only the side changes
                out[(hold, clean)] = R
        return out

    lvl = g.assign(yr=g.dt.dt.year).groupby("yr").close.mean().to_dict()
    real = run(names, a.friction)
    print(f"\n{'hold':>7}{'clean':>7}" + "".join(f"{p:>22}" for p in ("TRAIN", "VALIDATE", "TEST"))
          + f"{'ALL':>16}")
    print(f"{'':>14}" + "".join(f"{'n':>6}{'net pt':>8}{'t':>8}" for _ in range(3))
          + f"{'net pt':>8}{'win%':>8}")
    for (hold, clean), R in real.items():
        if R is None or len(R) < 60:
            continue
        line = f"{hold*a.bar:>5}m{'  yes' if clean else '   no':>9}"
        for P in (TR, VA, TE):
            s2 = R[R.sess.isin(P)]
            if len(s2) < 15:
                line += f"{len(s2):>6}{'-':>8}{'-':>8}"; continue
            t = s2.pt.mean()/(s2.pt.std(ddof=1)/np.sqrt(len(s2)))
            line += f"{len(s2):>6}{s2.pt.mean():>8.2f}{t:>8.2f}"
        line += f"{R.pt.mean():>8.2f}{100*(R.pt > 0).mean():>7.0f}%"
        print(line)

    # ── ★ THE SIGN-FLIP CONTROL — identical entries at identical bars, only the direction
    #    changes, so the entry population cannot move. 2026-09-12: the 5-way label PERMUTATION was
    #    retired after it was measured swinging the entry count 1,983 -> 2,646 (+33%) and scoring
    #    +1.20 net on one arrangement. A control that trades a different population, or that makes
    #    money, is broken.
    print(f"\n  SIGN-FLIP CONTROL — same bars, same n, direction reversed")
    print(f"{'hold':>7}{'clean':>7}{'n':>7}{'real':>9}{'flipped':>10}{'GROSS':>9}"
          f"{'t(gross)':>10}{'t>2?':>9}")
    for (hold, clean), R in real.items():
        if R is None or len(R) < 60:
            continue
        rm, fm = R.pt.mean(), R.flip.mean()
        t = rm/(R.pt.std(ddof=1)/np.sqrt(len(R)))
        gt = R.gross.mean()/(R.gross.std(ddof=1)/np.sqrt(len(R)))
        print(f"{hold*a.bar:>5}m{'  yes' if clean else '   no':>9}{len(R):>7}{rm:>9.2f}{fm:>10.2f}"
              f"{R.gross.mean():>9.2f}{gt:>10.2f}{('  YES' if gt > 2 else '  no'):>9}")

    if a.by_era:
        print(f"\n  BY CALENDAR YEAR — the whole point of the long tape. "
              f"⚠ points are NOT comparable across a 7x price level; read the sign and the t.")
        for (hold, clean), R in real.items():
            if R is None or len(R) < 200 or not clean:
                continue
            print(f"\n  hold {hold*a.bar}m, clean:")
            print(f"{'year':>8}{'n':>7}{'GROSS pt':>10}{'t':>8}{'net':>8}{'mean px':>10}"
                  f"{'gross as bp':>13}")
            for yr, sub in R.groupby("yr"):
                if len(sub) < 30:
                    continue
                gt = sub.gross.mean()/(sub.gross.std(ddof=1)/np.sqrt(len(sub)))
                px = lvl.get(yr, float("nan"))
                print(f"{yr:>8}{len(sub):>7}{sub.gross.mean():>10.2f}{gt:>8.2f}"
                      f"{sub.pt.mean():>8.2f}{px:>10.0f}{1e4*sub.gross.mean()/px:>13.2f}")

    print(f"\n  net points AFTER {a.friction:g}pt friction · entry = next bar open · "
          f"exit = fixed hold, no target, no stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
