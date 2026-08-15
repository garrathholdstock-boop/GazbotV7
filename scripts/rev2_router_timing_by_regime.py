#!/usr/bin/env python3
"""REV2 Q5 — does the router's 45/5/3 timing change survive on the TRENDING days?

SATURDAY #1 (+$502 live set / +$399 full set) rests on 4 of 40 days, on a 40-day window §4 itself
calls "overwhelmingly ONE regime", with this week at 84% chop — and the router is a trend
instrument. §4 flags that and does not test it. This tests it.

  * Rank all 40 Paris days by SESSION EFFICIENCY (|close−open| / sum|1-min changes| over the
    router's own trading window), which is the same quantity the router's threshold reads.
  * Hold out the TOP 8 — the trending eighth of the sample — and score shipped vs 45/5/3 on
    those 8 days alone, then on the remaining 32, then on all 40.
  * Name the days that actually produced the gain, with their session ER and their regime label,
    so "it is only ever measured where the router has nothing to do" is answered with days.

Everything is imported from scripts/router_study.py so the replay engine, the universes and the
shipped constants are literally the same code the §4 sweep ran.

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/rev2_router_timing_by_regime.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import router_study as RS                                     # noqa: E402
from gazbot7 import direction_router as dr, pnl               # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_router_timing_regime.json"
DAYS = 40
BEST = dict(er=0.15, net=30.0, step=5, hold=3, window=45, fast=False)   # §4's TAKE, minus net→20
HOLDOUT = 8


def session_er(mins, closes, t0, t1) -> float:
    c = [px for m, px in zip(mins, closes) if t0 <= m < t1]
    if len(c) < 30:
        return 0.0
    path = sum(abs(c[i] - c[i - 1]) for i in range(1, len(c))) or 1.0
    return abs(c[-1] - c[0]) / path


def main() -> None:
    t = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(t).timestamp() if isinstance(t, str) else t.timestamp()
    RS._register_bounds(today0, DAYS)
    con = duckdb.connect()
    con.execute(f"ATTACH '{dr.CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{RS.DB}' AS g (TYPE sqlite, READ_ONLY)")
    daydata = RS.load_days(con, today0, DAYS)
    con.close()

    er = {}
    for date, mins, closes, _tr in daydata:
        t0, t1 = RS._t0(date, daydata), RS._t1(date, daydata)
        er[date] = session_er(mins, closes, t0, t1)
    ranked = sorted(er, key=lambda d: -er[d])
    trend_days, rest = set(ranked[:HOLDOUT]), set(ranked[HOLDOUT:])
    print(f"{len(daydata)} Paris days. Session ER: median {sorted(er.values())[len(er)//2]:.3f}, "
          f"top-{HOLDOUT} cut at {er[ranked[HOLDOUT-1]]:.3f}, max {er[ranked[0]]:.3f}")
    print("  TREND eighth: " + ", ".join(f"{d}({er[d]:.2f})" for d in ranked[:HOLDOUT]))

    res = {"days": DAYS, "holdout": HOLDOUT, "session_er": {d: round(v, 4) for d, v in er.items()},
           "trend_days": sorted(trend_days), "sets": {}}

    for label, (down, up) in [("LIVE managed set", (RS.LIVE_DOWN, RS.LIVE_UP)),
                              ("FULL historical fader set", (RS.DOWN_FADERS, RS.UP_FADERS))]:
        print(f"\n{'='*88}\nUNIVERSE: {label}\n{'='*88}")
        block = {}
        for sub, name in ((None, "all 40 days"), (trend_days, f"the trending {HOLDOUT}"),
                          (rest, f"the other {DAYS-HOLDOUT}")):
            dd = daydata if sub is None else [d for d in daydata if d[0] in sub]
            a = RS.eval_config(dd, down, up, RS.SHIPPED, per_day=True)
            b = RS.eval_config(dd, down, up, BEST, per_day=True)
            block[name] = {"n_days": len(dd), "baseline": round(a["base"], 2),
                           "shipped_router": round(a["router"], 2),
                           "best_router": round(b["router"], 2),
                           "improvement": round(b["router"] - a["router"], 2),
                           "blocked_shipped": a["n_blk"], "blocked_best": b["n_blk"]}
            e = block[name]
            print(f"  {name:22s} baseline ${e['baseline']:+9,.2f}  shipped ${e['shipped_router']:+9,.2f}  "
                  f"45/5/3 ${e['best_router']:+9,.2f}  improvement ${e['improvement']:+8,.2f}  "
                  f"(blocked {e['blocked_shipped']}→{e['blocked_best']})")

        # which days actually move, and what regime were they
        a = RS.eval_config(daydata, down, up, RS.SHIPPED, per_day=True)["per"]
        b = RS.eval_config(daydata, down, up, BEST, per_day=True)["per"]
        moved = []
        for (d1, base1, r1, _), (d2, _b2, r2, _) in zip(a, b):
            if abs(r2 - r1) > 0.005:
                moved.append({"day": d1, "session_er": round(er[d1], 3),
                              "in_trend_eighth": d1 in trend_days,
                              "shipped": round(r1, 2), "best": round(r2, 2),
                              "delta": round(r2 - r1, 2)})
        block["days_that_moved"] = moved
        print(f"  days that changed at all: {len(moved)}")
        print(f"    {'day':7s}{'sessER':>8s}{'trend8?':>9s}{'shipped$':>10s}{'45/5/3$':>10s}{'delta':>10s}")
        for m in sorted(moved, key=lambda x: -abs(x["delta"])):
            print(f"    {m['day']:7s}{m['session_er']:8.3f}{'YES' if m['in_trend_eighth'] else 'no':>9s}"
                  f"{m['shipped']:10.2f}{m['best']:10.2f}{m['delta']:+10.2f}")
        res["sets"][label] = block

    json.dump(res, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
