#!/usr/bin/env python3
"""GF_MGC LAB — the shared bench for the gold 2x2 hunt (Friday V7, 2026-08-15).

This is PLUMBING ONLY: load gold's tape, build gold's own feature set, segment gold's own regimes,
and race an exit on TICKS. Every SIGNAL lives in the hunt scripts that import this. That split is
deliberate — RULE 1 of the section scope says every gate must be invented fresh for gold, and the
fastest way to break that rule by accident is to have a signal quietly baked into the loader.

★ THE FIVE TRAPS THIS FILE HAS HARD-CODED AGAINST (all of them have bitten this desk):

 1. `lake.connect()` DEFAULTS TO symbol='MNQ'. Every connect here passes symbol='MGC'.
 2. MGC IS $10.00/POINT and the fee is $1.50 PER ROUND TRIP. Both are module constants, once.
 3. `resample` LABELS A BAR BY ITS LEFT EDGE. A feature read off the bar stamped 10:00 is only
    known at 10:01, so `entry_ts = bar_ts + 60s` everywhere. (Cost the coil gate +$906 -> +$470.)
 4. THE BARS TABLE STACKS TIMEFRAMES. V5 carries 5s AND 1m AND 3m AND 5m for the same day —
    18,662 "bars" in a 24h day where 5s alone can only produce 17,280. Unfiltered, a day's OHLC is
    four interleaved series. Everything here filters `timeframe='5s'`.
 5. capture.db IS A 5-DAY ROLLING WINDOW. We never touch it directly; the lake view spans
    V5 (07-06..07-17) + lake (08-05..08-13) + hot (08-14).

★ THE OOS SPLIT IS FREE AND WE SHOULD USE IT. Gold capture has a real hole 07-18..08-04. Everything
before it (JUL, 10 bar-days) is tape that NO gold study has ever been fitted on — every attack in
`docs/MGC_LEADS_2026-08-14.md` was run on 08-05..08-14. So JUL is a genuine out-of-sample leg, not a
random split of one fitted sample. `split()` returns it by name.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7 import lake  # noqa: E402

SYMBOL = "MGC"
VPP = 10.00          # MGC $/point — NOT MNQ's 2.00
FEE_RT = 1.50        # per ROUND TRIP — not per side, not 5.0
CACHE = "/home/alphabot/gazbot7/data/cache_gf_mgc"

# The capture hole. Days strictly before this are the out-of-sample leg.
OOS_CUT = "2026-08-01"


# ────────────────────────────────────────────────────────────────────────────────
# LOAD
# ────────────────────────────────────────────────────────────────────────────────
def load(force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(minute bars, ticks) over every gold day we hold. Cached to parquet — the lake scan is ~40s
    and a dozen hunt scripts should not each pay it."""
    # pickle, not parquet: this box's venv has neither pyarrow nor fastparquet, and installing an
    # engine to cache a frame we re-read in 40s is not worth the dependency.
    os.makedirs(CACHE, exist_ok=True)
    mp, tp = f"{CACHE}/mgc_1m.pkl", f"{CACHE}/mgc_ticks.pkl"
    if not force and os.path.exists(mp) and os.path.exists(tp):
        return pd.read_pickle(mp), pd.read_pickle(tp)

    con = lake.connect(symbol=SYMBOL)
    bars = con.execute(f"""
        SELECT bar_ts, open, high, low, close, volume
        FROM bars WHERE symbol='{SYMBOL}' AND timeframe='5s' ORDER BY bar_ts
    """).df()
    ticks = con.execute(f"""
        SELECT ts_ms, price, size, aggressor FROM ticks WHERE symbol='{SYMBOL}' ORDER BY ts_ms
    """).df()
    con.close()

    bars["ts"] = pd.to_datetime(bars["bar_ts"], unit="s", utc=True)
    m = bars.set_index("ts").resample("1min").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum")).dropna(subset=["close"])
    m = m[m["close"] > 0]

    ticks["ts"] = pd.to_datetime(ticks["ts_ms"], unit="ms", utc=True)
    ticks = ticks[ticks["price"] > 0].sort_values("ts_ms").reset_index(drop=True)

    m.to_pickle(mp)
    ticks.to_pickle(tp)
    return m, ticks


