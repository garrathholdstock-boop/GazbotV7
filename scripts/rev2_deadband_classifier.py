#!/usr/bin/env python3
"""REV2 — is the DEAD BAND predictable? Movement 3 §7's lever, tested with §3's own instrument.

★ THE QUESTION THE REPORT LEFT HANGING. Movement 3 §3 says every precursor this desk owns is an ATR
proxy and carries no DIRECTION. §7 then says the money is in SIZE — 48.2% of entries land in the
+/-20pt dead band and pay $10.00 each to find out — and that declining them "needs no direction call
at all". Those two findings point at each other with nobody in between, because §3 measured
direction and §7 needs a SIZE call. ATR level scores AUC 0.77-0.81 against exactly the fixed POINT
thresholds §7's bands are built from, so the obvious question is: does ATR-at-entry separate the
dead band?

★ THE TEST. Take §7's pooled book (`_boards()` — every 5-minute thrust >= 2.0xATR over
2026-06-22..2026-08-28, raced on the 5s lake at a 2.5xATR stop / 6xATR target), label each entry by
whether |follow-through| landed inside +/-20 points, and run §3's own `auc()` harness on
ATR-at-entry and five other pre-entry features. §3's bar is stated in advance and is not moved here:

    AUC >= 0.60  ->  §7's lever is buildable TODAY off the ATR meter we already have.
    AUC <  0.60  ->  say so and close BUILD #4 loudly, which is what its own kill criterion asks.

★ AND THE CONTROL §3 INSISTS ON. A dead band is defined in POINTS, so any feature correlated with
ATR will score against it for the same reason §3 already demolished. So the same test is ALSO run
against an ATR-NORMALISED dead band (|follow| < 0.8 x ATR, chosen to keep the base rate close), and
the two AUCs are printed side by side. If ATR only separates the POINT band, that is the ATR-proxy
result a third time, not a lever.

  PYTHONPATH=src .venv/bin/python scripts/rev2_deadband_classifier.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")

import gf5_m3_lab as L                                                    # noqa: E402

OUT = pathlib.Path(f"{GB}/reports/friday_v7/sections/rev2_deadband.json")
BAR = 0.60
NPERM, SEED = 2000, 20260829


def main() -> int:
    m = L.minutes().join(L.ticks_min()[["nt", "ntz", "flow", "fz"]], how="left")
    d = m.loc["2026-06-22":"2026-08-28"].copy()

    # the pre-entry features, all lagged so nothing is read from the firing bar itself
    d["pre_volz"] = d["volz"].shift(1)
    d["pre_ntz"] = d["ntz"].shift(1)
    d["pre_atrexp"] = d["atr_exp"].shift(1)
    d["pre_afz"] = d["fz"].abs().shift(1)
    d["pre_er15"] = d["er15"].shift(1)
    d["pre_atr"] = d["atr20"].shift(1)

    t = L._boards(d)
    feats = ["pre_atr", "pre_atrexp", "pre_volz", "pre_ntz", "pre_afz", "pre_er15"]
    t = t.join(d[feats], on="ts")
    t["atr_at_entry"] = t["atr"]

    dead_pt = t["follow"].abs() < 20.0                       # §7's own band, in POINTS
    dead_atr = t["follow"].abs() < 0.8 * t["atr"]            # the same idea, in ATR

    rng = np.random.default_rng(SEED)
    rows = []
    for f in ["atr_at_entry"] + feats:
        x = t[f].to_numpy(float)
        a_pt = L.auc(x, dead_pt.to_numpy())
        a_atr = L.auc(x, dead_atr.to_numpy())
        # permutation p on the POINT band (the one §7's lever would use)
        obs = abs(a_pt - 0.5)
        null = [abs(L.auc(x, rng.permutation(dead_pt.to_numpy())) - 0.5) for _ in range(NPERM)]
        p = float((np.sum(np.asarray(null) >= obs) + 1) / (NPERM + 1))
        rows.append(dict(feature=f,
                         auc_point_band=None if a_pt != a_pt else round(a_pt, 3),
                         auc_atr_band=None if a_atr != a_atr else round(a_atr, 3),
                         p_permutation=round(p, 4),
                         clears_bar=bool(a_pt == a_pt and max(a_pt, 1 - a_pt) >= BAR)))

    # what a perfect dead-band decline is worth, and what the best available feature buys
    net, n = float(t.pnl.sum()), len(t)
    kept = t[~dead_pt]
    best = max(rows, key=lambda r: abs((r["auc_point_band"] or 0.5) - 0.5))
    xb = t[best["feature"]].to_numpy(float)
    hi = (best["auc_point_band"] or 0.5) < 0.5          # which tail predicts "dead"
    cut = np.nanquantile(xb, 0.482 if hi else 0.518)
    decl = (xb <= cut) if hi else (xb >= cut)
    trial = t[~decl]

    # ── ROBUSTNESS: the 48.2% cut is FITTED to this book's own base rate, so split it in time and
    # apply the FIRST half's cut to the SECOND. A threshold that only works where it was chosen is
    # the exact failure the gold section documents two movements away.
    half = t["ts"].quantile(0.5)
    is_, oos = t[t.ts <= half], t[t.ts > half]
    x_is = is_[best["feature"]].to_numpy(float)
    cut_is = np.nanquantile(x_is, 0.482 if hi else 0.518)
    def _apply(frame, c):
        xx = frame[best["feature"]].to_numpy(float)
        keep = frame[~((xx <= c) if hi else (xx >= c))]
        return dict(n=int(len(frame)), kept=int(len(keep)),
                    all_per=round(float(frame.pnl.mean()), 2),
                    kept_net=round(float(keep.pnl.sum()), 2),
                    kept_per=round(float(keep.pnl.mean()), 2) if len(keep) else None)
    wf = dict(cut_fitted_on_first_half=round(float(cut_is), 2),
              first_half=_apply(is_, cut_is), second_half=_apply(oos, cut_is),
              split_at=str(half))

    # strip the best 3 trades from the KEPT book — an edge that is three trades is not an edge
    kept_all = t[~decl].sort_values("pnl", ascending=False)
    sb3 = round(float(kept_all.pnl.sum() - kept_all.pnl.head(3).sum()), 2)

    res = dict(
        walk_forward=wf, kept_strip_best_3=sb3,
        book=dict(n=n, net=round(net, 2), per=round(net / n, 3),
                  dead_n=int(dead_pt.sum()), dead_pct=round(100 * float(dead_pt.mean()), 1),
                  dead_net=round(float(t.pnl[dead_pt].sum()), 2),
                  dead_per=round(float(t.pnl[dead_pt].mean()), 2)),
        perfect_decline=dict(n=int(len(kept)), net=round(float(kept.pnl.sum()), 2),
                             per=round(float(kept.pnl.mean()), 2)),
        atr_band_base_rate=round(100 * float(dead_atr.mean()), 1),
        bar=BAR, permutations=NPERM, seed=SEED, features=rows,
        best_feature=best["feature"],
        best_feature_trial=dict(declined=int(decl.sum()), kept=int(len(trial)),
                                net=round(float(trial.pnl.sum()), 2),
                                per=round(float(trial.pnl.mean()), 2)),
        verdict=("BUILDABLE" if any(r["clears_bar"] for r in rows) else "NOT BUILDABLE"))
    print(json.dumps(res, indent=2))
    OUT.write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
