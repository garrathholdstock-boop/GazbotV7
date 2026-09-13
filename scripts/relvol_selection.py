#!/usr/bin/env python3
"""RELATIVE VOLUME AS A DAY/TRADE SELECTION FILTER — the gap the whole sweep pointed at.

Four independent traditions 34 years apart nominated this first, it is the only finding in the
literature sweep with a published DOSE-RESPONSE (-0.02R / +0.08R / +0.38R across RelVol terciles),
and Crabel published the same filter in 1990. This desk has never built a selection filter of ANY
kind: every gate fires whenever its condition is true, on every day.

RelVol(w) = volume in the first w minutes of the US session / the mean of the same window over the
trailing 14 sessions. Computed causally - only sessions strictly before today.

⚠ ROLL-AWARE BY CONSTRUCTION: the ratio's numerator and denominator must be the same contract, and
  capture.db.bars has NO contract column. The MNQ roll moves volume 2.7% -> 17.3% -> 66.4% across
  one Friday-to-Sunday boundary, so a window that straddles a roll compares a dying contract with a
  live one. Sessions within 3 days of a quarterly roll are EXCLUDED and counted, never silently used.
⚠ It is a GATE, not a trade: it cannot invent an edge, it can only decline to pay friction. So the
  test is whether the losses concentrate in the low-RelVol buckets.
"""
from __future__ import annotations
import sqlite3
import numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
OPEN_S = 13 * 3600 + 30 * 60
ROLLS = [pd.Timestamp("2026-09-18").date()]          # quarterly expiries inside the trade record


def session_relvol(window_min: int, lookback: int = 14):
    c = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
    b = pd.read_sql("select bar_ts, volume from bars where symbol='MNQ' and timeframe='5s'", c)
    b["sec"] = b.bar_ts % 86400
    b["day"] = pd.to_datetime(b.bar_ts, unit="s", utc=True).dt.date
    w = b[(b.sec >= OPEN_S) & (b.sec < OPEN_S + window_min * 60)]
    vol = w.groupby("day").volume.sum().sort_index()
    base = vol.shift(1).rolling(lookback, min_periods=8).mean()      # strictly prior sessions
    rv = (vol / base).rename("relvol")
    near_roll = pd.Series([min(abs((d - r).days) for r in ROLLS) <= 3 for d in rv.index],
                          index=rv.index)
    return pd.DataFrame({"relvol": rv, "near_roll": near_roll, "vol": vol})


def main():
    t = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    tr = pd.read_sql("""select qty, pnl_usd, opened_at, gate, exit_reason from trades
                        where closed_at is not null""", t)
    tr["dt"] = pd.to_datetime(tr.opened_at, format="mixed", utc=True)
    tr["day"] = tr.dt.dt.date
    for w in (15, 30, 60):
        rv = session_relvol(w)
        j = tr.merge(rv, left_on="day", right_index=True, how="left")
        # ⚠ .fillna(False) on a merged column yields OBJECT dtype, and `~` on object is INTEGER
        # negation (-1), not logical not - it raised rather than silently inverting, which is luck.
        roll_mask = j.near_roll.fillna(False).astype(bool)
        drop_roll = int(roll_mask.sum())
        j = j[~roll_mask]
        nov = int(j.relvol.isna().sum())
        j = j.dropna(subset=["relvol"])
        s1 = j[j.qty == 1]
        print(f"\n{'='*74}\nRelVol over the first {w} minutes · {s1.day.nunique()} sessions "
              f"· {len(s1)} single-lot trades")
        print(f"  excluded: {drop_roll} trades within 3 days of the roll · {nov} with no RelVol "
              f"(inside the 14-session warm-up)")
        if len(s1) < 60:
            print("  too few to bucket"); continue
        # terciles, matching the published dose-response
        s1 = s1.copy()
        s1["b"] = pd.qcut(s1.relvol, 3, labels=["LOW (quiet)", "MID", "HIGH (busy)"])
        print(f"\n{'bucket':<14}{'relvol':>14}{'n':>6}{'total $':>10}{'$/trade':>10}{'win%':>7}")
        for b, g in s1.groupby("b", observed=True):
            print(f"{str(b):<14}{g.relvol.min():>6.2f}-{g.relvol.max():<7.2f}{len(g):>6}"
                  f"{g.pnl_usd.sum():>10,.0f}{g.pnl_usd.mean():>10.2f}{100*(g.pnl_usd>0).mean():>6.0f}%")
        lo = s1[s1.b == "LOW (quiet)"]
        print(f"\n  ★ skipping the LOW bucket alone: book {s1.pnl_usd.sum():+,.0f} -> "
              f"{s1[s1.b != 'LOW (quiet)'].pnl_usd.sum():+,.0f} "
              f"({-lo.pnl_usd.sum():+,.0f}) on {len(lo)} fewer trades")
        # and the finer cut the report asked for
        s1["d"] = pd.qcut(s1.relvol, 5, labels=False, duplicates="drop")
        print(f"  by quintile $/trade: "
              + " ".join(f"Q{int(k)+1} {v:+.2f}" for k, v in s1.groupby("d").pnl_usd.mean().items()))


if __name__ == "__main__":
    raise SystemExit(main())
