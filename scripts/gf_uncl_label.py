#!/usr/bin/env python3
"""GF UNCLASS — STEP 0: interrogate the LABEL before building anything on top of it.

The operator's standing rule for this phase: *"check its base rate on all bars; a label that is true
on most of the tape is not a footprint, it is noise, and that finding outranks any signal you build
on top of it."*

`run_census.cluster()` is a 4-branch waterfall:

    13 <= hour < 15                      -> OPEN/NEWS
    |flow z| >= 1  (needs >=30 buckets)  -> FLOW-LED (sign agrees) / VACUUM (sign disagrees)
    amp > 0.30 %                         -> VOL-EXPANSION
    otherwise                            -> UNCLASS

UNCLASS is therefore not a measurement. It is the RESIDUAL of three narrow tests, and one of those
tests can return "no verdict" for a reason that has nothing to do with the market (too few tick
buckets in the trailing 2h => fz=None => falls through to UNCLASS).

This script:
  1. re-implements the waterfall VECTORISED over the same 7-day capture.db window the census used,
  2. VALIDATES the reimplementation by reproducing the census's own label on all 68 runs,
  3. reports the base rate of every label on ALL minutes of the tape, not just the run minutes,
  4. decomposes UNCLASS into "genuinely quiet flow" vs "flow verdict was UNAVAILABLE".

    PYTHONPATH=src .venv/bin/python scripts/gf_uncl_label.py
"""
from __future__ import annotations

import datetime as dt
import json
import re

import duckdb
import numpy as np
import pandas as pd

CAP = "/home/alphabot/gazbot7/data/capture.db"
SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CENSUS_TXT = f"{SEC}/census_stdout.txt"
FLOW_Z, MIN_B = 1.0, 30
W, STEP = 180, 12          # census: 15-min window in 5s bars, slide 60s


def census_rows() -> pd.DataFrame:
    """The frozen census table, parsed back out of its own stdout (never re-run the census)."""
    rows = []
    for ln in open(CENSUS_TXT):
        m = re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]\d+)\s+(\d+)\s+"
                     r"(caught|sat out|FOUGHT)\s+(\S+)\s+([+-]\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", ln)
        if m:
            rows.append(dict(tm=m.group(1), dir=m.group(2), move=int(m.group(3)), ceil=int(m.group(4)),
                             us=m.group(5), gate=m.group(6), real=int(m.group(7)),
                             flow=m.group(8), amp=m.group(9), book=m.group(10), cl=m.group(11)))
    return pd.DataFrame(rows)


