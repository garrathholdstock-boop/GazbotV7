#!/usr/bin/env python3
"""GIVE-BACK STUDY — stage 8: try to KILL the one candidate that survived stage 7.

Candidate: abs_veto_short, QUIET window only, Lot B 2.5R -> 1.5R (Lot A stays 1.5R).
Everything below is an attempt to break it.

  PYTHONPATH=src ./.venv/bin/python scripts/adaptive_r_stress.py
"""
from __future__ import annotations

import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from adaptive_r_sim import SCR  # noqa: E402
from adaptive_r_verdict import ARCH_DAYS  # noqa: E402

pd.set_option("display.width", 260)
rng = np.random.default_rng(7)


def delta_by_day(a: pd.DataFrame, b: pd.DataFrame, win="QUIET"):
    """per-day (candidate - baseline) for a single LOT rule swap."""
    A = a[a.win == win].groupby("day").pnl.sum()
    B = b[b.win == win].groupby("day").pnl.sum()
    return (A - B).fillna(A).fillna(-B).fillna(0.0)


def report(d: pd.Series, label: str):
    tot = d.sum()
    lodo = min(tot - d[k] for k in d.index) if len(d) > 1 else tot
    s3 = tot - d.nlargest(3).sum()
    boot = np.array([rng.choice(d.values, len(d), replace=True).sum() for _ in range(4000)])
    arch = d[[k for k in d.index if k in ARCH_DAYS]].sum()
    cap = d[[k for k in d.index if k not in ARCH_DAYS]].sum()
    print(f"{label:38} total ${tot:8.0f} | days+ {int((d>0).sum())}/{len(d)} | "
          f"LODO ${lodo:8.0f} | strip-3 ${s3:8.0f} | P(>0) {(boot>0).mean():.3f} | "
          f"ARCH ${arch:7.0f} | CAP ${cap:7.0f}")
    return tot


def main():
    with open(f"{SCR}/ar_per.pkl", "rb") as fh:
        sig, per, CUTS = pickle.load(fh)
    G = "abs_veto_short"

    print("=" * 130)
    print("1. THE LOT-B PLATEAU — abs_veto_short QUIET, Lot B swapped from the loaded 2.5R")
    print("=" * 130)
    base = per[(G, "A2.5")]
    for r in ["A0.5", "A0.75", "A1.0", "A1.25", "A1.5", "A2.0", "A2.5", "A3.0", "A3.5",
              "tight", "k2.5", "wide"]:
        if (G, r) not in per:
            continue
        d = delta_by_day(per[(G, r)], base)
        report(d, f"  Lot B {r:6} vs loaded A2.5")

    print("\n" + "=" * 130)
    print("2. THE SAME SWAP IN THE US WINDOW — is the QUIET result window-specific?")
    print("=" * 130)
    for r in ["A1.0", "A1.25", "A1.5", "A2.0", "A3.5", "wide"]:
        d = delta_by_day(per[(G, r)], base, win="US")
        report(d, f"  US  Lot B {r:6} vs loaded A2.5")

    print("\n" + "=" * 130)
    print("3. CONCENTRATION — is the QUIET gain a couple of trades / a couple of days?")
    print("=" * 130)
    cand, bs = per[(G, "A1.5")], per[(G, "A2.5")]
    dq = delta_by_day(cand, bs)
    print(dq.round(1).to_string())
    print(f"\n  top-1 day = {100*dq.nlargest(1).sum()/dq.sum():.0f}% of the gain; "
          f"top-3 days = {100*dq.nlargest(3).sum()/dq.sum():.0f}%")
    ca, ba = cand[cand.win == "QUIET"], bs[bs.win == "QUIET"]
    print(f"  candidate lots {len(ca)} (${ca.pnl.sum():.0f}), "
          f"baseline lots {len(ba)} (${ba.pnl.sum():.0f})")

    print("\n" + "=" * 130)
    print("4. LIVE-LOSS MULTIPLIER — losses x L on BOTH books; where does the gain die?")
    print("=" * 130)
    for L in [1.0, 1.1, 1.2, 1.3, 1.5, 1.75, 2.0, 2.5, 3.1]:
        c = ca.pnl.where(ca.pnl >= 0, ca.pnl * L).sum()
        b = ba.pnl.where(ba.pnl >= 0, ba.pnl * L).sum()
        print(f"  L={L:4.2f}  candidate ${c:8.0f}   baseline ${b:8.0f}   delta ${c-b:8.0f}"
              f"   {'DEAD' if c <= b else ''}")

    print("\n" + "=" * 130)
    print("5. SLIPPAGE — 1 tick ($0.50/lot) adverse on every exit, both books")
    print("=" * 130)
    for slip in [0.0, 0.5, 1.0]:
        c = (ca.pnl - slip).sum()
        b = (ba.pnl - slip).sum()
        print(f"  {slip:.2f} pt/lot: candidate ${c:8.0f}  baseline ${b:8.0f}  delta ${c-b:8.0f}")

    print("\n" + "=" * 130)
    print("6. WINDOW-BOUNDARY SENSITIVITY — is 13:30 UTC doing the work?")
    print("=" * 130)
    for cut_h in [11.0, 12.0, 13.0, 13.5, 14.0, 15.0]:
        cut = int(cut_h * 3600)

        def w(ms, c=cut):
            sod = (ms // 1000) % 86400
            return (sod >= 22 * 3600) or (sod < c)
        A = cand[cand.dec_ms.map(w)].groupby("day").pnl.sum()
        B = bs[bs.dec_ms.map(w)].groupby("day").pnl.sum()
        d = (A - B).fillna(0.0)
        print(f"  quiet = 22:00 -> {cut_h:5.2f}   delta ${d.sum():8.0f}  "
              f"days+ {int((d>0).sum())}/{len(d)}  n_cand {int(cand.dec_ms.map(w).sum())}")

    print("\n" + "=" * 130)
    print("7. INDEPENDENT ENTRY STREAM — the same swap on the SHADOW abs_veto_55s book")
    print("=" * 130)
    print("   (shadow_trades are a DIFFERENT entry engine run live at the time; if the swap")
    print("    is real it should show there too, on entries my replay never generated)")
    d = pd.read_pickle(f"{SCR}/mfe_clean.pkl")
    sh = d[(d.popn == "SHADOW") & (d.gate.isin(["abs_veto_55s", "abs_veto_50s", "abs_veto_60s"]))
           & (d.side == "SHORT")].copy()
    for win in ("QUIET", "US"):
        s = sh[sh.win == win]
        if not len(s):
            continue
        # reprice each shadow SHORT entry at a 1.5R and a 2.5R fixed clip using its own
        # tick MFE/MAE path proxy: it reached 1.5R iff mfe_r >= 1.5 and it did so before -1R.
        # mae is a floor not a path, so this is an APPROXIMATION and flagged as such.
        r15 = np.where(s.mfe_r >= 1.5, 1.5 * s.atr, np.maximum(s.mae_pt, -s.atr))
        r25 = np.where(s.mfe_r >= 2.5, 2.5 * s.atr, np.maximum(s.mae_pt, -s.atr))
        print(f"  {win:6} n={len(s):4}  1.5R-clip ${(r15*2-1.5).sum():8.0f}   "
              f"2.5R-clip ${(r25*2-1.5).sum():8.0f}   delta ${((r15-r25)*2).sum():8.0f}")


if __name__ == "__main__":
    main()
