"""CHOP-DAY SCALP — Step 6: sweep CT-3 EXHAUST-CT (the operator's literal mechanism)
and run the placebo battery over the whole family.

Every R-target and threshold here is an operator GUESS until it is swept.  A cell that
is green alone is worthless; the question is whether there is a PLATEAU.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import gf_cs_bt as B
import gf_cs_lib as L

pd.set_option("display.width", 250)
CACHE: dict = {}


def sweep_ct3():
    rows = []
    for wall, push, prog, flat, er in itertools.product(
            [1.2, 1.5, 2.0], [0.0, 0.05, 0.10], [2.0, 4.0], [0.5, 1.0, 99.0], [0.15, 0.30]):
        p = dict(wall=wall, push=push, prog=prog, flat=flat, er=er)
        t = B.backtest("CT-3 EXHAUST-CT", 1.5, 0.75, 600, days=L.IS_DAYS,
                       params=p, cache=CACHE)
        s = L.stats(t)
        rows.append(dict(**p, **s, days=t["day"].nunique() if len(t) else 0))
    return pd.DataFrame(rows)


def sweep_exit(name, params, days):
    rows = []
    for ks, kt, hold in itertools.product([0.75, 1.0, 1.5, 2.0],
                                          [0.25, 0.5, 0.75, 1.0, 1.5],
                                          [300, 600, 900]):
        t = B.backtest(name, ks, kt, hold, days=days, params=params, cache=CACHE)
        s = L.stats(t)
        rows.append(dict(stop=ks, tgt=kt, hold=hold, **s))
    return pd.DataFrame(rows)


def placebo(name, params, ks, kt, hold, days, n=200):
    """Same gate, same entry times, SIDE SHUFFLED.  If the real net sits inside the
    placebo distribution the signal is carrying no direction."""
    real = L.stats(B.backtest(name, ks, kt, hold, days=days, params=params, cache=CACHE))
    nets = []
    for s in range(n):
        t = B.backtest(name, ks, kt, hold, days=days, params=params,
                       cache=CACHE, shuffle_seed=s)
        nets.append(t["net"].sum() if len(t) else 0.0)
    nets = np.array(nets)
    pct = float((nets >= real["net"]).mean())
    return dict(real=real["net"], n=real["n"], placebo_mean=round(nets.mean(), 2),
                placebo_sd=round(nets.std(), 2), beat_pct=round(100 * (1 - pct), 1),
                p_value=round(pct, 4))


def main() -> None:
    print("############ CT-3 PARAMETER SWEEP (in-sample, stop 1.5 ATR / tgt 0.75 ATR) ############")
    s = sweep_ct3()
    print(s.sort_values("net", ascending=False).to_string(index=False))
    s.to_csv(f"{B.OUT}/ct3_sweep.csv", index=False)
    pos = (s["net"] > 0).mean()
    print(f"\n   cells: {len(s)}   positive: {(s['net']>0).sum()} ({100*pos:.0f}%)   "
          f"median $/trade: {s['per'].median():.2f}   median n: {s['n'].median():.0f}")

    print("\n############ CT-3 EXIT SWEEP at its base thresholds ############")
    e = sweep_exit("CT-3 EXHAUST-CT", None, L.IS_DAYS)
    print(e.sort_values("net", ascending=False).head(20).to_string(index=False))
    e.to_csv(f"{B.OUT}/ct3_exit_sweep.csv", index=False)
    print(f"\n   cells: {len(e)}   positive: {(e['net']>0).sum()} "
          f"({100*(e['net']>0).mean():.0f}%)   median $/trade: {e['per'].median():.2f}")

    print("\n############ PLACEBO — side shuffled, 200 draws, in-sample ############")
    print(f"{'candidate':>20s} {'n':>5s} {'real$':>9s} {'placebo mu':>11s} "
          f"{'sd':>8s} {'beat%':>7s} {'p':>7s}")
    for name in B.CANDIDATES:
        r = placebo(name, None, 1.5, 0.75, 600, L.IS_DAYS, n=200)
        print(f"{name:>20s} {r['n']:5d} {r['real']:9.2f} {r['placebo_mean']:11.2f} "
              f"{r['placebo_sd']:8.2f} {r['beat_pct']:6.1f}% {r['p_value']:7.4f}")


if __name__ == "__main__":
    main()
