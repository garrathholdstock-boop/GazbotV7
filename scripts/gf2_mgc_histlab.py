#!/usr/bin/env python3
"""GF2 MGC HISTLAB — twelve months of gold, on a tape no gold study has ever opened.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_histlab.py --audit
    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_histlab.py --trigger

★ THE RESOURCE. `data/tape/bars/MGC/backfill_1min.parquet` — 357,692 one-minute MGC bars,
2025-07-27..2026-08-18. Every gold study this desk has run used 16-27 days. This is 184 CLEAN days
once the two defects below are cut out, and it ends (2026-07-29) essentially where our own depth
tape begins (07-16), so the two together are a near-contiguous THIRTEEN MONTHS.

★ TWO DEFECTS FOUND BEFORE USE — both would have produced confident wrong numbers.

  (1) PADDED BARS. The file is on a full 1380-minute grid per day, so every minute that did not
      trade is FORWARD-FILLED as open=high=low=close and volume=0. On 2025-10-07 only hours 0-2 and
      22-23 are real; the other nineteen hours are a flat line at one price. A rolling 60-minute
      high over that is a constant, an ATR over it is ~0, and a break gate reading it fires on the
      first real tick of the day, every day, forever. CUT: keep only `volume > 0` minutes, and only
      days holding >= 1,100 of them.

  (2) THE ROLL, 2026-07-30. Against our own captured quote tape the backfill agrees to a MEDIAN
      0.100pt (one tick) every day up to 07-29, then on 07-30 the mean 1-minute range collapses
      0.48 -> 0.03pt and the price sits 16-43pt BELOW our tape. That is a different, expiring
      contract, not gold. CUT: the history ends 2026-07-29. (This is also why the volume column
      reads 4-230 lots a day in August - the same rolled series. Volume is unusable throughout and
      is used ONLY as the traded/not-traded flag in defect 1.)

★ WHAT THIS TAPE CAN AND CANNOT ANSWER. It has NO book (depth starts 2026-07-16) and NO bid/ask, so
nothing book-conditioned lives here and the spread must be MODELLED, not raced. What it CAN do is
the one thing 27 days cannot: put a price-only trigger in front of a year of gold, across two
completely different volatility regimes (gold ran 3,300 -> 5,600 -> 4,000 over this window).

COSTS. MGC $10.00/pt. Fee $1.50 per ROUND TRIP. Modelled spread 0.30pt per leg (the median measured
on our 4.6M-row depth tape) => $7.50 all-in, the same number the 08-15 section used. Everything is
also reported at 0.15pt and 0.50pt per leg, because a modelled cost is an assumption.
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

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf2"
BACKFILL = "/home/alphabot/gazbot7/data/tape/bars/MGC/backfill_1min.parquet"
VPP, FEE_RT = 10.0, 1.50
SPREAD_PT = 0.30          # per leg, modelled
HIST_END = "2026-07-29"   # the roll
MIN_REAL_MIN = 1100
pd.set_option("display.width", 260)
_C: dict = {}


# ── tape ─────────────────────────────────────────────────────────────────────────────────────────
def load_clean() -> pd.DataFrame:
    if "m" in _C:
        return _C["m"]
    import duckdb
    c = duckdb.connect(); c.execute("SET memory_limit='2GB'")
    df = c.execute(f"""
        SELECT bar_ts, open, high, low, close, volume
        FROM read_parquet('{BACKFILL}')
        WHERE symbol='MGC' AND timeframe='1min' AND volume > 0
        ORDER BY bar_ts
    """).df()
    df["ts"] = pd.to_datetime(df["bar_ts"], unit="s", utc=True)
    df = df.set_index("ts").drop(columns=["bar_ts"])
    df["day"] = df.index.strftime("%Y-%m-%d")
    df = df[df["day"] <= HIST_END]
    good = df.groupby("day").size()
    df = df[df["day"].isin(good[good >= MIN_REAL_MIN].index)]
    _C["m"] = add_regime(df)
    return _C["m"]


def atr(m, n=14):
    prev = m["close"].shift(1)
    tr = pd.concat([m["high"] - m["low"], (m["high"] - prev).abs(), (m["low"] - prev).abs()],
                   axis=1).max(axis=1)
    return tr.rolling(n).mean()


def eff_ratio(close, n=30):
    net = close.diff(n).abs()
    path = close.diff().abs().rolling(n).sum()
    return (net / path).replace([np.inf, -np.inf], np.nan)


def session_of(idx):
    mod = idx.hour * 60 + idx.minute
    out = pd.Series("ASIA", index=idx)
    out[(mod >= 6 * 60) & (mod < 13 * 60 + 30)] = "LONDON"
    out[(mod >= 13 * 60 + 30) & (mod < 21 * 60)] = "US"
    return out


def add_regime(m: pd.DataFrame) -> pd.DataFrame:
    """★ ATR is normalised BY PRICE before it is cut into levels. Gold ran 3,300 -> 5,600 -> 4,000
    across this year, so a 2.0pt ATR is a violent tape in 2025 and a quiet one in 2026. A raw-point
    ATR cut would silently become a CALENDAR filter. The 27-day study could ignore this; a
    twelve-month one cannot. Cuts are gold's own percentiles, on this tape."""
    m = m.copy()
    m["atr"] = atr(m)
    m["atrp"] = m["atr"] / m["close"] * 10000.0          # ATR in basis points of price
    m["er"] = eff_ratio(m["close"])
    m["session"] = session_of(m.index).values
    a_lo, a_hi = m["atrp"].quantile(0.33), m["atrp"].quantile(0.67)
    e_lo, e_hi = m["er"].quantile(0.40), m["er"].quantile(0.75)
    reg = pd.Series("NORMAL_CHOP", index=m.index)
    reg[(m["atrp"] <= a_lo) & (m["er"] <= e_hi)] = "DEAD_CHOP"
    reg[(m["atrp"] >= a_hi) & (m["er"] >= e_hi)] = "CLEAN_TREND"
    reg[(m["atrp"] >= a_hi) & (m["er"] <= e_lo)] = "VIOLENT_WHIPSAW"
    reg[(m["atrp"].between(a_lo, a_hi, inclusive="neither")) & (m["er"] >= e_hi)] = "BUILDING"
    m["regime"] = reg.values
    m.attrs["cuts"] = {"atrp_p33": float(a_lo), "atrp_p67": float(a_hi),
                       "er_p40": float(e_lo), "er_p75": float(e_hi)}
    return m


