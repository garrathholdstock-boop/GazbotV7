#!/usr/bin/env python3
"""REV-3d — LAG COST PER BIG RUN, correctly paired.

The naive pairing (first fast fire vs first slow fire inside a +/-15min window) matches unrelated
events and produces nonsense — including "fast fires" that are LATER than the desk's, which are
extra entries, not saved lag.  The honest pairing is anchored on the desk's OWN behaviour:

    desk fill  = the first SLOW fire inside the run window, PLUS 55s where the gate carries the
                 absorption veto (abs_veto_long / abs_veto_short) — i.e. the real fill instant.
    fast fill  = the EARLIEST fast fire in the 150s BEFORE that desk fill (65s of bar staleness +
                 55s of veto + slack is the widest the lag can physically be).
    lag saved  = desk fill price - fast fill price, signed in the run's direction, x $2/pt x 2 lots
                 (the live scale-out puts two 1-lot sub-slots on every signal).
    no fast fire in the window -> lag saved is ZERO for that run, and it is still counted in the
    denominator.  Runs the fast layer never reached cannot be quietly dropped.

  PYTHONPATH=src ./.venv/bin/python scripts/rev3_lagcost.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb

import rev3_two_layer as R

BAR = ["abs_veto_long", "abs_veto_short", "grind_long"]
ALL = set(R.REGIMES)
LOOKBACK_S = 150
TREND_DAYS = ["2026-07-29", "2026-07-30"]


def census_runs(min_atr=1.5):
    con = duckdb.connect()
    rows = con.execute(f"SELECT bar_ts,open,high,low,close FROM '{R.SCRATCH}/bars5s.parquet' "
                       f"ORDER BY bar_ts").fetchall()
    con.close()
    W, STEP = 180, 12
    rng = [max(x[2] for x in rows[i:i + W]) - min(x[3] for x in rows[i:i + W])
           for i in range(0, len(rows) - W, STEP)]
    typ = sorted(rng)[len(rng) // 2]
    thr = min_atr * typ
    cands = sorted(((abs(rows[i + W][4] - rows[i][4]), i, rows[i + W][4] - rows[i][4])
                    for i in range(0, len(rows) - W, STEP)
                    if abs(rows[i + W][4] - rows[i][4]) >= thr), reverse=True)
    runs, used = [], []
    for _, i, mv in cands:
        if not any(abs(i - j) < W for j in used):
            used.append(i)
            runs.append((rows[i][0], mv))
    runs.sort()
    return typ, thr, runs


def main(days=None, label="TREND days 07-29 / 07-30"):
    days = days or TREND_DAYS
    typ, thr, runs = census_runs()
    out = []
    for day in days:
        d = R.build_day(day)
        F = {}
        for tag in BAR:
            F[tag] = dict(
                slow=[f for f in R.simulate(d, tag, fast_cells=set(), filt=R.BASE, collect=True)[1]
                      if f[1] == "slow"],
                fast=[f for f in R.simulate(d, tag, fast_cells=ALL, filt=R.BASE, collect=True)[1]
                      if f[1] == "fast"])
        for start, mv in runs:
            if not (d["t0"] <= start < d["t1"]):
                continue
            side = "LONG" if mv > 0 else "SHORT"
            for tag in BAR:
                if R.GATES[tag]["side"] != side:
                    continue
                s = [f for f in F[tag]["slow"] if start - 300 <= f[0] <= start + 900]
                if not s:
                    continue
                s0 = s[0]
                lf_sec = s0[0] + (R.VETO_SECS if R.GATES[tag]["veto"] else 0)
                i = lf_sec - d["t_lo"]
                lf_px = float(d["dec"][i]) if 0 <= i < len(d["dec"]) else None
                if lf_px is None:
                    continue
                pre = [f for f in F[tag]["fast"] if lf_sec - LOOKBACK_S <= f[0] <= lf_sec]
                rec = dict(day=day, t=dt.datetime.fromtimestamp(start, dt.UTC).strftime("%m-%d %H:%M"),
                           dir="UP" if mv > 0 else "DN", move=round(mv, 0), ceil=round(abs(mv) * 2, 0),
                           gate=tag, desk_px=lf_px, fast_px=None, early=None, dpt=0.0, dusd=0.0,
                           matched=False)
                if pre:
                    f0 = pre[0]
                    imp = (lf_px - f0[2]) if side == "LONG" else (f0[2] - lf_px)
                    rec.update(fast_px=f0[2], early=lf_sec - f0[0], dpt=round(imp, 2),
                               dusd=round(imp * R.VPP * 2, 1), matched=True)
                out.append(rec)

    print(f"{label} — typical 15-min range {typ:.1f}pt, run threshold {thr:.1f}pt")
    print(f"{'run (UTC)':<13}{'dir':>4}{'move':>7}{'$ceil':>7}  {'gate':<16}"
          f"{'desk fill':>10}{'fast fill':>10}{'s early':>8}{'dpt':>8}{'d$ 2lot':>9}")
    tm = tu = 0.0
    nm = 0
    for o in out:
        fp = f"{o['fast_px']:.2f}" if o["fast_px"] is not None else "—"
        ea = str(o["early"]) if o["early"] is not None else "—"
        print(f"{o['t']:<13}{o['dir']:>4}{o['move']:>+7.0f}{o['ceil']:>7.0f}  {o['gate']:<16}"
              f"{o['desk_px']:>10.2f}{fp:>10}{ea:>8}{o['dpt']:>+8.2f}{o['dusd']:>+9.0f}")
        if o["matched"]:
            nm += 1
            tm += o["dpt"]
            tu += o["dusd"]
    n = len(out)
    print(f"\nrun x gate pairs where the desk fired: {n};  the FAST layer pre-empted {nm} of them")
    if nm:
        print(f"LAG SAVED on the {nm} pre-empted: {tm:+.1f}pt = ${tu:+.0f}  (mean {tm/nm:+.2f}pt/run)")
    print(f"LAG SAVED over ALL {n} pairs (zeros included): {tm/n:+.2f}pt/pair = ${tu/n:+.1f}/pair, "
          f"${tu:+.0f} total")
    with open(f"{R.SCRATCH}/rev3_lagcost.json", "w") as f:
        json.dump(dict(typ=typ, thr=thr, rows=out, n=n, n_matched=nm, pt=tm, usd=tu), f)


if __name__ == "__main__":
    main()
