#!/usr/bin/env python3
"""MOVEMENT 2 companion (week ending 2026-08-14) — THE TIMING-DECAY CURVE + THE CLIP A/B.

The idle-gate lab's central mechanism claim is that the gates, when they DO fire, fire
several minutes before ignition — and that a few minutes early is worth almost nothing.
This measures that directly: enter in-direction (hindsight direction, so entry SELECTION
is perfect) at a ladder of lead times before each frozen sat-out run, tick-honest, same
Lot A 1.5R + Lot B wide-chandelier exit, and watch the money decay.

Second question, same population: the QUIET-TAPE CLIP (entry ATR < 22 → Lot A banks $40,
Lot B banks max(1.75R, $60)). Identical entries, clip ON vs clip OFF, so the delta is the
clip and nothing else.

  PYTHONPATH=src .venv/bin/python scripts/idle_gate_timing_decay_wk33.py
"""
from __future__ import annotations

import json
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

from gazbot7.deciders import Bar, compute_features  # noqa: E402
from idle_gate_backtest_wk33 import CAP, ATR_SPLIT, Tape, load_census, to_epoch, trade  # noqa: E402

LEADS = [0, 30, 60, 120, 180, 240, 300, 420, 540, 600]
JSON = "/home/alphabot/gazbot7/reports/friday_v7/sections/movement2_wk33.json"


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
    ctx = json.load(open(JSON))["ctx"]

    def entry_atr(T):
        i = idx.get(T - 60)
        if i is not None and i >= 6:
            return compute_features(bars[max(0, i - 59):i + 1]).atr or 20.0
        return 20.0

    out = {}
    print(f"{'lead':>6}{'n':>5}{'net$':>10}{'$/run':>9}{'win%':>6}{'strip3':>10}"
          f"{'US$':>9}{'ON$':>9}{'chop$':>9}{'whip$':>9}{'trend$':>9}")
    for L in LEADS:
        recs = []
        for r in sat:
            s = r["t"]; c = ctx.get(s)
            if not c or not c["tape"]:
                continue
            T = to_epoch(s)
            if (T - L) * 1000 < lo or T * 1000 > hi:
                continue
            side = "LONG" if r["dir"] == "UP" else "SHORT"
            res = trade(tape, (T - L) * 1000, side, entry_atr(T), (1.5, "wide"))
            if res:
                recs.append(dict(net=res["net"], us=c["us"], regime=c["regime"], run=s))
        n = len(recs); net = sum(x["net"] for x in recs); w = sum(1 for x in recs if x["net"] > 0)
        srt = sorted((x["net"] for x in recs), reverse=True)
        us = sum(x["net"] for x in recs if x["us"]); on = net - us
        chop = sum(x["net"] for x in recs if x["regime"] in ("DEAD-CHOP", "NORMAL-CHOP"))
        whip = sum(x["net"] for x in recs if x["regime"] == "VIOLENT-WHIPSAW")
        tren = sum(x["net"] for x in recs if x["regime"] in ("CLEAN-TREND", "TREND-NO-BREAK", "BUILDING"))
        print(f"{L:>6}{n:>5}{net:>+10.1f}{net/n:>+9.1f}{100*w/n:>5.0f}%{sum(srt[3:]):>+10.1f}"
              f"{us:>+9.1f}{on:>+9.1f}{chop:>+9.1f}{whip:>+9.1f}{tren:>+9.1f}")
        out[str(L)] = dict(n=n, net=round(net, 1), per=round(net / n, 1), win=round(100 * w / n),
                           strip3=round(sum(srt[3:]), 1), us=round(us, 1), on=round(on, 1),
                           chop=round(chop, 1), whip=round(whip, 1), trend=round(tren, 1))

    # ── the quiet-tape clip A/B: identical entries, clip ON vs OFF ───────────
    print("\nQUIET-TAPE CLIP A/B (identical entries at each lead; ATR<%.0fpt is 'quiet')" % ATR_SPLIT)
    print(f"{'lead':>6}{'n':>5}{'quiet':>7}{'clipON$':>10}{'clipOFF$':>11}{'delta$':>10}")
    clip = {}
    for L in (0, 60, 300):
        on_, off_, nq, n = 0.0, 0.0, 0, 0
        rows_ = []
        for r in sat:
            s = r["t"]; c = ctx.get(s)
            if not c or not c["tape"]:
                continue
            T = to_epoch(s)
            if (T - L) * 1000 < lo or T * 1000 > hi:
                continue
            side = "LONG" if r["dir"] == "UP" else "SHORT"
            a = entry_atr(T)
            r1 = trade(tape, (T - L) * 1000, side, a, (1.5, "wide"), clip=True)
            r0 = trade(tape, (T - L) * 1000, side, a, (1.5, "wide"), clip=False)
            if not r1 or not r0:
                continue
            n += 1; nq += (a < ATR_SPLIT)
            on_ += r1["net"]; off_ += r0["net"]
            if a < ATR_SPLIT:
                rows_.append(dict(run=s, atr=round(a, 1), on=r1["net"], off=r0["net"]))
        print(f"{L:>6}{n:>5}{nq:>7}{on_:>+10.1f}{off_:>+11.1f}{off_-on_:>+10.1f}")
        clip[str(L)] = dict(n=n, quiet=nq, on=round(on_, 1), off=round(off_, 1),
                            delta=round(off_ - on_, 1), rows=rows_)
    out["clip_ab"] = clip

    p = "/home/alphabot/gazbot7/reports/friday_v7/sections/movement2_decay_wk33.json"
    json.dump(out, open(p, "w"), indent=1)
    print("JSON ->", p)


if __name__ == "__main__":
    main()
