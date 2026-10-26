"""PHASE 4 (operator 2026-10-26: "better history"): MNQ vs MGC over ~12 months, quarter by quarter, EQUAL RISK (each quarter sized so the
median daily range matches 4 MNQ). Proper FRONT MONTH per session (most 1-min volume) from the raw per-contract IBKR files in data/backfill,
extended with the desk's own 5s capture after the last raw date. MGC starts 2025-09-24 (before that only the thin expiring Oct-25 contract was
pulled - the documented wrong-contract defect); MGC has a gap 2026-01-09..01-21 (no contract file covers it). Read-only."""
import sys, datetime as dt, numpy as np, pandas as pd
src = open("/home/alphabot/gazbot7/reports/research/markets/phase3_compare.py").read().split("\nrows = []")[0]
ns = {}; exec(compile(src, "p3", "exec"), ns)
DF, USD, K = ns["DF"], ns["USD"], 11
def series(sym, start):
    raw = ns["contract_bars"](sym); live = ns["lake_bars"](sym)
    first_live = int(live.ts.min())                     # the desk's own capture is the front month by construction: prefer it wherever it exists
    raw = raw[(raw.ts >= start) & (raw.ts < first_live)]
    d = pd.concat([raw[["ts", "open", "high", "low", "close", "volume", "sess"]], live]).sort_values("ts").drop_duplicates("ts")
    return d
def legs(d, sym):
    bars = list(zip(d.ts.astype(int), d.high.astype(float), d.low.astype(float), d.close.astype(float)))
    atr = DF.atr14(bars); piv = DF.zigzag(bars, atr, lambda leg, a: K * a)
    ts = np.array([b[0] for b in bars]); cl = np.array([b[3] for b in bars]); out = []
    for p0, p1 in zip(piv, piv[1:]):
        i0, i1 = np.searchsorted(ts, p0[0]), np.searchsorted(ts, p1[0])
        if i1 - i0 < 5: continue
        seg = cl[i0:i1 + 1]; dd = p0[2]; size = abs(p1[1] - p0[1]); path = np.abs(np.diff(seg)).sum()
        run = np.maximum.accumulate(seg * dd); ci = min(np.searchsorted(ts, p0[3]), len(cl) - 1)
        out.append((int((p0[0] + 7200) // 86400), size * USD[sym], size / path if path else 0, (run - seg * dd).max() / size if size else 0,
                    max(0.0, dd * (p1[1] - cl[ci])) * USD[sym]))
    return pd.DataFrame(out, columns=["sess", "size_usd", "eff", "pull", "left_usd"])
start = int(dt.datetime(2025, 9, 24, tzinfo=dt.timezone.utc).timestamp())
S = {s: series(s, start) for s in ("MNQ", "MGC")}
LG = {s: legs(S[s], s) for s in S}
qs = [("Q4-25", "2025-09-24", "2025-12-31"), ("Q1-26", "2026-01-01", "2026-03-31"), ("Q2-26", "2026-04-01", "2026-06-30"), ("Q3-26", "2026-07-01", "2026-09-30"), ("Oct-26", "2026-10-01", "2026-10-23")]
rows = []
for lab, a, b in qs:
    sa = (int(dt.datetime.fromisoformat(a + "T00:00:00+00:00").timestamp()) + 7200) // 86400; sb = (int(dt.datetime.fromisoformat(b + "T00:00:00+00:00").timestamp()) + 7200) // 86400
    med = {}
    for s in S:
        d = S[s][(S[s].sess >= sa) & (S[s].sess <= sb)]
        g = d.groupby("sess").agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"), n=("close", "size")); g = g[g.n > 600]
        rng = (g.h - g.l) * USD[s]; body = (g.c - g.o).abs() / (g.h - g.l); med[s] = (g, rng, body)
    ref = med["MNQ"][1].median() * 4
    for s in S:
        g, rng, body = med[s]; n = ref / rng.median(); L = LG[s][(LG[s].sess >= sa) & (LG[s].sess <= sb)]
        rows.append({"quarter": lab, "market": s, "sessions": len(g), "contracts (equal risk)": round(n, 1), "typical day $": round(rng.median() * n),
                     "bad day p90 $": round(rng.quantile(.9) * n), "chop days": f"{(body < .25).mean():.0%}", "legs/sess": round(len(L) / max(len(g), 1), 1),
                     "median leg $": round(L.size_usd.median() * n), "straightness": round(L.eff.median(), 3), "pullback": f"{L.pull.median():.0%}",
                     "$ left/session": round(L.left_usd.median() * n * len(L) / max(len(g), 1))})
t = pd.DataFrame(rows); pd.set_option("display.width", 300); print(t.to_string(index=False))
t.to_csv("/home/alphabot/gazbot7/reports/research/markets/phase4_year.csv", index=False)
