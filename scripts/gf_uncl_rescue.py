#!/usr/bin/env python3
"""GF UNCLASS — STEP 6: the RESCUE. The rider works in ASIA; the UNCLASS money is in EUROPE + US-PM.

$3,036 of the bucket's $4,097 ceiling and 25 of its 34 runs sit in 06:00-13:00 and 15:00-20:00 UTC,
and the ASIA-shaped rider is a proven grave there (EUROPE -$1,985 at PF 0.78). Declaring victory on
the ASIA shelf while the bucket's own money sits untouched would be exactly the move the operator
banned. So this file attacks that half directly, and every attempt is reported whether it works or not.

  R1  WIDER STILL          stops to 6xATR, targets to 12xATR, caps to 6 hours. The operator's note
                           says "2.5-3.0xATR and beyond" — the first grid stopped at 4.0.
  R2  MANAGED EXITS        chandelier trail, break-even, and a "no target, time only" hold.
  R3  DIRECTION            the bucket is 65% DOWN — is a short-only rider a different animal?
  R4  A DIFFERENT ENTRY    slower thrust (w=20/30) and a PULLBACK board (wait for a retrace of the
                           thrust before filling) — a late board into an extended move is the most
                           likely reason a continuation rule dies in the busy sessions.
  R5  SIZE ESCALATION      score every attempt on the actual census runs, by size band.

    PYTHONPATH=src .venv/bin/python scripts/gf_uncl_rescue.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gf_rider_engine import Racer, run_trades, stat, line, strip_best, placebo  # noqa: E402
from gf_rider_tape import build                                    # noqa: E402
from gf_uncl_ride import signals, segment                          # noqa: E402
from gf_uncl_members import census_rows                            # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
OUT = {"attempts": []}


def rec(name, seg, tr, extra=""):
    st = stat(tr)
    s3 = strip_best(tr, 3) if len(tr) > 3 else 0.0
    print(line(f"{seg}: {name}", st, f"strip3=${s3:>7,.0f} {extra}"))
    OUT["attempts"].append(dict(seg=seg, name=name, **st, strip3=float(s3)))
    return st


def main():
    m1, s5 = build()
    racer = Racer(s5)
    sig10 = signals(m1, 10, 2.0)

    # ══ R1 — WIDER STILL ══════════════════════════════════════════════════════════════════════
    print("══ R1 — WIDER STILL: stops to 6xATR, targets to 12xATR, caps to 360min ══")
    for seg in ("EUROPE", "US-PM"):
        s = sig10[sig10.seg == seg]
        print(f"\n-- {seg}  n_fires={len(s)} --")
        targs = [4.0, 6.0, 8.0, 12.0, np.inf]
        for cap in (120, 240, 360):
            print(f"  cap={cap}min   stop\\targ" + "".join(
                f"{('inf' if not np.isfinite(t) else f'{t:g}'):>13}" for t in targs))
            for sa in (3.0, 4.0, 5.0, 6.0):
                cells = []
                for ta in targs:
                    tr = run_trades(racer, s, stop_a=sa, targ_a=ta, cap_min=cap)
                    st = stat(tr)
                    cells.append(f"{st['net']:>8,.0f}({st['n']:>3d})")
                    OUT["attempts"].append(dict(seg=seg, name=f"R1 wide {sa}/{ta}/{cap}", **st))
                print(f"    {sa:>4}          " + "".join(f"{c:>13}" for c in cells))

    # ══ R2 — MANAGED EXITS ════════════════════════════════════════════════════════════════════
    print("\n══ R2 — MANAGED EXITS on the same fires (chandelier / break-even / hold) ══")
    for seg in ("EUROPE", "US-PM"):
        s = sig10[sig10.seg == seg]
        print(f"\n-- {seg} --")
        rec("3.0 stop / 6R targ (reference)", seg, run_trades(racer, s, stop_a=3.0, targ_a=6.0, cap_min=120))
        for arm, trail in ((2.0, 1.5), (3.0, 2.0), (4.0, 2.0)):
            rec(f"chandelier arm{arm} trail{trail}, no target", seg,
                run_trades(racer, s, stop_a=3.0, targ_a=np.inf, cap_min=240, arm_a=arm, trail_a=trail))
        for be in (1.0, 2.0):
            rec(f"BE at {be}R + 3.0 stop / 6R targ", seg,
                run_trades(racer, s, stop_a=3.0, targ_a=6.0, cap_min=120, be_a=be))
        rec("no target, 240min time-only, 3.0 stop", seg,
            run_trades(racer, s, stop_a=3.0, targ_a=np.inf, cap_min=240))

    # ══ R3 — DIRECTION ════════════════════════════════════════════════════════════════════════
    print("\n══ R3 — DIRECTION (the bucket is 65% DOWN) ══")
    for seg in ("EUROPE", "US-PM"):
        s = sig10[sig10.seg == seg]
        for side, nm in ((-1, "SHORT only"), (1, "LONG only")):
            ss = s[s.side == side]
            tr = run_trades(racer, ss, stop_a=2.5, targ_a=6.0, cap_min=120)
            pl = placebo(racer, s, len(ss), 100, stop_a=2.5, targ_a=6.0, cap_min=120)
            rec(nm, seg, tr, f"placebo p95 ${pl['per_p95']:.2f}")

    # ══ R4 — A DIFFERENT ENTRY ════════════════════════════════════════════════════════════════
    print("\n══ R4 — SLOWER THRUST, and a PULLBACK board instead of an immediate one ══")
    for w, k in ((20, 2.5), (30, 3.0), (30, 2.0)):
        sg = signals(m1, w, k)
        for seg in ("EUROPE", "US-PM"):
            s = sg[sg.seg == seg]
            if len(s) < 30:
                continue
            rec(f"thrust w={w} k={k}, 3.0/6R/120", seg,
                run_trades(racer, s, stop_a=3.0, targ_a=6.0, cap_min=120))

    # PULLBACK board: thrust fires at t, but do not fill until price retraces `pb` x ATR against it
    # within the next `wait` minutes. Fill at that level (a resting limit, so no slippage penalty
    # beyond the same one tick), else no trade.
    print("\n  -- PULLBACK board (wait for a retrace before filling) --")
    mm = m1.set_index("ts")
    for pb in (0.5, 1.0):
        for wait in (10, 20):
            for seg in ("EUROPE", "US-PM"):
                s = sig10[sig10.seg == seg]
                rows = []
                for r in s.itertuples():
                    lim = r.entry - r.side * pb * r.atr
                    fw = m1[(m1.ts >= r.ts) & (m1.ts <= r.ts + wait * 60)]
                    if not len(fw):
                        continue
                    hit = fw[(fw.l <= lim) if r.side > 0 else (fw.h >= lim)]
                    if not len(hit):
                        continue
                    rows.append(dict(ts=int(hit.iloc[0].ts) + 60, side=r.side, entry=lim,
                                     atr=r.atr, day=r.day, seg=seg, hh=r.hh, regime=r.regime))
                if len(rows) < 30:
                    continue
                tr = run_trades(racer, pd.DataFrame(rows).sort_values("ts"),
                                stop_a=3.0, targ_a=6.0, cap_min=120)
                rec(f"pullback {pb}xATR within {wait}min, 3.0/6R", seg, tr)

    # ══ R5 — score the best survivors on the census runs themselves ══════════════════════════
    print("\n══ R5 — the best EUROPE/US-PM attempt scored on the actual sat-out UNCLASS runs ══")
    A = pd.DataFrame(OUT["attempts"])
    A = A[(A.n >= 40)].sort_values("per", ascending=False)
    print(A.head(12).round(2).to_string(index=False))
    OUT["best_rescue"] = A.head(12).to_dict("records")

    json.dump(OUT, open(f"{SEC}/gf_uncl_rescue.json", "w"), indent=1, default=float)
    print(f"\n-> {SEC}/gf_uncl_rescue.json")


if __name__ == "__main__":
    main()
