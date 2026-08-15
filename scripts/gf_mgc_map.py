#!/usr/bin/env python3
"""GF_MGC MAP — before inventing a gate, MEASURE whether each of the four cells can exist at all.

    PYTHONPATH=src .venv/bin/python scripts/gf_mgc_map.py

★ WHY A MAP FIRST. Six gold attacks are already refuted, and every one of them was a GATE — a
trigger, a threshold, a backtest. The cheapest way to dig a seventh grave is to invent a seventh
trigger. So this file builds nothing tradeable. It asks the prior question:

    conditioned on what gold has just done, is the NEXT interval biased at all —
    and if it is, is the bias CONTINUATION (a momentum cell) or REVERSAL (a reversion cell)?

If a cell's conditional bias is indistinguishable from the unconditional drift, no threshold will
rescue it and the honest answer is a null with a named cause. If a bias exists, this tells me WHERE
(regime x session x side) so the gate is built on the tape's own structure rather than on a guess.

★ THE CONTROL IS THE BEST CONSTANT, NOT ZERO. `always_short` beat every directed gold gate in the
08-05 study. So every cell is scored against the unconditional move over the same horizon on the
same rows — the honest question is not "does it make money" but "does it beat just being long, or
just being short, all the time".

★ MULTIPLE COMPARISONS ARE THE OBVIOUS OBJECTION and it is a fair one: this grid is large and the
best cell in a large grid is usually noise. So nothing here is a finding. Cells are carried forward
ONLY when (a) the effect survives on BOTH halves of the sample split by date, and (b) there is a
nameable mechanism. Everything else is reported and dropped.

Costs are irrelevant here (no trades are taken) but the horizon moves are reported in DOLLARS at
MGC's $10/pt so the magnitudes can be read against the $7.50 true round-trip cost.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_tape import VPP, build_tape  # noqa: E402

pd.set_option("display.width", 220)


def forward(m: pd.DataFrame, h: int) -> pd.Series:
    """Move over the NEXT h minutes, in points. Strictly future — the shift is the whole safety."""
    return m["close"].shift(-h) - m["close"]


def impulse(m: pd.DataFrame, k: int) -> pd.Series:
    """Move over the PRIOR k minutes, in ATR units. Causal."""
    return (m["close"] - m["close"].shift(k)) / m["atr"]


def cell_table(m: pd.DataFrame, *, k: int, h: int, thr: float) -> pd.DataFrame:
    """The 2x2, measured. For each regime: after a prior-k-minute impulse of at least `thr` ATR,
    what does the next h minutes do — and how does that compare with doing it unconditionally?"""
    d = m.copy()
    d["imp"] = impulse(d, k)
    d["fwd"] = forward(d, h)
    d = d.dropna(subset=["imp", "fwd", "atr", "regime"])

    rows = []
    for reg, g in d.groupby("regime"):
        base_up = float((g["fwd"] > 0).mean())
        base_mu = float(g["fwd"].mean())
        for label, mask, sign in (
            ("MOM_LONG",  g["imp"] >= thr,  +1),   # up-impulse, bet it continues UP
            ("MOM_SHORT", g["imp"] <= -thr, -1),   # down-impulse, bet it continues DOWN
            ("REV_LONG",  g["imp"] <= -thr, +1),   # down-impulse, bet it bounces UP
            ("REV_SHORT", g["imp"] >= thr,  -1),   # up-impulse, bet it fades DOWN
        ):
            s = g.loc[mask, "fwd"] * sign
            if len(s) < 60:
                continue
            # the matched constant: same direction, but taken on EVERY row of this regime
            const = g["fwd"] * sign
            rows.append({
                "regime": reg, "cell": label, "n": len(s),
                "hit%": round(100.0 * float((s > 0).mean()), 1),
                "mean_pt": round(float(s.mean()), 3),
                "mean_$": round(float(s.mean()) * VPP, 2),
                "const_$": round(float(const.mean()) * VPP, 2),
                "edge_$": round((float(s.mean()) - float(const.mean())) * VPP, 2),
                "med_$": round(float(s.median()) * VPP, 2),
                "t": round(float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))), 2) if s.std(ddof=1) else 0.0,
                "base_up%": round(100.0 * base_up, 1), "base_mu$": round(base_mu * VPP, 2),
            })
    return pd.DataFrame(rows)


def halves(m: pd.DataFrame, *, k: int, h: int, thr: float) -> pd.DataFrame:
    """The same grid on each half of the calendar. A cell that flips sign here is noise, full stop —
    this is the test that killed the L2 direction attack (it flipped across 5 disjoint samples)."""
    days = sorted(m["day"].unique())
    cut = days[len(days) // 2]
    a = cell_table(m[m["day"] < cut], k=k, h=h, thr=thr)
    b = cell_table(m[m["day"] >= cut], k=k, h=h, thr=thr)
    j = a.merge(b, on=["regime", "cell"], suffixes=("_h1", "_h2"), how="inner")
    j["agree"] = np.sign(j["edge_$_h1"]) == np.sign(j["edge_$_h2"])
    return j[["regime", "cell", "n_h1", "edge_$_h1", "n_h2", "edge_$_h2", "agree",
              "hit%_h1", "hit%_h2"]]


def main() -> None:
    m, _ = build_tape()
    print("=" * 110)
    print("GF_MGC MAP — is there a conditional bias in gold at all?")
    print(f"  {len(m):,} minutes, {m['day'].nunique()} days, {m['day'].min()} .. {m['day'].max()}")
    print("=" * 110)

    # ── 0. the unconditional truth: what is the best CONSTANT on this tape? ──
    print("\n[0] THE BEST CONSTANT — every candidate must beat this, not zero")
    for h in (15, 30, 60, 120):
        f = forward(m, h).dropna()
        print(f"    horizon {h:>3}min   always_LONG {f.mean() * VPP:+7.2f}$/entry  "
              f"up {100.0 * (f > 0).mean():4.1f}%   |   always_SHORT {-f.mean() * VPP:+7.2f}$/entry  "
              f"down {100.0 * (f < 0).mean():4.1f}%   n={len(f):,}")
    dd = m.groupby("day")["close"].agg(["first", "last"])
    dd["move$"] = (dd["last"] - dd["first"]) * VPP
    print(f"\n    day-by-day close-over-close: {int((dd['move$'] > 0).sum())} up / "
          f"{int((dd['move$'] < 0).sum())} down of {len(dd)}, "
          f"mean {dd['move$'].mean():+.2f}$  median {dd['move$'].median():+.2f}$")
    print("    ⚠ the sample's DRIFT is the single biggest confound in every gold study — a directional")
    print("      cell that merely reproduces it has found nothing.")

    # ── 1. the 2x2 across horizons ──
    for k, h, thr in ((10, 30, 1.0), (20, 60, 1.5), (30, 120, 1.5), (60, 240, 2.0)):
        print("\n" + "=" * 110)
        print(f"[1] IMPULSE {k}min >= {thr} ATR  ->  NEXT {h}min      "
              f"(edge_$ = cell minus the same-direction constant on the same regime)")
        print("=" * 110)
        t = cell_table(m, k=k, h=h, thr=thr)
        if t.empty:
            print("    (no cell reached n>=60)")
            continue
        print(t.sort_values(["cell", "regime"]).to_string(index=False))

    # ── 2. the stability test ──
    print("\n" + "=" * 110)
    print("[2] BOTH-HALVES STABILITY — a cell that flips sign between calendar halves is noise")
    print("=" * 110)
    for k, h, thr in ((10, 30, 1.0), (20, 60, 1.5), (30, 120, 1.5)):
        print(f"\n  impulse {k}min>={thr}ATR -> {h}min")
        j = halves(m, k=k, h=h, thr=thr)
        if j.empty:
            print("    (nothing with n on both halves)")
            continue
        j = j.sort_values("agree", ascending=False)
        print(j.to_string(index=False))
        print(f"    cells agreeing on sign: {int(j['agree'].sum())}/{len(j)}")

    # ── 3. session shape — is gold's day structured by the clock? ──
    print("\n" + "=" * 110)
    print("[3] SESSION SHAPE — the one source the refuted attacks did not use")
    print("=" * 110)
    d = m.copy()
    d["fwd60"] = forward(d, 60)
    g = d.dropna(subset=["fwd60"]).groupby("session")["fwd60"]
    print(pd.DataFrame({
        "n": g.size(), "mean_$": (g.mean() * VPP).round(2), "up%": (100.0 * g.apply(lambda s: (s > 0).mean())).round(1),
        "abs_$": (g.apply(lambda s: s.abs().mean()) * VPP).round(2),
    }).to_string())
    print("\n  hourly: mean 60-min forward move and its ABSOLUTE size (the volatility clock)")
    d["h"] = d.index.hour
    gh = d.dropna(subset=["fwd60"]).groupby("h")["fwd60"]
    hh = pd.DataFrame({"n": gh.size(), "mean_$": (gh.mean() * VPP).round(2),
                       "abs_$": (gh.apply(lambda s: s.abs().mean()) * VPP).round(2),
                       "up%": (100.0 * gh.apply(lambda s: (s > 0).mean())).round(1)})
    print(hh.to_string())

    # ── 4. ⚠ the brief's explicit instruction: if DIRECTION is unpredictable, is SIZE predictable? ──
    print("\n" + "=" * 110)
    print("[4] IS SIZE PREDICTABLE WHERE DIRECTION IS NOT?  (the breakout-either-way question)")
    print("=" * 110)
    d = m.copy()
    d["fwd60_abs"] = forward(d, 60).abs()
    d["rng20"] = (d["high"].rolling(20).max() - d["low"].rolling(20).min()) / d["atr"]
    d = d.dropna(subset=["fwd60_abs", "rng20", "er"])
    d["compression"] = pd.qcut(d["rng20"], 5, labels=["Q1 tightest", "Q2", "Q3", "Q4", "Q5 widest"])
    g = d.groupby("compression", observed=True)["fwd60_abs"]
    tbl = pd.DataFrame({"n": g.size(), "mean_abs_$": (g.mean() * VPP).round(2),
                        "p75_abs_$": (g.quantile(0.75) * VPP).round(2)})
    tbl["vs_all"] = (tbl["mean_abs_$"] - d["fwd60_abs"].mean() * VPP).round(2)
    print("\n  by 20-min RANGE COMPRESSION (does a coil predict the SIZE of what follows?)")
    print(tbl.to_string())
    # rank correlation by hand — scipy is not installed in this venv and pandas' "spearman" needs it
    def rcorr(x: pd.Series, y: pd.Series) -> float:
        return float(x.rank().corr(y.rank()))

    print(f"\n  rank corr(20min range, |next 60min|) = {rcorr(d['rng20'], d['fwd60_abs']):+.4f}")
    print(f"  rank corr(ATR,          |next 60min|) = {rcorr(d['atr'], d['fwd60_abs']):+.4f}")
    print(f"  rank corr(ER,           |next 60min|) = {rcorr(d['er'], d['fwd60_abs']):+.4f}")
    print("\n  ⚠ read this the right way round: a POSITIVE corr on ATR means big begets big, which is")
    print("    volatility clustering and is not tradeable on its own. What a straddle needs is the")
    print("    TIGHTEST quintile to expand MORE than average — i.e. a NEGATIVE vs_all on Q5 and a")
    print("    positive one on Q1.")


if __name__ == "__main__":
    main()
