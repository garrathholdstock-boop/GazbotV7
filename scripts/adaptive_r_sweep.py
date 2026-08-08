#!/usr/bin/env python3
"""GIVE-BACK STUDY — stage 5: the ladder, the tape bands, and the incremental-value test.

Runs on the sequential simulator in adaptive_r_sim.py. Everything here is per-LOT: a
"pair" cell is two independent single-lot slots summed, which is exactly how the live
dual-slot scale-out desk books it.

★ THE FRAMING THAT DECIDES THIS STUDY: the desk's R is ALREADY ATR-proportional. The stop
is 1 x entry-ATR and the target is R x that stop, so a FIXED R already shrinks the dollar
target automatically when the tape goes quiet. "Tighten the R on quiet tape" therefore
means tighten it BEYOND the automatic ATR scaling. That is the only thing worth testing,
and it is what the incremental test below isolates.

  PYTHONPATH=src ./.venv/bin/python scripts/adaptive_r_sweep.py
"""
from __future__ import annotations

import pickle
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from adaptive_r_sim import (  # noqa: E402
    RULES, SCR, day_of, load_tape, session_ends, simulate, window_of,
)

pd.set_option("display.width", 260)

# The LOADED live pair per gate — verified in code (slot_strategy.scaleout_slots() with
# data/exit_overrides.json applied), not recalled. See stage-6 section for the printout.
LOADED = {"grind_long": ("A2.5", "wide"),
          "abs_veto_long": ("A1.0", "A1.5"),
          "abs_veto_short": ("A1.5", "A2.5"),
          "rgv_short": ("A1.5", "tight")}

LADDER = ["A0.5", "A0.75", "A1.0", "A1.25", "A1.5", "A2.0", "A2.5", "A3.0",
          "A3.5", "A4.0", "A5.0", "A6.0", "tight", "k2.5", "k3.5", "wide"]


def load():
    with open(f"{SCR}/ar_signals.pkl", "rb") as fh:
        sig = pickle.load(fh)
    ts, px, sg, sz, bars = load_tape()
    ends = session_ends(ts)
    # attach the two ALTERNATIVE tape proxies (ATR is already on the signal)
    con = duckdb.connect()
    b = con.execute(f"SELECT * FROM '{SCR}/mfe_bars1m.parquet' ORDER BY ts").df()
    h, lo, v = b.h.to_numpy(), b.l.to_numpy(), b.v.to_numpy()
    b["rr15"] = (pd.Series(h).rolling(15).max() - pd.Series(lo).rolling(15).min()).to_numpy()
    v5 = pd.Series(v).rolling(5).sum()
    b["rvol"] = (v5 / v5.rolling(60).median()).to_numpy()
    b["vrate"] = v5.to_numpy() / 5.0                      # raw contracts/min, last 5 min
    sig = sig.merge(b[["ts", "rr15", "rvol", "vrate"]], on="ts", how="left")
    sig["win"] = sig.dec_ms.map(window_of)
    sig["day"] = sig.dec_ms.map(day_of)
    return sig, (ts, px, ends)


def run_all(sig, tape):
    """Every rule as a standalone single-lot sequential slot, per gate."""
    ts, px, ends = tape
    out = []
    for gate, g in sig.groupby("gate"):
        g = g.sort_values("dec_ms")
        for key in LADDER:
            r = simulate(g, lambda _row, k=key: k, ts, px, ends, tag=gate)
            if len(r):
                r["gate"] = gate
                r["win"] = r.dec_ms.map(window_of)
                r["day"] = r.dec_ms.map(day_of)
                out.append(r)
    return pd.concat(out, ignore_index=True)


def ladder_table(res, gate, win=None):
    d = res[res.gate == gate]
    if win:
        d = d[d.win == win]
    rows = []
    for key in LADDER:
        s = d[d.rule == key]
        if not len(s):
            continue
        byday = s.groupby("day").pnl.sum()
        rows.append({"rule": key, "fills": len(s), "net$": s.pnl.sum(),
                     "$/fill": s.pnl.mean(), "win%": 100 * (s.pnl > 0).mean(),
                     "med hold s": s.hold_s.median(),
                     "LODO worst": min((byday.sum() - byday[d0]) for d0 in byday.index),
                     "days+": int((byday > 0).sum()), "days": len(byday)})
    return pd.DataFrame(rows)


def main():
    sig, tape = load()
    print("SIGNALS  (16 sessions, live deciders, unified tick tape)")
    print(sig.groupby(["gate", "win"]).size().unstack(fill_value=0).to_string(), "\n")

    res = run_all(sig, tape)
    with open(f"{SCR}/ar_res.pkl", "wb") as fh:
        pickle.dump((sig, res), fh)

    for gate in ["grind_long", "abs_veto_long", "abs_veto_short", "rgv_short"]:
        for win in ["QUIET", "US"]:
            t = ladder_table(res, gate, win)
            if not len(t):
                continue
            ld = LOADED[gate]
            print(f"\n=== {gate} — {win} window ===  (loaded pair: Lot A {ld[0]} / Lot B {ld[1]})")
            print(t.round(2).to_string(index=False))
    print(f"\nwrote {SCR}/ar_res.pkl")


if __name__ == "__main__":
    main()
