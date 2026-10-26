"""Market suitability research, PHASE 3 (operator 2026-10-26): the same 3-month window for MNQ, MGC, MES, M2K, MYM, MBT from IBKR 1-min bars.
Read-only. Continuous series = per session, the contract with the most 1-min volume that day (front month), no back-adjustment (rolls fall
between sessions and only the session's own bars are used). Movement (range, $ per micro, trend/chop days) + smoothness (the desk's own MIL
detector run on each market: legs/session, leg size, efficiency, deepest pullback, what is left after confirmation).

    .venv/bin/python reports/research/markets/phase3_compare.py
"""
import glob, os, re, sys, datetime as dt
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import mil_detector_fit as DF

GB = "/home/alphabot/gazbot7"
K = 11
SINCE, UNTIL = dt.date(2026, 7, 27), dt.date(2026, 10, 23)
USD = {"MNQ": 2.0, "MGC": 10.0, "MES": 5.0, "M2K": 5.0, "MYM": 0.5, "MBT": 0.1}       # $ per point per micro contract


def contract_bars(sym):
    """front-month 1-min bars from the per-contract backfill files (data/backfill/<SYM>_<expiry>_1min.parquet)"""
    files = glob.glob(f"{GB}/data/backfill/{sym}_*_1min.parquet")
    if not files:
        return None
    c = duckdb.connect(); parts = []
    for f in files:
        ex = re.search(rf"{sym}_(\d+)_1min", f).group(1)
        d = c.execute(f"SELECT ts, open, high, low, close, volume FROM read_parquet('{f}')").df(); d["ex"] = ex; parts.append(d)
    d = pd.concat(parts)
    d["sess"] = (d.ts + 7200) // 86400
    vol = d.groupby(["sess", "ex"]).volume.sum().reset_index()
    best = vol.loc[vol.groupby("sess").volume.idxmax(), ["sess", "ex"]]
    d = d.merge(best, on=["sess", "ex"]).sort_values("ts").drop_duplicates("ts")
    return d


def lake_bars(sym):
    c = duckdb.connect()
    a = c.execute(f"SELECT bar_ts AS ts, open, high, low, close, volume FROM read_parquet('{GB}/data/tape/bars/{sym}/backfill_1min.parquet') WHERE timeframe='1min'").df()
    b = c.execute(f"""SELECT (bar_ts//60)*60 AS ts, arg_min(open,bar_ts) AS open, max(high) AS high, min(low) AS low, arg_max(close,bar_ts) AS close, sum(volume) AS volume
                      FROM read_parquet('{GB}/data/tape/bars/{sym}/2026-*.parquet', union_by_name=true) WHERE timeframe='5s' GROUP BY 1""").df()
    d = pd.concat([a[a.ts < b.ts.min()] if len(b) else a, b]).sort_values("ts").drop_duplicates("ts")
    d["sess"] = (d.ts + 7200) // 86400
    return d


def analyse(sym, d):
    s0 = (int(dt.datetime(SINCE.year, SINCE.month, SINCE.day, tzinfo=dt.timezone.utc).timestamp()) + 7200) // 86400
    s1 = (int(dt.datetime(UNTIL.year, UNTIL.month, UNTIL.day, tzinfo=dt.timezone.utc).timestamp()) + 7200) // 86400
    d = d[(d.sess >= s0) & (d.sess <= s1)]
    g = d.groupby("sess").agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"), n=("close", "size"))
    g = g[g.n > 600]
    if len(g) < 20:
        return {"market": sym, "sessions": len(g), "note": "too little data"}
    rng = g.h - g.l; body = (g.c - g.o).abs() / rng
    bars = list(zip(d.ts.astype(int), d.high.astype(float), d.low.astype(float), d.close.astype(float)))
    atr = DF.atr14(bars); piv = DF.zigzag(bars, atr, lambda leg, a: K * a)
    ts = np.array([b[0] for b in bars]); cl = np.array([b[3] for b in bars]); L = []
    for p0, p1 in zip(piv, piv[1:]):
        i0, i1 = np.searchsorted(ts, p0[0]), np.searchsorted(ts, p1[0])
        if i1 - i0 < 5:
            continue
        seg = cl[i0:i1 + 1]; dirn = p0[2]; size = abs(p1[1] - p0[1])
        path = np.abs(np.diff(seg)).sum()
        run = np.maximum.accumulate(seg * dirn)
        ci = min(np.searchsorted(ts, p0[3]), len(cl) - 1)
        L.append((size, size / max(atr[i0], 0.25), (ts[i1] - ts[i0]) / 60, size / path if path else 0, (run - seg * dirn).max() / size if size else 0,
                  max(0.0, dirn * (p1[1] - cl[ci])) / size if size else 0))
    A = np.array(L); usd = USD[sym]; med = rng.median()
    return {"market": sym, "sessions": len(g), "med range $/micro": round(med * usd), "med range %": round((rng / g.c * 100).median(), 2),
            "trend days": f"{(body >= .6).mean():.0%}", "chop days": f"{(body < .25).mean():.0%}",
            "legs/sess": round(len(L) / len(g), 1), "med leg $/micro": round(np.median(A[:, 0]) * usd), "med leg ATR": round(np.median(A[:, 1]), 1),
            "med leg min": round(np.median(A[:, 2])), "efficiency": round(np.median(A[:, 3]), 3), "pullback % of leg": f"{np.median(A[:, 4]):.0%}",
            "left after confirm": f"{np.median(A[:, 5]):.0%}", "$ left/leg/micro": round(np.median(A[:, 0] * A[:, 5]) * usd),
            "$ left/sess/micro": round(np.median(A[:, 0] * A[:, 5]) * usd * len(L) / len(g))}


rows = []
for sym in ("MNQ", "MGC"):
    rows.append(analyse(sym, lake_bars(sym)))
for sym in ("MES", "M2K", "MYM", "MBT"):
    d = contract_bars(sym)
    rows.append(analyse(sym, d) if d is not None else {"market": sym, "note": "no data pulled"})
out = pd.DataFrame(rows)
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 30)
print(f"SAME WINDOW {SINCE}..{UNTIL}, IBKR 1-min, front month per session")
print(out.to_string(index=False))
out.to_csv(f"{GB}/reports/research/markets/phase3_compare.csv", index=False)
