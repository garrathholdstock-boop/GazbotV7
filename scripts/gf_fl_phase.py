#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 0c: IS THE LABEL STABLE? (the 60-second window has an arbitrary PHASE)

Found while cross-checking the frozen census: the census reports the 08-11 05:16 run with flow -109,
but the flow in the minute 05:15:00-05:16:00 is +48. Both are right. The census measures the 60s
BEFORE the run start, and the run start is a 5s-bar index off a grid whose origin is the first bar of
the scan — that run began at 05:16:40, so its 60s window is 05:15:40-05:16:40.

That matters because the SIGN of that window is what splits FLOW-LED from VACUUM. If sliding the same
60s window by a few seconds flips the sign, the cluster a run lands in is partly an artefact of where
the scan grid happened to start — not a property of the tape.

This re-measures every run's label at 12 phases (0,5,...,55s) of the same 60s window, rebuilding the
z-score population at each phase so the comparison is like-for-like, and reports how often the label
is unanimous.

Writes reports/friday_v7/sections/fl/phase.json
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from gazbot7.lake import connect  # noqa: E402
from gf_fl_label import detect_runs  # noqa: E402

FEAT = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl/feat.csv"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl/phase.json"
FLOW_Z = 1.0


def main():
    con = connect(symbol="MNQ")
    f5 = con.execute("""
        SELECT (ts_ms // 5000) * 5 AS ts,
               SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) AS flow
        FROM ticks GROUP BY 1 ORDER BY 1""").fetchdf()
    f5["ts"] = f5["ts"].astype("int64")
    lut = dict(zip(f5["ts"].to_numpy(), f5["flow"].to_numpy(float)))
    print(f"5s flow buckets: {len(f5):,}")

    df = pd.read_csv(FEAT)
    runs, typ, thr, _ = detect_runs(df)
    ts_min = df["ts"].to_numpy("int64")
    print(f"runs: {len(runs)}  thr={thr:.1f}pt")

    def flow60(end_ts):
        return sum(lut.get(end_ts - 5 * k, 0.0) for k in range(1, 13))

    # z population at a given phase: the same 60s statistic sampled every 60s over the trailing 2h
    def fz_at(end_ts, cur):
        pop = [flow60(end_ts - 60 * k) for k in range(1, 121)]
        pop = [p for p in pop if p != 0 or True]
        if len(pop) < 30:
            return None
        mu, sd = float(np.mean(pop)), float(np.std(pop, ddof=1))
        return None if sd <= 0 else (cur - mu) / sd

    offsets = list(range(0, 60, 5))
    rows, flips, unanimous = [], 0, 0
    counts = {"FLOW-LED": 0, "VACUUM": 0, "OTHER": 0}
    for i, mv in runs:
        t0 = int(ts_min[i])
        labs = []
        for off in offsets:
            end = t0 + off
            cur = flow60(end)
            z = fz_at(end, cur)
            if z is not None and abs(z) >= FLOW_Z:
                labs.append("FLOW-LED" if (cur > 0) == (mv > 0) else "VACUUM")
            else:
                labs.append("OTHER")
        uniq = set(labs)
        if len(uniq) == 1:
            unanimous += 1
        if "FLOW-LED" in uniq and "VACUUM" in uniq:
            flips += 1
        for lb in labs:
            counts[lb] += 1
        rows.append({"time": pd.to_datetime(t0, unit="s", utc=True).strftime("%m-%d %H:%M"),
                     "move": round(float(mv), 1),
                     "labels": {k: labs.count(k) for k in ("FLOW-LED", "VACUUM", "OTHER")}})

    res = {"runs": len(runs), "phases_per_run": len(offsets),
           "unanimous_runs": unanimous, "unanimous_pct": round(100 * unanimous / len(runs), 1),
           "runs_that_flip_FLOWLED_vs_VACUUM": flips,
           "flip_pct": round(100 * flips / len(runs), 1),
           "label_share_across_all_phases": {k: round(100 * v / (len(runs) * len(offsets)), 1)
                                             for k, v in counts.items()},
           "detector": {"typ_15m_range_pt": round(typ, 1), "threshold_pt": round(thr, 1)},
           "rows": rows}
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
