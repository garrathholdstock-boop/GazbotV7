#!/usr/bin/env python3
"""ENTRY CHATTER — replay the REAL drift.compute() minute by minute over the lake and dump the
full signal series per day, so persistence/clock entry rules can be built on it without re-deriving.

Output: reports/entry_lab/signal_series.json
  { day: {"open": px, "series": [[i, confirmed, dir, eff, rt, close_px], ...]} }
  i = number of session minute-bars used (compute(sess[:i])) — the SAME index the lake's
  `minute` field uses, so conf_min is interchangeable with rider_lab.
"""
import json, sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.drift import MIN_BARS, OPEN_UTC_MIN, compute
from gazbot7.day_rider import ENTRY_CUTOFF_MIN
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from drift_persistence_study import _lake_days

OUT = "/home/alphabot/gazbot7/reports/entry_lab/signal_series.json"

def main():
    days = _lake_days()
    res = {}
    for day, bars in sorted(days.items()):
        sess = [b for b in bars if OPEN_UTC_MIN * 60 <= (b[0] % 86400) < 21 * 3600]
        if len(sess) < 120:
            continue
        max_i = min(len(sess), ENTRY_CUTOFF_MIN - OPEN_UTC_MIN)
        ser = []
        for i in range(1, max_i + 1):
            r = compute(sess[:i])
            ser.append([i, bool(r.confirmed), r.direction, round(r.efficiency, 4),
                        round(r.roundtrip, 4), sess[i - 1][3], round(r.net_pt, 2)])
        res[day] = {"open": sess[0][3], "series": ser,
                    "close2040": next((b[3] for b in reversed(sess) if (b[0] % 86400) <= 20*3600+40*60), sess[-1][3])}
    json.dump(res, open(OUT, "w"))
    print(f"{len(res)} days -> {OUT}")

if __name__ == "__main__":
    main()
