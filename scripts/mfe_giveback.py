#!/usr/bin/env python3
"""GIVE-BACK STUDY — stage 2: MFE (maximum favourable excursion) accounting.

THE QUESTION (operator, 2026-08-01): on quiet tape, how much profit did each gate FIND
before handing it back? Not "which R scored best" — that is an R sweep and the Friday
report already did it. This measures, for every entry the desk actually took (live) or
would have taken (shadow):

    MFE      = peak unrealised profit reached between entry and the ACTUAL exit
    realised = what we actually kept
    GIVE-BACK = MFE - realised

Windows (desk day boundary = 22:00 UTC = Paris midnight):
    QUIET    22:00 -> 13:30 UTC   (session reopen through to the US cash open)
    US       13:30 -> 21:00 UTC   (the contrast; Wed 07-29 / Thu 07-30 live here)

Populations are kept SEPARATE and never pooled:
    LIVE   data/gazbot7.db trades   — venue truth, fees_usd = $1.50 on all 487
    SHADOW data/shadow.db  shadow_trades + shadow_real.real_pnl (tick-repriced)

CEILING WARNING: MFE is measured on TRADE ticks. A long exits at the bid, so the peak
trade price is not a price we could certainly have sold. Every MFE here is therefore an
UPPER BOUND on reachable money, and every give-back number is an upper bound too.

  PYTHONPATH=src ./.venv/bin/python scripts/mfe_giveback.py
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")

SCR = "/home/alphabot/gazbot7/scratchpad"
VPP = 2.0
FEE_RT = 1.50
QUIET_LO, QUIET_HI = 22 * 3600, 13 * 3600 + 1800   # seconds-of-day UTC


# ── tape ──────────────────────────────────────────────────────────────────────────────
def load_tape():
    import duckdb
    con = duckdb.connect()
    t = con.execute(f"SELECT * FROM '{SCR}/mfe_ticks.parquet' ORDER BY ts_ms").df()
    b = con.execute(f"SELECT * FROM '{SCR}/mfe_bars1m.parquet' ORDER BY ts").df()
    return (t.ts_ms.to_numpy(np.int64), t.price.to_numpy(float), t.signed.to_numpy(float),
            t.sz.to_numpy(float)), b


def window_of(ts_ms: int) -> str:
    sod = (ts_ms // 1000) % 86400
    return "QUIET" if (sod >= QUIET_LO or sod < QUIET_HI) else "US"


def paris_day(ts_ms: int) -> str:
    """Desk day = 22:00 UTC -> 22:00 UTC. Label it by the DATE it ends on."""
    return str(pd.Timestamp((ts_ms + 2 * 3600 * 1000) * 1_000_000, tz="UTC").date())


# ── bar-derived tape metrics at entry (all strictly BACKWARD-looking) ────────────────
def bar_metrics(bars: pd.DataFrame) -> pd.DataFrame:
    """ATR14, realised range 15m, RVOL, ER30 as of each 1-min bar CLOSE.

    ATR14 mirrors deciders._atr (mean true range over the last 14 completed bars).
    All three tape proxies are computed here so they can be raced against each other:
      atr14  — the desk's incumbent proxy
      rr15   — realised high-low range over the trailing 15 bars (points), ATR-independent
      rvol   — volume in the trailing 5 bars / median trailing-60-bar 5-bar volume
      er30   — Kaufman efficiency ratio over the trailing 30 closes
    """
    b = bars.sort_values("ts").reset_index(drop=True)
    h, lo, c, v = b.h.to_numpy(), b.l.to_numpy(), b.c.to_numpy(), b.v.to_numpy()
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))
    b["atr14"] = pd.Series(tr).rolling(14).mean().to_numpy()
    b["rr15"] = (pd.Series(h).rolling(15).max() - pd.Series(lo).rolling(15).min()).to_numpy()
    v5 = pd.Series(v).rolling(5).sum()
    b["rvol"] = (v5 / v5.rolling(60).median()).to_numpy()
    net = np.abs(c - pd.Series(c).shift(30).to_numpy())
    path = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(30).sum().to_numpy()
    b["er30"] = np.where(path > 0, net / path, 0.0)
    # gaps: a bar that follows a >5 min hole has stale rollings — flag it
    b["gap"] = b.ts.diff().fillna(60) > 300
    return b


def attach_metrics(entries: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """ASOF: the last 1-min bar that CLOSED at or before the entry (no lookahead)."""
    bm = bar_metrics(bars)
    bm["close_ms"] = (bm.ts + 60) * 1000
    e = entries.sort_values("entry_ms").reset_index(drop=True)
    out = pd.merge_asof(e, bm[["close_ms", "atr14", "rr15", "rvol", "er30", "gap"]],
                        left_on="entry_ms", right_on="close_ms", direction="backward")
    return out


# ── MFE on the tick path ──────────────────────────────────────────────────────────────
def mfe_scan(entries: pd.DataFrame, tape, horizon_ms: int = 60 * 60 * 1000) -> pd.DataFrame:
    ts, px, _sg, _sz = tape
    n = len(entries)
    cols = {k: np.full(n, np.nan) for k in
            ("mfe_pt", "mae_pt", "t_mfe_s", "mfe_h_pt", "t_mfe_h_s", "ticks", "exit_px_tape")}
    e_ms = entries.entry_ms.to_numpy(np.int64)
    x_ms = entries.exit_ms.to_numpy(np.int64)
    e_px = entries.entry_price.to_numpy(float)
    is_long = (entries.side.to_numpy() == "LONG")
    for i in range(n):
        a = np.searchsorted(ts, e_ms[i], "left")
        b = np.searchsorted(ts, x_ms[i], "right")
        bh = np.searchsorted(ts, e_ms[i] + horizon_ms, "right")
        if b <= a:
            continue
        seg = px[a:b]
        fav = (seg - e_px[i]) if is_long[i] else (e_px[i] - seg)
        j = int(np.argmax(fav))
        cols["mfe_pt"][i] = fav[j]
        cols["mae_pt"][i] = fav.min()
        cols["t_mfe_s"][i] = (ts[a + j] - e_ms[i]) / 1000.0
        cols["ticks"][i] = b - a
        cols["exit_px_tape"][i] = seg[-1]
        if bh > a:
            segh = px[a:bh]
            favh = (segh - e_px[i]) if is_long[i] else (e_px[i] - segh)
            jh = int(np.argmax(favh))
            cols["mfe_h_pt"][i] = favh[jh]
            cols["t_mfe_h_s"][i] = (ts[a + jh] - e_ms[i]) / 1000.0
    for k, vv in cols.items():
        entries[k] = vv
    return entries


# ── populations ───────────────────────────────────────────────────────────────────────
def live_entries() -> pd.DataFrame:
    import duckdb
    con = duckdb.connect()
    con.execute("ATTACH '/home/alphabot/gazbot7/data/gazbot7.db' AS g (TYPE sqlite, READ_ONLY)")
    df = con.execute("""
      SELECT id, gate, side, qty, entry_price, exit_price, pnl_usd, fees_usd, exit_reason,
             CAST(epoch(CAST(opened_at AS TIMESTAMP))*1000 AS BIGINT) AS entry_ms,
             CAST(epoch(CAST(closed_at AS TIMESTAMP))*1000 AS BIGINT) AS exit_ms
      FROM g.trades WHERE symbol='MNQ' ORDER BY opened_at
    """).df()
    df["realised"] = df.pnl_usd            # already net of the $1.50 fee (venue truth)
    df["popn"] = "LIVE"
    return df


def shadow_entries() -> pd.DataFrame:
    import duckdb
    con = duckdb.connect()
    con.execute("ATTACH '/home/alphabot/gazbot7/data/shadow.db' AS s (TYPE sqlite, READ_ONLY)")
    df = con.execute("""
      SELECT t.id, t.strategy AS gate, t.side, t.qty, t.entry_price, t.exit_price,
             t.entry_atr, t.target_r, t.stop_atr_mult, t.exit_reason,
             (t.entry_ts+60)*1000 AS entry_ms, (t.exit_ts+60)*1000 AS exit_ms,
             r.real_pnl
      FROM s.shadow_trades t JOIN s.shadow_real r ON r.trade_id=t.id
      WHERE t.symbol='MNQ' AND r.fill_status='filled' ORDER BY t.entry_ts
    """).df()
    df["realised"] = df.real_pnl           # tick-repriced, net of fee
    df["popn"] = "SHADOW"
    return df


def main():
    tape, bars = load_tape()
    ts = tape[0]
    lo, hi = int(ts.min()), int(ts.max())
    print(f"tape {len(ts):,} ticks  {pd.Timestamp(lo*1_000_000, tz='UTC')} .. "
          f"{pd.Timestamp(hi*1_000_000, tz='UTC')}\n")

    frames = []
    for f in (live_entries(), shadow_entries()):
        f = f[(f.entry_ms >= lo) & (f.exit_ms <= hi)].copy()
        f = attach_metrics(f, bars)
        f = mfe_scan(f, tape)
        frames.append(f)
    df = pd.concat(frames, ignore_index=True)
    df = df[df.ticks.notna() & (df.ticks > 1)].copy()

    df["win"] = df.entry_ms.map(window_of)
    df["day"] = df.entry_ms.map(paris_day)
    df["mfe_usd"] = df.mfe_pt * VPP * df.qty
    df["mfe_h_usd"] = df.mfe_h_pt * VPP * df.qty
    # ATR for live is reconstructed from the tape; shadow carries the desk's own value.
    df["atr"] = df.entry_atr.where(df["popn"] == "SHADOW", df.atr14) if "entry_atr" in df else df.atr14
    df["mfe_r"] = df.mfe_pt / df.atr
    df["mfe_h_r"] = df.mfe_h_pt / df.atr
    df["giveback"] = df.mfe_usd - df.realised
    df["gross"] = df.realised + FEE_RT
    import duckdb as _dd
    _dd.connect().execute(f"COPY (SELECT * FROM df) TO '{SCR}/mfe_entries.parquet' (FORMAT parquet)")

    print(f"scanned {len(df)} entries in the tick window "
          f"(LIVE {int((df["popn"]=="LIVE").sum())} / SHADOW {int((df["popn"]=="SHADOW").sum())})\n")
    for pop in ("LIVE", "SHADOW"):
        d = df[df["popn"] == pop]
        print(f"===== {pop} =====")
        g = d.groupby("win").agg(n=("realised", "size"), reached=("mfe_usd", "sum"),
                                 kept=("realised", "sum"), gb=("giveback", "sum"),
                                 med_mfe_r=("mfe_r", "median"), med_t=("t_mfe_s", "median"))
        g["keep_pct"] = (100 * g.kept / g.reached).round(1)
        print(g.round(1).to_string(), "\n")
    print("wrote", f"{SCR}/mfe_entries.parquet")
    with open(f"{SCR}/mfe_meta.json", "w") as fh:
        json.dump({"tick_lo": lo, "tick_hi": hi, "n": len(df)}, fh)


if __name__ == "__main__":
    main()
