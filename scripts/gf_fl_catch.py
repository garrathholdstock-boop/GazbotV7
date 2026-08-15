#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 9: did the invented gate actually SHOW UP for the cluster's own runs?

Three catch tables, all against the run set the census detector produces on the full lake:
  * every run                       (344, >=73pt in 15 min)
  * the 29 runs the census rule labels FLOW-LED — the cluster this section was handed
  * the top-15 by size, named individually, caught or missed
plus the two FLOW-LED members of the FROZEN census (08-11 05:16 and 08-14 00:03), which are the
runs this section was literally pointed at.

"Caught" = an FBREAK trade in the run's direction opened between 5 minutes before and 15 minutes
after the run's start — i.e. the gate was in the move, not merely trading that day.

Writes reports/friday_v7/sections/fl/catch.json
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from gf_fl_label import detect_runs  # noqa: E402

DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"
FEAT = f"{DIR}/feat.csv"
OUT = f"{DIR}/catch.json"
FLOW_Z = 1.0


def main():
    df = pd.read_csv(FEAT)
    tr = pd.read_csv(f"{DIR}/trades_abl_FBREAK.csv")
    us = tr[tr["session"] == "US"]
    runs, _, thr, _ = detect_runs(df)
    ts = df["ts"].to_numpy("int64")
    fz = df["fz"].to_numpy(float)
    flow = df["flow"].to_numpy(float)

    def caught(book, t0, d):
        sub = book[(book["dir"] == d) & (book["ts"] >= t0 - 300) & (book["ts"] <= t0 + 900)]
        return (len(sub) > 0, round(float(sub["net"].sum()), 2) if len(sub) else 0.0)

    rows = []
    for i, mv in runs:
        t0, d = int(ts[i]), (1 if mv > 0 else -1)
        z = fz[i]
        lab = ("FLOW-LED" if (flow[i] > 0) == (mv > 0) else "VACUUM") \
            if (not np.isnan(z) and abs(z) >= FLOW_Z) else "OTHER"
        cf, nf = caught(tr, t0, d)
        cu, nu = caught(us, t0, d)
        rows.append({"time": pd.to_datetime(t0, unit="s", utc=True).strftime("%m-%d %H:%M"),
                     "move": round(float(mv), 1), "label": lab,
                     "caught_full_book": cf, "net_full": nf,
                     "caught_us_book": cu, "net_us": nu,
                     "ceiling_1lot": round(abs(float(mv)) * 2.0, 0)})
    rows.sort(key=lambda r: -abs(r["move"]))

    def agg(sel, name):
        n = len(sel)
        c = sum(1 for r in sel if r["caught_full_book"])
        cu = sum(1 for r in sel if r["caught_us_book"])
        return {"set": name, "runs": n, "caught_full": f"{c}/{n}", "caught_us": f"{cu}/{n}",
                "ceiling_$": round(sum(r["ceiling_1lot"] for r in sel), 0),
                "net_on_caught_full_$": round(sum(r["net_full"] for r in sel), 2),
                "net_on_caught_us_$": round(sum(r["net_us"] for r in sel), 2)}

    res = {"run_threshold_pt": round(thr, 1),
           "tables": [agg(rows, "ALL RUNS"),
                      agg([r for r in rows if r["label"] == "FLOW-LED"], "FLOW-LED labelled"),
                      agg([r for r in rows if r["label"] == "VACUUM"], "VACUUM labelled"),
                      agg([r for r in rows if r["label"] == "OTHER"], "unlabelled"),
                      agg(rows[:25], "TOP 25 by size"), agg(rows[:15], "TOP 15 by size")],
           "top15_rows": rows[:15],
           "flow_led_rows": [r for r in rows if r["label"] == "FLOW-LED"]}

    # the two FLOW-LED members of the frozen census
    cen = []
    for t, mv in (("2026-08-11 05:16", -46), ("2026-08-14 00:03", -47)):
        t0 = int(pd.Timestamp(t, tz="UTC").timestamp())
        d = 1 if mv > 0 else -1
        cf, nf = caught(tr, t0, d)
        cen.append({"time": t, "move": mv, "caught_full_book": cf, "net": nf,
                    "session": "OVERNIGHT/PRE-OPEN — outside the gate's armed window"})
    res["frozen_census_flow_led_members"] = cen

    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("top15_rows", "flow_led_rows")},
                     indent=1))
    print("\nTOP 15:")
    for r in res["top15_rows"]:
        print(f"  {r['time']} {r['move']:+7.1f}pt {r['label']:9s} full={r['caught_full_book']!s:5s} "
              f"${r['net_full']:+8.2f}  us={r['caught_us_book']!s:5s} ${r['net_us']:+8.2f}")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
