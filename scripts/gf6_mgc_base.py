"""GF6 — MGC greenfield base frame, built on the RIGHT CONTRACT.

★★★ WHY THIS FILE EXISTS AND DOES NOT JUST CALL lake.connect(symbol="MGC").
The lake's `bars` view for gold unions `backfill_1min.parquet`, which `backfill_to_lake.py` builds by
deduping the seven per-expiry pulls on (symbol,timeframe,bar_ts) **keeping the FIRST** — i.e. the
earliest expiry that has a print at that instant. That is only the front month until liquidity rolls;
for the four-to-five weeks between the volume roll and the actual expiry it keeps the DYING contract.
Measured: **121 of 330 days, 37% of the year tape, are not the front contract.** Those days carry
zero-range minutes and phantom levels (median ATR-14 reads 0.000 in 2025-10 and 2026-04).

So this module rebuilds the series from the per-expiry files directly and takes, for each session,
the contract that actually carried the VOLUME that day.

★ BAR SOURCE = TRADE BARS. Production (`gazbot7.shadow_mgc`) folds md's trade bars, and the 08-25
  finding was that MGC results flip SIGN between the depth mid and the trade tape. The depth-mid
  builder was never shipped, so trade bars are the honest ruler.
★ NO LEFT-EDGE TRAP. Bars are stamped at their OPEN; a signal off the bar stamped T is known at
  T+60s, so every entry in this study fills at the OPEN of bar T+60s.
★ SESSION DAY = 22:00 UTC → 21:00 UTC (the CME gold day). Every lookback is computed INSIDE one
  session day, so no window ever spans the daily halt or a contract roll.
"""
from __future__ import annotations
import glob, os
import numpy as np, pandas as pd, duckdb

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/gf6"
VPP, FEE = 10.0, 1.50          # MGC = $10.00/point. $1.50 per ROUND TRIP.
TICK = 0.10                    # MGC tick = 0.10pt = $1.00

def _front_map(con):
    """day -> expiry that carried the most volume that day."""
    rows = []
    for f in sorted(glob.glob(f"{GB}/data/backfill/MGC_*_1min.parquet")):
        ex = os.path.basename(f).split("_")[1]
        d = con.execute(f"select cast(ts/86400 as int) d, sum(volume) v "
                        f"from read_parquet('{f}') group by 1").fetchdf()
        d["ex"] = ex; rows.append(d)
    a = pd.concat(rows)
    a = a.sort_values(["d", "v"]).groupby("d").last().reset_index()
    return dict(zip(a.d, a.ex))

def build():
    con = duckdb.connect()
    front = _front_map(con)
    frames = []
    for f in sorted(glob.glob(f"{GB}/data/backfill/MGC_*_1min.parquet")):
        ex = os.path.basename(f).split("_")[1]
        d = con.execute(f"select cast(ts as bigint) ts, open, high, low, close, volume "
                        f"from read_parquet('{f}')").fetchdf()
        d["ex"] = ex
        d = d[d.ts.floordiv(86400).map(front).eq(ex)]      # keep only its front days
        frames.append(d)
    hist = pd.concat(frames, ignore_index=True)

    # our own capture, 5s -> 1min. Definitionally the front month (md subscribes to it).
    live = con.execute(f"""
        select cast(bar_ts/60 as bigint)*60 AS ts, first(open order by bar_ts) AS open,
               max(high) AS high, min(low) AS low, last(close order by bar_ts) AS close, sum(volume) AS volume
        from read_parquet('{GB}/data/tape/bars/MGC/2*.parquet')
        where timeframe='5s' group by 1""").fetchdf()
    live["ex"] = "live5s"
    cut = int(hist.ts.max())
    live = live[live.ts > cut]

    df = pd.concat([hist, live], ignore_index=True).drop_duplicates("ts").sort_values("ts")
    df["dt"] = pd.to_datetime(df.ts, unit="s", utc=True)
    # CME gold session day: 22:00Z starts the next session
    df["sday"] = (df.dt + pd.Timedelta(hours=2)).dt.strftime("%Y-%m-%d")
    df["hhmm"] = df.dt.dt.hour * 60 + df.dt.dt.minute
    df["mos"] = ((df.ts + 7200) % 86400) // 60          # minutes into the session
    df = df.reset_index(drop=True)

    # ---- features, all computed INSIDE one session day -------------------------------
    G = df.groupby("sday", group_keys=False)
    pc = G.close.shift(1)
    tr = np.maximum(df.high - df.low, np.maximum((df.high - pc).abs(), (df.low - pc).abs()))
    df["tr"] = tr
    df["atr14"] = G.apply(lambda g: tr.loc[g.index].rolling(14, min_periods=10).mean())
    df["atr60"] = G.apply(lambda g: tr.loc[g.index].rolling(60, min_periods=40).mean())
    for w in (15, 30, 60):
        net = (df.close - G.close.shift(w)).abs()
        path = G.close.diff().abs().groupby(df.sday).rolling(w, min_periods=w).sum().reset_index(0, drop=True)
        df[f"er{w}"] = (net / path.replace(0, np.nan)).clip(0, 1)
        df[f"ret{w}"] = df.close - G.close.shift(w)
    df["hi60"] = G.high.apply(lambda s: s.rolling(60, min_periods=30).max()).shift(1)
    df["lo60"] = G.low.apply(lambda s: s.rolling(60, min_periods=30).min()).shift(1)
    df["hi_d"] = G.high.cummax().shift(1)
    df["lo_d"] = G.low.cummin().shift(1)
    df["vol_ma"] = G.volume.apply(lambda s: s.rolling(60, min_periods=30).mean())

    for h in (15, 30, 60, 120, 240):
        df[f"fwd{h}"] = G.close.shift(-h) - df.close
    os.makedirs(OUT, exist_ok=True)
    df.to_pickle(f"{OUT}/mgc_min.pkl")

    print(f"rows={len(df)} sessions={df.sday.nunique()} {df.sday.min()} -> {df.sday.max()}")
    m = df.assign(mo=df.sday.str[:7]).groupby("mo").agg(
        d=("sday", "nunique"), px=("close", "median"), atr=("atr14", "median"),
        zero=("tr", lambda s: float((s == 0).mean())))
    m["atr_bp"] = 1e4 * m.atr / m.px
    print(m.round(4).to_string())
    return df

if __name__ == "__main__":
    build()
