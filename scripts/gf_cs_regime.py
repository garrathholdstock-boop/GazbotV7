"""CHOP-DAY SCALP — Step 1: the regime census.

Segments the MNQ tape by REGIME (ATR level + efficiency + range-break) on 30-minute
blocks of 1-minute bars, and by TIME-OF-DAY (overnight/pre-open vs US session post
13:30 UTC).  Never on the clock alone.

Writes reports/friday_v7/sections/cs/regime_blocks.parquet + regime_days.json
"""
from __future__ import annotations

import json
import os

from gazbot7.lake import connect

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs"
START = "2026-07-16"          # depth (10-deep L2) starts here
END = "2026-08-15"

SQL = f"""
WITH b5 AS (
    SELECT bar_ts, open, high, low, close, volume
    FROM bars
    WHERE symbol='MNQ' AND timeframe='5s'
      AND bar_ts >= epoch(TIMESTAMP '{START} 00:00:00')
      AND bar_ts <  epoch(TIMESTAMP '{END} 00:00:00')
),
m1 AS (                                   -- fold 5s -> 1m.  NOT (bar_ts/60)*60 (float div!)
    SELECT bar_ts - bar_ts % 60          AS t,
           arg_min(open, bar_ts)          AS o,
           max(high)                      AS h,
           min(low)                       AS l,
           arg_max(close, bar_ts)         AS c,
           sum(volume)                    AS v
    FROM b5 GROUP BY 1
),
m1x AS (
    SELECT *, lag(c) OVER (ORDER BY t) AS pc FROM m1
),
tr AS (
    SELECT t, o, h, l, c, v,
           greatest(h - l, abs(h - coalesce(pc, o)), abs(l - coalesce(pc, o))) AS tr,
           abs(c - pc) AS step
    FROM m1x
),
roll AS (
    SELECT *,
           avg(tr)  OVER (ORDER BY t ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS atr20,
           sum(step) OVER (ORDER BY t ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS path30,
           abs(c - lag(c, 30) OVER (ORDER BY t))                                AS disp30,
           max(h) OVER (ORDER BY t ROWS BETWEEN 120 PRECEDING AND 1 PRECEDING)  AS hi2h,
           min(l) OVER (ORDER BY t ROWS BETWEEN 120 PRECEDING AND 1 PRECEDING)  AS lo2h
    FROM tr
)
SELECT t,
       to_timestamp(t)                              AS ts,
       strftime(to_timestamp(t), '%Y-%m-%d')        AS day,
       o, h, l, c, v, tr, atr20,
       CASE WHEN path30 > 0 THEN disp30 / path30 END AS er30,
       hi2h, lo2h,
       CASE WHEN h > hi2h THEN 1 ELSE 0 END          AS brk_up,
       CASE WHEN l < lo2h THEN 1 ELSE 0 END          AS brk_dn
FROM roll
ORDER BY t
"""


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    con = connect()
    m = con.execute(SQL).fetchdf()
    m = m.dropna(subset=["atr20", "er30"]).reset_index(drop=True)

    # ---- 30-minute blocks -------------------------------------------------
    m["blk"] = m["t"] - m["t"] % 1800
    g = m.groupby("blk")
    blk = g.agg(day=("day", "first"),
                n=("c", "size"),
                atr=("atr20", "mean"),
                er=("er30", "mean"),
                rng=("h", "max"),
                lo=("l", "min"),
                vol=("v", "sum"),
                brk=("brk_up", "max"),
                brkd=("brk_dn", "max"),
                c0=("c", "first"),
                c1=("c", "last")).reset_index()
    blk = blk[blk["n"] >= 25].copy()          # near-complete blocks only
    blk["range_pt"] = blk["rng"] - blk["lo"]
    blk["net_pt"] = blk["c1"] - blk["c0"]
    blk["rt"] = blk["range_pt"] / blk["atr"]   # range in ATRs
    blk["brk_any"] = ((blk["brk"] == 1) | (blk["brkd"] == 1)).astype(int)
    blk["hour"] = ((blk["blk"] % 86400) // 3600).astype(int)
    blk["minute"] = ((blk["blk"] % 3600) // 60).astype(int)
    blk["tod"] = blk.apply(
        lambda r: "US" if (r["hour"] * 60 + r["minute"]) >= 13 * 60 + 30
        and (r["hour"] * 60 + r["minute"]) < 20 * 60 else "ON", axis=1)

    atr_lo = blk["atr"].quantile(0.33)
    atr_hi = blk["atr"].quantile(0.67)

    def regime(r):
        if r["er"] >= 0.45 and r["brk_any"] == 1:
            return "CLEAN-TREND"
        if r["atr"] >= atr_hi and r["er"] < 0.25:
            return "VIOLENT-WHIPSAW"
        if r["er"] < 0.22 and r["atr"] < atr_lo:
            return "DEAD-CHOP"
        if r["er"] < 0.30:
            return "NORMAL-CHOP"
        return "BUILDING"

    blk["regime"] = blk.apply(regime, axis=1)
    blk.to_csv(f"{OUT}/regime_blocks.csv", index=False)

    # ---- day roll-up ------------------------------------------------------
    d = blk.groupby("day").agg(blocks=("blk", "size"),
                               atr=("atr", "mean"),
                               er=("er", "mean"),
                               day_range=("rng", "max"),
                               day_lo=("lo", "min")).reset_index()
    d["day_range_pt"] = d["day_range"] - d["day_lo"]
    frac = (blk.assign(one=1).pivot_table(index="day", columns="regime",
                                          values="one", aggfunc="sum")
            .fillna(0))
    frac = frac.div(frac.sum(axis=1), axis=0).round(3)
    d = d.merge(frac, on="day", how="left")
    d["chop_frac"] = d.get("DEAD-CHOP", 0) + d.get("NORMAL-CHOP", 0)
    d["daytype"] = d.apply(
        lambda r: "TREND" if r.get("CLEAN-TREND", 0) >= 0.15 else
                  ("CHOP" if r["chop_frac"] >= 0.55 else "MIXED"), axis=1)

    print(f"atr terciles: lo<{atr_lo:.2f}  hi>{atr_hi:.2f}   blocks={len(blk)}")
    print(blk.groupby("regime").agg(n=("blk", "size"), atr=("atr", "mean"),
                                    er=("er", "mean"), rt=("rt", "mean")).round(3).to_string())
    print()
    print(d.round(3).to_string())
    d.to_json(f"{OUT}/regime_days.json", orient="records", indent=1)

    x = blk.groupby(["tod", "regime"]).size().unstack(fill_value=0)
    print()
    print(x.to_string())


if __name__ == "__main__":
    main()
