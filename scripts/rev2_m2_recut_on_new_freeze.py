#!/usr/bin/env python3
"""REV2 — re-cut Movement 2's RUN-WINDOW arms onto the 2026-08-25 census re-freeze.

Movement 2 was computed on the SUPERSEDED 08-22 census (70 runs / 65 sat out / $9,987). The
re-freeze on 08-25 gives 68 runs / 62 sat out / $9,610. Two of the lab's four numbers depend on
that list and two do not:

  · WHOLE-WEEK BASE RATE (-$1,905.36 on 117 fires) is CENSUS-INDEPENDENT — it fires all six gates
    across every second of the week's tape and never looks at the run list at all. It does not
    move and does not need re-running.
  · The RUN-WINDOW arms DO depend on it, because the windows are cut around each run's ignition.

This re-sums the per-run fills already banked in movement2_idle_gates.json over only the runs that
survive into the new freeze, matched on the run's own UTC label. It is a re-cut, not a re-replay:
the fills themselves are unchanged, only which runs are counted.
"""
from __future__ import annotations
import json
import re

GB = "/home/alphabot/gazbot7"
SEC = f"{GB}/reports/friday_v7/sections"

ROW = re.compile(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]\d+)\s+(\d+)\s+(sat out|caught|fought)")
# The re-freeze moves a run's IGNITION MINUTE by a minute or two as well as adding and removing
# runs, so an exact label match reports 31 drops and 28 additions for what is mostly the same
# list. Runs are matched to the nearest surviving run within this tolerance instead.
TOL_S = 240


def new_freeze():
    """(all runs, sat-out runs) from the 08-25 census stdout, keyed by 'MM-DD HH:MM'."""
    allr, sat = {}, {}
    for line in open(f"{SEC}/census_stdout.txt"):
        m = ROW.match(line.strip())
        if not m:
            continue
        k = m.group(1)
        allr[k] = dict(dir=m.group(2), move=int(m.group(3)), ceil=int(m.group(4)), us=m.group(5))
        if m.group(5) == "sat out":
            sat[k] = allr[k]
    return allr, sat


def main():
    allr, sat = new_freeze()
    old = json.load(open(f"{SEC}/movement2_idle_gates.json"))
    runs = old["runs"]
    print(f"new freeze: {len(allr)} runs, {len(sat)} sat out")
    print(f"movement2 was built on {len(runs)} sat-out runs")

    import datetime as dt

    def secs(lbl):                     # 'MM-DD HH:MM' -> epoch, 2026
        return dt.datetime.fromisoformat("2026-" + lbl.replace(" ", "T") + ":00+00:00").timestamp()

    sat_ts = {k: secs(k) for k in sat}
    used = set()
    keep, dropped = [], []
    for r in runs:
        t = r["t"]
        hit = min(((k, abs(v - t)) for k, v in sat_ts.items() if k not in used),
                  key=lambda kv: kv[1], default=(None, 1e9))
        if hit[1] <= TOL_S:
            used.add(hit[0])
            keep.append(r)
        else:
            dropped.append(r)
    added = [k for k in sat if k not in used]
    print(f"  survive into the new list: {len(keep)}")
    print(f"  dropped by the re-freeze : {len(dropped)}  -> {[r['label'] for r in dropped]}")
    print(f"  NEW runs the lab never simulated: {len(added)} -> {added}")

    out = {"n_old": len(runs), "n_new_satout": len(sat), "kept": len(keep),
           "dropped": [r["label"] for r in dropped], "added": added, "arms": {}}
    for arm in ("pre_live", "pre_ungated", "post_live", "post_ungated"):
        for name, rows in (("old_65", runs), ("recut_on_new", keep)):
            fills, net, showed = 0, 0.0, 0
            wins = 0
            per = []
            for r in rows:
                got = False
                for g, v in r["arms"][arm].items():
                    for f in v["fills"]:
                        pnl = f["usd"]
                        fills += 1
                        net += pnl
                        wins += pnl > 0
                        per.append(pnl)
                        got = True
                showed += got
            best = max(per) if per else 0.0
            out["arms"].setdefault(arm, {})[name] = dict(
                runs_shown=showed, of=len(rows), fires=fills, net=round(net, 2),
                per_fire=round(net / fills, 2) if fills else None,
                win=round(100 * wins / fills, 1) if fills else None,
                strip_best=round(net - best, 2))
            print(f"  {arm:14s} {name:14s} shown {showed}/{len(rows):3d}  fires {fills:3d}  "
                  f"net {net:10,.2f}  $/fire {net/fills if fills else 0:8.2f}")
    json.dump(out, open(f"{SEC}/rev2_m2_recut.json", "w"), indent=1)
    print("\nwrote rev2_m2_recut.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
