#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 2: THE ESCALATION. Does a flow footprint appear as the runs get BIGGER?

The census mixes marginal 45pt runs with a 236pt monster, and the operator's standing instruction is
that the monsters may carry a cleaner footprint the marginal ones wash out. So instead of asking
"does flow lead runs" once, ask it at four sizes — every sat-out run, the top 50, the top 25, the
top 15 — and report the size at which the footprint (if any) becomes visible. That threshold IS a
finding, whichever way it lands.

Measured two ways on each size bucket:
  * the LABEL rate     — what share of those runs the census rule calls FLOW-LED, against the 10.0%
                         of ordinary tape that wears the same label (so: lift, not raw share)
  * the SIGNED FLOW    — mean flow z-score in the run's own direction in the 60s before it started.
                         If flow leads big runs, this must be POSITIVE and must GROW with size.

Also does the same on the FROZEN census (this week, 60 sat-out runs) so the two agree or the
disagreement is visible.

Writes reports/friday_v7/sections/fl/escalate.json
"""
from __future__ import annotations

import json
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from gf_fl_label import detect_runs  # noqa: E402

FEAT = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl/feat.csv"
CENSUS = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl/escalate.json"
FLOW_Z = 1.0


def bucket_stats(rows, tape_fl, tape_vac):
    fz = np.array([r["fz_signed"] for r in rows if r["fz_signed"] is not None])
    nfl = sum(1 for r in rows if r["label"] == "FLOW-LED")
    nvac = sum(1 for r in rows if r["label"] == "VACUUM")
    return {
        "n": len(rows),
        "median_move_pt": round(float(np.median([abs(r["move"]) for r in rows])), 1),
        "min_move_pt": round(float(min(abs(r["move"]) for r in rows)), 1),
        "FLOW-LED": nfl, "VACUUM": nvac, "OTHER": len(rows) - nfl - nvac,
        "pct_FLOW_LED": round(100 * nfl / len(rows), 1),
        "pct_VACUUM": round(100 * nvac / len(rows), 1),
        "lift_FLOW_LED_vs_tape": round((100 * nfl / len(rows)) / tape_fl, 2) if tape_fl else None,
        "lift_VACUUM_vs_tape": round((100 * nvac / len(rows)) / tape_vac, 2) if tape_vac else None,
        "mean_signed_fz": round(float(fz.mean()), 3) if len(fz) else None,
        "median_signed_fz": round(float(np.median(fz)), 3) if len(fz) else None,
        "pct_signed_fz_positive": round(100 * float((fz > 0).mean()), 1) if len(fz) else None,
        "t_stat_signed_fz": round(float(fz.mean() / (fz.std(ddof=1) / np.sqrt(len(fz)))), 2)
        if len(fz) > 2 else None,
    }


def main():
    df = pd.read_csv(FEAT)
    lab = json.load(open("/home/alphabot/gazbot7/reports/friday_v7/sections/fl/label.json"))
    tape_fl = lab["base_rate"]["pct_tape_FLOW_LED_by_same_rule"]
    tape_vac = lab["base_rate"]["pct_tape_VACUUM_by_same_rule"]

    runs, typ, thr, _ = detect_runs(df)
    fz = df["fz"].to_numpy(float)
    flow = df["flow"].to_numpy(float)
    ts = df["ts"].to_numpy("int64")
    rows = []
    for i, mv in runs:
        z, f = fz[i], flow[i]
        d = 1 if mv > 0 else -1
        if not np.isnan(z) and abs(z) >= FLOW_Z:
            label = "FLOW-LED" if (f > 0) == (mv > 0) else "VACUUM"
        else:
            label = "OTHER"
        rows.append({"time": pd.to_datetime(ts[i], unit="s", utc=True).strftime("%m-%d %H:%M"),
                     "move": round(float(mv), 1), "label": label,
                     "fz_signed": None if np.isnan(z) else round(float(d * z), 3),
                     "atr": float(df["atr15"].iloc[i]), "er": float(df["er15"].iloc[i])})
    rows.sort(key=lambda r: -abs(r["move"]))

    res = {"tape_base_rates": {"FLOW-LED_pct": tape_fl, "VACUUM_pct": tape_vac},
           "detector": {"runs": len(runs), "threshold_pt": round(thr, 1),
                        "typ_15m_range_pt": round(typ, 1)},
           "lake_escalation": {}}
    for name, n in (("ALL", len(rows)), ("TOP50", 50), ("TOP25", 25), ("TOP15", 15)):
        res["lake_escalation"][name] = bucket_stats(rows[:n], tape_fl, tape_vac)
    res["lake_top25_rows"] = rows[:25]

    # ── the FROZEN census (this week), for agreement ──────────────────────────────────────────
    cen = []
    for ln in open(CENSUS):
        m = re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]\d+)\s+\d+\s+(\S+)", ln)
        if m and "sat out" in ln:
            cen.append({"time": m.group(1), "move": int(m.group(3)), "cluster": ln.split()[-1]})
    cen.sort(key=lambda r: -abs(r["move"]))
    res["census_frozen"] = {
        "sat_out": len(cen),
        "clusters_all": {c: sum(1 for r in cen if r["cluster"] == c) for c in
                         sorted({r["cluster"] for r in cen})},
        "clusters_top25": {c: sum(1 for r in cen[:25] if r["cluster"] == c) for c in
                           sorted({r["cluster"] for r in cen[:25]})},
        "clusters_top15": {c: sum(1 for r in cen[:15] if r["cluster"] == c) for c in
                           sorted({r["cluster"] for r in cen[:15]})},
    }
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "lake_top25_rows"}, indent=1))
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
