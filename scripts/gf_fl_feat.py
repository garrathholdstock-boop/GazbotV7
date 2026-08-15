#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 0a: build the minute feature table off the FULL PARQUET LAKE.

Every later step (label audit, candidate hunt, sweeps, placebo, robustness) reads this ONE cached
table so nothing silently re-derives on a different window. capture.db is NOT touched: it holds 5
trading days and would shrink the sample by 5x with no error.

One row per traded MINUTE of MNQ, 2026-07-05..2026-08-14 (28 tick-days; the 07-18..07-23 hole
between the V5 archive and the V7 capture is REAL and is left as a gap, not bridged).

Columns
  ts        bucket start (UTC epoch); the bucket covers [ts, ts+60)
  flow      net aggressor size (buy - sell) inside the bucket   <- the census's `flow`
  fz        z-score of `flow` vs the trailing 2h of the SAME statistic, EXCLUDING the current
            bucket, min 30 buckets  <- the census's `fz`; |fz|>=1 is what makes a run FLOW-LED
  close/hi/lo/vol/nt   traded price + size inside the bucket
  atr15     mean per-minute true range over the trailing 15 min (points)
  er15      efficiency ratio over the trailing 15 min (|net| / sum|1-min steps|)
  ext15     trailing 15-min close-to-close move (points)
  rvol      bucket volume / mean bucket volume over the trailing 60 min
  fwdN      close(T+N) - close(T); mfeN/maeN the best/worst excursion inside those N minutes
            (NULL when the forward window is not contiguous — no straddling a session break)

Writes reports/friday_v7/sections/fl/feat.csv
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl/feat.csv"
Z_LOOKBACK_MIN = 120     # trailing 2 hours, in minute buckets
Z_MIN_BUCKETS = 30


def main():
    con = connect(symbol="MNQ")
    df = con.execute("""
        -- ⚠ `CAST(ts_ms/1000 AS BIGINT)/60*60` is a NO-OP in DuckDB (`/` is FLOAT division), which
        -- silently buckets by SECOND, not minute — the exact instrument bug the V7 scope flags.
        -- `//` is the integer divide. Verified below: 28 days must give ~40k rows, not 1.9M.
        SELECT (ts_ms // 60000) * 60                                              AS ts,
               SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) AS flow,
               SUM(size)                                                          AS vol,
               COUNT(*)                                                           AS nt,
               MAX(price)                                                         AS hi,
               MIN(price)                                                         AS lo,
               ARG_MAX(price, ts_ms)                                              AS close,
               ARG_MIN(price, ts_ms)                                              AS open
        FROM ticks GROUP BY 1 ORDER BY 1""").fetchdf()
    df["ts"] = df["ts"].astype("int64")
    print(f"minute buckets: {len(df):,}")

    idx = pd.to_datetime(df["ts"], unit="s", utc=True)
    df["day"] = idx.dt.strftime("%Y-%m-%d")
    df["hour"] = idx.dt.hour
    df["hhmm"] = idx.dt.strftime("%H:%M")

    # ── fz: standardise against the trailing 2h of the same statistic, current bucket EXCLUDED ──
    s = df.set_index(idx)["flow"].astype(float)
    prev = s.shift(1)
    mu = prev.rolling("120min", min_periods=Z_MIN_BUCKETS).mean()
    sd = prev.rolling("120min", min_periods=Z_MIN_BUCKETS).std()
    fz = (s - mu) / sd
    fz[(sd.isna()) | (sd <= 0)] = np.nan
    df["fz"] = fz.values
    df["flow_ratio"] = df["flow"] / df["vol"].replace(0, np.nan)

    # ── contiguity: a bucket is contiguous with the previous one if exactly 60s apart ──────────
    gap = df["ts"].diff().fillna(1e9) > 60
    df["seg"] = gap.cumsum()          # session/segment id; features never cross a seg boundary

    c = df["close"].astype(float)
    tr = (df["hi"] - df["lo"]).astype(float)

    def seg_roll(col, win, fn, minp=None):
        return col.groupby(df["seg"]).transform(
            lambda x: getattr(x.rolling(win, min_periods=minp or win), fn)())

    df["atr15"] = seg_roll(tr, 15, "mean")
    step = c.groupby(df["seg"]).diff().abs()
    net15 = c - c.groupby(df["seg"]).shift(15)
    sum15 = seg_roll(step, 15, "sum")
    df["ext15"] = net15
    df["er15"] = (net15.abs() / sum15.replace(0, np.nan)).clip(0, 1)
    df["rvol"] = df["vol"] / seg_roll(df["vol"].astype(float), 60, "mean", minp=20)
    df["atr_pct"] = df["atr15"] / c

    # ── forward outcomes (contiguous only) ────────────────────────────────────────────────────
    for n in (5, 10, 15, 30):
        fwd = c.groupby(df["seg"]).shift(-n) - c
        df[f"fwd{n}"] = fwd
        hi = df["hi"].astype(float).groupby(df["seg"]).transform(
            lambda x: x[::-1].rolling(n, min_periods=n).max()[::-1]).shift(-1)
        lo = df["lo"].astype(float).groupby(df["seg"]).transform(
            lambda x: x[::-1].rolling(n, min_periods=n).min()[::-1]).shift(-1)
        df[f"up{n}"] = hi - c
        df[f"dn{n}"] = c - lo

    df.to_csv(OUT, index=False)
    print(f"→ {OUT}")
    print(df[["ts", "day", "flow", "fz", "atr15", "er15", "ext15", "fwd15"]].tail(3).to_string())
    print("\nfz coverage:", int(df["fz"].notna().sum()), "of", len(df))
    print("days:", df["day"].nunique(), df["day"].min(), "..", df["day"].max())


if __name__ == "__main__":
    main()
