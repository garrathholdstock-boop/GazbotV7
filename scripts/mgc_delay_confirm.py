#!/usr/bin/env python3
"""MGC ARM-THEN-CONFIRM — don't predict the side, WAIT for it. (Operator's proposal, 2026-08-05.)

  "why dont we do a delay like we do with abs_veto? when the move is coming trigger goes off. we then
   take 20-30 seconds to assess which way, remaining flexible. then we go bang."

★ THIS IS A DIFFERENT QUESTION FROM THE CENSUS. `mgc_run_census.py` asked whether the side can be
PREDICTED at the arm bar and answered no: slope 54.9%, breaks 55-56.5%, all ~2pp over "always SHORT"
at 53.7%. This asks whether the side can be REACTED TO — arm on the magnitude features that DO work
(ATR d=+0.80, ER30 d=+0.43), then let the tape commit before choosing. Same precedent as abs_veto's
55-second veto, the desk's most reliable gate.

THE TWO WAYS IT CAN FAIL, and both are measured here rather than assumed:

  1. THE DELAY EATS THE MOVE. You enter D seconds later and worse. The run is 40 min from the ARM, so
     waiting spends part of it — and on a fast move, the best part. Every P&L figure below enters at
     the POST-DELAY price and measures the extent that is still LEFT, never the extent from the arm.
  2. THE FIRST 30 SECONDS IS A HEAD-FAKE. Reacting to noise is worse than predicting, because you pay
     the spread to follow a wick. That is what the commitment threshold tests.

★ "REMAINING FLEXIBLE" = THE COMMIT THRESHOLD. If price has not moved at least C x ATR during the
delay window, the tape has not chosen and the trade is SKIPPED. C=0 is the no-flexibility control
(always take something), which is the version most likely to chase noise.

★ THE BENCHMARK IS THE BEST CONSTANT, NOT 50%. Over this tape "always SHORT" is right 53.7% of the
time from pure drift. Scoring against a coinflip is what made a 1.2pp feature look like 4.9pp.

  PYTHONPATH=src .venv/bin/python scripts/mgc_delay_confirm.py
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import Bar, _atr  # noqa: E402
from gazbot7.lake import connect  # noqa: E402
from gazbot7.sizing import efficiency_ratio  # noqa: E402

VPP = 10.0
HORIZON = 40 * 60      # the census run window, measured from the ARM — the delay spends part of it


def load(con):
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
               arg_max(close, bar_ts) c FROM bars WHERE timeframe='5s'
        GROUP BY 1 ORDER BY 1""").fetchall()
    bars = [Bar(ts=int(m), open=float(c), high=float(h), low=float(lo), close=float(c), volume=0.0)
            for m, h, lo, c in rows]
    tk = con.execute("SELECT ts_ms, price FROM ticks ORDER BY ts_ms").fetchall()
    ts = [int(t) // 1000 for t, _ in tk]
    px = [float(p) for _, p in tk]
    return bars, ts, px


def arms(bars, atr_floor, er_floor):
    """Bars where the MAGNITUDE features say a move is coming — the only thing the census validated."""
    out = []
    for i in range(60, len(bars) - 45):
        w = bars[max(0, i - 60):i + 1]
        atr = _atr(w)
        if atr <= 0 or atr < atr_floor:
            continue
        if efficiency_ratio(w, 30) < er_floor:
            continue
        out.append((bars[i].ts, atr))
    return out


def at(ts, px, t):
    """Last traded price at or before t, and its index."""
    i = bisect.bisect_right(ts, t) - 1
    return (px[i], i) if i >= 0 else (None, -1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee", type=float, default=1.50)
    ap.add_argument("--atr", type=float, default=2.6)
    ap.add_argument("--er", type=float, default=0.22)
    z = ap.parse_args()

    con = connect(symbol="MGC")
    bars, ts, px = load(con)
    A = arms(bars, z.atr, z.er)
    print(f"MGC {len(bars):,} bars, {len(ts):,} ticks   "
          f"arm: ATR>={z.atr} & ER30>={z.er}  ->  {len(A)} arms\n")

    # ─────────────────────────────────────────────────────────────────────────────────────────
    # PART 1 — after waiting D seconds, does the direction it CHOSE keep going?
    # Measured from the post-delay entry over the REMAINING horizon, so the delay's cost is inside
    # the number rather than beside it.
    # ─────────────────────────────────────────────────────────────────────────────────────────
    print("PART 1 — DOES THE CONFIRMED SIDE CONTINUE?")
    print(f"{'delay':>6}{'commit':>8}{'taken':>7}{'skip%':>7}{'correct':>9}"
          f"{'best const':>12}{'edge':>7}")
    grid = {}
    for D in (10, 20, 30, 45, 60, 90):
        for C in (0.0, 0.15, 0.25, 0.40):
            ok = n = longs = 0
            for t0, atr in A:
                p0, _ = at(ts, px, t0)
                pd, i_d = at(ts, px, t0 + D)
                if p0 is None or pd is None or i_d < 0:
                    continue
                mv = pd - p0
                if abs(mv) < C * atr:          # tape has not committed -> stay flat
                    continue
                if mv == 0:
                    continue
                side = "LONG" if mv > 0 else "SHORT"
                # remaining extent, from the ENTRY price, over what is LEFT of the 40-min window
                j = bisect.bisect_right(ts, t0 + HORIZON)
                seg = px[i_d:j]
                if len(seg) < 5:
                    continue
                up, dn = max(seg) - pd, pd - min(seg)
                true = "LONG" if up >= dn else "SHORT"
                n += 1
                ok += (side == true)
                longs += (true == "LONG")
            if n < 20:
                continue
            base = max(longs / n, 1 - longs / n) * 100
            hit = 100 * ok / n
            grid[(D, C)] = (n, hit, base)
            print(f"{D:>5}s{C:>8.2f}{n:>7}{100*(1-n/len(A)):>6.0f}%{hit:>8.1f}%"
                  f"{base:>11.1f}%{hit-base:>+7.1f}")

    good = [(v[1] - v[2], k, v) for k, v in grid.items()]
    good.sort(reverse=True)
    if good:
        e, k, v = good[0]
        print(f"\nbest: delay {k[0]}s commit {k[1]} -> {v[1]:.1f}% vs {v[2]:.1f}% constant "
              f"({e:+.1f}pp, n={v[0]})")
    print("★ A few points over the best CONSTANT is the drift, not a signal. The bar to clear is the")
    print("  constant column, and it must clear it by enough to pay the spread and the lost move.\n")

    # ─────────────────────────────────────────────────────────────────────────────────────────
    # PART 2 — what the delay COSTS. If confirmation works but the entry has already given the move
    # away, the gate still cannot pay. This is the half a hit-rate table cannot show.
    # ─────────────────────────────────────────────────────────────────────────────────────────
    print("PART 2 — WHAT THE WAIT COSTS (favourable extent still available at entry)")
    print(f"{'delay':>6}{'median move left (ATR)':>26}{'vs no-delay':>13}")
    ref = None
    for D in (0, 10, 20, 30, 45, 60, 90):
        left = []
        for t0, atr in A:
            pd, i_d = at(ts, px, t0 + D)
            if pd is None:
                continue
            j = bisect.bisect_right(ts, t0 + HORIZON)
            seg = px[i_d:j]
            if len(seg) < 5:
                continue
            left.append(max(max(seg) - pd, pd - min(seg)) / atr)
        if not left:
            continue
        left.sort()
        m = left[len(left) // 2]
        if ref is None:
            ref = m
        print(f"{D:>5}s{m:>26.2f}{100*(m/ref-1):>+12.0f}%")

    # ─────────────────────────────────────────────────────────────────────────────────────────
    # PART 3 — P&L, 2-lot, tick-sequenced, at the post-delay entry. The actual question.
    # ─────────────────────────────────────────────────────────────────────────────────────────
    print("\nPART 3 — 2-LOT P&L AT THE CONFIRMED ENTRY  (A=1.0R scalp, B=wide chandelier 3.5xATR)")
    print(f"{'config':<30}{'n':>5}{'total':>10}{'lotA':>9}{'lotB':>9}{'win':>7}"
          f"{'green':>9}{'strip-1':>9}")

    def pnl(D, C, k_stop=1.0, a_r=1.0, k_ch=3.5, side_mode="confirm"):
        trades, busy = [], 0
        for t0, atr in A:
            if t0 < busy:
                continue
            p0, _ = at(ts, px, t0)
            pd, i_d = at(ts, px, t0 + D)
            if p0 is None or pd is None:
                continue
            mv = pd - p0
            if side_mode == "confirm":
                if abs(mv) < C * atr or mv == 0:
                    continue
                side = "LONG" if mv > 0 else "SHORT"
            elif side_mode == "fade":
                if abs(mv) < C * atr or mv == 0:
                    continue
                side = "SHORT" if mv > 0 else "LONG"
            else:
                side = "SHORT"
            sgn = 1 if side == "LONG" else -1
            entry = pd
            r = k_stop * atr
            stop = entry - sgn * r
            tgt = entry + sgn * a_r * r
            best = entry
            ea = eb = None
            j = bisect.bisect_right(ts, t0 + HORIZON)
            for p in px[i_d:j]:
                if sgn * (p - entry) > sgn * (best - entry):
                    best = p
                trail = best - sgn * k_ch * atr
                if ea is None:                       # stop checked BEFORE target, always
                    if sgn * (p - stop) <= 0:
                        ea = stop
                    elif sgn * (p - tgt) >= 0:
                        ea = tgt
                if eb is None:
                    if sgn * (p - stop) <= 0:
                        eb = stop
                    elif sgn * (best - entry) > k_ch * atr and sgn * (p - trail) <= 0:
                        eb = trail
                if ea is not None and eb is not None:
                    break
            last = px[j - 1] if j > i_d else entry
            ea = last if ea is None else ea
            eb = last if eb is None else eb
            pa = sgn * (ea - entry) * VPP - z.fee
            pb = sgn * (eb - entry) * VPP - z.fee
            trades.append((t0, pa, pb))
            busy = t0 + HORIZON
        return trades

    def show(trades, label):
        if len(trades) < 5:
            print(f"{label:<30}{len(trades):>5}   too few")
            return
        tot = sum(a + b for _, a, b in trades)
        byday = defaultdict(float)
        for t0, a, b in trades:
            byday[dt.datetime.fromtimestamp(t0, dt.UTC).date().isoformat()] += a + b
        green = sum(1 for v in byday.values() if v > 0)
        wins = sum(1 for _, a, b in trades if a + b > 0)
        strip = tot - max(a + b for _, a, b in trades)
        print(f"{label:<30}{len(trades):>5}{tot:>10.0f}{sum(a for _,a,_ in trades):>9.0f}"
              f"{sum(b for _,_,b in trades):>9.0f}{100*wins/len(trades):>6.0f}%"
              f"{green:>4}/{len(byday):<4}{strip:>9.0f}")

    for D in (20, 30, 45, 60):
        for C in (0.0, 0.25):
            show(pnl(D, C), f"confirm {D}s commit {C}")
    print()
    show(pnl(30, 0.25, side_mode="fade"), "FADE the 30s move (control)")
    show(pnl(30, 0.25, side_mode="short"), "ALWAYS SHORT (control)")
    show(pnl(0, 0.0), "NO DELAY, no confirm (control)")
    print("\n★ The controls are the point. If FADE or ALWAYS-SHORT matches confirm, the delay is not")
    print("  reading direction — it is just trading less, and trading less is free to arrange.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
