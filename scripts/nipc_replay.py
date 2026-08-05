#!/usr/bin/env python3
"""NIPC ACCEPTANCE REPLAY — does the LIVE implementation reproduce the greenfield lab?

The whole point of writing NIPC as desk code rather than trusting the report is that a
live implementation can silently diverge from the lab construct. So this harness drives
the *actual shipped* ``gazbot7.deciders.NipcTracker`` — the same object slot_strategy
feeds on the live desk — over the same 12 days of tape the lab used, and prints its
numbers against the lab's published ones.

Tape (data/capture.db):
  * 07-24, 07-27..07-31 — 250ms TICKS available → tick-honest fills and exits.
  * 07-16, 17, 20..23   — 5s bars only → bar-replay (the lab's own IS half; the report
                          states those 6 days were bar-replay too).
Every reprice here is a CEILING: live losses run 1.1–3.1× modelled.

Costs: $5/round-trip, one tick (0.25 pt = $0.50) of ADVERSE slippage on entry and on
exit, stops win all ties inside a bar. Deliberately unkind, per the report.

Usage:  PYTHONPATH=src ./.venv/bin/python scripts/nipc_replay.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import (  # noqa: E402
    NIPC_BAR_S,
    NIPC_ER15_BARS,
    NIPC_FLAT_BY_S,
    NIPC_HOLD_CAP_S,
    Bar,
    NipcTracker,
    _atr,
    nipc_dead_chop,
)
from gazbot7.cadence import DECISION_MS  # noqa: E402
from gazbot7.sizing import efficiency_ratio  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
SYMBOL = "MNQ"
TICK = 0.25
VPP = 2.0
FEE_RT = float(os.environ.get("NIPC_FEE_RT", "1.50"))   # ★2026-08-01 CORRECTED 5.0 → 1.50 (operator).
# VENUE TRUTH, not an assumption: all 487 closed trades in data/gazbot7.db carry fees_usd = $1.50 exactly,
# per round trip. The 5.0 was inherited from the greenfield lab's NIPC cell and is 3.3x too high — and it
# matters far more here than almost anywhere else on the desk, because a FIXED per-trade cost is a
# regressive tax on a thin-edge high-frequency gate: at ~$5.7 gross/trade, $5 eats 87% of the edge and
# $1.50 eats 26%. Same error inflated the lab's own number, so it moves BOTH sides of the comparison.
# (Note the desk's other harnesses — grave_newsfade/grave_vacuum — already use 1.5; this one was the outlier.)
DAYS = ["2026-07-16", "2026-07-17", "2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23",
        "2026-07-24", "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]
TICK_DAYS: set = {"2026-07-24", "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"}
WARM_FROM_S = 11 * 3600      # start feeding bars at 11:00 UTC so ATR14/ER15 and the 24-bar
                             # impulse deque are warm well before the 13:00 window opens.
STOP_FEED_S = 15 * 3600 + 3600   # stop at 16:00 UTC (well past the 15:30 flat)

# ── regime buckets ────────────────────────────────────────────────────────────────────
# ⚠ RECONSTRUCTION. The report states only "regime thresholds are taken from this window's
# own quartiles so every bucket is populated" and does not publish the cut points. Only
# DEAD-CHOP is specified exactly (rule 7: ATR1m<18 AND ER15<0.35) — and dead-chop is the
# only bucket the POLICY depends on, so the headline (blanket minus dead-chop) is testable
# even though the other four labels are not.
ATR_VIOLENT = 25.0
ER_TREND = 0.55


def bucket(atr1m: float, er15: float) -> str:
    if nipc_dead_chop(atr1m, er15):
        return "dead-chop"
    if er15 >= ER_TREND:
        return "clean-trend"
    if er15 >= 0.35:
        return "in-between-building"
    if atr1m >= ATR_VIOLENT:
        return "violent-whipsaw"
    return "normal-chop"


# ── tape ──────────────────────────────────────────────────────────────────────────────
def load_day(con, day: str):
    lo = con.execute(f"SELECT epoch(TIMESTAMP '{day} 00:00:00')").fetchone()[0]
    b0, b1 = int(lo) + WARM_FROM_S, int(lo) + STOP_FEED_S
    bars = con.execute(
        "SELECT bar_ts, open, high, low, close, volume FROM cap.bars "
        "WHERE symbol=? AND timeframe='5s' AND bar_ts>=? AND bar_ts<? ORDER BY bar_ts",
        [SYMBOL, b0, b1]).fetchall()
    ticks = []
    if day in TICK_DAYS:
        ticks = con.execute(
            "SELECT ts_ms, price FROM cap.ticks WHERE symbol=? AND ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
            [SYMBOL, b0 * 1000, b1 * 1000]).fetchall()
    return [Bar(int(r[0]), r[1], r[2], r[3], r[4], r[5] or 0.0) for r in bars], ticks


def minute_context(bars5):
    """(atr1m, er15) per 5s bar, computed from 1-minute bars COMPLETED BEFORE that bar's
    minute — the same basis the live desk uses (MinuteBars only exposes closed minutes)."""
    mins, cur = [], None
    ctx, per_min = [], {}
    for b in bars5:
        m = (b.ts // 60) * 60
        if cur is None or m > cur["m"]:
            if cur is not None:
                mins.append(Bar(cur["m"], cur["o"], cur["h"], cur["l"], cur["c"], cur["v"]))
            per_min[m] = (_atr(mins), efficiency_ratio(mins, NIPC_ER15_BARS)) if len(mins) >= 2 else (0.0, 0.0)
            cur = {"m": m, "o": b.open, "h": b.high, "l": b.low, "c": b.close, "v": b.volume}
        else:
            cur["h"] = max(cur["h"], b.high)
            cur["l"] = min(cur["l"], b.low)
            cur["c"] = b.close
            cur["v"] += b.volume
        ctx.append(per_min[m])
    return ctx


def bar_events(b: Bar, side: str | None):
    """Synthetic intrabar print path for a bar-replay day. ADVERSE extreme first for the
    side we hold (so a bar that touches both stop and target books the STOP — the report's
    'stops win all ties' rule). Flat/armed → nearer extreme first (neutral)."""
    t0 = b.ts * 1000
    if side == "LONG":
        seq = [b.open, b.low, b.high, b.close]
    elif side == "SHORT":
        seq = [b.open, b.high, b.low, b.close]
    elif abs(b.high - b.open) <= abs(b.open - b.low):
        seq = [b.open, b.high, b.low, b.close]
    else:
        seq = [b.open, b.low, b.high, b.close]
    return [(t0 + i * 1250, p) for i, p in enumerate(seq)]


# ── one day ───────────────────────────────────────────────────────────────────────────
def replay_day(day: str, bars5, ticks, *, lot_a: float | None, lot_b: float,
               tracker_cls=NipcTracker, stop_mult: float = 1.0, close_only: bool = False,
               cadence_ms: int = 0, apply_regime: bool = False):
    # tracker_cls / stop_mult / close_only exist only for the divergence hunt
    # (scripts/nipc_variants.py); the shipped policy is the default of every one of them.
    """Sequential single-position replay driving the SHIPPED NipcTracker.

    ``lot_b`` is the wide lot's R multiple; ``lot_a`` (or None for the lab's 1-lot headline
    config) is the scalp lot. Both lots share ONE entry, ONE stop and the time exits — only
    the target differs — and the position is flat (rule 6) only once Lot B is done, exactly
    as the dual-slot desk behaves.
    """
    ctx = minute_context(bars5)
    # ★2026-08-03 apply_regime is now settable. Default False = the lab's blanket book (dead-chop is
    # BUCKETED afterwards). True = what PRODUCTION does — dead-chop is BLOCKED AT DETECTION, so no setup
    # forms at all. These are NOT equivalent: blocking changes the state machine's path, because an
    # impulse that never arms cannot be the one that a later pullback resolves against. Post-hoc
    # bucketing keeps the machine running through dead-chop and can therefore be in a different state.
    tk = tracker_cls(apply_regime=apply_regime)
    ti, ntk = 0, len(ticks)
    pos = None
    trades = []
    day0 = (bars5[0].ts // 86400) * 86400 if bars5 else 0
    flat_ms = (day0 + NIPC_FLAT_BY_S) * 1000

    def book(p, ts, reason, fill):
        sgn = 1.0 if p["side"] == "LONG" else -1.0
        legs = []
        if lot_a is not None:
            af = p["a_fill"] if p["a_fill"] is not None else fill
            legs.append(("A", (af - p["entry"]) * sgn * VPP - FEE_RT))
        legs.append(("B", (fill - p["entry"]) * sgn * VPP - FEE_RT))
        trades.append({**p["rec"], "exit_ts": ts, "exit": fill, "reason": reason,
                       "net": sum(v for _, v in legs),
                       "net_a": dict(legs).get("A", 0.0), "net_b": dict(legs)["B"],
                       "a_hit": p["a_fill"] is not None,
                       "hold_s": (ts - p["ts"]) / 1000.0})

    for i, b in enumerate(bars5):
        atr1m, er15 = ctx[i]
        t0, t1 = b.ts * 1000, (b.ts + NIPC_BAR_S) * 1000
        if day in TICK_DAYS:                       # ── real 250ms prints ──
            evs = []
            while ti < ntk and ticks[ti][0] < t1:
                if ticks[ti][0] >= t0:
                    evs.append((int(ticks[ti][0]), float(ticks[ti][1])))
                ti += 1
        else:                                      # ── bar-replay path ──
            evs = bar_events(b, pos["side"] if pos else None)
        if close_only and pos is not None:         # diagnostic: exits on 5s CLOSES only
            evs = [(t1 - 1, b.close)]
        # ★2026-08-03 PRODUCTION-CADENCE MODE. The live desk does NOT see raw ticks: md.py publishes
        # T_TAPE once per second (tape_interval_s=1.0) and slot_strategy._nipc_step runs off that, so
        # the tracker gets ~60 trigger checks a minute against this replay's ~3,532. Rule 3 says "fill
        # at the first tick trading through it" — production cannot do that, it sees one SNAPSHOT per
        # second and never the extremes traversed between. cadence_ms downsamples to the last print in
        # each bucket, which is exactly what a 1s poll of a live tape observes.
        if cadence_ms and evs:
            keep, seen = [], set()
            for ts, px in evs:                     # last print per bucket = what a 1s poll would read
                seen.add(ts // cadence_ms)
            buckets = {}
            for ts, px in evs:
                buckets[ts // cadence_ms] = (ts, px)
            evs = [buckets[k] for k in sorted(buckets)]
        for ts, px in evs:
            if pos is not None:
                lng = pos["side"] == "LONG"
                # Lot A scalp banks first if its target is touched on the way (stop is
                # checked FIRST below, so a bar that does both books the stop for both lots).
                reason = fill = None
                if lng and px <= pos["stop"]:
                    reason, fill = "STOP", pos["stop"] - TICK
                elif (not lng) and px >= pos["stop"]:
                    reason, fill = "STOP", pos["stop"] + TICK
                elif lng and px >= pos["target"]:
                    reason, fill = "TARGET", pos["target"] - TICK
                elif (not lng) and px <= pos["target"]:
                    reason, fill = "TARGET", pos["target"] + TICK
                elif ts >= flat_ms:
                    reason, fill = "SESSION_FLAT", (px - TICK if lng else px + TICK)
                elif ts - pos["ts"] >= NIPC_HOLD_CAP_S * 1000:
                    reason, fill = "TIME_CAP", (px - TICK if lng else px + TICK)
                if reason is None and lot_a is not None and pos["a_fill"] is None:
                    if lng and px >= pos["target_a"]:
                        pos["a_fill"] = pos["target_a"] - TICK
                    elif (not lng) and px <= pos["target_a"]:
                        pos["a_fill"] = pos["target_a"] + TICK
                if reason is not None:            # (Lot A keeps its bank if it already scaled out)
                    book(pos, ts, reason, fill)
                    pos = None
                    tk.note_exit(ts)
            elif tk.setup is not None and tk.setup.armed_ms:
                s = tk.trigger(ts, px)
                if s is not None:
                    entry = s.entry_level + TICK if s.side == "LONG" else s.entry_level - TICK
                    R = s.r_pt
                    sgn = 1.0 if s.side == "LONG" else -1.0
                    pos = {"side": s.side, "entry": entry, "R": R, "ts": ts,
                           "stop": entry - sgn * R * stop_mult,
                           "target": entry + sgn * lot_b * R,
                           "target_a": entry + sgn * (lot_a or lot_b) * R,
                           "a_fill": None,
                           "rec": {"day": day, "side": s.side, "entry_ts": ts, "entry": entry,
                                   "R": R, "atr1m": s.atr1m, "er15": s.er15,
                                   "regime": bucket(s.atr1m, s.er15), "retrace": s.retrace,
                                   "span": s.span}}
        tk.on_bar(b, atr1m=atr1m, er15=er15, busy=(pos is not None))
    return trades


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--target-r", type=float, default=2.5, help="Lot B fixed-R target")
    ap.add_argument("--lot-a", type=float, default=None, help="add a Lot A scalp at this R")
    ap.add_argument("--apply-regime", action="store_true",
                    help="block dead-chop AT DETECTION as production does, instead of bucketing it "
                         "afterwards as the lab did. Changes the state machine's path, not just labels.")
    ap.add_argument("--cadence-ms", type=int, default=DECISION_MS,
                    help=f"downsample the DECISION stream to one print per N ms. Defaults to the "
                         f"shared gazbot7.cadence.DECISION_MS ({DECISION_MS}) so the replay sees what "
                         f"the live desk sees. Pass 0 for raw ticks — that is the LAB's assumption and "
                         f"it flatters entries the desk could never have filled.")
    ap.add_argument("--days", default=None,
                    help="comma-separated YYYY-MM-DD to replay instead of the built-in lab window. "
                         "Any day given here is treated as TICK-covered (250ms prints), which is right "
                         "for recent days — capture keeps ticks and the lab list predates them.")
    a = ap.parse_args()
    days = DAYS
    if a.days:                       # ★2026-08-03: replay an arbitrary day (e.g. a live session)
        days = [d.strip() for d in a.days.split(",") if d.strip()]
        TICK_DAYS.update(days)

    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS cap (TYPE SQLITE, READ_ONLY)")
    allt = []
    for d in days:
        bars5, ticks = load_day(con, d)
        if not bars5:
            print(f"  {d}: NO BARS — skipped", file=sys.stderr)
            continue
        tr = replay_day(d, bars5, ticks, lot_a=a.lot_a, lot_b=a.target_r,
                        cadence_ms=a.cadence_ms, apply_regime=a.apply_regime)
        allt += tr
        print(f"  {d}: {len(bars5):>5} bars {len(ticks):>8} ticks -> {len(tr):>3} trades "
              f"{sum(t['net'] for t in tr):>+9.0f}", file=sys.stderr)

    home = [t for t in allt if t["regime"] != "dead-chop"]

    def blk(name, rows):
        n = len(rows)
        if not n:
            return f"{name:<24} n=0"
        net = sum(r["net"] for r in rows)
        w = sum(1 for r in rows if r["net"] > 0)
        return (f"{name:<24} n={n:<4} net={net:>+8.0f}  $/tr={net/n:>+6.1f}  win={100*w/n:>4.1f}%")

    print("\n" + "=" * 78)
    print(f"NIPC REPLAY — 1 lot, fixed {a.target_r}R, ${FEE_RT:.2f}/RT + 1 tick adverse each side")
    print("=" * 78)
    print(blk("BLANKET (all regimes)", allt))
    print(blk("HOME (dead-chop OFF)", home))
    print("\n-- per regime (blanket book, bucketed) --")
    byreg = defaultdict(list)
    for t in allt:
        byreg[t["regime"]].append(t)
    for k in ("normal-chop", "violent-whipsaw", "in-between-building", "clean-trend", "dead-chop"):
        print(blk("  " + k, byreg.get(k, [])))
    print("\n-- per side (HOME) --")
    for s in ("LONG", "SHORT"):
        print(blk("  " + s, [t for t in home if t["side"] == s]))
    print("\n-- per day (HOME) --")
    byday = defaultdict(list)
    for t in home:
        byday[t["day"]].append(t)
    for d in days:
        print(blk("  " + d, byday.get(d, [])))
    if home:
        rs = sorted(t["R"] for t in home)
        print(f"\nmedian R = {rs[len(rs)//2]:.1f} pt   "
              f"mean hold = {sum(t['hold_s'] for t in home)/len(home)/60:.1f} min   "
              f"TARGET={sum(1 for t in home if t['reason']=='TARGET')} "
              f"STOP={sum(1 for t in home if t['reason']=='STOP')} "
              f"TIME={sum(1 for t in home if t['reason']=='TIME_CAP')} "
              f"FLAT={sum(1 for t in home if t['reason']=='SESSION_FLAT')}")
        print(f"days green = {sum(1 for d in byday if sum(t['net'] for t in byday[d])>0)} / {len(byday)}   "
              f"worst day = {min(sum(t['net'] for t in v) for v in byday.values()):+.0f}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(allt, f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
