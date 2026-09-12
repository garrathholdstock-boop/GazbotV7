"""CHOP-SCALP step 5 — the candidate engine.

A candidate = (named entry filter) x (target, stop). Trades are taken SEQUENTIALLY and
NON-OVERLAPPING: walk the day in time and skip any signal arriving before the previous
trade closed, which is what a one-slot desk actually does and which stops the fee tax
being counted on trades the desk could never have taken.

Every number here is net: MNQ $2.00/pt, $1.50 the ROUND TRIP, entry crossed by one tick
(already in the event table's `entry`), stops filled one tick beyond the trigger.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, SLIP_STOP_PT, load_events, IS_DAYS, OOS_DAYS, WEEK

CHOP_R = ("CHOP", "DEAD_CHOP")

# ---------------------------------------------------------------- named entry filters
def F(d, name):
    chop = d.regime.isin(CHOP_R)
    if name == "CT0_NAIVE":            return chop
    if name == "CT1_VWAPFLAT":         return chop & (d.f_vwap_flat <= 0.5)
    if name == "CT2_WALL":             return chop & (d.f_wall1 >= 1.5)
    if name == "CT2b_WALL5":           return chop & (d.f_wall5 >= 1.3)
    if name == "CT3_FOOTPRINT":        return chop & (d.f_agg20 >= 150)
    if name == "CT4_EXH_LITERAL":      return chop & (d.f_agg20.abs() >= 400) & (d.f_mv20.abs() <= 2.0) & (d.f_wall1 >= 1.5)
    if name == "CT4b_EXH_SOFT":        return chop & (d.f_agg20 >= 200) & (d.f_mv20.abs() <= 3.0) & (d.f_wall1 >= 1.2)
    if name == "CT5_STALL":            return chop & (d.f_stall20 >= d.f_stall20[chop].quantile(0.80))
    if name == "CT6_ANTIWALL":         return chop & (d.f_wall5 <= 0.8)
    if name == "CT7_SPIKE":            return chop & (d.f_mv20 >= 4.0)
    if name == "CT8_PULL":             return chop & (d.f_pull >= d.f_pull[chop].quantile(0.80))
    if name == "CT10_DEEPEXT":         return chop & (d.f_ext30 > 0)
    if name == "CT11_SPIKE_ANTIWALL":  return chop & (d.f_mv20 >= 4.0) & (d.f_wall5 <= 1.0)
    if name == "CT12_SPIKE_PULL":      return chop & (d.f_mv20 >= 4.0) & (d.f_pull >= d.f_pull[chop].quantile(0.60))
    if name == "CT13_DEEP_SPIKE":      return chop & (d.f_ext30 > 0) & (d.f_mv20 >= 4.0)
    if name == "CT14_US_ONLY":         return chop & (d.sess == "US")
    if name == "AT0_ALLTAPE":          return pd.Series(True, index=d.index)
    raise KeyError(name)

CANDS = ["CT0_NAIVE", "CT1_VWAPFLAT", "CT2_WALL", "CT2b_WALL5", "CT3_FOOTPRINT",
         "CT4_EXH_LITERAL", "CT4b_EXH_SOFT", "CT5_STALL", "CT6_ANTIWALL", "CT7_SPIKE",
         "CT8_PULL", "CT10_DEEPEXT", "CT11_SPIKE_ANTIWALL", "CT12_SPIKE_PULL",
         "CT13_DEEP_SPIKE", "CT14_US_ONLY", "AT0_ALLTAPE"]

GRID = [(t, s) for t in (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0) for s in (3.0, 4.0, 5.0, 6.0, 8.0, 10.0)]


def sequential(sub, tp, sp):
    """One slot, no overlap. Returns the taken rows with $ P&L attached."""
    kind = sub[f"k_{tp}_{sp}"].values
    dur = sub[f"d_{tp}_{sp}"].values
    res = sub[f"r_{tp}_{sp}"].values
    t = sub.dts.values
    take = np.zeros(len(sub), bool)
    free_at = -10**18
    for i in range(len(sub)):
        if kind[i] == "NOFILL" or t[i] < free_at:
            continue
        take[i] = True
        free_at = t[i] + (dur[i] if np.isfinite(dur[i]) else 900.0)
    o = sub[take].copy()
    k = kind[take]; r = res[take]
    pts = np.where(k == "STOP", -(sp + SLIP_STOP_PT), r)
    o["usd"] = pts * VPP - FEE
    o["kind"] = k
    return o


def run(d, name, tp, sp):
    m = F(d, name)
    out = []
    for day, g in d[m].groupby("date"):
        out.append(sequential(g.sort_values("dts"), tp, sp))
    if not out:
        return None
    return pd.concat(out, ignore_index=True)


def stats(o, label=""):
    if o is None or len(o) == 0:
        return {"label": label, "n": 0, "net": 0.0, "per_tr": 0.0, "win": 0.0, "open": 0}
    return {"label": label, "n": int(len(o)), "net": round(float(o.usd.sum()), 2),
            "per_tr": round(float(o.usd.mean()), 3), "win": round(float((o.usd > 0).mean()), 3),
            "open": int((o.kind == "OPEN").sum()),
            "days": int(o.date.nunique()),
            "best": round(float(o.usd.max()), 2), "worst": round(float(o.usd.min()), 2)}


if __name__ == "__main__":
    d = load_events()
    rows = []
    for name in CANDS:
        for tp, sp in GRID:
            o = run(d, name, tp, sp)
            if o is None or len(o) < 10:
                continue
            s = stats(o, name); s.update(tp=tp, sp=sp)
            for tag, days in (("IS", IS_DAYS), ("OOS", OOS_DAYS), ("WEEK", WEEK)):
                sub = o[o.date.isin(days)]
                s[f"n_{tag}"] = len(sub); s[f"net_{tag}"] = round(float(sub.usd.sum()), 2)
                s[f"ptr_{tag}"] = round(float(sub.usd.mean()), 3) if len(sub) else 0.0
            rows.append(s)
    R = pd.DataFrame(rows)
    R.to_csv(f"{OUT}/sweep.csv", index=False)
    print(f"[cells] {len(R)}")
    print("\n=== best cell per candidate, ranked by FULL-WINDOW $/trade ===")
    best = R.sort_values("per_tr", ascending=False).groupby("label").head(1).sort_values("per_tr", ascending=False)
    print(best[["label", "tp", "sp", "n", "net", "per_tr", "win", "days",
                "n_IS", "net_IS", "ptr_IS", "n_OOS", "net_OOS", "ptr_OOS"]].to_string(index=False))
    print("\n=== candidate SUMMARY across its whole grid (the plateau test) ===")
    agg = R.groupby("label").agg(cells=("per_tr", "size"), pos=("per_tr", lambda s: int((s > 0).sum())),
                                 med_ptr=("per_tr", "median"), max_ptr=("per_tr", "max"),
                                 med_n=("n", "median")).round(3)
    print(agg.sort_values("med_ptr", ascending=False).to_string())
