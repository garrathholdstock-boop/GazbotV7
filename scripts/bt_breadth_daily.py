#!/usr/bin/env python3
"""THE BREADTH TEST — does trading MANY markets once a day do what the arithmetic says?

The desk's two-market probe (NQ+GC, 26y) realised a 1.39x breadth multiplier against a theoretical
1.39x. This is the same test on 14 markets across 6 sectors, which is the version that matters:
at rho~0.3 the theory says ~1.6x, which takes a per-market Sharpe of ~0.5 into the 0.8s.

★ NO LOOKBACK IS PICKED. The signal is an equal-weight ENSEMBLE of 60/120/250-day trends, which is
  standard practice and removes the single largest tuning knob. Picking the best lookback per market
  is exactly the search this desk keeps dying to.
★ THE CONTROL IS BUY-AND-HOLD, vol-targeted identically. On the two-market probe the control WON
  (1.06 vs 0.72) because 2000-2026 is a huge bull in both. Across 14 markets it is a fairer fight,
  and if trend still loses, that is the answer.
⚠ YAHOO =F SERIES ARE FRONT-MONTH CONTINUOUS, NOT BACK-ADJUSTED. Roll days inject a basis jump that
  is not a tradeable return. Sensitivity is reported by winsorizing daily returns at +/-5 sigma.
⚠ EFFECTIVE BETS, NOT MARKET COUNT. Three equity indices at rho 0.9 are ONE bet. The desk's nine
  "validated" abs_veto arms turned out to be 1.29 effective bets; the same arithmetic applies here.
"""
from __future__ import annotations
import argparse, glob, os
import numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
SECTORS = {
 "NQF": "equity", "ESF": "equity", "RTYF": "equity",
 "GCF": "metals", "SIF": "metals", "HGF": "metals",
 "CLF": "energy", "NGF": "energy",
 "6EF": "fx", "6JF": "fx", "6AF": "fx",
 "ZNF": "rates", "ZBF": "rates",
 "BTCUSD": "crypto",
}
LOOKBACKS = (60, 120, 250)


def load() -> pd.DataFrame:
    out = {}
    for f in sorted(glob.glob(f"{GB}/data/external/yahoo/*_1d.csv")):
        k = os.path.basename(f).replace("_1d.csv", "")
        if k not in SECTORS:
            continue
        d = pd.read_csv(f)
        d["date"] = pd.to_datetime(d.date, unit="s", utc=True).dt.date
        out[k] = d.set_index("date").close
    px = pd.DataFrame(out).sort_index()
    # ★★ FORWARD-FILL ONTO THE COMMON CALENDAR. Fourteen markets keep fourteen holiday calendars,
    # so the union index leaves a hole in every series — and rolling(60) needs 60 CONSECUTIVE
    # non-null values, so those holes silently deleted most of the sample: NQ computed on 3,296 of
    # 5,901 rows and RTY on ZERO, reported as a NaN row rather than an error. ffill does not touch
    # leading NaNs, so a market still contributes nothing before it exists.
    return px.ffill()


def run(px, cost_bp, winsor=None, start=None, end=None):
    ret = px.pct_change()
    if winsor:
        z = ret.sub(ret.mean()).div(ret.std())
        ret = ret.mask(z.abs() > winsor, np.nan)          # drop, never clip: a roll is not a return
    if start:
        ret = ret[[d.year >= start for d in ret.index]]
        px = px[[d.year >= start for d in px.index]]
    if end:
        ret = ret[[d.year <= end for d in ret.index]]
        px = px[[d.year <= end for d in px.index]]
    sig = sum((px > px.shift(L)).astype(float) * 2 - 1 for L in LOOKBACKS) / len(LOOKBACKS)
    sig = sig.shift(1)                                     # decide on yesterday, trade today
    vol = ret.rolling(60, min_periods=40).std().shift(1)
    w = (0.01 / vol).clip(0, 5) * sig
    turn = (w - w.shift(1)).abs()
    pnl = w * ret - turn * (cost_bp / 1e4)
    bh = (0.01 / vol).clip(0, 5) * ret                     # the control: always long, same sizing
    return pnl, bh, ret


