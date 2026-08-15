#!/usr/bin/env python3
"""MGC RUN CATCHER — THE EXIT MATRIX (Friday 2026-08-14 re-derivation).

The claim under test: gold's runs are GRINDS (median efficiency ~0.2, hours long), so a momentum
TRAIL is shaken out of them and the exit — not the entry filter — is what caps the strategy.

Method. Take the run-catcher's boarding signals UNCHANGED (`mgc_run_catcher.gate_signals`, every
term causal, entry raced from bar-close + 60s). Then reprice the SAME entries under a matrix of
exits: trail width x stop width x hold cap. Nothing about the entry changes between cells, so any
difference is the exit and only the exit.

Also prints the ORACLE decomposition — trades that boarded one of the week's big runs vs everything
else. ⚠ That split uses labels only knowable AFTERWARDS. It is an upper bound on what a perfect
day-filter could pay, never a result.

  PYTHONPATH=src .venv/bin/python scripts/mgc_exit_matrix.py [--days 9]
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from mgc_run_catcher import find_runs, gate_signals  # noqa: E402
from mgc_session_anchor import VPP, FEE_RT, atr, load, minute_bars, race  # noqa: E402

GATE = dict(thrust_atr=1.5, er_min=0.50, expand_min=1.0)     # the run-catcher's own best cell
MATRIX = [
    # (label, trail xATR or None, stop xATR, cap minutes)
    ("2.5xATR trail · 1.5 stop · 3h", 2.5, 1.5, 180),
    ("no trail · 1.5xATR stop · 3h", None, 1.5, 180),
    ("no trail · 3xATR stop · 3h", None, 3.0, 180),
    ("no trail · 5xATR stop · 3h", None, 5.0, 180),
    ("no trail · 5xATR stop · 6h", None, 5.0, 360),
    ("no trail · 5xATR stop · 8h", None, 5.0, 480),
    ("no trail · 5xATR stop · 10h", None, 5.0, 600),
    ("no trail · 5xATR stop · 12h", None, 5.0, 720),
    ("no trail · 3xATR stop · 8h", None, 3.0, 480),
    ("no trail · 3xATR stop · 12h", None, 3.0, 720),
    ("no trail · 8xATR stop · 8h", None, 8.0, 480),
    ("5xATR trail · 5 stop · 8h", 5.0, 5.0, 480),
]


def run_cell(m, ticks, sigs, trail, stop_k, cap, run_windows):
    tk, px = ticks["ts_ms"].to_numpy(), ticks["price"].to_numpy()
    rows = []
    for ts, side, entry, _stop, av in sigs:
        e_ms = int(ts.value // 10**6) + 60_000
        j = np.searchsorted(tk, e_ms)
        k = np.searchsorted(tk, e_ms + cap * 60000 + 1)
        stop = entry - side * stop_k * av
        xp, why, mins = race(tk[j:k], px[j:k], side, entry, stop, None,
                             (trail * av) if trail else None, cap * 60000)
        pnl = side * (xp - entry) * VPP - FEE_RT
        boarded = any(a <= ts <= b and d == side for a, b, d in run_windows)
        rows.append(dict(ts=ts, side=side, pnl=pnl, why=why, mins=mins, boarded=boarded))
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=9)
    a = ap.parse_args()
    bars, ticks = load()
    m_all = minute_bars(bars)
    cut = m_all.index.max().normalize() - pd.Timedelta(days=a.days)
    m = m_all.loc[cut:]
    weeks = max(1.0, m.index.normalize().nunique() / 5.0)

    runs = find_runs(m)
    top = runs.sort_values("usd", ascending=False).head(5)
    run_windows = [(r["start"], r["end"], int(r["dir"])) for _, r in top.iterrows()]
    sigs = gate_signals(m, **GATE)
    print(f"  MGC {m.index.min():%Y-%m-%d} .. {m.index.max():%Y-%m-%d} · "
          f"{m.index.normalize().nunique()} days (~{weeks:.1f} wk) · ${VPP:.0f}/pt · "
          f"{len(sigs)} boarding signals · gate {GATE}")
    print(f"  top-5 runs used for the oracle split: "
          f"{', '.join(f'{r.start:%m-%d %H:%M} {"UP" if r.dir>0 else "DN"} ${r.usd:,.0f}' for _, r in top.iterrows())}\n")

    print("  ALL = every boarding signal (what a live gate would actually take).")
    print("  ORACLE = only the signals that landed inside a top-5 run — a perfect day-filter, "
          "knowable only afterwards.\n")
    print(f"  {'exit':34s}{'n':>5}{'win%':>7}{'ALL net$':>10}{'$/wk':>9}{'median$':>10}"
          f"{'ORACLE n':>10}{'ORACLE $':>10}{'$/wk':>9}")
    best = None
    for label, trail, stop_k, cap in MATRIX:
        df = run_cell(m, ticks, sigs, trail, stop_k, cap, run_windows)
        net = df["pnl"].sum()
        orc = df[df.boarded]
        onet = orc["pnl"].sum()
        print(f"  {label:34s}{len(df):>5d}{100*(df.pnl>0).mean():>7.1f}{net:>10,.0f}"
              f"{net/weeks:>9,.0f}{df.pnl.median():>10,.1f}{len(orc):>10d}{onet:>10,.0f}"
              f"{onet/weeks:>9,.0f}")
        if best is None or net > best[1]:
            best = (label, net, df)

    print(f"\n  ═══ ORACLE DECOMPOSITION under the best exit ({best[0]}) ═══")
    df = best[2]
    for tag, sel in (("boarded a top-5 run", df[df.boarded]), ("everything else", df[~df.boarded])):
        if len(sel):
            print(f"  {tag:24s} n={len(sel):3d}  net=${sel.pnl.sum():>9,.0f}  "
                  f"exp=${sel.pnl.mean():>7,.2f}  win={100*(sel.pnl>0).mean():>5.1f}%")
    print("  ⚠ the boarded/not split uses labels knowable only afterwards — an upper bound on a "
          "perfect day-filter, NOT a result.")

    print("\n  ═══ HOLD-TIME CURVE at the 5xATR stop (where does holding stop paying?) ═══")
    for cap in (120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720):
        df = run_cell(m, ticks, sigs, None, 5.0, cap, run_windows)
        print(f"    cap {cap//60:>2d}h  net=${df.pnl.sum():>9,.0f}  ${df.pnl.sum()/weeks:>8,.0f}/wk  "
              f"win={100*(df.pnl>0).mean():>5.1f}%  median hold {df.mins.median():>5,.0f}min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
