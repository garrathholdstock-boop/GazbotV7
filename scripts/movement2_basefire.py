#!/usr/bin/env python3
"""MOVEMENT 2 — THE BASE-RATE CONTROL.

The run-window measurement only looks at tape we ALREADY KNOW contained a big run. That is
hindsight selection: it counts a gate's fires where the move existed and never counts the ones
where it did not. This fires the same six gates, same live config, across the ENTIRE captured
week (08-17..08-21) so every fire is counted — the honest denominator.

  PYTHONPATH=src .venv/bin/python scripts/movement2_basefire.py
"""
from __future__ import annotations
import datetime as dt, json, sqlite3, sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from movement2_idle_gates import (BASE_GATES, CAP, SYM, Tape, simulate, load_runs)
from gazbot7.slot_strategy import scaleout_slots

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/movement2_basefire.json"
CHUNK = 4 * 3600


def main():
    con = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    lo, hi = con.execute("SELECT MIN(ts_ms),MAX(ts_ms) FROM ticks WHERE symbol=?", (SYM,)).fetchone()
    t_lo, t_hi = int(lo // 1000) + 4000, int(hi // 1000)     # +4000s so the 60-bar deque is warm
    specs = {s.tag: s for s in scaleout_slots()}
    by_base = {g: (specs[f"{g}_A"], specs[f"{g}_B"]) for g in BASE_GATES}
    out = {g: {"fills": [], "blocked": {}, "raw": 0} for g in BASE_GATES}
    t = t_lo
    while t < t_hi:
        end = min(t + CHUNK, t_hi)
        tape = Tape(con, t, end + 7200)
        fills, blocked, raw = simulate(tape, by_base, t, end, ungated=False)
        for g in BASE_GATES:
            out[g]["fills"] += fills[g]
            out[g]["raw"] += raw[g]
            for k, v in blocked[g].items():
                out[g]["blocked"][k] = out[g]["blocked"].get(k, 0) + v
        n = sum(len(fills[g]) for g in BASE_GATES)
        print(f"{dt.datetime.fromtimestamp(t, dt.UTC):%m-%d %H:%M} .. "
              f"{dt.datetime.fromtimestamp(end, dt.UTC):%H:%M}  fires={n}", flush=True)
        t = end
    json.dump(out, open(OUT, "w"))
    print("\n== FULL-WEEK BASE RATE (live config, every fire counted) ==")
    print(f"{'gate':<20}{'fires':>7}{'net$':>11}{'win%':>7}{'$/fire':>9}")
    tot = 0.0
    for g in BASE_GATES:
        f = out[g]["fills"]
        s = sum(x["usd"] for x in f); tot += s
        w = 100 * sum(1 for x in f if x["usd"] > 0) / len(f) if f else 0
        print(f"{g:<20}{len(f):>7}{s:>+11.2f}{w:>7.0f}{(s/len(f) if f else 0):>+9.2f}")
    print(f"{'ROSTER':<20}{sum(len(out[g]['fills']) for g in BASE_GATES):>7}{tot:>+11.2f}")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
