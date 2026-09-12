#!/usr/bin/env python3
"""GF2 MGC — THE LONG HISTORY. Validate, then open, the 1-minute gold backfill nobody has used.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_hist.py --validate
    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_hist.py --build

★ WHAT THIS IS. `data/tape/bars/MGC/backfill_1min.parquet` holds 357,692 one-minute MGC bars from
2025-07-27 to 2026-08-18 — 320 trading days, thirteen months. Every gold study this desk has ever
run used 16-27 days. Nothing has touched this file: `lake.connect()` globs `*.parquet` so it is
already inside the `bars` view, and `lake.coverage()` actually CRASHES on it (it tries to parse
'backfill_1day' as a date), which is presumably why nobody noticed it was there.

★ IT IS NOT A DROP-IN REPLACEMENT AND I AM NOT GOING TO PRETEND IT IS. Three limits, stated first:
  1. NO BOOK. There is no depth before 2026-07-16, so nothing book-conditioned can be tested here.
     What CAN be tested is the price-only TRIGGER, which is the part a 27-day sample cannot validate.
  2. NO SPREAD. One-minute OHLC has no bid/ask, so the honest $7.50 round trip must be MODELLED
     (0.30pt x 2 legs + $1.50) rather than raced. I charge it as a fixed haircut and also show the
     result at 2x that cost, because a modelled spread is an assumption and assumptions get stressed.
  3. NO INTRABAR PATH. A minute bar does not say whether its high or its low came first. Every
     ambiguity is resolved AGAINST the trade (stop before target, always), same rule as the 5s racer.
★ AND ONE DATA DEFECT, FOUND BEFORE USE: the VOLUME column collapses to near-zero from 2026-07-31
  onward (whole days totalling 4-230 lots against a June median of ~116k). Prices are continuous
  across that seam; volume is not. NOTHING here may use volume. Verified below, not assumed.

MGC $10.00/pt · fee $1.50/RT · modelled spread 0.30pt x 2 legs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7 import lake  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf2"
BACKFILL = "/home/alphabot/gazbot7/data/tape/bars/MGC/backfill_1min.parquet"
VPP, FEE_RT, SPREAD_PT = 10.0, 1.50, 0.30
pd.set_option("display.width", 260)


def load_hist() -> pd.DataFrame:
    import duckdb
    c = duckdb.connect(); c.execute("SET memory_limit='2GB'")
    df = c.execute(f"""
        SELECT bar_ts, open, high, low, close, volume
        FROM read_parquet('{BACKFILL}') WHERE symbol='MGC' AND timeframe='1min'
        ORDER BY bar_ts
    """).df()
    df["ts"] = pd.to_datetime(df["bar_ts"], unit="s", utc=True)
    df = df.set_index("ts").drop(columns=["bar_ts"])
    df["day"] = df.index.strftime("%Y-%m-%d")
    return df


def validate() -> dict:
    """Does the backfill agree with the tape we captured ourselves? Two checks, both from scratch."""
    h = load_hist()
    print("=" * 120)
    print("BACKFILL AUDIT — 1-minute MGC bars")
    print("=" * 120)
    print(f"rows {len(h):,}   {h.index.min()} .. {h.index.max()}   days {h['day'].nunique()}")
    bpd = h.groupby("day").size()
    print(f"bars/day: median {bpd.median():.0f}  p10 {bpd.quantile(.1):.0f}  max {bpd.max():.0f} "
          f"(a full CME gold session is 1380 minutes)")

    # 1. the volume defect
    v = h.groupby("day")["volume"].sum()
    print(f"\nVOLUME DEFECT: days with total volume < 1,000 lots: {int((v < 1000).sum())} of {len(v)}")
    bad = v[v < 1000]
    print(f"  first such day {bad.index.min()}   last {bad.index.max()}   "
          f"contiguous run from {v[v.index >= '2026-07-31'].index.min()}: "
          f"{int((v[v.index >= '2026-07-31'] < 1000).mean() * 100)}% of days after 07-31")
    print("  -> VOLUME IS UNUSABLE. Nothing in this study reads it.")

    # 2. price agreement against our own quote-mid tape on the overlap
    sys.path.insert(0, os.path.dirname(__file__))
    from gf_mgc_tape import build_tape
    m, _ = build_tape()
    j = h[["close", "high", "low"]].join(m[["close", "high", "low"]], how="inner",
                                         lsuffix="_bf", rsuffix="_q").dropna()
    d = (j["close_bf"] - j["close_q"])
    print(f"\nPRICE AGREEMENT vs our own depth-quote-mid minute bars:")
    print(f"  overlapping minutes {len(j):,}   ({j.index.min().date()} .. {j.index.max().date()})")
    print(f"  corr(close) {j['close_bf'].corr(j['close_q']):.6f}")
    print(f"  median |diff| {d.abs().median():.3f} pt   p95 {d.abs().quantile(.95):.3f} pt   "
          f"mean bias {d.mean():+.3f} pt")
    rng_bf = (j["high_bf"] - j["low_bf"]); rng_q = (j["high_q"] - j["low_q"])
    print(f"  1-min RANGE: backfill mean {rng_bf.mean():.3f} pt  vs quote-mid {rng_q.mean():.3f} pt "
          f"(ratio {rng_bf.mean()/max(rng_q.mean(),1e-9):.2f}x)")
    print("  (a TRADE-tape range is a touch wider than a MID range - that is the spread, and it is")
    print("   the right sign. A ratio far from ~1 would mean a different instrument or timeframe.)")

    # 3. continuity across contract rolls — gaps in the close-to-close series
    cc = h["close"].diff().abs()
    big = cc[cc > 20]
    print(f"\nCONTINUITY: close-to-close jumps > 20pt: {len(big)}  "
          f"(largest {cc.max():.1f} pt at {cc.idxmax() if len(cc) else '-'})")
    print(f"  overnight/session gaps are expected; a CONTRACT ROLL would show as one huge step.")
    res = {"rows": len(h), "days": int(h["day"].nunique()),
           "span": [str(h.index.min()), str(h.index.max())],
           "overlap_minutes": len(j), "corr": round(float(j["close_bf"].corr(j["close_q"])), 6),
           "median_abs_diff": round(float(d.abs().median()), 3),
           "mean_bias": round(float(d.mean()), 3),
           "range_ratio": round(float(rng_bf.mean() / max(rng_q.mean(), 1e-9)), 3),
           "volume_dead_days": int((v < 1000).sum())}
    json.dump(res, open(f"{OUT}/hist_audit.json", "w"), indent=1)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    validate()
