"""CHOP-DAY SCALP — Step 3: the model-free BOOK SEPARATION race.

Before any gate is built.  At every price extreme of the trailing 30-minute range,
run a symmetric first-touch race on the real tick path (+/- 0.75 ATR, 10-minute
horizon) and ask a single question:

    does the RESTING BOOK on the continuation side separate the turns from the
    breakouts, where PRICE ALONE does not?

No parameters are fitted here.  A fade is a 50/50 unless something conditions it.
Output: reports/friday_v7/sections/cs/race.json + printed separation tables.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import gf_cs_lib as L

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs"

POS_HI, POS_LO = 0.90, 0.10
BARRIER_ATR = 0.75
HORIZON = 600.0
DEDUP_S = 60.0
MIN_RANGE_ATR = 1.5          # the 30m range must be worth fading


def events_for_day(day: str) -> pd.DataFrame:
    f = L.feat(day)
    f = f.dropna(subset=["atr20", "er30", "vwap30", "hi30", "lo30",
                         "bid5", "ask5", "vwap30_10m"]).copy()
    f = f[(f["atr20"] > 0) & (f["hi30"] > f["lo30"])]
    f["pos30"] = (f["close"] - f["lo30"]) / (f["hi30"] - f["lo30"])
    f["rng_atr"] = (f["hi30"] - f["lo30"]) / f["atr20"]
    f["vslope"] = (f["vwap30"] - f["vwap30_10m"]) / f["atr20"]
    f["stretch"] = (f["close"] - f["vwap30"]) / f["atr20"]
    f["bkr_ask"] = f["ask5"] / f["bid5"].replace(0, np.nan)
    f["bkr_bid"] = f["bid5"] / f["ask5"].replace(0, np.nan)
    f["dask_n"] = f["dask5_30s"] / f["ask5_5m"].replace(0, np.nan)
    f["dbid_n"] = f["dbid5_30s"] / f["bid5_5m"].replace(0, np.nan)
    f["dlt_n"] = f["dlt60s"] / f["tvol60s"].replace(0, np.nan)
    f["absorb"] = f["dlt60s"].abs() / (f["mv60s"].abs() + 1.0)

    hi = f[(f["pos30"] >= POS_HI) & (f["rng_atr"] >= MIN_RANGE_ATR)].copy()
    hi["at"] = "HIGH"
    lo = f[(f["pos30"] <= POS_LO) & (f["rng_atr"] >= MIN_RANGE_ATR)].copy()
    lo["at"] = "LOW"
    ev = pd.concat([hi, lo]).sort_values("t")

    # de-duplicate: one event per side per DEDUP_S seconds
    keep, last = [], {}
    for t, side in zip(ev["t"].to_numpy(), ev["at"].to_numpy()):
        if t - last.get(side, -1e9) >= DEDUP_S:
            keep.append(True)
            last[side] = t
        else:
            keep.append(False)
    ev = ev[np.array(keep)].copy()
    ev["day"] = day
    return ev


def main() -> None:
    tt_cache = {}
    rows = []
    for day in L.DAYS:
        ev = events_for_day(day)
        tt, pp = L.ticks(day)
        tt_cache[day] = (tt, pp)
        res, hit_t = [], []
        # decision time is the bar's CLOSE (t+5), never its open: the features use
        # this bar's close/high/low, so racing from t would look 5s ahead.
        for t, px, atr in zip(ev["t"].to_numpy(), ev["close"].to_numpy(),
                              ev["atr20"].to_numpy()):
            b = BARRIER_ATR * atr
            h, th, _ = L.race(tt, pp, t + 5.0, px + b, px - b, HORIZON)
            res.append(h)
            hit_t.append(th - t - 5.0)
        ev["hit"] = res
        ev["secs"] = hit_t
        rows.append(ev)
        print(f"{day}  events={len(ev):5d}  "
              f"UP={sum(r == 'UP' for r in res):4d} DN={sum(r == 'DN' for r in res):4d} "
              f"TIME={sum(r == 'TIME' for r in res):4d}", flush=True)
    ev = pd.concat(rows, ignore_index=True)

    # revert = the barrier the FADE wants, touched first
    ev["revert"] = np.where(ev["at"] == "HIGH", ev["hit"] == "DN", ev["hit"] == "UP")
    ev["cont"] = np.where(ev["at"] == "HIGH", ev["hit"] == "UP", ev["hit"] == "DN")
    dec = ev[ev["hit"].isin(["UP", "DN"])].copy()          # decided races only

    # side-agnostic book features, oriented to the FADE
    dec["farwall"] = np.where(dec["at"] == "HIGH", dec["bkr_ask"], dec["bkr_bid"])
    dec["far_refill"] = np.where(dec["at"] == "HIGH", dec["dask_n"], dec["dbid_n"])
    dec["push"] = np.where(dec["at"] == "HIGH", dec["dlt_n"], -dec["dlt_n"])
    dec["prog"] = np.where(dec["at"] == "HIGH", dec["mv60s"], -dec["mv60s"])
    # VWAP slope ORIENTED to the fade: + means the drift is already going our way
    dec["vs_help"] = np.where(dec["at"] == "HIGH", -dec["vslope"], dec["vslope"])
    dec["vs_flat"] = dec["vslope"].abs()
    dec["chop"] = np.where(dec["er30"] < 0.30, "chop", "trend")
    dec["tod"] = np.where(((dec["t"] % 86400) >= 13.5 * 3600)
                          & ((dec["t"] % 86400) < 20 * 3600), "US", "ON")

    def tab(col, q=5, sub=None):
        d = dec if sub is None else dec[sub]
        d = d.dropna(subset=[col])
        if len(d) < 50:
            return None
        try:
            b = pd.qcut(d[col], q, duplicates="drop")
        except ValueError:
            return None
        g = d.groupby(b, observed=True).agg(n=("revert", "size"),
                                            p=("revert", "mean"),
                                            lo=(col, "min"), hi=(col, "max"))
        g["p"] = (100 * g["p"]).round(1)
        g["z"] = ((g["n"] * g["p"] / 100 - g["n"] * 0.5)
                  / np.sqrt(g["n"] * 0.25)).round(2)
        return g.round(3)

    print("\n\n############ BASELINE ############")
    for name, sub in [("ALL extremes", None),
                      ("chop blocks (ER30<0.30)", dec["chop"] == "chop"),
                      ("trend blocks", dec["chop"] == "trend"),
                      ("chop + US session", (dec["chop"] == "chop") & (dec["tod"] == "US")),
                      ("chop + overnight", (dec["chop"] == "chop") & (dec["tod"] == "ON")),
                      ("HIGH (fade=short)", dec["at"] == "HIGH"),
                      ("LOW (fade=long)", dec["at"] == "LOW")]:
        d = dec if sub is None else dec[sub]
        n = len(d)
        p = d["revert"].mean()
        z = (n * p - n * 0.5) / np.sqrt(n * 0.25) if n else float("nan")
        print(f"  {name:28s} n={n:6d}  P(revert first)={100*p:5.1f}%   z={z:+.2f}")

    chop = dec["chop"] == "chop"
    print("\n############ BOOK SEPARATION (chop blocks only) ############")
    for col, label in [("farwall", "far-side wall  (continuation-side 5-deep / near-side 5-deep)"),
                       ("far_refill", "far-side 30s size change / 5m mean  (+ = refilling)"),
                       ("push", "aggressor delta into the extreme / total vol  (+ = pushing)"),
                       ("prog", "60s price progress in the push direction (pt)"),
                       ("absorb", "|60s delta| / (|60s move|+1)  = absorption"),
                       ("stretch", "(price - 30m VWAP) / ATR"),
                       ("vs_help", "10m VWAP slope ORIENTED to the fade (+ = drift already our way)"),
                       ("vs_flat", "|10m VWAP slope| / ATR  — the operator's FLATNESS filter"),
                       ("rng_atr", "30m range / ATR"),
                       ("er30", "efficiency (30m)")]:
        g = tab(col, 5, chop)
        print(f"\n-- {label}   [{col}]")
        print("   (no data)" if g is None else g.to_string())

    dec.to_csv(f"{OUT}/race_events.csv", index=False)
    summary = {
        "n_events": int(len(ev)), "n_decided": int(len(dec)),
        "p_revert_all": round(float(dec["revert"].mean()), 4),
        "p_revert_chop": round(float(dec[chop]["revert"].mean()), 4),
        "barrier_atr": BARRIER_ATR, "horizon_s": HORIZON,
        "days": L.DAYS,
    }
    json.dump(summary, open(f"{OUT}/race.json", "w"), indent=1)
    print("\n", json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