def stats(x):
    x = x.dropna()
    if not len(x) or x.std() == 0:
        return dict(ann=np.nan, vol=np.nan, sharpe=np.nan, dd=np.nan)
    cum = (1 + x).cumprod()
    return dict(ann=x.mean() * 252 * 100, vol=x.std() * np.sqrt(252) * 100,
                sharpe=x.mean() / x.std() * np.sqrt(252),
                dd=(cum / cum.cummax() - 1).min() * 100)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cost-bp", type=float, default=3.0)
    a = ap.parse_args()
    px = load()
    print(f"{px.shape[1]} markets · {px.shape[0]:,} daily bars · {px.index[0]} .. {px.index[-1]}")
    print("  coverage:", ", ".join(f"{c}:{px[c].notna().sum():,}" for c in px.columns), "\n")

    pnl, bh, ret = run(px, a.cost_bp)
    print(f"PER MARKET (trend ensemble {LOOKBACKS}, vol-targeted, {a.cost_bp:g}bp per turn)")
    print(f"{'market':>9}{'sector':>9}{'ann %':>8}{'SHARPE':>8}{'maxDD':>9}   |{'b&h sharpe':>12}")
    for c in px.columns:
        s, b = stats(pnl[c]), stats(bh[c])
        print(f"{c:>9}{SECTORS[c]:>9}{s['ann']:>8.1f}{s['sharpe']:>8.2f}{s['dd']:>9.1f}   |"
              f"{b['sharpe']:>12.2f}")

    port = pnl.mean(axis=1, skipna=True)
    pbh = bh.mean(axis=1, skipna=True)
    sm = [stats(pnl[c])["sharpe"] for c in px.columns]
    live = [c for c in px.columns if pnl[c].notna().sum() > 250]   # a dead column poisons the matrix
    rho = pnl[live].corr().values
    avg = (rho.sum() - np.trace(rho)) / (rho.shape[0] ** 2 - rho.shape[0])
    K = len(live)
    neff = K / (1 + (K - 1) * avg)
    print(f"\nPORTFOLIO, equal weight")
    for lbl, x in (("TREND, 14 markets", port), ("buy & hold control", pbh)):
        s = stats(x)
        print(f"  {lbl:<24}ann {s['ann']:>5.1f}%   vol {s['vol']:>5.1f}%   SHARPE {s['sharpe']:>5.2f}"
              f"   maxDD {s['dd']:>6.1f}%")
    pos = [x for x in sm if np.isfinite(x)]
    print(f"\n  mean per-market Sharpe      {np.nanmean(pos):.2f}   "
          f"(median {np.nanmedian(pos):.2f})")
    print(f"  ⚠ the ratio below is inflated by the NEGATIVE per-market Sharpes in the mean — "
          f"read it against the theory line, not on its own")
    print(f"  portfolio Sharpe            {stats(port)['sharpe']:.2f}")
    print(f"  breadth multiplier REALISED {stats(port)['sharpe']/np.nanmean(sm):.2f}x")
    print(f"  average strategy corr       {avg:+.3f}   -> EFFECTIVE BETS {neff:.1f} of {K} markets")
    print(f"  theory at that corr         {np.sqrt(neff):.2f}x")

    print(f"\nSENSITIVITY")
    for cb in (1, 3, 10, 25):
        p, _, _ = run(px, cb)
        print(f"  cost {cb:>2}bp/turn        portfolio Sharpe {stats(p.mean(axis=1))['sharpe']:.2f}")
    p, _, _ = run(px, a.cost_bp, winsor=5)
    print(f"  roll-jump guard (5σ drop) portfolio Sharpe {stats(p.mean(axis=1))['sharpe']:.2f}")
    for lo, hi in ((2000, 2008), (2009, 2016), (2017, 2026)):
        p, b, _ = run(px, a.cost_bp, start=lo, end=hi)
        print(f"  {lo}-{hi}             trend {stats(p.mean(axis=1))['sharpe']:>5.2f}   "
              f"b&h {stats(b.mean(axis=1))['sharpe']:>5.2f}")
    print(f"\n  by sector (equal weight within sector, then across):")
    bysec = pd.DataFrame({s: pnl[[c for c in px.columns if SECTORS[c] == s]].mean(axis=1)
                          for s in sorted(set(SECTORS.values()))})
    for s in bysec.columns:
        print(f"    {s:<8}{stats(bysec[s])['sharpe']:>6.2f}")
    print(f"    {'SECTOR-BALANCED PORTFOLIO':<8} {stats(bysec.mean(axis=1))['sharpe']:>.2f}")


if __name__ == "__main__":
    raise SystemExit(main())
