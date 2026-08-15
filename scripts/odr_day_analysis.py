#!/usr/bin/env python3
"""ODR day-detection: validate the replay, then hunt a CAUSAL day classifier and placebo it.

Reads data/odr_day_classifier.json (41 replayed days) + data/odr_replay_trades.json, and the REAL
forward shadow book from shadow.db. Answers, in order:
  A. Does the replay reproduce the 5 real forward days? (if not, nothing below is worth reading)
  B. How concentrated is the money by day, on BOTH the replay and the real book?
  C. Can any pre-13:00 feature call a juicy day EARLY and CAUSALLY?
  D. PLACEBO: is that rule better than dropping the same NUMBER of days at random?
  E. Power: how many days would it take to prove?

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/odr_day_analysis.py
"""
from __future__ import annotations
import json
import sqlite3
import sys

import numpy as np
import pandas as pd

pd.set_option("display.width", 250)
rng = np.random.default_rng(20260814)

D = pd.read_json("/home/alphabot/gazbot7/data/odr_day_classifier.json", orient="index")
D.index = D.index.astype(str)
if D.index.str.isnumeric().all():                      # epoch-ms index from to_json
    D.index = pd.to_datetime(D.index.astype(np.int64), unit="ms").strftime("%Y-%m-%d")
D = D.sort_index()
T = pd.read_json("/home/alphabot/gazbot7/data/odr_replay_trades.json")

FEATS = ["atr_1300", "on_range", "on_net", "on_er", "on_roundtrip",
         "run_in_er", "run_in_range", "gap"]

# ────────────────── A. validate the replay against the real forward book ──────────────────
con = sqlite3.connect("/home/alphabot/gazbot7/data/shadow.db")
real = pd.read_sql("""SELECT t.strategy, t.entry_ts, r.real_pnl
                      FROM shadow_trades t JOIN shadow_real r ON r.trade_id=t.id
                      WHERE t.strategy IN ('odr_c5_s20','odr_c5_s30','odr_c10_s20','odr_c10_s30')""", con)
con.close()
real["day"] = pd.to_datetime(real.entry_ts, unit="s", utc=True).dt.strftime("%Y-%m-%d")
rd = real.groupby("day").agg(real_n=("real_pnl", "size"), real_net=("real_pnl", "sum"))

print("═══ A. REPLAY VALIDATION — replay vs the REAL forward shadow book ═══")
v = rd.join(D[["n", "net"]].rename(columns={"n": "rep_n", "net": "rep_net"}))
v["sign_ok"] = np.sign(v.real_net) == np.sign(v.rep_net)
print(v.round(1).to_string())
print(f"  → day-sign agreement {v.sign_ok.sum()}/{len(v)} · "
      f"real ${v.real_net.sum():+,.0f} ({v.real_n.sum()} tr) vs replay ${v.rep_net.sum():+,.0f} ({v.rep_n.sum()} tr)")
print(f"  → per-trade: real ${v.real_net.sum()/v.real_n.sum():+.2f}  replay ${v.rep_net.sum()/v.rep_n.sum():+.2f}")

# ────────────────── B. concentration ──────────────────
print("\n═══ B. IS THE MONEY CONCENTRATED IN A MINORITY OF DAYS? ═══")
for label, net in (("REPLAY 41d", D.net), ("REAL 5d", rd.real_net)):
    s = net.sort_values(ascending=False)
    tot = s.sum()
    g, r = s[s > 0], s[s <= 0]
    print(f"  {label:11} total ${tot:+,.0f} · green {len(g)}d ${g.sum():+,.0f} · red {len(r)}d ${r.sum():+,.0f}")
    if len(s) >= 5:
        print(f"              top-5 days ${s.head(5).sum():+,.0f} = {100*s.head(5).sum()/abs(tot) if tot else 0:.0f}% of |total| · "
              f"bottom-5 ${s.tail(5).sum():+,.0f}")
    print(f"              ORACLE (green days only) ${g.sum():+,.0f} over {len(g)} days")

