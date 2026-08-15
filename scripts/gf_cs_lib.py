"""CHOP-DAY SCALP — shared tape helpers.

Tick loading (cached) + first-touch barrier resolution on the real tick path.
Every exit anywhere in this study goes through `race()` / `resolve()`: the stop and
the target race each other tick by tick, in order.  No MFE is ever reported as a win.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

CACHE = "/home/alphabot/gazbot7/data/cache_gf_cs"
FEAT = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs/feat"

# ---- venue truth (DATA CONTRACT) -------------------------------------------
VPP_MNQ = 2.00        # $ per point, MNQ
FEE_RT = 1.50         # $ per ROUND TRIP.  not 5, not 2, not per side
TICK = 0.25           # MNQ tick size

DAYS = ["2026-07-16", "2026-07-17", "2026-07-24",
        "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31",
        "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07",
        "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"]
IS_DAYS = DAYS[:13]                 # in-sample  2026-07-16 .. 2026-08-07
OOS_DAYS = DAYS[13:]                # out-of-sample: THIS WEEK 08-10 .. 08-14


def ticks(day: str) -> tuple[np.ndarray, np.ndarray]:
    """(ts_seconds_float, price) for one day, ascending.  Cached to .npz."""
    os.makedirs(CACHE, exist_ok=True)
    path = f"{CACHE}/{day}.npz"
    if os.path.exists(path):
        z = np.load(path)
        return z["t"], z["p"]
    from gazbot7.lake import connect
    con = connect()
    df = con.execute(
        "SELECT ts_ms, price FROM ticks WHERE symbol='MNQ' "
        f"AND ts_ms >= epoch_ms(TIMESTAMP '{day} 00:00:00') "
        f"AND ts_ms <  epoch_ms(TIMESTAMP '{day} 00:00:00' + INTERVAL 1 DAY) "
        "ORDER BY ts_ms").fetchdf()
    t = df["ts_ms"].to_numpy(np.float64) / 1000.0
    px = df["price"].to_numpy(np.float64)
    np.savez(path, t=t, p=px)
    return t, px


def feat(day: str) -> pd.DataFrame:
    """The 5s feature tape for a day.  DuckDB reads the parquet (pandas has no
    parquet engine on this box)."""
    import duckdb
    return duckdb.sql(f"SELECT * FROM '{FEAT}/{day}.parquet' ORDER BY t").df()


def race(tt, pp, t0: float, up: float, dn: float, horizon: float):
    """First-touch race from t0.  Returns (hit, t_hit, px_hit) where hit is
    'UP' / 'DN' / 'TIME'.  `up`/`dn` are absolute price barriers."""
    i0 = np.searchsorted(tt, t0, side="left")
    i1 = np.searchsorted(tt, t0 + horizon, side="right")
    if i1 <= i0:
        return "TIME", t0 + horizon, np.nan
    seg = pp[i0:i1]
    u = np.flatnonzero(seg >= up)
    d = np.flatnonzero(seg <= dn)
    iu = u[0] if u.size else np.inf
    idn = d[0] if d.size else np.inf
    if iu == np.inf and idn == np.inf:
        return "TIME", tt[i1 - 1], seg[-1]
    if iu < idn:
        return "UP", tt[i0 + int(iu)], up
    if idn < iu:
        return "DN", tt[i0 + int(idn)], dn
    # same tick touched both (a gap through the whole band): the adverse one wins
    return "BOTH", tt[i0 + int(iu)], np.nan


def entry_fill(tt, pp, t_sig: float, side: str, max_wait: float = 5.0):
    """Market entry: the first print at/after the signal, crossed one tick adverse."""
    i = np.searchsorted(tt, t_sig, side="left")
    if i >= tt.size or tt[i] > t_sig + max_wait:
        return None
    px = pp[i]
    return (px + TICK) if side == "LONG" else (px - TICK), tt[i]


def pnl_usd(side: str, entry: float, exit_px: float, qty: int = 1) -> float:
    """Tick-honest $: $2.00/pt on MNQ, minus $1.50 per round trip."""
    pts = (exit_px - entry) if side == "LONG" else (entry - exit_px)
    return pts * VPP_MNQ * qty - FEE_RT * qty


def stats(df: pd.DataFrame, col: str = "net") -> dict:
    if df.empty:
        return dict(n=0, net=0.0, win=float("nan"), per=float("nan"))
    return dict(n=int(len(df)), net=round(float(df[col].sum()), 2),
                win=round(100.0 * float((df[col] > 0).mean()), 1),
                per=round(float(df[col].mean()), 2))