# ────────────────────────────────────────────────────────────────────────────────
# GOLD'S OWN FEATURES  (nothing here is ported; every window is justified in-line)
# ────────────────────────────────────────────────────────────────────────────────
def features(m: pd.DataFrame) -> pd.DataFrame:
    """Per-minute state. EVERY column is known at the bar's CLOSE, i.e. usable from `ts + 60s`."""
    f = m.copy()
    prev = f["close"].shift(1)
    tr = pd.concat([f["high"] - f["low"], (f["high"] - prev).abs(),
                    (f["low"] - prev).abs()], axis=1).max(axis=1)
    f["atr"] = tr.rolling(14, min_periods=10).mean()
    f["atr60"] = tr.rolling(60, min_periods=40).mean()
    f["atr_pct"] = f["atr"] / f["close"]

    # Efficiency ratio over 30 min: how much of the path became displacement.
    # 30min because gold's runs are HOURS (median 206min in the run census) — a 5-min ER on a grind
    # reads as noise. This is gold's timescale, not MNQ's.
    d = f["close"].diff().abs()
    for w in (15, 30, 60):
        f[f"er{w}"] = (f["close"] - f["close"].shift(w)).abs() / d.rolling(w).sum()
        f[f"net{w}"] = f["close"] - f["close"].shift(w)
        f[f"path{w}"] = d.rolling(w).sum()
    # Roundtrip: path length in ATR units — the day rider's second floor, dimensionless like ER.
    f["rt60"] = f["path60"] / (f["atr"] * 60.0)

    # Structure: where price sits inside its own recent envelope.
    for w in (60, 240):
        f[f"hi{w}"] = f["high"].rolling(w).max()
        f[f"lo{w}"] = f["low"].rolling(w).min()
        rng = (f[f"hi{w}"] - f[f"lo{w}"]).replace(0, np.nan)
        f[f"pos{w}"] = (f["close"] - f[f"lo{w}"]) / rng
        f[f"rng{w}_atr"] = (f[f"hi{w}"] - f[f"lo{w}"]) / f["atr"]

    # Compression: 20-min range against its own 2h median (the coil bouncer's mechanic).
    r20 = f["high"].rolling(20).max() - f["low"].rolling(20).min()
    f["r20"] = r20
    f["coil"] = r20 / r20.rolling(120).median()

    # Vol expansion: current ATR against the same clock-hour's own recent level. Gold's vol has a
    # hard session shape (London + COMEX), so ratioing against a flat 4h window makes every 13:30
    # look like an expansion. This ratios against the SAME minute-of-day on prior days.
    f["mod"] = f.index.hour * 60 + f.index.minute
    f["day"] = f.index.strftime("%Y-%m-%d")
    tod = f.groupby("mod")["atr"].transform(lambda s: s.rolling(5, min_periods=2).median().shift(1))
    f["vol_x"] = f["atr"] / tod

    f["dow"] = f.index.dayofweek
    f["session"] = np.select(
        [f["mod"] < 420, f["mod"] < 810, f["mod"] < 1240],
        ["ASIA", "LONDON", "US"], default="LATE")
    return f


# ────────────────────────────────────────────────────────────────────────────────
# GOLD'S OWN REGIME TAXONOMY
# ────────────────────────────────────────────────────────────────────────────────
def regimes(f: pd.DataFrame) -> pd.DataFrame:
    """Segment on ATR LEVEL x ER x RANGE-BREAK, keyed on GOLD's own percentiles.

    The operator's backtest discipline names five buckets. They are cut here from gold's own
    distribution, never from an MNQ constant — a 0.35 ER floor means something different on a tape
    whose median ER is 0.124. The cuts are terciles, fixed before any P&L was looked at.
    """
    f = f.copy()
    a_lo, a_hi = f["atr"].quantile([0.33, 0.67])
    e_lo, e_hi = f["er30"].quantile([0.33, 0.67])
    f["atr_band"] = np.select([f["atr"] <= a_lo, f["atr"] >= a_hi], ["LOW", "HIGH"], "MID")
    f["er_band"] = np.select([f["er30"] <= e_lo, f["er30"] >= e_hi], ["LOW", "HIGH"], "MID")

    brk = (f["close"] >= f["hi240"].shift(1)) | (f["close"] <= f["lo240"].shift(1))
    f["breakout"] = brk

    f["regime"] = np.select(
        [(f["atr_band"] == "LOW") & (f["er_band"] == "LOW"),
         (f["atr_band"] == "HIGH") & (f["er_band"] == "LOW"),
         (f["er_band"] == "HIGH") & (f["atr_band"] != "LOW"),
         (f["er_band"] == "MID")],
        ["DEAD_CHOP", "VIOLENT_WHIPSAW", "CLEAN_TREND", "BUILDING"],
        default="NORMAL_CHOP")
    return f