# ── the bar racer ────────────────────────────────────────────────────────────────────────────────
class BarRacer:
    """Race an exit forward on 1-minute OHLC. A minute bar does not record whether its high or its
    low came first, so the order of checks is STOP -> TRAIL -> TARGET -> extend the peak: every
    ambiguity is resolved AGAINST the trade, exactly as the 5-second racer does.

    Entry is at the NEXT bar's OPEN (the signal bar's close is only known at its right edge - the
    `resample` trap from 2026-08-14, which cost one gold gate half its result). Costs: the entry
    crosses half a spread and so does the exit, plus the $1.50 fee.
    """

    def __init__(self, m: pd.DataFrame, spread_pt: float = SPREAD_PT):
        self.o = m["open"].to_numpy(); self.h = m["high"].to_numpy()
        self.l = m["low"].to_numpy(); self.c = m["close"].to_numpy()
        self.idx = m.index
        self.pos = {t: i for i, t in enumerate(m.index)}
        self.day = m["day"].to_numpy()
        self.n = len(m)
        self.sp = spread_pt

    def race(self, i0: int, side: int, *, stop_pts, target_pts=None, arm_pts=None,
             trail_pts=None, cap_min=480, eod=True) -> dict | None:
        """i0 = index of the SIGNAL bar; entry fills at bar i0+1's open."""
        i = i0 + 1
        if i >= self.n - 1:
            return None
        fill_in = self.o[i] + side * self.sp / 2.0
        stop = fill_in - side * stop_pts
        target = fill_in + side * target_pts if target_pts is not None else None
        peak = 0.0; mae = 0.0; armed = False; trail_lvl = None
        d0 = self.day[i]
        last = min(i + int(cap_min), self.n - 1)
        for k in range(i, last + 1):
            if eod and self.day[k] != d0:
                k -= 1
                break
            adverse = self.l[k] if side > 0 else self.h[k]
            favour = self.h[k] if side > 0 else self.l[k]
            mae = min(mae, side * (adverse - fill_in))
            if (adverse <= stop) if side > 0 else (adverse >= stop):
                return self._out(i, k, side, fill_in, stop, "STOP", peak, mae)
            if armed and trail_lvl is not None and ((adverse <= trail_lvl) if side > 0 else (adverse >= trail_lvl)):
                return self._out(i, k, side, fill_in, trail_lvl, "TRAIL", peak, mae)
            if target is not None and ((favour >= target) if side > 0 else (favour <= target)):
                return self._out(i, k, side, fill_in, target, "TARGET", peak, mae)
            peak = max(peak, side * (favour - fill_in))
            if arm_pts is not None and peak >= arm_pts:
                armed = True
            if armed and trail_pts is not None:
                trail_lvl = fill_in + side * (peak - trail_pts)
        k = max(i, min(k, self.n - 1))
        return self._out(i, k, side, fill_in, self.c[k], "TIME_CAP", peak, mae)

    def _out(self, i, k, side, fill_in, px_out, reason, peak, mae):
        fill_out = px_out - side * self.sp / 2.0
        return {"i_in": i, "i_out": k, "ts": self.idx[i], "fill_in": round(float(fill_in), 3),
                "fill_out": round(float(fill_out), 3), "reason": reason,
                "minutes": int(k - i),
                "true_pnl": round(side * (fill_out - fill_in) * VPP - FEE_RT, 2),
                "gross_pt": round(side * (px_out - self.o[i]), 3),
                "mfe_pt": round(float(peak), 2), "mae_pt": round(float(mae), 2)}


