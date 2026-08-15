"""CHOP-DAY SCALP — the 41ms-book leg.

The DATA CONTRACT is explicit that capture.db's `book` (41ms, event-driven) sees
fleeting quotes that depth.db's 250ms sample cannot.  "Is this wall real or is it
being pulled and re-posted" is exactly a fleeting-quote question, so the 250ms
null on the wall term is not the last word.  This re-runs the separation race with
the 41ms REPLENISHMENT statistics, on the 11 days where both exist.
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

import gf_cs_book41 as K

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs"


def z(p, n):
    return (n * p - n * 0.5) / np.sqrt(n * 0.25) if n else float("nan")


def main() -> None:
    ev = pd.read_csv(f"{OUT}/race_events.csv")
    ev = ev[ev["day"].isin(K.DAYS41)].copy()
    b = duckdb.sql(f"SELECT * FROM '{K.OUT}/*.parquet'").df()

    # the 41ms stats are per 5s bucket; roll them to a trailing 30s window
    b = b.sort_values("t")
    for c in ["a_refill", "b_refill", "a_pull", "b_pull",
              "a_added", "b_added", "a_removed", "b_removed"]:
        b[c + "_30"] = b[c].rolling(6, min_periods=1).sum()
    ev = ev.merge(b, on="t", how="inner")
    hi = ev["at"] == "HIGH"

    # oriented to the FADE: "far" = the side price must consume to CONTINUE
    ev["far_refill41"] = np.where(hi, ev["a_refill_30"], ev["b_refill_30"])
    ev["far_pull41"] = np.where(hi, ev["a_pull_30"], ev["b_pull_30"])
    ev["far_added41"] = np.where(hi, ev["a_added_30"], ev["b_added_30"])
    ev["far_removed41"] = np.where(hi, ev["a_removed_30"], ev["b_removed_30"])
    ev["far_defend"] = ev["far_added41"] / (ev["far_removed41"] + 1.0)
    ev["far_churn"] = (ev["far_refill41"] + ev["far_pull41"])
    ev["far_net41"] = ev["far_added41"] - ev["far_removed41"]
    ev["far_size41"] = np.where(hi, ev["a_avg"], ev["b_avg"])
    ev["near_size41"] = np.where(hi, ev["b_avg"], ev["a_avg"])
    ev["l1_ratio41"] = ev["far_size41"] / ev["near_size41"].replace(0, np.nan)

    chop = ev["er30"] < 0.30
    print(f"41ms-book overlap days={ev['day'].nunique()}  events={len(ev)}  "
          f"chop={int(chop.sum())}")
    print(f"baseline P(revert) all={100*ev['revert'].mean():.1f}%  "
          f"chop={100*ev[chop]['revert'].mean():.1f}%  "
          f"z(chop)={z(ev[chop]['revert'].mean(), int(chop.sum())):+.2f}")

    print("\n############ 41ms REPLENISHMENT SEPARATION (chop blocks) ############")
    d = ev[chop]
    for col, lab in [("far_defend", "added/removed on the continuation side (>1 = defended)"),
                     ("far_refill41", "count of level-1 size INCREASES, 30s"),
                     ("far_pull41", "count of level-1 size DECREASES, 30s"),
                     ("far_churn", "total level-1 events, 30s (quote churn)"),
                     ("far_net41", "contracts added minus removed, 30s"),
                     ("l1_ratio41", "41ms mean level-1 size, far / near")]:
        s = d.dropna(subset=[col])
        if len(s) < 200:
            continue
        q = pd.qcut(s[col], 5, duplicates="drop")
        g = s.groupby(q, observed=True)["revert"].agg(["size", "mean"])
        g["P"] = (100 * g["mean"]).round(1)
        g["z"] = [round(z(m, n), 2) for n, m in zip(g["size"], g["mean"])]
        print(f"\n-- {lab}  [{col}]")
        print(g[["size", "P", "z"]].to_string())

    print("\n############ 41ms vs 250ms — same wall question, two fidelities ############")
    s = d.dropna(subset=["l1_ratio41", "farwall"])
    for col in ["farwall", "l1_ratio41"]:
        top = s[s[col] >= s[col].quantile(0.80)]
        bot = s[s[col] <= s[col].quantile(0.20)]
        print(f"  {col:>12s}  top20% n={len(top):4d} P={100*top['revert'].mean():5.1f}% "
              f"z={z(top['revert'].mean(), len(top)):+5.2f}   "
              f"bottom20% n={len(bot):4d} P={100*bot['revert'].mean():5.1f}% "
              f"z={z(bot['revert'].mean(), len(bot)):+5.2f}")

    print("\n############ the DEFENDED-WALL cell, the one the brief actually asks for ############")
    for dfd in [1.0, 1.2, 1.5]:
        for pr in [2.0, 4.0, 99.0]:
            s = d[(d["far_defend"] >= dfd) & (d["prog"].abs() <= pr)]
            if len(s) < 60:
                continue
            print(f"  defend>={dfd}  |60s move|<={pr:4.0f}pt   n={len(s):5d}  "
                  f"P(revert)={100*s['revert'].mean():5.1f}%  "
                  f"z={z(s['revert'].mean(), len(s)):+5.2f}")

    ev.to_csv(f"{OUT}/race41.csv", index=False)


if __name__ == "__main__":
    main()
