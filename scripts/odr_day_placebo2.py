#!/usr/bin/env python3
"""ODR day-classifier: the SEARCH-AWARE placebo, the gated A/B, and the shared-classifier question.

The first pass searched 8 features x 17 quantiles x 2 directions = 272 candidate day-rules and then
placebo'd the WINNER. That p-value is uncorrected: with 272 tries, a 1-in-30 result is what you
EXPECT from noise. The honest control is to run the ENTIRE SEARCH against shuffled day labels and
ask how often the search finds something as good — that prices in the hunting.

Also here:
  · gated (60-63) vs ungated (54-57) on the OVERLAPPING window only, never all-time.
  · the stop-width axis on the full family (gated + ungated) so it matches the operator's framing.
  · whether ONE day-classifier could serve both odr (MNQ) and the MGC run-catcher.

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/odr_day_placebo2.py
"""
from __future__ import annotations
import sqlite3
import sys

import numpy as np
import pandas as pd

pd.set_option("display.width", 250)
rng = np.random.default_rng(8142026)

D = pd.read_json("/home/alphabot/gazbot7/data/odr_day_classifier.json", orient="index")
if D.index.astype(str).str.isnumeric().all():
    D.index = pd.to_datetime(D.index.astype(np.int64), unit="ms").strftime("%Y-%m-%d")
D = D.sort_index()
FEATS = ["atr_1300", "on_range", "on_net", "on_er", "on_roundtrip", "run_in_er", "run_in_range", "gap"]


def best_rule(feat_df: pd.DataFrame, y: pd.Series):
    """The exact search from pass 1: best net over feature x quantile x direction."""
    best = None
    for f in FEATS:
        x = feat_df[f].astype(float)
        ok = x.notna()
        xs, ys = x[ok], y[ok]
        if len(xs) < 20:
            continue
        for q in np.arange(0.10, 0.91, 0.05):
            thr = xs.quantile(q)
            for d in (">=", "<="):
                keep = xs >= thr if d == ">=" else xs <= thr
                if keep.sum() < 8 or keep.sum() > len(xs) - 4:
                    continue
                net = ys[keep].sum()
                if best is None or net > best[0]:
                    best = (net, f, d, thr, int(keep.sum()))
    return best


print("═══ G. SEARCH-AWARE PLACEBO — shuffle the day labels, re-run the WHOLE search ═══")
print("  Pass 1 searched 272 rules then placebo'd the winner. This prices in the hunting itself.")
real_best = best_rule(D, D.net)
print(f"  real best rule: {real_best[1]} {real_best[2]} {real_best[3]:.4g} "
      f"→ ${real_best[0]:+,.0f} on {real_best[4]}d  (of ${D.net.sum():+,.0f} unfiltered)")

NSHUF = 2000
shuf_best = []
y = D.net.values.copy()
for _ in range(NSHUF):
    yp = pd.Series(rng.permutation(y), index=D.index)
    b = best_rule(D, yp)
    if b:
        shuf_best.append(b[0])
shuf_best = np.array(shuf_best)
p = (shuf_best >= real_best[0]).mean() * 100
print(f"  same search on {NSHUF} SHUFFLED label sets: median best ${np.median(shuf_best):+,.0f} · "
      f"90th pct ${np.percentile(shuf_best,90):+,.0f} · max ${shuf_best.max():+,.0f}")
print(f"  → the real search is beaten by {p:.1f}% of PURE-NOISE searches.")
print(f"  → VERDICT: {'NOT separable from noise once the search is priced in' if p > 10 else 'survives the search-aware control'}")

# how much of the "edge" is just dropping days — a no-feature control that keeps the same count
k = real_best[4]
drop_best = np.array([np.sort(rng.permutation(y))[-k:].sum() for _ in range(2000)])
print(f"  reference: the BEST possible {k}-day subset (cheating oracle) = ${np.sort(y)[-k:].sum():+,.0f}")

# ───────────────── H. gated vs ungated, OVERLAPPING window only ─────────────────
print("\n═══ H. THE DRIFT GATE (sims 60-63) — overlapping window ONLY ═══")
con = sqlite3.connect("/home/alphabot/gazbot7/data/shadow.db")
r = pd.read_sql("""SELECT t.strategy,t.side,t.entry_ts,t.entry_price,t.exit_reason,r.real_pnl
                   FROM shadow_trades t JOIN shadow_real r ON r.trade_id=t.id
                   WHERE t.strategy LIKE 'odr%'""", con)
