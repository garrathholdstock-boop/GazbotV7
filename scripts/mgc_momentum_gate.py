#!/usr/bin/env python3
"""MGC GREENFIELD MOMENTUM GATE — build one from gold's own tape, and test it honestly.

Operator, 2026-08-05: "try and create a momentum gate using the 2 lot exits with B being wide
chandelier. see what you can do."

WHAT THE CENSUS SAID (scripts/mgc_run_census.py), because this harness only makes sense against it:

  * Gold produces 29 runs worth >= $300 over 12 days — about 2.4/day. Raw material EXISTS.
  * Two features precede them: ATR (effect d=+0.80) and ER30 (d=+0.43). Both are MAGNITUDE features.
  * NOTHING calls the SIDE. vwap_slope gets 54.9% — against 53.7% for "always SHORT", the constant
    call. A 1.2 point edge over a constant is the 12-day downward drift, not a signal.

So the honest prior is that this gate should not work: it can tell when a move is coming and cannot
tell which way. This harness is built to let that show rather than to hide it.

★ IT IS BUILT SEQUENTIALLY, ONE POSITION AT A TIME. Memory [[exit-lab-paired-method-overstates]]:
stacking overlapping positions swung a study by $5,076 and biased it toward tight Rs. A new entry is
refused while one is open, exactly as the desk behaves.

★ EXITS ARE SEQUENCED ON TICKS, NOT BARS. 1.66M MGC ticks cover 2026-07-05..07-17. A 5s bar that
touches both stop and target hides WHICH CAME FIRST, and memory [[backtest-on-5s-250ms-persist-all]]
measured that as an 87% flush-loss error. Lot A and Lot B are walked tick by tick.

★ VENUE TRUTH: $10.00/POINT — five times MNQ. Every other harness hardcodes 2.0.
★ FEE IS A STATED ASSUMPTION, NOT A MEASUREMENT. All 433 live MGC fills record 0.00 commission — a
  recording gap, not free trading. $1.50/RT/lot is carried over from MNQ's measured figure and is
  almost certainly LOW for gold. --fee re-runs it; the sensitivity is printed.

★ THE HONEST COLUMN IS DAYS-GREEN. Total P&L over 12 days is one number that one afternoon can make.

  PYTHONPATH=src .venv/bin/python scripts/mgc_momentum_gate.py
  PYTHONPATH=src .venv/bin/python scripts/mgc_momentum_gate.py --sweep
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import Bar, _atr, compute_features  # noqa: E402
from gazbot7.lake import connect  # noqa: E402
from gazbot7.sizing import efficiency_ratio  # noqa: E402

VPP = 10.0          # ★ MGC venue truth, pinned from 431 of 433 live fills
MAX_HOLD_MIN = 40   # the census horizon — a run that has not developed in 40 min is not a run


def load(con):
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
               arg_max(close, bar_ts) c, sum(volume) v
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    bars = [Bar(ts=int(m), open=float(c), high=float(h), low=float(lo), close=float(c),
                volume=float(v or 0)) for m, h, lo, c, v in rows]
    ticks = con.execute("SELECT ts_ms, price FROM ticks ORDER BY ts_ms").fetchall()
    ticks = [(int(t) // 1000, float(p)) for t, p in ticks]
    return bars, ticks


def walk(ticks, t0, side, entry, stop, tgt_a, k_chand, atr, hold_s):
    """Sequence BOTH lots tick by tick. Returns (exit_a, exit_b, reason_a, reason_b).

    Lot A: fixed-R scalp — first touch of target or stop.
    Lot B: WIDE CHANDELIER — trails k_chand * ATR from the best price seen, stop until it engages.
    ★ The stop is checked BEFORE the target on every tick. Where both are inside one tick's gap the
      loss is taken; assuming the good fill is how a backtest quietly invents money.
    """
    import bisect
    i = bisect.bisect_left(ticks, (t0, -1e18))
    sgn = 1 if side == "LONG" else -1
    best = entry
    exit_a = exit_b = None
    ra = rb = "hold"
    for ts, px in ticks[i:i + 200_000]:
        if ts - t0 > hold_s:
            break
        if sgn * (px - entry) > sgn * (best - entry):
            best = px
        trail = best - sgn * k_chand * atr
        if exit_a is None:
            if sgn * (px - stop) <= 0:
                exit_a, ra = stop, "stop"
            elif sgn * (px - tgt_a) >= 0:
                exit_a, ra = tgt_a, "target"
        if exit_b is None:
            if sgn * (px - stop) <= 0:
                exit_b, rb = stop, "stop"
            elif sgn * (best - entry) > k_chand * atr and sgn * (px - trail) <= 0:
                exit_b, rb = trail, "chandelier"
        if exit_a is not None and exit_b is not None:
            return exit_a, exit_b, ra, rb
    last = None
    for ts, px in ticks[i:i + 200_000]:
        if ts - t0 > hold_s:
            break
        last = px
    last = last if last is not None else entry
    if exit_a is None:
        exit_a, ra = last, "max_hold"
    if exit_b is None:
        exit_b, rb = last, "max_hold"
    return exit_a, exit_b, ra, rb


def run(bars, ticks, *, atr_floor, er_floor, k_stop, a_r, k_chand, fee, dirn="slope"):
    trades = []
    busy_until = 0
    for i in range(60, len(bars) - 2):
        b = bars[i]
        if b.ts < busy_until:
            continue                      # ★ one position at a time
        w = bars[max(0, i - 60):i + 1]
        atr = _atr(w)
        if atr <= 0 or atr < atr_floor:
            continue
        try:
            f = compute_features(w)
        except Exception:
            continue
        if efficiency_ratio(w, 30) < er_floor:
            continue
        v = f.vwap_slope_atr if dirn == "slope" else f.net_atr_5
        if dirn == "short":
            side = "SHORT"
        elif abs(v) < 1e-9:
            continue
        else:
            side = "LONG" if v > 0 else "SHORT"
        sgn = 1 if side == "LONG" else -1
        entry = b.close
        r = k_stop * atr
        stop = entry - sgn * r
        tgt_a = entry + sgn * a_r * r
        ea, eb, ra, rb = walk(ticks, b.ts, side, entry, stop, tgt_a, k_chand, atr,
                              MAX_HOLD_MIN * 60)
        pa = sgn * (ea - entry) * VPP - fee
        pb = sgn * (eb - entry) * VPP - fee
        trades.append({"ts": b.ts, "side": side, "atr": atr, "a": pa, "b": pb,
                       "pnl": pa + pb, "ra": ra, "rb": rb,
                       "day": dt.datetime.fromtimestamp(b.ts, dt.UTC).date().isoformat()})
        busy_until = b.ts + MAX_HOLD_MIN * 60
    return trades


def report(trades, label, fee):
    if not trades:
        print(f"{label:<34} no trades")
        return None
    n = len(trades)
    tot = sum(t["pnl"] for t in trades)
    a = sum(t["a"] for t in trades)
    b = sum(t["b"] for t in trades)
    byday = defaultdict(float)
    for t in trades:
        byday[t["day"]] += t["pnl"]
    green = sum(1 for v in byday.values() if v > 0)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    # ★ strip-best: one print made the whole MGC live record look positive (+$1,103 -> -$524)
    strip = tot - max(t["pnl"] for t in trades)
    print(f"{label:<34}{n:>5}{tot:>10.0f}{a:>9.0f}{b:>9.0f}"
          f"{100*wins/n:>7.0f}%{green:>4}/{len(byday):<4}{strip:>10.0f}")
    return {"n": n, "tot": tot, "a": a, "b": b, "green": green, "days": len(byday),
            "strip": strip, "trades": trades}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee", type=float, default=1.50)
    ap.add_argument("--sweep", action="store_true")
    z = ap.parse_args()

    con = connect(symbol="MGC")
    bars, ticks = load(con)
    d0 = dt.datetime.fromtimestamp(bars[0].ts, dt.UTC).date()
    d1 = dt.datetime.fromtimestamp(bars[-1].ts, dt.UTC).date()
    print(f"MGC {len(bars):,} min bars, {len(ticks):,} ticks, {d0}..{d1}")
    print(f"VPP ${VPP:.2f}/pt   fee ${z.fee:.2f}/RT/lot (ASSUMED — MGC fills record 0.00)\n")

    hdr = (f"{'config':<34}{'n':>5}{'total':>10}{'lotA':>9}{'lotB':>9}"
           f"{'win':>8}{'green':>9}{'strip-1':>10}")

    if z.sweep:
        print("SWEEP — entry floors x exits.  B is the WIDE chandelier throughout.")
        print(hdr)
        best = []
        for atr_floor in (2.2, 2.6, 3.0):
            for er_floor in (0.18, 0.22, 0.28):
                for k_stop in (1.0, 1.5):
                    for a_r in (1.0, 1.5):
                        for k_chand in (2.5, 3.5):
                            t = run(bars, ticks, atr_floor=atr_floor, er_floor=er_floor,
                                    k_stop=k_stop, a_r=a_r, k_chand=k_chand, fee=z.fee)
                            lab = f"atr{atr_floor} er{er_floor} k{k_stop} a{a_r} ch{k_chand}"
                            rr = report(t, lab, z.fee)
                            if rr:
                                best.append((rr["tot"], lab, rr))
        best.sort(reverse=True)
        print(f"\n★ {sum(1 for x in best if x[0] > 0)} of {len(best)} cells positive")
        if best:
            top = best[0][2]
            print(f"★ best cell {best[0][1]}: ${top['tot']:.0f} over {top['n']} trades, "
                  f"green {top['green']}/{top['days']} days, strip-best-1 ${top['strip']:.0f}")
            print("  A sweep's best cell is a SELECTION, not a result — 72 cells were tried.")
        return 0

    print("HEADLINE CONFIGS  (entry = ATR>=2.6 and ER30>=0.22, side by vwap_slope)")
    print(hdr)
    cfg = dict(atr_floor=2.6, er_floor=0.22, k_stop=1.0, fee=z.fee)
    for a_r, k_chand in ((1.0, 2.5), (1.5, 3.5), (1.0, 3.5)):
        report(run(bars, ticks, a_r=a_r, k_chand=k_chand, **cfg),
               f"A={a_r}R  B=chandelier {k_chand}xATR", z.fee)

    print("\nCONTROLS — a gate must beat these or it is not a gate")
    report(run(bars, ticks, a_r=1.0, k_chand=2.5, dirn="short", **cfg),
           "ALWAYS SHORT (same entries)", z.fee)
    report(run(bars, ticks, a_r=1.0, k_chand=2.5, dirn="net", **cfg),
           "side by net_atr_5", z.fee)
    print("\nNO ENTRY FILTER — does the ATR/ER screen add anything at all?")
    report(run(bars, ticks, atr_floor=0.0, er_floor=0.0, k_stop=1.0, a_r=1.0,
               k_chand=2.5, fee=z.fee), "no filter, side by slope", z.fee)

    print("\nFEE SENSITIVITY (headline config, A=1.0R B=2.5x)")
    for fee in (1.50, 3.00, 5.00):
        report(run(bars, ticks, a_r=1.0, k_chand=2.5, atr_floor=2.6, er_floor=0.22,
                   k_stop=1.0, fee=fee), f"fee ${fee:.2f}/RT/lot", fee)
    return 0


if __name__ == "__main__":
    sys.exit(main())