# ────────────────── C. causal single-feature rules ──────────────────
print("\n═══ C. CAN A PRE-13:00 FEATURE CALL THE DAY? (Spearman + best threshold) ═══")
print("  feature          rho    p50-split: LOW half $ / HIGH half $        best causal rule")
res = []
for f in FEATS:
    x = D[f].astype(float)
    ok = x.notna() & D.net.notna()
    if ok.sum() < 20:
        continue
    xs, ys = x[ok], D.net[ok]
    rho = xs.rank().corr(ys.rank())          # Spearman = Pearson on ranks (no scipy on this box)
    med = xs.median()
    lo, hi = ys[xs <= med].sum(), ys[xs > med].sum()
    best = None
    for q in np.arange(0.10, 0.91, 0.05):               # keep days ABOVE / BELOW a quantile
        thr = xs.quantile(q)
        for direction in (">=", "<="):
            keep = xs >= thr if direction == ">=" else xs <= thr
            if keep.sum() < 8 or keep.sum() > len(xs) - 4:
                continue
            net = ys[keep].sum()
            if best is None or net > best[0]:
                best = (net, direction, thr, int(keep.sum()), q)
    res.append(dict(f=f, rho=rho, lo=lo, hi=hi, best=best))
    b = f"keep {best[1]}{best[2]:.4g} → ${best[0]:+,.0f} on {best[3]}d" if best else "—"
    print(f"  {f:15} {rho:+.3f}   ${lo:+8,.0f} / ${hi:+8,.0f}    {b}")

# ────────────────── D. placebo control ──────────────────
print("\n═══ D. PLACEBO — beat dropping the same NUMBER of days at RANDOM (10,000 draws) ═══")
print("  Removing 60% of days looks brilliant whenever the removed 60% lost. This is the control.")
print("  rule                                   kept  rule $     placebo median $   beaten by   verdict")
net_all = D.net.values
for r_ in res:
    if not r_["best"]:
        continue
    net, direction, thr, k, q = r_["best"]
    draws = np.array([rng.choice(net_all, size=k, replace=False).sum() for _ in range(10000)])
    pct = (draws >= net).mean() * 100
    tag = "NOISE" if pct > 10 else ("weak" if pct > 5 else "SURVIVES")
    print(f"  {r_['f']:14} {direction}{thr:>9.4g}          {k:>3}d  ${net:+8,.0f}   ${np.median(draws):+8,.0f}"
          f"        {pct:5.1f}%   {tag}")

# the ORACLE, placebo'd the same way — the upper bound the operator was quoted
g = int((D.net > 0).sum())
draws = np.array([rng.choice(net_all, size=g, replace=False).sum() for _ in range(10000)])
print(f"  {'ORACLE (cheats)':14} {'green-only':>10}          {g:>3}d  ${D.net[D.net>0].sum():+8,.0f}   "
      f"${np.median(draws):+8,.0f}        {(draws>=D.net[D.net>0].sum()).mean()*100:5.1f}%   upper bound")

# ────────────────── E. power ──────────────────
print("\n═══ E. POWER — how many days to prove a day-rule? ═══")
sd = D.net.std()
print(f"  per-DAY sd of odr P&L (41 replayed days) = ${sd:,.0f}")
for eff in (300, 500, 800):
    n = (2.8 * sd / eff) ** 2
    print(f"  to detect a ${eff}/day edge at ~80% power you need ≈ {n:.0f} days ({n/5:.0f} weeks)")
print(f"  the forward shadow book has FIVE days. That is {5/((2.8*sd/500)**2)*100:.0f}% of what a "
      f"$500/day effect needs.")

# ────────────────── F. stop width (the weaker secondary axis) ──────────────────
print("\n═══ F. SECONDARY AXIS — stop width, on the replay (41d) and the real book (5d) ═══")
T["stop_k"] = T.cell.str.extract(r"_s(\d+)")[0].map({"20": "2.0xATR", "30": "3.0xATR"})
g2 = T.groupby("stop_k").agg(n=("pnl", "size"), net=("pnl", "sum"),
                             win=("pnl", lambda s: 100 * (s > 0).mean()))
g2["per"] = g2.net / g2.n
print("  REPLAY 41d:\n" + g2.round(2).to_string())
real["stop_k"] = real.strategy.str.extract(r"_s(\d+)")[0].map({"20": "2.0xATR", "30": "3.0xATR"})
g3 = real.groupby("stop_k").agg(n=("real_pnl", "size"), net=("real_pnl", "sum"),
                                win=("real_pnl", lambda s: 100 * (s > 0).mean()))
g3["per"] = g3.net / g3.n
print("  REAL 5d:\n" + g3.round(2).to_string())
print("\n  per-day, which stop width wins (real book):")
pv = real.pivot_table(index="day", columns="stop_k", values="real_pnl", aggfunc="sum").round(1)
pv["s30_wins"] = pv["3.0xATR"] > pv["2.0xATR"]
print(pv.to_string())
