#!/usr/bin/env python3
"""DOES THE L2 BOOK CALL GOLD'S DIRECTION? — the one information source price could not supply.

Operator, 2026-08-05, after three price-based nulls: allocate the depth slot for MGC. It turned out no
slot was free (all three IBKR subscriptions live: MNQ depth, MGC depth, MNQ 41ms book) — but MGC
already had **19 days of fully-populated 10-level depth**, so the study runs at zero cost and on MORE
tape than any MGC study so far. Operator chose not to spend the slot.

★ WHY THIS IS THE RIGHT LAST TEST. Three price-based attacks all failed the same way:
    predict direction (census)          ~2pp over the best CONSTANT
    react to direction (delay-confirm)  NEGATIVE in all 24 cells
    filter by regime (router meter)     placebo-null, beaten by 31-80% of random removals
  Each concluded that gold's direction is not in the price series. The book is a genuinely different
  information source — resting liquidity and its depletion, not past prices — and on MNQ it produced
  the one surviving cell in ~100 ([[ofi-veto-grind-lead]]).

★ THE DEPTH FEED ALSO FILLS THE HOLE. MGC ticks/bars stop 07-17 and resume 08-04. depth_snap ran
straight through, so mid = (bid1p+ask1p)/2 reconstructs a 250ms price series across **15 full days**
including the gap. Price here comes from the BOOK, not from trades — spread averages 0.22-0.57pt, so
mid is well-defined, but it is a quote midpoint and not a traded price. Stated, not hidden.

★ THE BAR IS THE BEST CONSTANT, NOT 50%. On this tape a fixed directional call is right ~54% of the
time from drift alone. Scoring against a coinflip is what made a 1.2pp feature look like 4.9pp.

★ AND THE BOOK MAY VETO RATHER THAN SELECT. That is what it did on MNQ. Both are tested: can a book
feature CHOOSE the side, and — given a side — does book disagreement predict failure?

  PYTHONPATH=src .venv/bin/python scripts/mgc_book_direction.py
"""
from __future__ import annotations

import argparse
import statistics
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.lake import connect  # noqa: E402

LOOK = 40          # forward window, minutes — same horizon as every earlier MGC study
ATR_N = 60


