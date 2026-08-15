#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 1: the five invented candidates, scored tick-honest on the full lake.

Every candidate here is built from ONE idea — the cluster's own mechanism, that a >=1-sigma burst of
net aggressor flow LEADS price — and each one attacks a different reason the plain version might
fail: it needs persistence, it needs structure, it needs an existing leg, or the sign is backwards.

  FBURST   the literal label: flow event >= Z, take it in the flow's direction
  FDWELL   the same, but the burst must PERSIST (>=2 of the last 3 minutes, same sign)
  FBREAK   flow event AND the minute makes a new 15-min extreme in the flow direction
  FACCEL   flow event AND the trailing 15-min leg is already going the same way (join, don't guess)
  FFADE    the mirror — the same flow event taken AGAINST the flow (if the label's sign is backwards,
           this is where the money is, and the honest thing is to test it in the same harness)

Exit for the first pass (swept later, in gf_fl_sweep.py): stop 1.0 x atr15, target 2.0 x atr15,
30-minute time stop. Costs are the engine's: $1.50/round trip + 1 tick of slippage on every market
fill, $2.00 a point.

Writes reports/friday_v7/sections/fl/cands.json + fl/trades_<NAME>.csv
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from gf_fl_engine import score, simulate  # noqa: E402

FEAT = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl/feat.csv"
DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"


def load_feat():
    df = pd.read_csv(FEAT)
    idx = pd.to_datetime(df["ts"], unit="s", utc=True)
    df["minute_of_day"] = idx.dt.hour * 60 + idx.dt.minute
    add_regime(df)
    return df


def add_regime(df):
    """The desk's regime vocabulary, keyed on ATR LEVEL + ER + range, never on the clock alone.
    Cut points are percentiles of this tape's own atr15 so they travel across volatility eras."""
    a = df["atr15"]
    p33, p50, p67 = a.quantile(0.33), a.quantile(0.50), a.quantile(0.67)
    er = df["er15"]
    reg = pd.Series("BUILDING", index=df.index, dtype=object)
    reg[(er >= 0.40) & (a >= p50)] = "CLEAN-TREND"
    reg[(er < 0.20) & (a >= p67)] = "VIOLENT-WHIPSAW"
    reg[(er < 0.20) & (a <= p33)] = "DEAD-CHOP"
    reg[(er < 0.20) & (a > p33) & (a < p67)] = "NORMAL-CHOP"
    reg[a.isna() | er.isna()] = "UNKNOWN"
    df["regime"] = reg
    df["atr_cuts"] = f"{p33:.1f}/{p50:.1f}/{p67:.1f}"
    m = df["minute_of_day"]
    ses = pd.Series("OVERNIGHT", index=df.index, dtype=object)     # 20:00-07:00Z
    ses[(m >= 7 * 60) & (m < 13 * 60 + 30)] = "PRE-OPEN"           # 07:00-13:30Z
    ses[(m >= 13 * 60 + 30) & (m < 20 * 60)] = "US"                # 13:30-20:00Z
    df["session"] = ses
    return df


# ── candidate signal builders ────────────────────────────────────────────────────────────────────
def sig_fburst(df, z=2.0, **kw):
    m = (df["fz"].abs() >= z) & df["fz"].notna() & (df["flow"] != 0)
    return _mk(df, m, np.sign(df["flow"]))


def sig_fdwell(df, z=1.5, need=2, look=3, **kw):
    s = np.sign(df["flow"]) * (df["fz"].abs() >= z)
    up = (s > 0).rolling(look, min_periods=look).sum()
    dn = (s < 0).rolling(look, min_periods=look).sum()
    cont = (df["ts"] - df["ts"].shift(look - 1)) == (look - 1) * 60
    m = ((up >= need) | (dn >= need)) & cont
    d = np.where(up >= need, 1, -1)
    return _mk(df, m, pd.Series(d, index=df.index))


def sig_fbreak(df, z=1.5, look=15, **kw):
    hi = df["hi"].rolling(look, min_periods=look).max().shift(1)
    lo = df["lo"].rolling(look, min_periods=look).min().shift(1)
    d = np.sign(df["flow"])
    brk = ((d > 0) & (df["close"] > hi)) | ((d < 0) & (df["close"] < lo))
    m = (df["fz"].abs() >= z) & brk & df["fz"].notna()
    return _mk(df, m, d)


def sig_faccel(df, z=1.5, min_ext=0.5, **kw):
    d = np.sign(df["flow"])
    aligned = np.sign(df["ext15"]) == d
    big = df["ext15"].abs() >= min_ext * df["atr15"]
    m = (df["fz"].abs() >= z) & aligned & big & df["fz"].notna()
    return _mk(df, m, d)


def sig_ffade(df, z=2.0, **kw):
    m = (df["fz"].abs() >= z) & df["fz"].notna() & (df["flow"] != 0)
    return _mk(df, m, -np.sign(df["flow"]))


BUILDERS = {"FBURST": sig_fburst, "FDWELL": sig_fdwell, "FBREAK": sig_fbreak,
            "FACCEL": sig_faccel, "FFADE": sig_ffade}


def _mk(df, mask, dirs):
    mask = mask.fillna(False).to_numpy(bool) if hasattr(mask, "fillna") else np.asarray(mask, bool)
    dd = np.asarray(dirs, float)
    out = []
    sub = df[mask]
    for (_, r), d in zip(sub.iterrows(), dd[mask]):
        if not np.isfinite(r["atr15"]) or d == 0:
            continue
        out.append({"ts": int(r["ts"]), "day": r["day"], "dir": int(d),
                    "atr": float(r["atr15"]), "er": float(r["er15"]),
                    "fz": float(r["fz"]), "regime": r["regime"], "session": r["session"],
                    "ext": float(r["ext15"]) if np.isfinite(r["ext15"]) else 0.0})
    return out


def run(name, sigs, stop_k=1.0, targ_k=2.0, hold=30, **kw):
    """The stop/target are ATR-scaled per signal, so one config means the same THING in a 6pt regime
    and a 30pt one. simulate() takes fixed points, so signals are bucketed by their own ATR."""
    sigs = [dict(s, stop_pt=max(2.0, stop_k * s["atr"]),
                 targ_pt=(targ_k * s["atr"] if targ_k else None)) for s in sigs]
    keep, skipped = simulate(sigs, stop_pt=None, max_hold_min=hold, **kw)
    sc = score(keep, name)
    sc["signals"] = len(sigs)
    sc["skipped_overlap"] = skipped
    return keep, sc


def splits(trades):
    out = {}
    for key in ("regime", "session"):
        d = {}
        for t in trades:
            d.setdefault(t[key], []).append(t)
        out[key] = {k: score(v, k) for k, v in sorted(d.items())}
    d = {}
    for t in trades:
        d.setdefault(t["day"], []).append(t)
    out["day"] = {k: score(v, k) for k, v in sorted(d.items())}
    return out


def main():
    df = load_feat()
    print("regime mix:", df["regime"].value_counts().to_dict())
    print("atr cuts:", df["atr_cuts"].iloc[0])
    board, allsplits = [], {}
    for name, fn in BUILDERS.items():
        sigs = fn(df)
        trades, sc = run(name, sigs)
        board.append(sc)
        allsplits[name] = splits(trades)
        pd.DataFrame(trades).to_csv(f"{DIR}/trades_{name}.csv", index=False)
        print(f"{name:8s} sig={sc['signals']:5d} n={sc['n']:4d} net=${sc['net']:9.2f} "
              f"win={sc['win_pct']}% $/tr={sc['per_trade']}")
    json.dump({"board": board, "splits": allsplits,
               "regime_mix": df["regime"].value_counts().to_dict(),
               "atr_cuts": df["atr_cuts"].iloc[0]},
              open(f"{DIR}/cands.json", "w"), indent=1)
    print(f"\n→ {DIR}/cands.json")


if __name__ == "__main__":
    main()
