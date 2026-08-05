#!/usr/bin/env python3
"""MGC RUN CENSUS — what does a gold run actually look like, and what precedes it?

Operator, 2026-08-05: "do a census on the top runs over whatever period we have good data for and try
and create a momentum gate".

WHY A CENSUS FIRST. Yesterday's screen ported the EXISTING MNQ gates onto gold and 24 of 27 cells lost
money. That tested whether MNQ's entry logic transfers — it does not — but says nothing about whether
gold HAS momentum worth trading. This asks the prior question: find the biggest directional moves on
gold's own tape, then look at what the minutes BEFORE them had in common. If nothing separates the
pre-run window from ordinary tape, there is no momentum gate to build and the honest answer is to stop.

★ VENUE TRUTH: MGC IS $10.00/POINT, five times MNQ's $2.00 — pinned from 433 live V5 fills, where the
`multiplier` column reads 10.0 on 431 of them. Every V7 harness hardcodes VPP=2.0; running one on gold
unmodified understates P&L fivefold and looks entirely plausible doing it.

★ WINDOW: the contiguous V5 block. MGC tape has a real hole (V5 stopped 07-17, V7 tick capture for gold
began 08-04), so the only run of consecutive days with ticks is 2026-07-06..07-17. Studying across the
seam would silently treat a 17-day gap as a bar boundary.

  PYTHONPATH=src .venv/bin/python scripts/mgc_run_census.py
"""
from __future__ import annotations

import datetime as dt
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import Bar, _atr, compute_features  # noqa: E402
from gazbot7.lake import connect  # noqa: E402
from gazbot7.sizing import efficiency_ratio  # noqa: E402

VPP = 10.0
# ★ FIRST PASS USED 3.0 ATR AND FOUND 24.5 "runs" PER DAY — which means it was not finding runs, it
# was finding ordinary tape. Gold's ATR is ~1.6pt, so 3 ATR is ~5 points, a move gold makes constantly.
# The threshold was calibrated to MNQ intuitions where ATR is 15-25 points. A run has to be worth
# TRADING, so it is now an absolute dollar figure at the real $10/pt: $300 = 30 points.
RUN_MIN_ATR = 3.0      # kept as a floor, but the binding test is RUN_MIN_USD below
RUN_MIN_USD = 300.0    # a run must be worth at least this much at $10/pt
LOOK = 40              # bars to look forward for the run's full extent


def minute_bars(con, symbol="MGC"):
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
               arg_max(close, bar_ts) c, sum(volume) v
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    return [Bar(ts=int(m), open=float(c), high=float(h), low=float(lo), close=float(c),
                volume=float(v or 0)) for m, h, lo, c, v in rows]