def run(racer: BarRacer, e: pd.DataFrame, **kw) -> pd.DataFrame:
    """Stops/targets/trails are ATR MULTIPLES, scaled per entry."""
    keys = {"stop": "stop_pts", "target": "target_pts", "arm": "arm_pts", "trail": "trail_pts"}
    rows = []
    for r in e.itertuples():
        a = float(r.atr)
        if not np.isfinite(a) or a <= 0:
            continue
        args = {v: kw[k] * a for k, v in keys.items() if kw.get(k) is not None}
        res = racer.race(int(r.i), int(r.side), cap_min=kw.get("cap_min", 480), **args)
        if res is None:
            continue
        rows.append({**{c: getattr(r, c) for c in e.columns if c != "ts"}, **res})
    return pd.DataFrame(rows)


def stat(d, col="true_pnl") -> dict:
    if d is None or d.empty:
        return {"n": 0, "net": 0.0, "win": 0.0, "per": 0.0, "med": 0.0, "days": 0}
    v = d[col]
    return {"n": int(len(v)), "net": round(float(v.sum()), 0),
            "win": round(100.0 * float((v > 0).mean()), 1), "per": round(float(v.mean()), 2),
            "med": round(float(v.median()), 2),
            "days": int(d["day"].nunique()) if "day" in d else 0}


def line(lbl, s, extra=""):
    return (f"  {lbl:<44} n={s['n']:>5}  {s['days']:>3}d  net ${s['net']:>9,.0f}  "
            f"{s['per']:>7.2f}/tr  win {s['win']:>5.1f}%  med {s['med']:>7.2f}  {extra}")


# ── the trigger, price-only ──────────────────────────────────────────────────────────────────────
def breaks(m: pd.DataFrame, *, look=60, margin_atr=0.10, cool=45, fade=True) -> pd.DataFrame:
    """Same trigger as the 08-15 section: close beyond its own `look`-minute extreme by
    margin_atr x ATR. The extreme is over bars STRICTLY BEFORE the signal bar."""
    d = m
    hi = d["high"].rolling(look).max().shift(1)
    lo = d["low"].rolling(look).min().shift(1)
    ok = hi.notna() & lo.notna() & d["atr"].notna()
    up = ok & (d["close"] >= hi + margin_atr * d["atr"])
    dn = ok & (d["close"] <= lo - margin_atr * d["atr"])
    sig = np.where(up, 1, np.where(dn, -1, 0))
    pos = np.nonzero(sig)[0]
    rows, last = [], {}
    idx = d.index
    for i in pos:
        brk = int(sig[i]); side = -brk if fade else brk
        t = idx[i]
        if side in last and (t - last[side]).total_seconds() < cool * 60:
            continue
        last[side] = t
        rows.append({"i": int(i), "ts": t, "side": side, "brk": brk,
                     "level": float(hi.iloc[i] if brk > 0 else lo.iloc[i]),
                     "atr": float(d["atr"].iloc[i]), "atrp": float(d["atrp"].iloc[i]),
                     "er": float(d["er"].iloc[i]) if np.isfinite(d["er"].iloc[i]) else np.nan,
                     "regime": d["regime"].iloc[i], "session": d["session"].iloc[i],
                     "day": d["day"].iloc[i]})
    return pd.DataFrame(rows)


def audit():
    m = load_clean()
    print("=" * 126)
    print("GF2 HISTLAB — the twelve-month gold tape, after both defects are cut out")
    print("=" * 126)
    print(f"minutes {len(m):,}   days {m['day'].nunique()}   {m['day'].min()} .. {m['day'].max()}")
    bpd = m.groupby("day").size()
    print(f"real minutes/day: median {bpd.median():.0f}  min {bpd.min():.0f}  max {bpd.max():.0f}")
    print(f"price range over the window: {m['low'].min():.1f} .. {m['high'].max():.1f}")
    print(f"\ncuts (gold's own percentiles, ATR in BASIS POINTS of price): {m.attrs['cuts']}")
    print("\nregime census:")
    g = m.groupby("regime").agg(minutes=("close", "size"), atr_pt=("atr", "median"),
                                atrp_bp=("atrp", "median"), er=("er", "median"))
    g["share%"] = (100 * g["minutes"] / len(m)).round(1)
    print(g.sort_values("minutes", ascending=False).round(3).to_string())
    print("\nregime x session:")
    print(pd.crosstab(m["regime"], m["session"]).to_string())
    print("\nATR in POINTS by calendar quarter — why the ATR cut had to be normalised by price:")
    m2 = m.copy(); m2["q"] = m2.index.to_period("Q").astype(str)
    print(m2.groupby("q").agg(minutes=("close", "size"), px=("close", "median"),
                              atr_pt=("atr", "median"), atr_bp=("atrp", "median")).round(3).to_string())
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    ap.parse_args()
    audit()
