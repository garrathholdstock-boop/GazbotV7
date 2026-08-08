#!/usr/bin/env python3
"""EXHAUSTION_LONG model (operator 2026-07-28: "have you ever modelled an exhaustion long?").

No — only exhaustion_SHORT has ever traded/tuned. The gate's signal is two-sided (footprint.py):
buy-heavy tape absorbed into an ASK wall → SHORT; sell-heavy tape absorbed into a BID wall → LONG.
Only the SHORT slot is on the roster. This tests whether the LONG side (fade a sell-exhaustion,
go long for the bounce) is even +EV — on the INDEPENDENT V5 archive (Jul 5–17, ~12 days, tick+L2),
under the gate's NATIVE snap-back exit (8pt stop / 12pt target / 120s), the honest tick fill path.
Runs BOTH sides on the same walk so exhaustion_short is the known-good anchor for the comparison.

Reuses gazbot7's OWN footprint_summary + exhaustion_signal (zero drift). Fees $1.50/RT, $2/pt.
⚠ one regime (July), native fixed exit only (no adaptive) — a first LEAD on viability, not a verdict.

  PYTHONPATH=src .venv/bin/python scripts/exhaustion_long_test.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.footprint import exhaustion_signal, footprint_summary  # noqa: E402

TICKS = "/home/alphabot/alphabot2/data/ticks.db"
DEPTH = "/home/alphabot/gazbot7/data/depth.db"
STOP_PT, TARGET_PT, HOLD_S = 8.0, 12.0, 120
VPP, FEE = 2.0, 1.5


def adapter():
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
    r = c.execute("SELECT price FROM ticks WHERE symbol='MNQ' AND ts_ms>? AND ts_ms<=? ORDER BY ts_ms DESC LIMIT 1",
                  (entry_ms, entry_ms + HOLD_S * 1000)).fetchone()
    return (r["price"] if r else entry_px), entry_ms + HOLD_S * 1000


def dstr(ms):
    return sqlite3.connect(":memory:").execute("SELECT date(?/1000,'unixepoch')", (ms,)).fetchone()[0]


def main(cadence_ms=5000):
    c = adapter()
    buckets = [r[0] for r in c.execute(
        f"SELECT DISTINCT (ts_ms/{cadence_ms})*{cadence_ms} b FROM tk.trade_tick WHERE symbol='MNQ' ORDER BY 1")]
    print(f"walking {len(buckets)} cadence buckets ({cadence_ms}ms) over the V5 archive…", flush=True)
    res = {"exhaustion_short": {"pnl": 0.0, "n": 0, "w": 0, "next_ms": 0, "wins": 0.0, "loss": 0.0},
           "exhaustion_long":  {"pnl": 0.0, "n": 0, "w": 0, "next_ms": 0, "wins": 0.0, "loss": 0.0}}
    per_day = defaultdict(lambda: defaultdict(float))

    for i, now_ms in enumerate(buckets):
        if i and i % 20000 == 0:
            print(f"  …{i}/{len(buckets)} buckets  "
                  f"short:{res['exhaustion_short']['n']} long:{res['exhaustion_long']['n']}", flush=True)
        fp = footprint_summary(c, "MNQ", now_ms)
        sig = exhaustion_signal(fp["net_signed"], fp["price_move_pt"], fp["bid1_size"], fp["ask1_size"],
                                fp["bid1_price"], fp["ask1_price"])
        if sig is None:
            continue
        side, entry = sig
        name = "exhaustion_short" if side == "SHORT" else "exhaustion_long"
        d = res[name]
        if now_ms < d["next_ms"]:
            continue
        xpx, xms = _exit(c, side, entry, now_ms)
        g = ((entry - xpx) if side == "SHORT" else (xpx - entry)) * VPP - FEE
        d["pnl"] += g; d["n"] += 1; d["w"] += g > 0; d["next_ms"] = xms
        d["wins" if g > 0 else "loss"] += g
        per_day[dstr(now_ms)][name] += g

    print(f"\n{'gate':18}{'n':>5}{'win%':>7}{'P&L$':>9}{'avg$':>7}{'avgW':>7}{'avgL':>7}")
    for name in ("exhaustion_short", "exhaustion_long"):
        d = res[name]
        if d["n"] == 0:
            print(f"{name:18}{0:>5}   — no fires")
            continue
        nw = d["w"]; nl = d["n"] - d["w"]
        print(f"{name:18}{d['n']:>5}{100*d['w']/d['n']:>6.0f}%{d['pnl']:>+9.0f}{d['pnl']/d['n']:>+7.1f}"
              f"{(d['wins']/nw if nw else 0):>+7.1f}{(d['loss']/nl if nl else 0):>+7.1f}")

    days = sorted(per_day)
    print(f"\nper-day P&L (native 8/12 snap-back):")
    print(f"{'day':>12}{'exh_short':>11}{'exh_long':>10}")
    for dd in days:
        print(f"{dd:>12}{per_day[dd]['exhaustion_short']:>+11.0f}{per_day[dd]['exhaustion_long']:>+10.0f}")
    ls = [per_day[dd]['exhaustion_long'] for dd in days]
    print(f"\nexhaustion_long: {sum(1 for x in ls if x>0)}/{len(ls)} green days, "
          f"total {sum(ls):+.0f}, worst day {min(ls):+.0f}, best {max(ls):+.0f}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)