def split(day: str) -> str:
    """JUL = the genuine out-of-sample leg (no gold study has ever been fitted on it)."""
    return "JUL_OOS" if day < OOS_CUT else "AUG_IS"


# ────────────────────────────────────────────────────────────────────────────────
# TICK-HONEST EXIT RACE
# ────────────────────────────────────────────────────────────────────────────────
class Tape:
    """Tick arrays with a per-day index, so a race does not scan 2.3M rows to find its start."""

    def __init__(self, ticks: pd.DataFrame):
        self.tk = ticks["ts_ms"].to_numpy(dtype=np.int64)
        self.px = ticks["price"].to_numpy(dtype=float)

    def slice(self, t0_ms: int, cap_ms: int):
        i = int(np.searchsorted(self.tk, t0_ms, "left"))
        j = int(np.searchsorted(self.tk, t0_ms + cap_ms + 1, "right"))
        return self.tk[i:j], self.px[i:j]


def race(tape: Tape, t0_ms: int, side: int, entry: float, *, stop_pts: float,
         target_pts: float | None = None, arm_pts: float | None = None,
         trail_pts: float | None = None, cap_min: float = 240.0,
         be_at_pts: float | None = None) -> dict:
    """Walk ticks forward. The ORDER of stop vs target inside a bar is the whole reason this races
    ticks rather than bar closes — on MNQ resolving it on bar closes flattered results 87%.

    Returns exit price, reason, minutes held, and the excursions (MFE/MAE) INSIDE the trade's own
    life — never a fixed forward window, which counts money we were flat for.
    """
    cap_ms = int(cap_min * 60_000)
    tk, px = tape.slice(t0_ms, cap_ms)
    if len(tk) == 0:
        return {"exit": entry, "reason": "NO_TICKS", "mins": 0.0, "mfe": 0.0, "mae": 0.0}

    stop = entry - side * stop_pts
    target = entry + side * target_pts if target_pts is not None else None
    peak = entry
    mfe = mae = 0.0
    armed = False
    moved_stop = stop

    for i in range(len(tk)):
        p = px[i]
        exc = side * (p - entry)
        mfe = max(mfe, exc)
        mae = min(mae, exc)
        peak = max(peak, exc)

        if be_at_pts is not None and peak >= be_at_pts:
            moved_stop = max(moved_stop, entry) if side > 0 else min(moved_stop, entry)
        if arm_pts is not None and peak >= arm_pts:
            armed = True

        hit_stop = (p <= moved_stop) if side > 0 else (p >= moved_stop)
        if hit_stop:
            return {"exit": moved_stop, "reason": "STOP", "mins": (tk[i] - tk[0]) / 60000.0,
                    "mfe": mfe, "mae": mae}
        if target is not None and ((p >= target) if side > 0 else (p <= target)):
            return {"exit": target, "reason": "TARGET", "mins": (tk[i] - tk[0]) / 60000.0,
                    "mfe": mfe, "mae": mae}
        if armed and trail_pts is not None:
            tl = entry + side * (peak - trail_pts)
            if ((p <= tl) if side > 0 else (p >= tl)):
                return {"exit": tl, "reason": "TRAIL", "mins": (tk[i] - tk[0]) / 60000.0,
                        "mfe": mfe, "mae": mae}
        if tk[i] - tk[0] >= cap_ms:
            return {"exit": p, "reason": "TIME_CAP", "mins": (tk[i] - tk[0]) / 60000.0,
                    "mfe": mfe, "mae": mae}
    return {"exit": px[-1], "reason": "TAPE_END", "mins": (tk[-1] - tk[0]) / 60000.0,
            "mfe": mfe, "mae": mae}


def pnl(side: int, entry: float, exit_: float, lots: int = 1) -> float:
    return round((side * (exit_ - entry) * VPP - FEE_RT) * lots, 2)


