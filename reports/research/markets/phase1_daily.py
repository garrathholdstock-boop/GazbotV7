"""Market suitability research, PHASE 1 (operator 2026-10-26): intraday movement and extremes from daily bars (Yahoo, already on disk).
Read-only. Per market: daily range (pts, % of price, $ per 1 micro contract), how often big days happen, and how directional days are
(body = |close-open| / range: high = trend day, low = chop). Last 3 years and last 12 months."""
import pandas as pd, numpy as np, datetime as dt
Y = "/home/alphabot/gazbot7/data/external/yahoo"
MKT = {"NQ (MNQ)": ("NQF", 2.0), "ES (MES)": ("ESF", 5.0), "RTY (M2K)": ("RTYF", 5.0), "GC (MGC)": ("GCF", 10.0), "BTC spot (MBT proxy)": ("BTCUSD", 0.1)}
def load(f):
    d = pd.read_csv(f"{Y}/{f}_1d.csv")
    ts = d["ts"] if "ts" in d else d["date"]
    d["day"] = pd.to_datetime(ts, unit="s").dt.date
    d = d[(d.high > d.low) & (d.close > 0)]
    if f != "BTCUSD":
        d = d[d.volume > 0]
    return d
rows = []
for name, (f, usd) in MKT.items():
    d = load(f)
    for lab, since in (("3y", dt.date(2023, 9, 12)), ("12m", dt.date(2025, 9, 12))):
        x = d[d.day >= since]
        rng = x.high - x.low; pct = rng / x.close * 100; body = (x.close - x.open).abs() / rng
        med = rng.median()
        rows.append({"market": name, "window": lab, "days": len(x), "med range pts": round(med, 1), "med range %": round(pct.median(), 2),
                     "med $/micro": round(med * usd), "p90 $/micro": round(rng.quantile(.9) * usd), "p99 $/micro": round(rng.quantile(.99) * usd),
                     "days >2x med": f"{(rng > 2 * med).mean():.1%}", "trend days (body>=.6)": f"{(body >= .6).mean():.0%}", "chop days (body<.25)": f"{(body < .25).mean():.0%}",
                     "med body": round(body.median(), 2)})
out = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(out.to_string(index=False))
out.to_csv("/home/alphabot/gazbot7/reports/research/markets/phase1_daily.csv", index=False)
