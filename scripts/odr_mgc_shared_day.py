#!/usr/bin/env python3
"""★ ONE DAY-CLASSIFIER FOR TWO DESKS? — do MNQ's odr days and MGC's run-days coincide?

Two independent strategies on two instruments both live or die on a minority of days:
  · the MNQ Open Rider (odr_*) — 2 green days paid +$1,748, 3 red days lost -$2,229 (08-10..08-14)
  · the MGC run-catcher       — run-days pay, the rest bleed (docs/MGC_LEADS_2026-08-14.md)
If the SAME days are juicy on both, one detector serves both and is worth more than either gate.
If they are unrelated, we need two detectors and the shared-classifier idea is dead.

MGC "run-ness" is measured the way the run-catcher cares about it: the biggest sustained directional
excursion of the day in DOLLARS at $10.00/point (MGC's multiplier — never MNQ's $2.00).

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/odr_mgc_shared_day.py
"""
from __future__ import annotations
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect

pd.set_option("display.width", 250)
MGC_PPV = 10.0          # MGC = $10.00/point. MNQ = $2.00. Never mix them.

D = pd.read_json("/home/alphabot/gazbot7/data/odr_day_classifier.json", orient="index")
D.index = pd.to_datetime(D.index).strftime("%Y-%m-%d")      # normalise however read_json parsed it
D = D.sort_index()

con = connect(symbol="MGC")
b = con.execute("""SELECT bar_ts t, high h, low l, close c
                   FROM bars WHERE timeframe='5s' ORDER BY bar_ts""").df()
con.close()
b["d"] = pd.to_datetime(b.t, unit="s", utc=True).strftime("%Y-%m-%d") if False else \
    pd.to_datetime(b.t, unit="s", utc=True).dt.strftime("%Y-%m-%d")

rows = []
for d, g in b.groupby("d"):
    if len(g) < 5000:
        continue
    c = g.c.values.astype(float)
    # biggest sustained directional excursion = max over the day of (running max - running min
    # in each direction) — the run-catcher's prize, in dollars
    runmin = np.minimum.accumulate(c)
    runmax = np.maximum.accumulate(c)
    up = (c - runmin).max()
    dn = (runmax - c).max()
    path = np.abs(np.diff(c)).sum()
    rows.append(dict(d=d, mgc_up=up * MGC_PPV, mgc_dn=dn * MGC_PPV,
                     mgc_run=max(up, dn) * MGC_PPV,
                     mgc_rng=(g.h.max() - g.l.min()) * MGC_PPV,
                     mgc_er=abs(c[-1] - c[0]) / path if path > 0 else 0.0))
M = pd.DataFrame(rows).set_index("d")

both = D[["net", "n", "atr_1300", "on_er", "on_roundtrip"]].join(M, how="inner")
print(f"═══ OVERLAPPING DAYS WITH BOTH MNQ AND MGC TAPE: {len(both)} ═══\n")
# ⚠ a flat >=$300 bar is degenerate here: at $10.00/pt that is only 30 points and ALL 16 days clear
# it, so the crosstab carries no information. Split at the MEDIAN run instead — "was today a
# BIG-run day for gold, by gold's own standards".
both["mgc_runday"] = both.mgc_run >= both.mgc_run.median()
both["odr_green"] = both.net > 0
print(both[["net", "odr_green", "mgc_run", "mgc_runday", "mgc_er", "atr_1300"]].round(2).to_string())

print("\n═══ DO THE GOOD DAYS COINCIDE? ═══")
ct = pd.crosstab(both.odr_green, both.mgc_runday)
print("  rows = odr day green?   cols = MGC run-day (>=$300 excursion)?")
print(ct.to_string())
agree = (both.odr_green == both.mgc_runday).mean() * 100
print(f"\n  agreement: {agree:.0f}% of days ({(both.odr_green==both.mgc_runday).sum()}/{len(both)})")
print(f"  Spearman(odr day $, MGC run $)  = {both.net.rank().corr(both.mgc_run.rank()):+.3f}")
print(f"  Spearman(odr day $, MGC range)  = {both.net.rank().corr(both.mgc_rng.rank()):+.3f}")
print(f"  Spearman(odr day $, MGC day ER) = {both.net.rank().corr(both.mgc_er.rank()):+.3f}")

# a coin-flip baseline: how often would two independent labels agree by chance?
p1, p2 = both.odr_green.mean(), both.mgc_runday.mean()
chance = (p1 * p2 + (1 - p1) * (1 - p2)) * 100
print(f"  chance agreement given the two base rates ({p1:.0%} / {p2:.0%}) = {chance:.0f}%")
print(f"  → lift over chance: {agree - chance:+.0f} points")

print("\n═══ WOULD MNQ's OWN PRE-13:00 FEATURES PREDICT AN MGC RUN-DAY? ═══")
for f in ["atr_1300", "on_er", "on_roundtrip"]:
    print(f"  Spearman({f:13}, MGC run $) = {both[f].rank().corr(both.mgc_run.rank()):+.3f}")