con.close()
r["day"] = pd.to_datetime(r.entry_ts, unit="s", utc=True).dt.strftime("%Y-%m-%d")
r["gated"] = r.strategy.str.endswith("_g")
r["cell"] = r.strategy.str.replace("_g$", "", regex=True)

gdays = sorted(r[r.gated].day.unique())
print(f"  gated arms exist on: {gdays}  ← {len(gdays)} day(s)")
ov = r[r.day.isin(gdays)]
t = ov.groupby("gated").agg(n=("real_pnl", "size"), net=("real_pnl", "sum"),
                            win=("real_pnl", lambda s: 100 * (s > 0).mean()))
t["per"] = (t.net / t.n).round(2)
t.index = ["UNGATED (54-57)", "GATED (60-63)"]
print(t.round(2).to_string())
print("\n  paired by CELL on the overlapping day:")
pv = ov.pivot_table(index="cell", columns="gated", values="real_pnl", aggfunc=["sum", "size"]).fillna(0)
pv.columns = ["ungated $", "gated $", "ungated n", "gated n"]
print(pv.round(1).to_string())
same = pv["ungated $"].equals(pv["gated $"])
print(f"  → identical per cell: {same}. The gate has rejected ZERO entries so far.")
print("  ⚠ all-time gated vs ungated would compare 1 day against 5 — that measures the CALENDAR, not the gate.")

# ───────────────── I. stop width on the FULL family (matches operator framing) ─────────────────
print("\n═══ I. STOP WIDTH — full odr family (gated + ungated), real book ═══")
r["stop_k"] = r.strategy.str.extract(r"_s(\d+)")[0].map({"20": "2.0xATR", "30": "3.0xATR"})
g = r.groupby("stop_k").agg(n=("real_pnl", "size"), net=("real_pnl", "sum"),
                            win=("real_pnl", lambda s: 100 * (s > 0).mean()))
g["per"] = (g.net / g.n).round(2)
print(g.round(2).to_string())
print("\n  vs the DAY effect, on the same book:")
dd = r.groupby("day").real_pnl.sum()
print(f"    best day ${dd.max():+,.0f} · worst day ${dd.min():+,.0f} · spread ${dd.max()-dd.min():,.0f}")
print(f"    stop-width spread ${g.net.max()-g.net.min():,.0f}  → the DAY effect is "
      f"{(dd.max()-dd.min())/(g.net.max()-g.net.min()):.1f}x the stop-width effect")

# ───────────────── J. does the odr day-label agree with MGC's run-days? ─────────────────
print("\n═══ J. COULD ONE DAY-CLASSIFIER SERVE BOTH odr (MNQ) AND the MGC run-catcher? ═══")
print("  Test: is an MNQ-juicy day also an MGC-juicy day? Compare per-day odr P&L against MGC's")
print("  own daily character on the overlapping tape.")
try:
    sys.path.insert(0, "/home/alphabot/gazbot7/src")
    from gazbot7.lake import connect
    con = connect(symbol="MGC")
    mg = con.execute("""
        SELECT strftime(to_timestamp(bar_ts),'%Y-%m-%d') d,
               max(high)-min(low) rng, count(*) n,
               (arg_max(close,bar_ts)-arg_min(open,bar_ts)) net
        FROM bars WHERE timeframe='5s' GROUP BY 1 HAVING count(*)>500 ORDER BY 1""").df()
    con.close()
    mg = mg.set_index("d")
    both = D[["net", "atr_1300", "on_er"]].join(mg[["rng", "net"]].rename(
        columns={"net": "mgc_net", "rng": "mgc_rng"}), how="inner")
    both["mgc_move"] = both.mgc_net.abs()
    print(f"  overlapping days with BOTH MNQ and MGC tape: {len(both)}")
    if len(both) >= 8:
        print(both.round(3).to_string())
        rho = both.net.rank().corr(both.mgc_move.rank())
        print(f"\n  Spearman(odr day $, |MGC net move|) = {rho:+.3f}  over {len(both)} days")
        print(f"  Spearman(odr day $, MGC day range)  = "
              f"{both.net.rank().corr(both.mgc_rng.rank()):+.3f}")
        print("  → a shared classifier needs the two instruments' good days to COINCIDE.")
    else:
        print("  too few overlapping days to test — MGC coverage is 07-07..07-17 + 08-05..08-14.")
except Exception as e:
    print(f"  MGC arm unavailable: {e}")