def minute_frame(con):
    """One row per minute: OHLC from the book mid, plus resting-liquidity features.

    Aggregated in DuckDB rather than row-looped in Python — 2.4M snaps, and memory
    [[duckdb-pandas-for-analytics]] is explicit that raw sqlite row-loops are the wrong tool.
    """
    bidsz = " + ".join(f"COALESCE(bid{i}s,0)" for i in range(1, 11))
    asksz = " + ".join(f"COALESCE(ask{i}s,0)" for i in range(1, 11))
    b5 = " + ".join(f"COALESCE(bid{i}s,0)" for i in range(1, 6))
    a5 = " + ".join(f"COALESCE(ask{i}s,0)" for i in range(1, 6))
    return con.execute(f"""
        WITH s AS (
          SELECT ts_ms,
                 (bid1p+ask1p)/2.0            AS mid,
                 COALESCE(bid1s,0)            AS b1,
                 COALESCE(ask1s,0)            AS a1,
                 {b5}                         AS b5,
                 {a5}                         AS a5,
                 {bidsz}                      AS b10,
                 {asksz}                      AS a10
          FROM depth
          WHERE bid1p IS NOT NULL AND ask1p IS NOT NULL AND ask1p > bid1p
        )
        SELECT CAST(ts_ms/60000 AS BIGINT)*60      AS m,
               max(mid) AS hi, min(mid) AS lo,
               arg_max(mid, ts_ms) AS cl,
               avg((b1-a1)/NULLIF(b1+a1,0))        AS imb1,
               avg((b5-a5)/NULLIF(b5+a5,0))        AS imb5,
               avg((b10-a10)/NULLIF(b10+a10,0))    AS imb10,
               avg(b10+a10)                        AS depth_tot,
               count(*)                            AS n
        FROM s GROUP BY 1 HAVING count(*) >= 20 ORDER BY 1""").fetchall()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--atr", type=float, default=0.0, help="ATR floor in points (0 = no filter)")
    z = ap.parse_args()

    con = connect(symbol="MGC")
    rows = minute_frame(con)
    if len(rows) < 500:
        print(f"only {len(rows)} usable minutes — not enough")
        return 0
    m = [r[0] for r in rows]
    hi = [float(r[1]) for r in rows]
    lo = [float(r[2]) for r in rows]
    cl = [float(r[3]) for r in rows]
    imb1 = [float(r[4] or 0) for r in rows]
    imb5 = [float(r[5] or 0) for r in rows]
    imb10 = [float(r[6] or 0) for r in rows]
    dep = [float(r[7] or 0) for r in rows]
    import datetime as dt
    days = sorted({dt.datetime.fromtimestamp(x, dt.UTC).date() for x in m})
    print(f"MGC book: {len(rows):,} minutes over {len(days)} days "
          f"({days[0]} .. {days[-1]})   price = book mid, 250ms")
    print("★ this INCLUDES 07-18..08-03, the window where MGC ticks/bars do not exist\n")

    # ATR from the mid series
    atr = [0.0] * len(rows)
    for i in range(1, len(rows)):
        w0 = max(1, i - ATR_N)
        trs = [max(hi[j] - lo[j], abs(hi[j] - cl[j - 1]), abs(lo[j] - cl[j - 1]))
               for j in range(w0, i + 1)]
        atr[i] = sum(trs) / len(trs) if trs else 0.0

    # ── the test: at each minute, does a BOOK feature call the side of the next 40 minutes? ──
    # Contiguity guard: a 40-minute forward window must not span a session gap, or the "run" is an
    # overnight jump. Minutes are only used when the forward window is genuinely contiguous.
    cases = []
    for i in range(ATR_N, len(rows) - LOOK):
        if m[i + LOOK] - m[i] > LOOK * 60 * 1.5:
            continue
        if atr[i] <= 0 or atr[i] < z.atr:
            continue
        c0 = cl[i]
        up = max(hi[i + 1:i + 1 + LOOK]) - c0
        dn = c0 - min(lo[i + 1:i + 1 + LOOK])
        cases.append({"i": i, "side": "LONG" if up >= dn else "SHORT",
                      "imb1": imb1[i], "imb5": imb5[i], "imb10": imb10[i],
                      "d_imb5": imb5[i] - imb5[i - 5], "d_imb10": imb10[i] - imb10[i - 5],
                      "dep": dep[i], "atr": atr[i], "ext": max(up, dn) / atr[i]})
    if not cases:
        print("no usable windows")
        return 0
    longs = sum(1 for c in cases if c["side"] == "LONG") / len(cases)
    best_const = max(longs, 1 - longs) * 100
    print(f"windows: {len(cases):,}   best CONSTANT call = "
          f"{'LONG' if longs > 0.5 else 'SHORT'} at {best_const:.1f}%\n")

    print("PART 1 — CAN A BOOK FEATURE *CHOOSE* THE SIDE?")
    print(f"{'feature':<26}{'correct':>9}{'vs constant':>13}{'n':>8}")
    FEATS = [("L1 imbalance", "imb1"), ("L1-5 imbalance", "imb5"), ("L1-10 imbalance", "imb10"),
             ("d L1-5 imbalance (5m)", "d_imb5"), ("d L1-10 imbalance (5m)", "d_imb10")]
    for name, k in FEATS:
        for sgn, tag in ((1, ""), (-1, " (FADED)")):
            ok = n = 0
            for c in cases:
                v = c[k] * sgn
                if abs(v) < 1e-9:
                    continue
                n += 1
                ok += (("LONG" if v > 0 else "SHORT") == c["side"])
            if n:
                print(f"{name+tag:<26}{100*ok/n:>8.1f}%{100*ok/n-best_const:>+12.1f}{n:>8}")

    # a stronger form: only act when the book is LOPSIDED, where the signal should be clearest
    print("\nPART 2 — ONLY WHEN THE BOOK IS LOPSIDED (does conviction help?)")
    print(f"{'feature':<20}{'cut':>7}{'taken':>8}{'correct':>9}{'vs constant':>13}")
    for name, k in (("L1-5 imbalance", "imb5"), ("L1-10 imbalance", "imb10")):
        vals = sorted(abs(c[k]) for c in cases)
        for q, lab in ((0.50, "top50%"), (0.75, "top25%"), (0.90, "top10%")):
            cut = vals[int(q * len(vals))]
            sel = [c for c in cases if abs(c[k]) >= cut]
            if len(sel) < 40:
                continue
            ok = sum(1 for c in sel if ("LONG" if c[k] > 0 else "SHORT") == c["side"])
            lg = sum(1 for c in sel if c["side"] == "LONG") / len(sel)
            bc = max(lg, 1 - lg) * 100
            print(f"{name:<20}{lab:>7}{len(sel):>8}{100*ok/len(sel):>8.1f}%{100*ok/len(sel)-bc:>+12.1f}")

    # ── PART 3: the shape that worked on MNQ — the book as a VETO on a direction already chosen ──
    print("\nPART 3 — THE BOOK AS A *VETO* (the shape that survived on MNQ)")
    print("given the best constant direction, does book DISAGREEMENT mark the failures?")
    fixed = "LONG" if longs > 0.5 else "SHORT"
    fs = 1 if fixed == "LONG" else -1
    print(f"{'veto rule':<34}{'kept':>7}{'correct':>9}{'vs no-veto':>12}")
    base_ok = sum(1 for c in cases if c["side"] == fixed)
    print(f"{'no veto (always '+fixed+')':<34}{len(cases):>7}"
          f"{100*base_ok/len(cases):>8.1f}%{0.0:>+12.1f}")
    for name, k in (("L1-5 imbalance", "imb5"), ("L1-10 imbalance", "imb10")):
        for thr in (0.0, 0.05, 0.15):
            kept = [c for c in cases if c[k] * fs >= -thr]     # stand down only if book contradicts
            if len(kept) < 40 or len(kept) == len(cases):
                continue
            ok = sum(1 for c in kept if c["side"] == fixed)
            print(f"{name+f' contradicts >{thr}':<34}{len(kept):>7}{100*ok/len(kept):>8.1f}%"
                  f"{100*ok/len(kept)-100*base_ok/len(cases):>+12.1f}")

    print("\nPART 4 — SANITY: does the book separate BIG moves from ordinary tape at all?")
    big = [c for c in cases if c["ext"] >= 3.0]
    ordn = [c for c in cases if c["ext"] < 3.0]
    print(f"{'feature':<24}{'before big':>12}{'ordinary':>11}{'effect d':>10}")
    for name, k in (("|L1 imbalance|", "imb1"), ("|L1-5 imbalance|", "imb5"),
                    ("|L1-10 imbalance|", "imb10"), ("total depth", "dep")):
        if not big or not ordn:
            break
        a = statistics.mean(abs(c[k]) for c in big)
        b = statistics.mean(abs(c[k]) for c in ordn)
        s = statistics.pstdev([abs(c[k]) for c in ordn]) or 1e-9
        d = (a - b) / s
        flag = "  <-- REAL" if abs(d) >= 0.30 else ("  (weak)" if abs(d) >= 0.15 else "")
        print(f"{name:<24}{a:>12.3f}{b:>11.3f}{d:>+10.2f}{flag}")
    print(f"n: {len(big)} big-move windows vs {len(ordn)} ordinary")
    print("\n★ If the book cannot choose the side AND cannot veto, gold is done: price and book are")
    print("  the only two sources this desk has, and both would have said no.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
