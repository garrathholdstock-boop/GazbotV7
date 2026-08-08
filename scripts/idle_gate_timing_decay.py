#!/usr/bin/env python3
"""MOVEMENT 2 companion — THE TIMING-DECAY CURVE.

The idle-gate lab's central mechanism claim is that the gates, when they DO fire, fire
several minutes before ignition — and that a few minutes early is worth almost nothing.
This measures that directly: enter in-direction (hindsight direction, so entry SELECTION
is perfect) at a ladder of lead times before each frozen sat-out run, tick-honest, same
Lot A 1.5R + Lot B wide-chandelier exit, and watch the money decay.

  PYTHONPATH=src .venv/bin/python scripts/idle_gate_timing_decay.py
"""
from __future__ import annotations

import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

from gazbot7.deciders import Bar, compute_features, efficiency_ratio  # noqa: E402
from idle_gate_backtest_wk32 import CAP, Tape, load_census, to_epoch, trade  # noqa: E402

LEADS = [0, 30, 60, 120, 180, 240, 300, 420, 540, 600]


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    rows = con.execute("""
        WITH m AS (SELECT (bar_ts - (bar_ts % 60)) AS mt, bar_ts, open, high, low, close, volume
                   FROM c.bars WHERE symbol='MNQ' AND timeframe='5s')
        SELECT mt, arg_min(open,bar_ts), max(high), min(low), arg_max(close,bar_ts), sum(volume)
        FROM m GROUP BY mt ORDER BY mt""").fetchall()
    bars = [Bar(int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rows]
    idx = {b.ts: i for i, b in enumerate(bars)}
    t = con.execute("SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' ORDER BY ts_ms").fetchnumpy()
    ts_a, px_a = t["ts_ms"].astype("int64"), t["price"].astype("float64")
    tape = Tape(ts_a, px_a)
    lo, hi = int(ts_a[0]), int(ts_a[-1])

    sat = [r for r in load_census() if r["us"] == "sat out"]
    ctx = json.load(open("/home/alphabot/gazbot7/reports/friday_v7/sections/movement2_wk32.json"))["ctx"]

    out = {}
    print(f"{'lead':>6}{'n':>5}{'net$':>10}{'$/run':>9}{'win%':>6}{'strip3':>10}"
          f"{'US$':>9}{'ON$':>9}{'chop$':>9}{'whip$':>9}")
    for L in LEADS:
        recs = []
        for r in sat:
            s = r["t"]; c = ctx[s]
            if not c["tape"]:
                continue
            T = to_epoch(s)
            if (T - L) * 1000 < lo or T * 1000 > hi:
                continue
            i = idx.get(T - 60)          # full-precision entry ATR, same basis as the main lab
            atr = 20.0
            if i is not None and i >= 6:
                atr = compute_features(bars[max(0, i - 59):i + 1]).atr or 20.0
            side = "LONG" if r["dir"] == "UP" else "SHORT"
            res = trade(tape, (T - L) * 1000, side, atr, (1.5, "wide"))
            if res:
                recs.append(dict(net=res["net"], us=c["us"], regime=c["regime"], run=s))
        n = len(recs); net = sum(x["net"] for x in recs); w = sum(1 for x in recs if x["net"] > 0)
        srt = sorted((x["net"] for x in recs), reverse=True)
        us = sum(x["net"] for x in recs if x["us"]); on = net - us
        chop = sum(x["net"] for x in recs if x["regime"] in ("DEAD-CHOP", "NORMAL-CHOP"))
        whip = sum(x["net"] for x in recs if x["regime"] == "VIOLENT-WHIPSAW")
        print(f"{L:>6}{n:>5}{net:>+10.1f}{net/n:>+9.1f}{100*w/n:>5.0f}%{sum(srt[3:]):>+10.1f}"
              f"{us:>+9.1f}{on:>+9.1f}{chop:>+9.1f}{whip:>+9.1f}")
        out[str(L)] = dict(n=n, net=round(net, 1), per=round(net / n, 1), win=round(100 * w / n),
                           strip3=round(sum(srt[3:]), 1), us=round(us, 1), on=round(on, 1),
                           chop=round(chop, 1), whip=round(whip, 1))
    p = "/home/alphabot/gazbot7/reports/friday_v7/sections/movement2_decay.json"
    json.dump(out, open(p, "w"), indent=1)
    print("JSON ->", p)


if __name__ == "__main__":
    main()
