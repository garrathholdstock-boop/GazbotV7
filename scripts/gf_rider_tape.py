#!/usr/bin/env python3
"""GF RIDER — the shared tape for the pooled sat-out rider study (MNQ).

Built ONCE from the PARQUET LAKE (never capture.db, which is a 5-trading-day rolling window).

★ WHY 5-SECOND BARS AND NOT TICKS. The tick lake holds 28 sessions with a real hole at the V5->V7
seam (2026-07-18..07-23) and nothing at all before 07-05. The 5s BAR stream spans **2026-06-19 ..
2026-08-14 with no gap — 45 sessions**, because v5 kept 5s bars from 06-19 and the lake picks up at
07-16. For a price-only run-catcher that is the correct source: it nearly doubles n and it hands us
a genuine out-of-sample leg (June + early July) that sits entirely BEFORE the census week.

    s5   5-second o/h/l/c/v  — exit racing.  A stop and a target inside the same 5s bar are
         resolved AGAINST the trade, always.
    m1   1-minute bars       — the signal timeframe, matching the live service which samples once
         a minute.  Entry is on the NEXT bar's open after a CLOSED bar triggers, so nothing here
         can enter at a price the rule had not yet seen.
    flow net aggressor per minute, from the TICK lake where it exists (28 of the 45 sessions).
         Anything causal that uses flow is scored only on the days that carry it, and says so.

    PYTHONPATH=src .venv/bin/python scripts/gf_rider_tape.py [--force]
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.lake import connect  # noqa: E402

CACHE = "/home/alphabot/gazbot7/data/gf_rider"
SYM = "MNQ"
VPP = 2.00          # MNQ $2.00 / point.  MGC is $10 — do not cross the wires.
FEE = 1.50          # $1.50 PER ROUND TRIP.  Not per side, not $5, not $2.
SLIP = 0.25         # one MNQ tick crossed per side; charged on entry AND exit.

# ⚠ DuckDB `/` is FLOAT division even on BIGINTs, so `(ts/60)*60` is a NO-OP — the bug that made a
# prior week's tape read 5s bars as 1m bars. `//` is the integer divide. Every bucket here uses `//`.


def build(force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    os.makedirs(CACHE, exist_ok=True)
    m1p, s5p = f"{CACHE}/m1.pkl", f"{CACHE}/s5.pkl"
    if not force and os.path.exists(m1p) and os.path.exists(s5p):
        return pd.read_pickle(m1p), pd.read_pickle(s5p)

    con = connect(symbol=SYM)

    print("loading 5s bars (v5 + lake + hot) ...", flush=True)
    s5 = con.execute("""
        SELECT bar_ts // 5 * 5 AS ts,
               first(open ORDER BY bar_ts) AS o, max(high) AS h,
               min(low) AS l, last(close ORDER BY bar_ts) AS c, sum(volume) AS v
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").df()
    print(f"  5s bars from the lake: {len(s5):,}", flush=True)

    # ── the SUNDAY-REOPEN patch ────────────────────────────────────────────────────────────────
    # The nightly lake mirror skips the Sunday 22:00Z reopen sessions, but capture.db's BAR table
    # keeps 60 days and has them. Two of the sixty sat-out runs (08-09 22:02 and 08-09 23:47) live
    # on exactly such a session, so without this patch the pooled study would silently score 58 of
    # 60 and call it 60. Only days the lake does NOT already have are taken — no double counting.
    have = set(pd.to_datetime(s5["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d"))
    pat = con.execute("""
        SELECT bar_ts // 5 * 5 AS ts, first(open ORDER BY bar_ts) o, max(high) h, min(low) l,
               last(close ORDER BY bar_ts) c, sum(volume) v
        FROM cap.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1 ORDER BY 1""").df()
    pat = pat[~pd.to_datetime(pat["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d").isin(have)]
    if len(pat):
        gained = sorted(set(pd.to_datetime(pat["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d")))
        print(f"  + {len(pat):,} 5s bars from capture.db for {len(gained)} lake-missing "
              f"sessions: {', '.join(gained)}", flush=True)
        s5 = pd.concat([s5, pat]).sort_values("ts").reset_index(drop=True)

    print("rolling 5s -> 1m ...", flush=True)
    s5["m"] = s5["ts"] // 60 * 60
    m1 = s5.groupby("m").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"),
                             c=("c", "last"), v=("v", "sum"), nb=("ts", "size")).reset_index()
    m1 = m1.rename(columns={"m": "ts"})
    s5 = s5.drop(columns=["m"])
    print(f"  1m bars: {len(m1):,}", flush=True)

    print("joining tick flow where it exists ...", flush=True)
    try:
        fl = con.execute("""
            SELECT ts_ms // 1000 // 60 * 60 AS ts,
                   sum(CASE WHEN aggressor='buy' THEN size
                            WHEN aggressor='sell' THEN -size ELSE 0 END) AS fl,
                   count(*) AS nt
            FROM ticks GROUP BY 1""").df()
        m1 = m1.merge(fl, on="ts", how="left")
    except Exception as e:                                   # tick view absent -> flow-free study
        print(f"  no tick flow ({e})")
        m1["fl"], m1["nt"] = np.nan, np.nan
    con.close()

    m1 = enrich(m1)
    m1.to_pickle(m1p)
    s5.to_pickle(s5p)
    return m1, s5


def enrich(m1: pd.DataFrame) -> pd.DataFrame:
    """Everything a CAUSAL entry rule is allowed to look at — trailing only, closed bars only."""
    m1 = m1.sort_values("ts").reset_index(drop=True)
    t = pd.to_datetime(m1["ts"], unit="s", utc=True)
    m1["day"] = t.dt.strftime("%Y-%m-%d")
    m1["hh"] = t.dt.hour + t.dt.minute / 60.0
    m1["dow"] = t.dt.dayofweek

    # session-aware blocks: never let a rolling window straddle a weekend or an overnight hole
    m1["blk"] = (m1["ts"].diff().fillna(60) > 1800).cumsum()
    g = m1.groupby("blk", sort=False)

    pc = g["c"].shift(1)
    m1["tr"] = pd.concat([m1["h"] - m1["l"], (m1["h"] - pc).abs(), (m1["l"] - pc).abs()],
                         axis=1).max(axis=1)
    # ATR on 1-min bars, 30-period (~half an hour of context). This is the UNIT every threshold
    # below is expressed in, so a rule tuned on a 20pt-ATR July day still means something on an
    # 8pt-ATR August one.
    m1["atr"] = m1.groupby("blk")["tr"].transform(lambda s: s.rolling(30, min_periods=15).mean())

    for w in (5, 10, 15, 20, 30):
        m1[f"net{w}"] = m1["c"] - g["c"].shift(w)
        m1[f"path{w}"] = m1.groupby("blk")["tr"].transform(lambda s, w=w: s.rolling(w).sum())
        m1[f"er{w}"] = (m1[f"net{w}"].abs() / m1[f"path{w}"]).replace([np.inf, -np.inf], np.nan)
        m1[f"hh{w}"] = m1.groupby("blk")["h"].transform(lambda s, w=w: s.rolling(w).max())
        m1[f"ll{w}"] = m1.groupby("blk")["l"].transform(lambda s, w=w: s.rolling(w).min())

    m1["fl"] = m1["fl"].fillna(0.0)
    m1["has_flow"] = m1["nt"].notna()
    m1["flow5"] = m1.groupby("blk")["fl"].transform(lambda s: s.rolling(5).sum())
    m1["flow15"] = m1.groupby("blk")["fl"].transform(lambda s: s.rolling(15).sum())
    m1["vol30"] = m1.groupby("blk")["v"].transform(lambda s: s.rolling(30).mean())
    m1["rvol"] = m1["v"] / m1["vol30"]
    # "is vol high FOR NOW" — ATR's percentile inside the trailing 6h. Causal by construction.
    m1["atr_pr"] = m1.groupby("blk")["atr"].transform(
        lambda s: s.rolling(360, min_periods=60).rank(pct=True))
    # the desk's own regime vocabulary, computed the same way the router computes it
    m1["regime"] = regime_of(m1)
    return m1


def regime_of(m1: pd.DataFrame) -> pd.Series:
    """The five buckets the backtest-discipline rule demands, keyed on ATR LEVEL + ER + range-break
    — never on the clock alone. `atr_pr` is the trailing-6h percentile of ATR, `er15` the 15-minute
    efficiency ratio, `brk` whether the last 15m broke the prior 30m range.

    ★ THE CUTS ARE CALIBRATED TO THIS TAPE, NOT GUESSED. MNQ's 15-min ER runs median 0.111, p90
    0.258, p99 0.385 across the 45 sessions. A first pass used the textbook 0.45 "trend" line and
    produced 107 clean-trend minutes out of 55,070 — a bucket that exists on paper and never in the
    data, which would have hidden the whole home-regime question. 0.25 is this instrument's p88."""
    er, ap = m1["er15"], m1["atr_pr"]
    brk = (m1["c"] > m1["hh30"].shift(15)) | (m1["c"] < m1["ll30"].shift(15))
    out = pd.Series("normal-chop", index=m1.index, dtype=object)
    out[(ap < 0.35) & (er < 0.10)] = "dead-chop"
    out[(er >= 0.15) & (er < 0.25)] = "in-between-building"
    out[(er >= 0.25) & (ap >= 0.35)] = "clean-trend"
    out[(er < 0.15) & (ap >= 0.80)] = "violent-whipsaw"
    out[brk & (er >= 0.25)] = "clean-trend"
    out[er.isna() | ap.isna()] = "unknown"
    return out


if __name__ == "__main__":
    m1, s5 = build(force="--force" in sys.argv)
    d = m1.groupby("day").agg(bars=("ts", "size"), atr=("atr", "median"))
    print(d.to_string())
    print(f"\nsessions={m1['day'].nunique()}  span={m1['day'].min()}..{m1['day'].max()}")
    print(f"flow-carrying minutes: {m1['has_flow'].sum():,} of {len(m1):,} "
          f"({m1.loc[m1['has_flow'], 'day'].nunique()} sessions)")
    print(f"median ATR(1m,30) = {m1['atr'].median():.2f}pt")
    print("\nregime mix:\n" + m1["regime"].value_counts().to_string())