def main() -> int:
    con = connect(symbol="MGC")
    bars = minute_bars(con)
    if len(bars) < 200:
        print(f"only {len(bars)} MGC minute bars — not enough for a census")
        return 0
    d0 = dt.datetime.fromtimestamp(bars[0].ts, dt.UTC).date()
    d1 = dt.datetime.fromtimestamp(bars[-1].ts, dt.UTC).date()
    days = len({dt.datetime.fromtimestamp(b.ts, dt.UTC).date() for b in bars})
    print(f"MGC tape: {len(bars):,} minute bars over {days} days ({d0} .. {d1})\n")

    # ── find runs: from each bar, the largest favourable extent within LOOK bars ──
    runs = []
    for i in range(60, len(bars) - LOOK):
        w = bars[max(0, i - 60):i + 1]
        atr = _atr(w)
        if atr <= 0:
            continue
        c0 = bars[i].close
        fwd = bars[i + 1:i + 1 + LOOK]
        up = max(x.high for x in fwd) - c0
        dn = c0 - min(x.low for x in fwd)
        side, ext = ("LONG", up) if up >= dn else ("SHORT", dn)
        if ext / atr >= RUN_MIN_ATR and ext * VPP >= RUN_MIN_USD:
            runs.append({"i": i, "ts": bars[i].ts, "side": side, "atr": atr,
                         "ext_pt": ext, "ext_atr": ext / atr, "px": c0})
    # keep only the peak of each cluster — consecutive bars all "see" the same run
    runs.sort(key=lambda r: -r["ext_atr"])
    kept, used = [], set()
    for r in runs:
        if any(abs(r["i"] - k) < 30 for k in used):
            continue
        kept.append(r)
        used.add(r["i"])
    kept.sort(key=lambda r: r["ts"])

    print(f"RUNS >= {RUN_MIN_ATR} ATR AND >= ${RUN_MIN_USD:.0f} within {LOOK} min: {len(kept)}  "
          f"({len(kept)/max(days,1):.1f} per day)\n")
    print(f"{'when':<17}{'side':<6}{'ATR':>6}{'move pt':>9}{'move $':>9}{'x ATR':>7}"
          f"{'ER30':>7}{'ext':>7}{'slope':>7}")
    feats = []
    for r in kept[:25]:
        w = bars[max(0, r["i"] - 60):r["i"] + 1]
        f = compute_features(w)
        er = efficiency_ratio(w, 30)
        feats.append((r, f, er))
        print(f"{dt.datetime.fromtimestamp(r['ts'], dt.UTC).strftime('%m-%d %H:%M'):<17}"
              f"{r['side']:<6}{r['atr']:>6.2f}{r['ext_pt']:>9.2f}{r['ext_pt']*VPP:>9.0f}"
              f"{r['ext_atr']:>7.1f}{er:>7.2f}{f.ext_atr:>7.2f}{f.vwap_slope_atr:>7.2f}")
    if len(kept) > 25:
        print(f"   ... and {len(kept)-25} more")

    # ── the question that matters: does the pre-run window LOOK different from ordinary tape? ──
    print("\n" + "=" * 76)
    print("DO THE MINUTES BEFORE A RUN LOOK DIFFERENT FROM ORDINARY TAPE?")
    all_f = []
    for i in range(60, len(bars) - LOOK, 5):
        w = bars[max(0, i - 60):i + 1]
        try:
            f = compute_features(w)
        except Exception:
            continue
        all_f.append((efficiency_ratio(w, 30), f.atr, abs(f.ext_atr), f.vwap_slope_atr, f.net_atr_5))
    run_f = []
    for r in kept:
        w = bars[max(0, r["i"] - 60):r["i"] + 1]
        try:
            f = compute_features(w)
        except Exception:
            continue
        run_f.append((efficiency_ratio(w, 30), f.atr, abs(f.ext_atr), f.vwap_slope_atr, f.net_atr_5))

    def med(rows, k):
        v = sorted(x[k] for x in rows)
        return v[len(v)//2] if v else 0.0

    def mean(rows, k):
        return sum(x[k] for x in rows) / len(rows) if rows else 0.0

    def sd(rows, k):
        m = mean(rows, k)
        return (sum((x[k]-m)**2 for x in rows)/len(rows)) ** 0.5 if rows else 0.0

    # ★ RATIOS OF NEAR-ZERO MEDIANS ARE MEANINGLESS. The first pass flagged vwap_slope as "separating"
    # on -0.032 vs -0.078 — both essentially zero, the ratio pure noise. Judge on EFFECT SIZE instead:
    # the difference in means measured in standard deviations of ordinary tape. |d| >= 0.3 is a real
    # shift; anything less is not something you can build an entry on.
    print(f"{'feature':<20}{'RUN mean':>10}{'tape mean':>11}{'tape SD':>9}{'effect d':>10}")
    for k, name in ((0, "ER30"), (1, "ATR (pt)"), (2, "|ext| (ATR)"),
                    (3, "vwap slope"), (4, "net_atr_5")):
        a, b, s_ = mean(run_f, k), mean(all_f, k), sd(all_f, k)
        d = (a - b) / s_ if s_ else 0.0
        flag = "  <-- REAL SHIFT" if abs(d) >= 0.30 else ("  (weak)" if abs(d) >= 0.15 else "")
        print(f"{name:<20}{a:>10.3f}{b:>11.3f}{s_:>9.3f}{d:>+10.2f}{flag}")
    print(f"\nn: {len(run_f)} pre-run windows vs {len(all_f)} ordinary samples")
    print("★ A feature that does not separate here cannot be an entry condition. If NOTHING")
    print("  separates, gold's runs are unpredictable from this feature set and the honest")
    print("  answer is that there is no momentum gate to build — not that we need more tuning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