# ────────────────────────────────────────────────────────────────────────────────
# SCORING + ROBUSTNESS
# ────────────────────────────────────────────────────────────────────────────────
def score(trades: pd.DataFrame, label: str = "") -> dict:
    if trades is None or len(trades) == 0:
        return {"label": label, "n": 0, "net": 0.0, "win": 0.0, "per": 0.0, "median": 0.0}
    p = trades["pnl"]
    return {"label": label, "n": int(len(p)), "net": round(float(p.sum()), 2),
            "win": round(100.0 * float((p > 0).mean()), 1),
            "per": round(float(p.mean()), 2), "median": round(float(p.median()), 2),
            "days": int(trades["day"].nunique()) if "day" in trades else 0}


def battery(trades: pd.DataFrame) -> dict:
    """strip-best-3 / worst-3, leave-one-day-out worst, per-half, per-leg. The judging rule is
    expectancy + robustness — win% is NEVER a kill criterion here."""
    if len(trades) == 0:
        return {}
    p = trades["pnl"].sort_values()
    out = {
        "strip_best3": round(float(p.iloc[:-3].sum()), 2) if len(p) > 3 else None,
        "strip_worst3": round(float(p.iloc[3:].sum()), 2) if len(p) > 3 else None,
    }
    if "day" in trades:
        byday = trades.groupby("day")["pnl"].sum()
        tot = float(byday.sum())
        out["loo_worst"] = round(tot - float(byday.max()), 2)      # drop the BEST day
        out["days_green"] = round(100.0 * float((byday > 0).mean()), 1)
        out["best_day"] = f"{byday.idxmax()} {byday.max():+.0f}"
        out["worst_day"] = f"{byday.idxmin()} {byday.min():+.0f}"
        legs = trades.groupby(trades["day"].map(split))["pnl"].agg(["count", "sum"])
        out["legs"] = {k: [int(v["count"]), round(float(v["sum"]), 2)] for k, v in legs.iterrows()}
    return out


def placebo(trades: pd.DataFrame, universe: pd.DataFrame, tape: Tape, entry_fn,
            n_runs: int = 40, seed: int = 7) -> dict:
    """Draw the SAME NUMBER of entries at random from the same universe of minutes, with the same
    time-of-day mix, and run them through the same exit. A filter that "wins" by removing losers is
    beaten by random removal — that is the test that killed the router-filtered gold attack."""
    rng = np.random.default_rng(seed)
    real = float(trades["pnl"].sum())
    n = len(trades)
    if n == 0 or len(universe) < n:
        return {"runs": 0}
    beaten = 0
    nets = []
    for _ in range(n_runs):
        idx = rng.choice(len(universe), size=n, replace=False)
        sample = universe.iloc[np.sort(idx)]
        net = float(entry_fn(sample, tape, rng))
        nets.append(net)
        if net >= real:
            beaten += 1
    return {"runs": n_runs, "beaten": beaten, "real": round(real, 2),
            "placebo_mean": round(float(np.mean(nets)), 2),
            "placebo_p90": round(float(np.percentile(nets, 90)), 2)}


def fmt(rows: list[dict], cols: list[str]) -> str:
    """Markdown table."""
    head = "| " + " | ".join(cols) + " |\n|" + "|".join(["---"] * len(cols)) + "|\n"
    body = ""
    for r in rows:
        body += "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n"
    return head + body


if __name__ == "__main__":
    m, t = load(force="--force" in sys.argv)
    f = regimes(features(m))
    print(f"bars {len(m):,}  ticks {len(t):,}  days {f['day'].nunique()}")
    print(f"span {f.index.min()} .. {f.index.max()}")
    print("\nATR/ER percentiles (GOLD's own):")
    print(f[["atr", "er15", "er30", "er60", "rt60", "coil", "vol_x"]]
          .quantile([0.1, 0.33, 0.5, 0.67, 0.9]).round(3).to_string())
    print("\nREGIME CENSUS (minutes):")
    g = f.groupby("regime").agg(mins=("close", "size"), atr=("atr", "median"),
                                er30=("er30", "median"), days=("day", "nunique"))
    g["pct"] = (100 * g["mins"] / len(f)).round(1)
    print(g.round(3).to_string())
    print("\nBY DAY:")
    d = f.groupby("day").agg(mins=("close", "size"), atr=("atr", "median"),
                             er30=("er30", "median"), rng=("close", lambda s: s.max() - s.min()))
    d["leg"] = [split(x) for x in d.index]
    print(d.round(3).to_string())
