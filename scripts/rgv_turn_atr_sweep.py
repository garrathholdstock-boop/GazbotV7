#!/usr/bin/env python3
"""rg_long_fast_v (#29): sweep turn_atr — how fast a turn to grab — with a TRAIN/TEST split.

★ THE QUESTION (operator, 2026-08-19): the arm is a working fader whose payoff is right and whose
HIT RATE is short. Live: CHANDELIER n=89 avg +$68.73 vs STOP n=181 avg -$40.59 — winners 1.7x losers
at a 31% hit rate, needing ~37% to break even, for an all-time -$1,230.50 over 270. `turn_atr=0.15`
is how big a turn-back it demands before grabbing, so it is the lever that most directly moves that
hit rate. Sweep it.

★★ WHY THIS RE-RUNS THE GATE INSTEAD OF REPLAYING RECORDED TRADES. `turn_atr` is a GATE parameter:
it changes WHICH signals fire, not merely when. Replaying the arm's own booked trades would hold the
turn_atr=0.15 population fixed and only re-price it — the exact limitation `absveto_delay_sweep.py`
documents about itself ("every short-delay number here is an UPPER BOUND ... a real 5s gate would
take a larger, worse population"). So each cell here re-runs the REAL `gate_reversal_grab` over the
tape and builds its OWN population, which is the only way a threshold sweep means anything.

★ THE EXIT IS THE ARM'S OWN. rg_long_fast_v is `chandelier=True`, so ShadowSim's chandelier branch
applies (shadow.py): exit_chandelier(start_k=3.5, min_k=0.5, tighten=0.75), else STOP only via
exit_scalp(target_r=99, stop_atr_mult=1.0). NO adverse-cut and NO absorption — those apply only to
the fixed-R variants, and adding them would model a different arm. Mirrored exactly, not re-derived.

★ NO LEFT-EDGE LOOK-AHEAD. A 1-minute bar labelled `m` covers [m, m+60) and is only COMPLETE at
m+60 — reading it at `m` replays the decision minute and is the banked
[[resample-labels-the-left-edge]] trap (+$9xx of phantom edge last time). Features are computed on
bars CLOSED at or before the decision instant, and the fill is the first TICK at/after it.

★ TICK-HONEST EXITS, and OCCUPANCY MODELLED. The position is managed tick-by-tick (peak updated on
every tick, chandelier and stop evaluated there), because the shadow's own bar-resolution exits leak
past their stops on 44% of trades. ONE position at a time, exactly as ShadowSim runs it — a looser
turn_atr both takes more trades AND misses more while busy, and that trade-off is the answer.

⚠ TICK HOLE. V7 tick capture began 2026-07-24 (V5 stopped 07-17), so 07-18..07-23 has bars but no
ticks and is EXCLUDED — reported, never silently dropped.

  PYTHONPATH=src .venv/bin/python scripts/rgv_turn_atr_sweep.py
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import os
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")

from gazbot7.deciders import (  # noqa: E402
    Bar,
    Position,
    compute_features,
    exit_chandelier,
    exit_scalp,
    gate_reversal_grab,
)

VPP, FEE = 2.0, 1.50
# ★ THE WINDOW IS ROLLING, NOT SESSION-ANCHORED. The shadow service feeds ShadowSim a
# `MinuteBars` deque of maxlen=RunConfig.bar_lookback=60 COMPLETED 1-minute bars, warmed to
# capacity. A first cut of this sweep passed the whole session-so-far instead, which stretches
# `ext_atr = (price-vwap)/atr` — the very quantity `ext_min` tests — and fired 311 trades where the
# real arm took 141, a 2.2x population. Same gate, different tape, different answer: exactly the
# lab-is-not-production trap. Validate any change here against the real arm before trusting it.
LOOKBACK = 60
# rg_long_fast_v's LIVE params (default_slate()), with turn_atr swept.
BASE = dict(side="LONG", ext_min=2.0, fast_slope=True, fast_turn=True, atr_min=13.0)
# its exit block, from the ShadowVariant
START_K, MIN_K, TIGHTEN, STOP_ATR_MULT = 3.5, 0.5, 0.75, 1.0
TURNS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.35, 0.50, 0.75]
# ★ net30_floor — the regime-DEPTH floor. `net30_pt` is the trailing 30-bar net move in POINTS, so a
# LONG fade sitting inside a DEEP established down-leg is a falling knife and is skipped. The value
# researched on 2026-07-25 and running on the LIVE rgv slot is -125.0 (slot_strategy.py:127, "≈ -5·ATR");
# direction_router.py:77 removed rgv_long from the day-level DOWN bench precisely because this
# per-entry floor dominates it. rg_long_fast_v has NEVER carried it — None is its live setting.
# ⚠ net30_pt needs >=31 bars to mean anything (deciders.py:420); LOOKBACK=60 satisfies that.
NET30 = [None, -200.0, -175.0, -150.0, -125.0, -100.0, -75.0, -50.0]
SWEEPS = {"turn_atr": (TURNS, 0.15), "net30_floor": (NET30, None)}   # (values, the arm's LIVE value)
WARMUP = LOOKBACK               # deque is warmed to capacity before the loop starts


def sessions(con, since, until):
    """1-minute bars per calendar day. Integer modulo — DuckDB '/' is FLOAT and (ts/60)*60 is a NO-OP."""
    rows = con.execute(f"""
        WITH b AS (SELECT (bar_ts - bar_ts % 60) AS m,
                          arg_min(open, bar_ts) o, max(high) h, min(low) l,
                          arg_max(close, bar_ts) c, sum(volume) v
                   FROM bars
                   WHERE symbol='MNQ' AND timeframe='5s'
                     AND bar_ts >= epoch(TIMESTAMP '{since} 00:00:00')
                     AND bar_ts <  epoch(TIMESTAMP '{until} 00:00:00')
                   GROUP BY 1)
        SELECT strftime(to_timestamp(m), '%Y-%m-%d') d, m, o, h, l, c, v FROM b ORDER BY m""").fetchall()
    out: dict[str, list] = {}
    for d, m, o, h, lo, c, v in rows:
        out.setdefault(d, []).append(Bar(int(m), float(o), float(h), float(lo), float(c), float(v or 0)))
    return out


def ticks_for_day(con, day):
    t0 = dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp()
    rows = con.execute(
        "SELECT ts_ms, price FROM ticks WHERE symbol='MNQ' AND ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
        [int(t0 * 1000), int((t0 + 86400) * 1000)]).fetchall()
    return [int(r[0]) for r in rows], [float(r[1]) for r in rows]


def run_day(bars, tk_ts, tk_px, param, value):
    """One variant over one session. ONE position at a time, exactly as ShadowSim runs it.

    ⚠ A `for i in range(...)` here would be WRONG: after a trade closes, execution must resume at the
    first bar that CLOSED AFTER the exit, and rebinding the loop variable of a `for` does nothing in
    Python — the sweep would silently open overlapping positions and every cell would be inflated by
    trades the arm could never have taken. An explicit index it is.
    """
    trades = []
    i = WARMUP
    while i < len(bars):
        # bar i-1 is COMPLETE at bars[i].ts — decide there, never at the bar's own left edge
        decide_ms = bars[i].ts * 1000
        try:
            f = compute_features(bars[i - LOOKBACK:i])       # rolling window of CLOSED bars
        except Exception:
            i += 1
            continue
        kw = dict(BASE)
        kw.setdefault("turn_atr", 0.15)          # live value, held fixed unless it IS the swept param
        kw[param] = value
        if gate_reversal_grab(f, **kw) is None:
            i += 1
            continue
        j = bisect.bisect_left(tk_ts, decide_ms)             # fill on the first tick at/after
        if j >= len(tk_ts):
            break
        entry, atr, peak = tk_px[j], f.atr, 0.0
        exit_k = None
        k = j + 1
        while k < len(tk_ts):                                # manage on TICKS
            px = tk_px[k]
            fav = px - entry                                 # LONG-only arm (BASE side='LONG')
            if fav > peak:
                peak = fav
            pos = Position("LONG", entry, atr, peak)
            reason = exit_chandelier(pos, px, start_k=START_K, min_k=MIN_K, tighten=TIGHTEN)
            if reason is None:
                reason = exit_scalp(pos, px, target_r=99.0, stop_atr_mult=STOP_ATR_MULT)
            if reason:
                trades.append(dict(entry_ts=tk_ts[j] // 1000, exit_ts=tk_ts[k] // 1000,
                                   atr=atr, reason=reason, pnl=fav * VPP - FEE))
                exit_k = k
                break
            k += 1
        if exit_k is None:
            break                                            # tape ran out — book nothing, stop the day
        exit_s = tk_ts[exit_k] // 1000
        i += 1
        while i < len(bars) and bars[i].ts <= exit_s:         # skip bars closed while we were busy
            i += 1
    return trades


def agg(ts):
    if not ts:
        return dict(n=0, pnl=0.0, avg=0.0, win=0.0, hold=0.0, chand=0, stop=0)
    n = len(ts)
    w = sum(1 for t in ts if t["pnl"] > 0)
    return dict(n=n, pnl=sum(t["pnl"] for t in ts), avg=sum(t["pnl"] for t in ts) / n,
                win=100.0 * w / n,
                hold=sum(t["exit_ts"] - t["entry_ts"] for t in ts) / n / 60.0,
                chand=sum(1 for t in ts if t["reason"] == "CHANDELIER"),
                stop=sum(1 for t in ts if t["reason"] != "CHANDELIER"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--param", default="turn_atr", choices=sorted(SWEEPS))
    ap.add_argument("--since", default="2026-07-24")     # V7 ticks start here
    ap.add_argument("--split", default="2026-08-07")
    ap.add_argument("--until", default="2026-08-20")
    a = ap.parse_args()
    values, live_val = SWEEPS[a.param]

    from gazbot7.lake import connect
    con = connect(symbol="MNQ")
    days = sessions(con, a.since, a.until)
    print(f"sweeping {a.param} · sessions: {len(days)} ({min(days)} .. {max(days)}), "
          f"split at {a.split}\n")

    key = lambda v: "None" if v is None else f"{v}"      # noqa: E731 — None must survive as a cell
    results = {key(v): {"train": [], "test": []} for v in values}
    skipped = []
    for d in sorted(days):
        tk_ts, tk_px = ticks_for_day(con, d)
        if len(tk_ts) < 1000:
            skipped.append(d)
            continue
        half = "train" if d < a.split else "test"
        for v in values:
            results[key(v)][half].extend(run_day(days[d], tk_ts, tk_px, a.param, v))

    if skipped:
        print(f"⚠ {len(skipped)} session(s) EXCLUDED for no ticks: {', '.join(skipped)}\n")

    print(f"{a.param:>12} │ {'TRAIN n':>8}{'pnl':>10}{'avg':>8}{'win%':>7} │ "
          f"{'TEST n':>7}{'pnl':>10}{'avg':>8}{'win%':>7} │ {'chand/stop (test)':>18}")
    print("─" * 107)
    live_row = None
    for v in values:
        tr, te = agg(results[key(v)]["train"]), agg(results[key(v)]["test"])
        mark = " ←LIVE" if v == live_val else ""
        line = (f"{key(v):>12} │ {tr['n']:>8}{tr['pnl']:>10.0f}{tr['avg']:>8.2f}{tr['win']:>7.1f} │ "
                f"{te['n']:>7}{te['pnl']:>10.0f}{te['avg']:>8.2f}{te['win']:>7.1f} │ "
                f"{te['chand']:>8}/{te['stop']:<9}{mark}")
        print(line)
        if v == live_val:
            live_row = (tr, te)

    print()
    best_tr = max(values, key=lambda v: (agg(results[key(v)]["train"])["avg"]
                                         if results[key(v)]["train"] else -9e9))
    bt, be = agg(results[key(best_tr)]["train"]), agg(results[key(best_tr)]["test"])
    print(f"TRAIN-best {a.param} = {key(best_tr)}: train ${bt['pnl']:.0f} (avg ${bt['avg']:.2f}, n={bt['n']}) "
          f"→ TEST ${be['pnl']:.0f} (avg ${be['avg']:.2f}, n={be['n']}, win {be['win']:.1f}%)")
    if live_row:
        lt, le = live_row
        print(f"LIVE       {a.param} = {key(live_val)}: train ${lt['pnl']:.0f} (avg ${lt['avg']:.2f}, n={lt['n']}) "
              f"→ TEST ${le['pnl']:.0f} (avg ${le['avg']:.2f}, n={le['n']}, win {le['win']:.1f}%)")
        print(f"\nOUT-OF-SAMPLE DELTA vs live: ${be['pnl'] - le['pnl']:+.0f} "
              f"(avg ${be['avg'] - le['avg']:+.2f}/trade)")
    print("\n⚠ The TEST column is the only one that counts. A cell that wins on train and not on test")
    print("  is a curve fit, and this arm's last two weeks were a hot streak — see the 08-19 study.")
    print("⚠ A FILTER THAT REMOVES TRADES IS SUPPOSED TO SHRINK n. Read the n columns beside the P&L:")
    print("  a cell that fires on almost nothing has not found an edge, it has abstained.")

    os.makedirs(f"{GB}/reports/rgv_turn_atr", exist_ok=True)
    with open(f"{GB}/reports/rgv_turn_atr/sweep_{a.param}.json", "w") as fh:
        json.dump({str(t): {h: agg(v) for h, v in d.items()} for t, d in results.items()}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