def main():
    cr = census_rows()
    print(f"census rows parsed: {len(cr)}  (expect 68)")
    print(cr["cl"].value_counts().to_string())

    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")

    # ── the same 7-day window, the same 5s bars ────────────────────────────────────────────────
    t1 = con.execute("SELECT max(bar_ts) FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'").fetchone()[0]
    b = con.execute(f"""SELECT bar_ts, open, high, low, close FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= {t1} - 7*86400 ORDER BY bar_ts""").df()
    print(f"\n5s bars in the census window: {len(b):,}  "
          f"{dt.datetime.fromtimestamp(b.bar_ts.iloc[0], dt.UTC):%m-%d %H:%M} .. "
          f"{dt.datetime.fromtimestamp(b.bar_ts.iloc[-1], dt.UTC):%m-%d %H:%M}")

    # amp% = prior 5 minutes (60 x 5s bars) hi-lo, as a % of close — the VOL-EXPANSION test
    hi = b["high"].rolling(60).max().shift(1)
    lo = b["low"].rolling(60).min().shift(1)
    b["amp"] = 100.0 * (hi - lo) / b["close"]

    # ── flow, and the flow Z-SCORE, vectorised ────────────────────────────────────────────────
    # census: net aggressor over the 60s BEFORE t, standardised against the same statistic over the
    # trailing 2h in non-overlapping 60s buckets, >=30 buckets required else NO verdict.
    tk = con.execute(f"""SELECT (ts_ms/1000)::BIGINT // 60 * 60 AS m,
               SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END) AS f
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms >= ({t1} - 8*86400)::BIGINT*1000 GROUP BY 1 ORDER BY 1""").df()
    grid = pd.DataFrame({"m": np.arange(tk["m"].min(), tk["m"].max() + 60, 60)})
    tk = grid.merge(tk, on="m", how="left")            # missing minute = no ticks = no bucket
    f = tk["f"]
    mu = f.rolling(120, min_periods=MIN_B).mean().shift(1)
    sd = f.rolling(120, min_periods=MIN_B).std().shift(1)
    nb = f.notna().rolling(120, min_periods=1).sum().shift(1)
    tk["fz"] = np.where((nb >= MIN_B) & (sd > 0), (f - mu) / sd, np.nan)
    tk["flow"] = f
    tk["nb"] = nb

    # ── evaluate the waterfall on EVERY minute of the window ──────────────────────────────────
    g = b.iloc[::STEP].copy()                          # the census's own 60s grid
    g["m"] = (g["bar_ts"] // 60 * 60).astype("int64")
    g = g.merge(tk[["m", "flow", "fz", "nb"]], on="m", how="left")
    g["hour"] = pd.to_datetime(g["bar_ts"], unit="s", utc=True).dt.hour
    # the census reads the FORWARD 15-min move for direction; for a base rate on all bars we use the
    # same forward window so the sign test is like-for-like with how a run was labelled.
    fwd = b.set_index("bar_ts")["close"]
    g["mv"] = g["bar_ts"].map(lambda t: fwd.get(t + 900, np.nan)) - g["close"]

    def label(r):
        if 13 <= r.hour < 15:
            return "OPEN/NEWS"
        if pd.notna(r.flow) and pd.notna(r.fz) and abs(r.fz) >= FLOW_Z:
            return "FLOW-LED" if (r.flow > 0) == (r.mv > 0) else "VACUUM"
        if pd.notna(r.amp) and r.amp > 0.30:
            return "VOL-EXPANSION"
        return "UNCLASS"

    g["lab"] = g.apply(label, axis=1)
    g = g[g["mv"].notna()]
    n = len(g)
    print(f"\n══ BASE RATE OF EVERY CLUSTER LABEL ON ALL {n:,} MINUTES OF THE CENSUS WINDOW ══")
    vc = g["lab"].value_counts()
    for k, v in vc.items():
        print(f"   {k:<16}{v:>7,}   {100*v/n:>5.1f}% of all bars")

    # ── validation: does the reimplementation reproduce the census's own labels on the 68 runs? ──
    cr["ts"] = cr["tm"].apply(lambda s: int(dt.datetime.strptime("2026-" + s, "%Y-%m-%d %H:%M")
                                            .replace(tzinfo=dt.UTC).timestamp()))
    gg = g[["m", "lab", "fz", "flow", "amp", "nb"]].rename(columns={"amp": "amp_m", "flow": "flow_m"})
    chk = cr.merge(gg, left_on="ts", right_on="m", how="left")
    ok = (chk["cl"] == chk["lab"]).sum()
    print(f"\n══ VALIDATION — reproduce the census label on its own 68 runs ══")
    print(f"   matched {ok}/{len(chk)}  ({100*ok/len(chk):.0f}%)")
    bad = chk[(chk["cl"] != chk["lab"]) & chk["lab"].notna()]
    if len(bad):
        print("   mismatches:")
        for _, r in bad.iterrows():
            fzs = f"{r.fz:+.2f}" if pd.notna(r.fz) else "none"
            print(f"     {r.tm}  census={r.cl:<13} mine={r.lab:<13} fz={fzs:>6} "
                  f"flow={r.flow_m:>+8.0f} buckets={r.nb:.0f}")

    # ── WHY a minute lands in UNCLASS ─────────────────────────────────────────────────────────
    u = g[g["lab"] == "UNCLASS"]
    no_verdict = u["fz"].isna().sum()
    quiet = (u["fz"].abs() < FLOW_Z).sum()
    print(f"\n══ WHAT UNCLASS ACTUALLY MEANS, minute by minute ══")
    print(f"   flow verdict UNAVAILABLE (fz could not be computed) : {no_verdict:>7,}  {100*no_verdict/len(u):.1f}%")
    print(f"   flow verdict available but |z| < 1 (ordinary flow)  : {quiet:>7,}  {100*quiet/len(u):.1f}%")
    print(f"   -> UNCLASS is {100*len(u)/n:.1f}% of the tape")

    # same decomposition for the 34 sat-out UNCLASS runs
    su = chk[(chk["cl"] == "UNCLASS") & (chk["us"] == "sat out")]
    print(f"\n   of the {len(su)} sat-out UNCLASS RUNS: fz unavailable on "
          f"{su['fz'].isna().sum()}, |z|<1 on {(su['fz'].abs() < FLOW_Z).sum()}")

    # ── hour-of-day profile: UNCLASS runs vs the UNCLASS base rate ────────────────────────────
    print(f"\n══ HOUR-OF-DAY: is UNCLASS a market state or a clock artefact? ══")
    print(f"   {'hr':>3} {'UNCLASS % of that hour':>24} {'sat-out UNCLASS runs':>22}")
    su_h = pd.to_datetime(su["ts"], unit="s", utc=True).dt.hour.value_counts()
    for h in range(24):
        gh = g[g["hour"] == h]
        if not len(gh):
            continue
        pct = 100 * (gh["lab"] == "UNCLASS").mean()
        print(f"   {h:>3} {pct:>23.0f}% {su_h.get(h, 0):>22}")

    out = dict(n_minutes=int(n), base_rate={k: dict(n=int(v), pct=round(100 * v / n, 2)) for k, v in vc.items()},
               validation_match=f"{ok}/{len(chk)}",
               unclass_no_flow_verdict_pct=round(100 * no_verdict / len(u), 1),
               satout_unclass_runs=int(len(su)),
               satout_unclass_no_verdict=int(su["fz"].isna().sum()))
    json.dump(out, open(f"{SEC}/gf_uncl_label.json", "w"), indent=1)
    print(f"\n-> {SEC}/gf_uncl_label.json")


if __name__ == "__main__":
    main()
