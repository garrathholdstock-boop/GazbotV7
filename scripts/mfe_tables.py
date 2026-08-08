#!/usr/bin/env python3
"""GIVE-BACK STUDY — stage 3: the give-back tables.

Reframes the raw MFE scan into the numbers that actually answer the operator's question.
A naive sum(MFE) vs sum(kept) ratio is degenerate — sum of maxima is always positive while
a break-even book's realised sums to ~0, so the "give-back ratio" is ~100% by construction
and says nothing. The honest questions are per-trade:

  * how many entries reached a REAL profit (>= 1R, >= 2R, >= $20, >= $40) ...
  * ... and then finished at or below zero?          <- "runs up then runs back down"
  * on those round-trippers, how many dollars per trade were touched and handed back?
  * how long did the peak take to arrive (can a tighter clip realistically catch it)?

HYGIENE (applied before every table):
  * hold capped at the desk's own 120-min MAX_HOLD (config.py) — the shadow sim has no
    such cap and a handful of its holds run 50 HOURS across a weekend, which would
    dominate any MFE sum.
  * any entry whose window straddles a tape gap > 5 min (session break) is dropped.
  * MFE is on TRADE ticks = a CEILING (a long sells at the bid).

  PYTHONPATH=src ./.venv/bin/python scripts/mfe_tables.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import duckdb

SCR = "/home/alphabot/gazbot7/scratchpad"
VPP, FEE = 2.0, 1.50
MAXHOLD_S = 120 * 60

# live gate tag -> base gate (strip _A/_B, fold legacy names onto today's roster)
BASE = {"grind": "grind_long", "thrust": "abs_veto(thrust legacy)",
        "thrust_short": "abs_veto(thrust legacy)", "rgv": "rgv_short"}


def base_gate(g: str) -> str:
    g = str(g)
    for suf in ("_A", "_B"):
        if g.endswith(suf):
            g = g[: -len(suf)]
    return BASE.get(g, g)


def load():
    df = duckdb.connect().execute(f"SELECT * FROM '{SCR}/mfe_entries.parquet'").df()
    df["hold_s"] = (df.exit_ms - df.entry_ms) / 1000.0
    df["base"] = df.gate.map(base_gate)
    keep = (df.hold_s <= MAXHOLD_S) & (df.hold_s > 0) & df.mfe_pt.notna() & (df.atr > 0)
    print(f"dropped {int((~keep).sum())} of {len(df)} entries "
          f"(hold > 120 min / no tick path / bad ATR)")
    return df[keep].copy()


def q(s, p):
    return float(np.nanquantile(s, p)) if len(s) else float("nan")


def giveback_table(d: pd.DataFrame, by: str) -> pd.DataFrame:
    rows = []
    for k, g in d.groupby(by):
        red = g[g.realised <= 0]
        # "round-trippers": went >= 1R green, still finished at or below zero
        rt1 = g[(g.mfe_r >= 1.0) & (g.realised <= 0)]
        rt2 = g[(g.mfe_r >= 2.0) & (g.realised <= 0)]
        rows.append({
            by: k, "n": len(g),
            "$/tr": g.realised.mean(),
            "net$": g.realised.sum(),
            "reach>=1R": len(g[g.mfe_r >= 1.0]),
            "reach>=2R": len(g[g.mfe_r >= 2.0]),
            "RT1 n": len(rt1),
            "RT1 %": 100 * len(rt1) / max(len(g), 1),
            "RT1 touched$": rt1.mfe_usd.sum(),
            "RT1 kept$": rt1.realised.sum(),
            "RT2 n": len(rt2),
            "RT2 touched$": rt2.mfe_usd.sum(),
            "med MFE$": g.mfe_usd.median(),
            "med MFE R": g.mfe_r.median(),
            "med t2peak s": g.t_mfe_s.median(),
            "red n": len(red), "red MFE$ med": red.mfe_usd.median(),
        })
    return pd.DataFrame(rows).sort_values("n", ascending=False)


def main():
    d = load()
    pd.set_option("display.width", 250)
    for pop in ("LIVE", "SHADOW"):
        p = d[d.popn == pop]
        print(f"\n{'='*100}\n{pop}  n={len(p)}  ({p.day.nunique()} desk-days)\n{'='*100}")
        for w in ("QUIET", "US"):
            s = p[p.win == w]
            print(f"\n--- {w} window --- n={len(s)}  net ${s.realised.sum():,.0f}  "
                  f"${s.realised.mean():.2f}/trade")
            t = giveback_table(s, "base")
            t = t[t.n >= 5]
            print(t.round(2).to_string(index=False))
    # desk-wide MFE deciles, quiet window
    print(f"\n{'='*100}\nMFE DISTRIBUTION — QUIET window (deciles)\n{'='*100}")
    for pop in ("LIVE", "SHADOW"):
        s = d[(d.popn == pop) & (d.win == "QUIET")]
        dec = [round(q(s.mfe_usd, x / 10), 1) for x in range(1, 10)]
        decr = [round(q(s.mfe_r, x / 10), 2) for x in range(1, 10)]
        print(f"{pop:7} n={len(s):5}  MFE $ deciles {dec}")
        print(f"{'':7}          MFE R deciles {decr}")
    d.to_pickle(f"{SCR}/mfe_clean.pkl")
    print(f"\nwrote {SCR}/mfe_clean.pkl")


if __name__ == "__main__":
    main()
