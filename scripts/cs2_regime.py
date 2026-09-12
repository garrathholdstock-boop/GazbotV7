"""CHOP-SCALP 2026-08-25 — step 1: regime segmentation of the tape.

Builds 1-min bars from the lake's 5s bars for MNQ, computes ATR-14, 30-min efficiency
ratio (ER), range-break, and VWAP-slope; classifies every 30-min block into one of
five regimes; classifies each DAY. Writes cs2/regime_blocks.csv + cs2/regime_days.json.

Regime keys (ATR level + ER + range-break, NOT the clock):
  DEAD_CHOP  ATR < atr_lo  and ER < er_lo
  CHOP       ER < er_lo  (ATR >= atr_lo)
  BUILD      er_lo <= ER < er_hi
  TREND      ER >= er_hi and no violent reversal
  WHIPSAW    ER >= er_lo but range/|net| very high with sign flips  (violent)
"""
import glob, json, os, sys
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/sections/cs2"
os.makedirs(OUT, exist_ok=True)
SYM = "MNQ"

def bars_1m(days):
    con = duckdb.connect()
    files = [f"{GB}/data/tape/bars/{SYM}/{d}.parquet" for d in days]
    files = [f for f in files if os.path.exists(f)]
    q = f"""
    SELECT bar_ts, open, high, low, close, volume
    FROM read_parquet({files!r})
    WHERE symbol='{SYM}' AND timeframe='5s'
    ORDER BY bar_ts
    """
    df = con.execute(q).df()
    df["m"] = (df.bar_ts // 60) * 60
    g = df.groupby("m").agg(open=("open", "first"), high=("high", "max"),
                            low=("low", "min"), close=("close", "last"),
                            volume=("volume", "sum")).reset_index()
    g = g.rename(columns={"m": "ts"})
    return g

def feats(g):
    g = g.sort_values("ts").reset_index(drop=True)
    pc = g.close.shift(1)
    tr = np.maximum(g.high - g.low, np.maximum((g.high - pc).abs(), (g.low - pc).abs()))
    g["atr14"] = tr.rolling(14).mean()
    for w in (15, 30, 60):
        net = (g.close - g.close.shift(w)).abs()
        path = g.close.diff().abs().rolling(w).sum()
        g[f"er{w}"] = np.where(path > 0, net / path, np.nan)
        g[f"net{w}"] = g.close - g.close.shift(w)
        g[f"rng{w}"] = g.high.rolling(w).max() - g.low.rolling(w).min()
    # vwap of the UTC day, and its 15-min slope in ATR units
    day = (g.ts // 86400)
    tp = (g.high + g.low + g.close) / 3
    g["_pv"] = tp * g.volume
    g["vwap"] = g.groupby(day)._pv.cumsum() / g.groupby(day).volume.cumsum()
    g["vwap_slope15"] = (g.vwap - g.vwap.shift(15))
    g["atr_rel"] = g.atr14 / g.atr14.rolling(1380, min_periods=200).median()
    g["ext_atr"] = (g.close - g.vwap) / g.atr14
    return g.drop(columns=["_pv"])

def classify(row, er_lo, er_hi):
    """ATR LEVEL is measured RELATIVE to the trailing 1-session median (atr_rel), never in absolute
    points: MNQ ATR-14 ran ~20pt in late July and ~7pt in mid-August, so an absolute floor would
    label the whole of August dead and the whole of July violent. ER is the direction axis."""
    if not np.isfinite(row.er30) or not np.isfinite(row.atr_rel):
        return "NA"
    if row.er30 >= er_hi:
        return "TREND"
    if row.er30 < er_lo:
        if row.atr_rel >= 1.50:
            return "WHIPSAW"          # violent and going nowhere
        return "DEAD_CHOP" if row.atr_rel < 0.70 else "CHOP"
    return "BUILD"

if __name__ == "__main__":
    days = sorted(os.path.basename(f)[:-8] for f in glob.glob(f"{GB}/data/tape/bars/{SYM}/2026-*.parquet"))
    print(f"[bars] {len(days)} day-files {days[0]}..{days[-1]}", flush=True)
    g = feats(bars_1m(days))
    ER_LO, ER_HI = 0.20, 0.40
    g["regime"] = [classify(r, ER_LO, ER_HI) for r in g.itertuples()]
    g["date"] = pd.to_datetime(g.ts, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    g["hh"] = pd.to_datetime(g.ts, unit="s", utc=True).dt.hour
    g["blk"] = (g.ts // 1800) * 1800
    g.to_csv(f"{OUT}/bars_1m.csv", index=False)

    # 30-min block roll-up
    b = g.groupby("blk").agg(date=("date", "first"), n=("ts", "size"),
                             atr=("atr14", "median"), atr_rel=("atr_rel", "median"),
                             er30=("er30", "median"),
                             net=("close", lambda s: s.iloc[-1] - s.iloc[0]),
                             rng=("high", "max"), lo=("low", "min"),
                             vol=("volume", "sum")).reset_index()
    b["rng"] = b.rng - b.lo
    mode = g.groupby("blk").regime.agg(lambda s: s.value_counts().idxmax())
    b["regime"] = b.blk.map(mode)
    b.to_csv(f"{OUT}/regime_blocks.csv", index=False)

    # day roll-up
    d = g.dropna(subset=["atr14"]).groupby("date").agg(
        n=("ts", "size"), atr=("atr14", "median"),
        first=("close", "first"), last=("close", "last"),
        hi=("high", "max"), lo=("low", "min"), vol=("volume", "sum")).reset_index()
    d["net"] = d.last - d["first"]
    d["rng"] = d.hi - d.lo
    d["eff"] = d.net.abs() / d.rng
    # US-session (13:30-20:00Z) only view — the operator's chop days are session days
    us = g[(g.hh >= 13) & (g.hh < 20)].dropna(subset=["atr14"])
    du = us.groupby("date").agg(us_first=("close", "first"), us_last=("close", "last"),
                                us_hi=("high", "max"), us_lo=("low", "min"),
                                us_atr=("atr14", "median")).reset_index()
    du["us_net"] = du.us_last - du.us_first
    du["us_rng"] = du.us_hi - du.us_lo
    du["us_eff"] = du.us_net.abs() / du.us_rng
    d = d.merge(du, on="date", how="left")
    frac = g.pivot_table(index="date", columns="regime", values="ts", aggfunc="size").fillna(0)
    frac = (frac.T / frac.sum(axis=1)).T
    d = d.merge(frac.reset_index(), on="date", how="left")
    d["daytype"] = np.where(d.us_eff >= 0.45, "TREND", np.where(d.us_eff <= 0.25, "CHOP", "MIXED"))
    d.to_csv(f"{OUT}/regime_days.csv", index=False)
    print(d.to_string(index=False))
    print()
    print(b.regime.value_counts().to_string())
