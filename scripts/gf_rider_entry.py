#!/usr/bin/env python3
"""GF RIDER · STEP 2b — the ENTRY threshold is an operator GUESS too. Sweep it.

Step 1 picked w=10/k=1.5 because it boards 59 of the 60 sat-out runs. That is the SENSITIVITY end of
the dial and it fires 490 times a session — 25x more often than a run happens. The census's own bar
is a 15-minute move of 44pt against a ~8pt ATR, i.e. roughly 5xATR, so the proof requirement almost
certainly wants to be far higher than 1.5.

This sweeps (w, k) jointly against the wide exits, and scores each cell on BOTH things that matter:

    money   $/trade over the whole 49-session tape, per regime and per session-half
    reach   how many of the 60 sat-out census runs it still boards (big-moves-caught)

A cell that makes money by never firing has no reach and is useless; a cell with perfect reach and
no money is the k=1.5 result we already have.

    PYTHONPATH=src .venv/bin/python scripts/gf_rider_entry.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_rider_board import sat_out_runs  # noqa: E402
from gf_rider_engine import Racer, by, line, run_trades, stat, strip_best  # noqa: E402
from gf_rider_signals import signals  # noqa: E402
from gf_rider_tape import build  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
pd.set_option("display.width", 250)

EXITS = {
    "wide 3.0/6R":   dict(stop_a=3.0, targ_a=6.0, cap_min=120),
    "wide 4.0/6R":   dict(stop_a=4.0, targ_a=6.0, cap_min=120),
    "BE2 3.0/HOLD":  dict(stop_a=3.0, targ_a=np.inf, cap_min=120, be_a=2.0),
    "hold 60 hard":  dict(stop_a=99.0, targ_a=np.inf, cap_min=60),
}


def reach(sig: pd.DataFrame, runs: pd.DataFrame) -> int:
    """big-moves-caught: sat-out runs with at least one fire, correctly signed, inside the run."""
    n = 0
    for r in runs.itertuples():
        f = sig[(sig["sig_ts"] >= r.ts) & (sig["sig_ts"] <= r.ts + 900) & (sig["side"] == r.dirn)]
        n += len(f) > 0
    return n


def main():
    m1, s5 = build()
    racer = Racer(s5)
    runs = sat_out_runs()
    sessions = m1["day"].nunique()
    print(f"═══ STEP 2b · ENTRY-THRESHOLD SWEEP — {sessions} sessions, "
          f"{len(runs)} sat-out runs ═══\n")

    rows = []
    for w in (10, 15, 20, 30):
        for k in (1.5, 2.0, 2.5, 3.0, 4.0, 5.0):
            sig = signals(m1, w, k)
            if len(sig) < 30:
                continue
            rc = reach(sig, runs)
            for ename, kw in EXITS.items():
                tr = run_trades(racer, sig, **kw)
                st = stat(tr)
                if st["n"] < 25:
                    continue
                us = tr[tr["tod"] != "overnight"]
                rows.append(dict(w=w, k=k, exit=ename, fires=len(sig),
                                 fires_ses=round(len(sig) / sessions, 1), reach=rc,
                                 n=st["n"], net=st["net"], per=st["per"], win=st["win"],
                                 pf=st["pf"], strip3=strip_best(tr, 3),
                                 us_n=len(us), us_net=round(us["net"].sum(), 0),
                                 us_per=round(us["net"].mean(), 2) if len(us) else 0.0))
            print(f"  w={w:>2d} k={k:<4.1f} fires={len(sig):>6,d} "
                  f"({len(sig)/sessions:>5.1f}/ses)  boards {rc}/{len(runs)} runs", flush=True)

    g = pd.DataFrame(rows)
    print("\n── EVERY (w, k, exit) CELL, sorted by $/trade over the WHOLE tape ──\n")
    print(g.sort_values("per", ascending=False).to_string(index=False))

    print("\n── the same cells, US-SESSION ONLY (13:00-20:00 UTC) ──\n")
    print(g.sort_values("us_per", ascending=False).head(30).to_string(index=False))

    print("\n── REACH vs MONEY: what does tightening the proof requirement cost in runs boarded? ──\n")
    r2 = g.groupby(["w", "k"]).agg(fires_ses=("fires_ses", "first"), reach=("reach", "first"),
                                   best_per=("per", "max"), best_us=("us_per", "max")).reset_index()
    print(r2.to_string(index=False))

    json.dump(g.to_dict("records"), open(f"{OUT}/gf_rider_entry.json", "w"), indent=1, default=str)
    print(f"\n→ {OUT}/gf_rider_entry.json")


if __name__ == "__main__":
    main()
