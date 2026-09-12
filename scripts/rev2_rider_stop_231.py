#!/usr/bin/env python3
"""REV2 — does a protective stop beat running naked, on the SAME 231 sessions the operator's
2026-08-20 "no stop" decision was taken on?

Why this exists. The Rev1 card proposed a 3.0xATR resting stop as "the week's highest-value change"
on the strength of SIX rider entries in ONE week. src/gazbot7/day_rider.py:93-102 records that the
operator refused a stop on 2026-08-20 ("i dont want any stop. leave them all naked"), and records
the desk's own counter-evidence beside it: the venue stop "costs $3,451 of expectancy AND has a
WORSE worst-day (-$1,603) than running naked (-$1,531)". A one-week grid cannot overturn that; the
only honest way to re-open it is to race the proposal on the same population, with the ladder that
actually shipped that day.

WHAT IS RACED. The LIVE configuration as of 2026-08-20: 4 lots, per-lot profit rungs at
50/100/200/300pt ($100/$200/$400/$600 at $2.00/pt/lot), the shipped ATR trail (arm 4xATR, trail
2xATR off the peak, ATR frozen at entry), hard flat 20:40Z, no breakeven move. The ONLY thing that
changes between arms is the protective stop. Fee $1.50 per round trip per lot.

Every arm is reported at entry delay 0/2/4/8 minutes, per rider_lab's own standing rule — the live
detector confirms later than the lab and a candidate that only wins at delay 0 is not real.
"""
from __future__ import annotations
import json
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
sys.path.insert(0, f"{GB}/scripts")

import rider_lab as R                                                    # noqa: E402


def live_cfg(**kw):
    """The rider as it actually ships on 2026-08-20 — the ladder, the trail, no breakeven."""
    c = R.Cfg(rungs=[50.0, 100.0, 200.0, 300.0], lots=4,
              adverse_cut_pt=0.0, adverse_cut_atr=0.0,
              breakeven_after_lot=0, trail_atr_arm=4.0, trail_atr_mult=2.0)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def main() -> int:
    from gazbot7.lake import connect
    con = connect(symbol="MNQ")
    S = R.sessions()
    arms = [("naked (LIVE, 2026-08-20)", dict(adverse_cut_atr=0.0))]
    for k in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0):
        arms.append((f"stop {k:.1f}xATR", dict(adverse_cut_atr=k)))

    out = {"n_sessions": len(S), "arms": {}}
    for label, kw in arms:
        out["arms"][label] = {}
        for delay in (0, 2, 4, 8):
            rows = R.run_all(con, live_cfg(entry_delay_min=delay, **kw), S)
            s = R.summarise(rows, label)
            # leave-one-MONTH-out worst fold, and the days the stop actually bit
            by_month = {}
            for r in rows:
                by_month.setdefault(r["day"][:7], []).append(r["total"])
            tot = sum(r["total"] for r in rows)
            s["loo_month_worst"] = round(min(tot - sum(v) for v in by_month.values()), 0)
            s["n_cut"] = sum(1 for r in rows
                             if any(x[0] == "ADVERSE_CUT" for x in r["per_lot"]))
            s["p10"] = round(sorted(r["total"] for r in rows)[len(rows) // 10], 0)
            out["arms"][label][delay] = s
            print(f"{label:26s} delay={delay}  {s}")
        print()

    with open(f"{GB}/reports/friday_v7/sections/rev2_rider_stop_231.json", "w") as fh:
        json.dump(out, fh, indent=1)
    print("wrote rev2_rider_stop_231.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
