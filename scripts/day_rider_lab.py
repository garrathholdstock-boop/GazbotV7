#!/usr/bin/env python3
"""DAY RIDER LAB — the standing monitor and tuner for the desk's second (and only profitable) book.

    PYTHONPATH=src .venv/bin/python scripts/day_rider_lab.py [--sweep] [--exits]

Operator, 2026-08-15: *"i also didnt see any analysis in the report on the mnq day rider ... this
could become a critical piece of trading gear. we need to be monitoring and fine tuning."*

He is right and the gap is embarrassing: in the week to 08-14 the rider made **+$1,617.50 on 5
trades** while the six-gate tournament lost **-$325.00 on 108** — take the rider out and the week is
red — and it has no section of its own, no monitor, and no tuning surface. It is mentioned inside
other people's chapters and audited once by a rev2 script. That is not oversight of a critical
component.

★ WHAT THIS ANSWERS, in the order that matters:
  1. THE LIVE RECORD — every trade it has actually taken, and how it exited.
  2. DETECTION — across every session in the lake, how often does the LIVE detector fire, and what
     does firing look like versus sitting out? This is where the n is: 5 trades is nothing, but 55
     sessions of detector behaviour is a real sample.
  3. THE EXIT — the entries are fixed; what would holding, trailing or claiming have produced on
     them? The desk has found three times this week that the exit is where the money is.
  4. TUNING — the ER/RT threshold plateau, swept, with the best CONSTANT as the control.

★ DISCIPLINE, and each of these is a trap this desk has already fallen into:
  · Gate on `DriftRead.confirmed`, NEVER `.ok` — `ok` only means "enough data to say anything", and
    gating on it enters EVERY session and manufactures a fake edge ([[drift-ok-is-not-confirmed]]).
  · `direction` is a STRING ("UP"/"DOWN"/""), not a sign.
  · Score against the best CONSTANT (always-long / always-short), never a coin flip — a directional
    signal on a drifting sample beats 50% for free.
  · MFE is not a win rate: report MAE beside it, because the operator WATCHES and can claim, and a
    move he could have claimed is only real if the stop did not come first.
  · MNQ is $2.00/pt and the fee is $1.50/RT. Unlike gold, MNQ's spread is one tick, so there is no
    $7.50 cost correction here — but never copy this constant to MGC.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7 import drift, lake  # noqa: E402

VPP, FEE_RT, LOTS = 2.0, 1.50, 2
OPEN_MIN, FLAT_MIN = 13 * 60 + 30, 20 * 60 + 40
DB = "/home/alphabot/gazbot7/data/gazbot7.db"


def minute_bars() -> pd.DataFrame:
    con = lake.connect(symbol="MNQ")
    b = con.execute("SELECT bar_ts, open, high, low, close FROM bars "
                    "WHERE symbol='MNQ' ORDER BY bar_ts").df()
    b["ts"] = pd.to_datetime(b["bar_ts"], unit="s", utc=True)
    m = b.set_index("ts").resample("1min").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    return m.dropna()


def sessions(m: pd.DataFrame):
    for day, dm in m.groupby(m.index.date):
        s = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=OPEN_MIN)
        e = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=FLAT_MIN)
        w = dm.loc[s:e]
        if len(w) >= 90:
            yield str(day), w


ENTRY_CUTOFF_MIN = 90       # live: no new entry after 15:00 UTC (= +90 from the 13:30 open)


def detect(win: pd.DataFrame, upto: int = ENTRY_CUTOFF_MIN):
    """FIRST CONFIRMATION, scanning minute by minute — because that is what the live rider does.

    ★★2026-08-15 THIS WAS WRONG AND IT INVERTED THE RESULT. The first version sampled the detector
    ONCE at +60min. The live service polls every minute from the 13:30 open and enters on the FIRST
    confirmation, which CLAUDE.md records as 13:38-14:09 across 31 validated sessions — i.e. 20-50
    MINUTES EARLIER than a +60 snapshot, on a different price.

    Worse, efficiency OSCILLATES across the 0.15 floor (0.157 -> 0.114 -> 0.150 -> 0.158 inside 8
    minutes is recorded in day_rider.py), so a single late snapshot MISSES sessions the live rider
    caught and then dropped below the floor. That is why the snapshot version found 15 fires where
    the desk's own 35-session study found 35, and why it scored the armed trail BELOW hold when the
    validated measurement has it ABOVE ($7,341 vs $6,544).

    Returns (DriftRead, index-into-win) so the caller enters at the price the rider entered at.
    """
    for i in range(15, min(len(win), upto) + 1):
        bars = [(int(ts.value // 10**9), r["high"], r["low"], r["close"])
                for ts, r in win.iloc[:i].iterrows()]
        r = drift.compute(bars)
        if r.confirmed and r.direction:
            return r, i - 1
    return None


def outcome(win: pd.DataFrame, i: int, side: int) -> dict:
    seg = win.iloc[i:]
    if len(seg) < 5:
        return {}
    e = float(seg["close"].iloc[0])
    g = LOTS * VPP
    mfe = float(side * ((seg["high"].max() if side > 0 else seg["low"].min()) - e))
    mae = float(side * ((seg["low"].min() if side > 0 else seg["high"].max()) - e))
    fin = float(side * (seg["close"].iloc[-1] - e))
    return {"entry": e, "final$": fin * g - FEE_RT * LOTS, "mfe$": mfe * g - FEE_RT * LOTS,
            "mae$": mae * g, "fin_pt": fin, "mfe_pt": mfe, "mae_pt": mae}


def study(m: pd.DataFrame, upto: int = 60) -> pd.DataFrame:
    rows = []
    for day, win in sessions(m):
        hit = detect(win)
        r, i = (hit if hit else (None, 0))
        row = {"day": day, "fired": r is not None, "entry_min": i}
        if r is not None:
            sd = 1 if r.direction == "UP" else -1
            row.update({"dir": sd, "eff": round(r.efficiency, 3), "rt": round(r.roundtrip, 3),
                        "atr": round(r.atr, 1), **outcome(win, i, sd)})
        for nm, sd in (("long", 1), ("short", -1)):
            row[f"const_{nm}$"] = outcome(win, i, sd).get("final$", np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def live_record():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    d = pd.read_sql("SELECT date(closed_at) day, side, qty, entry_price, exit_price, pnl_usd, "
                    "exit_reason FROM trades WHERE gate='day_rider' AND data_quality IS NULL "
                    "ORDER BY closed_at", c)
    c.close()
    return d


def report(df: pd.DataFrame, upto: int, verbose=True):
    f = df[df.fired]
    if not len(f):
        print(f"  detect @+{upto}m: 0 of {len(df)} sessions fired")
        return None
    al, ash = df["const_long$"].dropna(), df["const_short$"].dropna()
    best_const, best_hit = max(al.sum(), ash.sum()), max((al > 0).mean(), (ash > 0).mean()) * 100
    hit = (f["final$"] > 0).mean() * 100
    if verbose:
        print(f"  {'day':<12}{'dir':>4}{'eff':>6}{'rt':>6}{'final$':>10}{'MFE$':>10}{'MAE$':>10}")
        for _, r in f.iterrows():
            print(f"  {r['day']:<12}{'UP' if r['dir'] > 0 else 'DN':>4}{r['eff']:>6.2f}"
                  f"{r['rt']:>6.2f}{r['final$']:>10.2f}{r['mfe$']:>10.2f}{r['mae$']:>10.2f}")
    print(f"\n  DETECT @+{upto}m · fired {len(f)}/{len(df)} sessions ({len(f)/len(df):.0%})")
    print(f"    direction held to the 20:40 flat : {hit:.1f}%")
    print(f"    total ${f['final$'].sum():>9.2f}   median ${f['final$'].median():>8.2f}   "
          f"per fired day ${f['final$'].mean():>7.2f}")
    print(f"    ★ MFE (a WATCHING operator's ceiling): total ${f['mfe$'].sum():>9.2f}  "
          f"median ${f['mfe$'].median():>8.2f}")
    print(f"    worst MAE ${f['mae$'].min():>9.2f}  median MAE ${f['mae$'].median():>8.2f}")
    print(f"    CONTROL best constant ${best_const:>9.2f} ({best_hit:.1f}%) — "
          f"long ${al.sum():.0f} / short ${ash.sum():.0f}")
    print(f"    ⇒ edge over the best constant: {hit - best_hit:+.1f}pp on hit rate, "
          f"${f['final$'].sum() - best_const:+,.0f} on dollars")
    return {"n": len(f), "hit": hit, "total": f["final$"].sum(), "edge_pp": hit - best_hit}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="ER/RT threshold plateau")
    ap.add_argument("--exits", action="store_true", help="what other exits would have made")
    a = ap.parse_args()

    m = minute_bars()
    print(f"  MNQ {m.index.min():%Y-%m-%d} .. {m.index.max():%Y-%m-%d} · "
          f"{m.index.normalize().nunique()} days · ${VPP:.2f}/pt · {LOTS} lots · "
          f"session {OPEN_MIN//60}:{OPEN_MIN%60:02d}→{FLAT_MIN//60}:{FLAT_MIN%60:02d} UTC")
    print(f"  detector: gazbot7.drift.compute (the LIVE one) — ER>={drift.ER_MIN}, RT>={drift.RT_MIN}\n")

    lr = live_record()
    print(f"  ══ 1. THE LIVE RECORD — {len(lr)} trades, ${lr['pnl_usd'].sum():,.2f} ══")
    for _, r in lr.iterrows():
        print(f"    {r['day']}  {r['side']:<5} q{r['qty']:g}  {r['entry_price']:>9.2f} → "
              f"{r['exit_price']:>9.2f}  ${r['pnl_usd']:>8.2f}  {r['exit_reason']}")
    print(f"    exits used: {dict(lr['exit_reason'].value_counts())}")

    print(f"\n  ══ 2. DETECTION — the LIVE thresholds across every session ══")
    base = study(m, 60)
    report(base, 60)

    if a.exits:
        print(f"\n  ══ 3. THE EXIT — the entries are FIXED; what would each exit have made? ══")
        print("  The live rider does NOT hold to the close: it arms an ATR trail (4xATR ahead, 2xATR")
        print("  off peak), the operator CLAIMS, and 20:40 is the hard floor. Section 2 measured")
        print("  hold-to-close, which is the one policy the desk does not run. So price them all.")
        m2 = m
        rows = []
        for day, win in sessions(m2):
            hit = detect(win)
            if hit is None:
                continue
            r, i = hit
            sd = 1 if r.direction == "UP" else -1
            seg = win.iloc[i:]
            e = float(seg["close"].iloc[0])
            atr = max(r.atr, 1e-9)
            g = LOTS * VPP
            px = seg["close"].to_numpy()
            hi, lo = seg["high"].to_numpy(), seg["low"].to_numpy()
            fav = sd * (px - e)
            peak = np.maximum.accumulate(sd * ((hi if sd > 0 else lo) - e))
            out = {"day": day}
            # (a) hold to the clock
            out["hold"] = fav[-1] * g - FEE_RT * LOTS
            # (b) the LIVE rule: arm at 4xATR ahead, then trail 2xATR off the peak
            armed, exit_v = False, None
            for k in range(len(px)):
                if not armed and peak[k] >= 4.0 * atr:
                    armed = True
                if armed and fav[k] <= peak[k] - 2.0 * atr:
                    exit_v = fav[k]; break
            out["live_trail"] = (exit_v if exit_v is not None else fav[-1]) * g - FEE_RT * LOTS
            # (c) tighter arm/trail variants
            for arm, tr in ((2.0, 1.0), (3.0, 1.5), (2.0, 2.0)):
                armed, ev = False, None
                for k in range(len(px)):
                    if not armed and peak[k] >= arm * atr:
                        armed = True
                    if armed and fav[k] <= peak[k] - tr * atr:
                        ev = fav[k]; break
                out[f"trail_{arm:g}/{tr:g}"] = (ev if ev is not None else fav[-1]) * g - FEE_RT * LOTS
            # (d) the operator watching: claim at the peak (ORACLE ceiling, cheats)
            out["claim_peak(oracle)"] = peak[-1] * g - FEE_RT * LOTS
            rows.append(out)
        d = pd.DataFrame(rows).set_index("day")
        print(f"\n  {'exit policy':<22}{'total$':>11}{'per day$':>11}{'green':>8}{'worst$':>11}")
        for c in d.columns:
            print(f"  {c:<22}{d[c].sum():>11,.0f}{d[c].mean():>11,.0f}"
                  f"{int((d[c] > 0).sum()):>4}/{len(d):<3}{d[c].min():>11,.0f}")
        print("\n  ⚠ claim_peak is an ORACLE — it exits at the high-water mark, which is only")
        print("    knowable afterwards. It is the CEILING a watching operator plays against, not a result.")

    if a.sweep:
        print(f"\n  ══ 4. TUNING — is the live threshold on a plateau or a cliff? ══")
        print(f"  {'ER':>6}{'RT':>6}{'fired':>7}{'held%':>7}{'total$':>10}{'MFE$':>10}")
        er0, rt0 = drift.ER_MIN, drift.RT_MIN
        try:
            for er in (0.05, 0.10, 0.15, 0.20, 0.25):
                for rt in (0.35, 0.45, 0.55):
                    drift.ER_MIN, drift.RT_MIN = er, rt
                    d = study(m, 60)
                    f = d[d.fired]
                    mark = "  ← LIVE" if (er, rt) == (er0, rt0) else ""
                    if not len(f):
                        print(f"  {er:>6.2f}{rt:>6.2f}{0:>7}{'—':>7}{'—':>10}{'—':>10}{mark}")
                        continue
                    print(f"  {er:>6.2f}{rt:>6.2f}{len(f):>7}{(f['final$'] > 0).mean()*100:>7.1f}"
                          f"{f['final$'].sum():>10.2f}{f['mfe$'].sum():>10.2f}{mark}")
        finally:
            drift.ER_MIN, drift.RT_MIN = er0, rt0
    return 0


if __name__ == "__main__":
    sys.exit(main())
