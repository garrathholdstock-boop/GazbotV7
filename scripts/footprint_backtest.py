#!/usr/bin/env python3
"""Backtest the two FOOTPRINT gates (capitulation_long, exhaustion_short) on the V5 archive
tick + L2 data (~12 days, Jul 5–17). These are tick/book gates, so this is a TICK replay
(not bar-close) — the honest fill path. Reuses gazbot7's own footprint_summary / gate_capitulation
/ exhaustion_signal via an adapter that maps the V5 schema (trade_tick / depth_snap) to the
`ticks` / `book` tables the code expects.

Exits: the footprint fixed-point scalp (8pt stop / 12pt target / 120s), on the tick path.
CAVEAT: one regime (Jul), fixed-point exit (the live capitulation uses an ATR 2R) — a LEAD,
not a verdict; the tick fills ARE honest though (unlike the bar-close gate_backtest).

  PYTHONPATH=src python scripts/footprint_backtest.py
"""

from __future__ import annotations

import argparse
import sqlite3

from gazbot7.deciders import gate_capitulation
from gazbot7.footprint import exhaustion_signal, footprint_summary

STOP_PT, TARGET_PT, HOLD_S = 8.0, 12.0, 120
VPP, FEE = 2.0, 1.5
TICKS = "/home/alphabot/alphabot2/data/ticks.db"
DEPTH = "/home/alphabot/gazbot7/data/depth.db"


def adapter():
    """A conn exposing V5 trade_tick/depth_snap as the `ticks`/`book` tables the footprint
    code reads (ticks: ts_ms,price,size,aggressor · book: side,level,price,size)."""
    c = sqlite3.connect(":memory:", uri=True)
    c.row_factory = sqlite3.Row
    c.execute(f"ATTACH 'file:{TICKS}?mode=ro' AS tk")
    c.execute(f"ATTACH 'file:{DEPTH}?mode=ro' AS dp")
    c.execute("CREATE TEMP VIEW ticks AS SELECT symbol, ts_ms, price, size, aggressor FROM tk.trade_tick")
    c.execute("CREATE TEMP VIEW book AS "
              "SELECT symbol, ts_ms, 'bid' side, 1 level, bid1p price, bid1s size FROM dp.depth_snap "
              "UNION ALL SELECT symbol, ts_ms, 'ask' side, 1 level, ask1p price, ask1s size FROM dp.depth_snap")
    return c


def _exit(c, side, entry_px, entry_ms):
    """Tick-path exit: first of stop / target / time, over the real ticks after entry."""
    stop = entry_px + STOP_PT if side == "SHORT" else entry_px - STOP_PT
    tgt = entry_px - TARGET_PT if side == "SHORT" else entry_px + TARGET_PT
    for ts, px in c.execute(
        "SELECT ts_ms, price FROM ticks WHERE symbol='MNQ' AND ts_ms>? AND ts_ms<=? ORDER BY ts_ms",
            (entry_ms, entry_ms + HOLD_S * 1000)):
        hit_stop = (px >= stop) if side == "SHORT" else (px <= stop)
        hit_tgt = (px <= tgt) if side == "SHORT" else (px >= tgt)
        if hit_stop:
            return stop, ts
        if hit_tgt:
            return tgt, ts
    # timed out → last price in the window
    r = c.execute("SELECT price FROM ticks WHERE symbol='MNQ' AND ts_ms>? AND ts_ms<=? ORDER BY ts_ms DESC LIMIT 1",
                  (entry_ms, entry_ms + HOLD_S * 1000)).fetchone()
    return (r["price"] if r else entry_px), entry_ms + HOLD_S * 1000


def backtest(cadence_ms=5000):
    c = adapter()
    # active cadence buckets = distinct cadence-slots that actually have MNQ ticks (skip dead time)
    buckets = [r[0] for r in c.execute(
        f"SELECT DISTINCT (ts_ms/{cadence_ms})*{cadence_ms} b FROM tk.trade_tick WHERE symbol='MNQ' ORDER BY 1")]
    res = {"capitulation_long": {"pnl": 0.0, "n": 0, "w": 0, "next_ms": 0},
           "exhaustion_short": {"pnl": 0.0, "n": 0, "w": 0, "next_ms": 0}}
    for now_ms in buckets:
        fp = footprint_summary(c, "MNQ", now_ms)
        # capitulation_long — fade a sell-flush (LONG only)
        d = res["capitulation_long"]
        if now_ms >= d["next_ms"]:
            e = gate_capitulation(None, cap_sell=fp["cap_sell"], cap_buy=fp["cap_buy"], cap_base=fp["cap_base"],
                                  cap_dpx=fp["cap_dpx"], cap_flip=fp["cap_flip"], climax_min=3.0, dom_min=0.7)
            if e is not None and e.side == "LONG" and fp["bid1_price"]:
                entry = (fp["bid1_price"] + fp["ask1_price"]) / 2.0
                xpx, xms = _exit(c, "LONG", entry, now_ms)
                g = (xpx - entry) * VPP - FEE
                d["pnl"] += g; d["n"] += 1; d["w"] += g > 0; d["next_ms"] = xms
        # exhaustion_short — fade heavy buying into an ask wall (SHORT only)
        d = res["exhaustion_short"]
        if now_ms >= d["next_ms"]:
            sig = exhaustion_signal(fp["net_signed"], fp["price_move_pt"], fp["bid1_size"], fp["ask1_size"],
                                    fp["bid1_price"], fp["ask1_price"])
            if sig is not None and sig[0] == "SHORT":
                entry = sig[1]
                xpx, xms = _exit(c, "SHORT", entry, now_ms)
                g = (entry - xpx) * VPP - FEE
                d["pnl"] += g; d["n"] += 1; d["w"] += g > 0; d["next_ms"] = xms
    c.close()
    return res, len(buckets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cadence", type=int, default=5000, help="decision cadence ms")
    a = ap.parse_args()
    res, nb = backtest(a.cadence)
    print(f"footprint gates on the V5 tick+L2 tape (~12 days, {nb:,} active {a.cadence//1000}s cadence points)\n")
    print(f"{'GATE':18} {'N':>4} {'win%':>5} {'NET':>9}")
    for tag, d in res.items():
        n = d["n"]
        print(f"{tag:18} {n:>4} {round(100*d['w']/n) if n else 0:>4}% ${round(d['pnl']):>+8.0f}")
    print("\n⚠ tick fills (honest) but a FIXED 8/12pt exit (live capitulation uses ATR 2R) · one regime · a LEAD.")


if __name__ == "__main__":
    main()
