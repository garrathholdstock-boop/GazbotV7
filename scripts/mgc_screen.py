#!/usr/bin/env python3
"""MGC SCREEN — every current V7 gate x every exit, on 11 days of gold tape.

Operator, 2026-08-04: "pin the venue truth and run the screen. then run all our current gates and the
different exits on different tapes to see how we go. over the 11 days."

★★ VENUE TRUTH, PINNED FROM 433 LIVE V5 FILLS — NOT ASSUMED.
  POINT VALUE = $10.00/point.  Median implied 10.000 across 409 fills with a >0.05 move; the trades
  table's own `multiplier` column reads 10.0 on 431 of 433 rows. (The other two read 1.0 — the known
  exit-multiplier-defaults-to-1.0 recording bug, so their stored P&L is wrong. Two rows, flagged.)
  ⚠ FEE = UNKNOWN. Every MGC row has fees_usd = 0.00, which is a RECORDING GAP, not free trading. So
  the fee is a PARAMETER here and the screen reports SENSITIVITY across a plausible range instead of
  quietly adopting MNQ's $1.50. Assuming a fee is exactly how the $5-vs-$1.50 error inverted the NIPC
  verdict this morning; assuming ZERO would be the same mistake with a friendlier sign.
  ★ SCALE MATTERS: at $10/point, MGC is 5x MNQ's $2 per point. Every V7 harness hardcodes VPP=2.0, so
  running any of them on gold unmodified would understate P&L fivefold and look plausible doing it.

★ WHAT IT DOES. For each live gate (params read from scaleout_slots(), never source) it runs an
independent sequential desk under each candidate exit, racing stop against target on real V5 trade
ticks. First touch wins — never MFE. Reported per exit AND per day, because "different tapes" is the
question: an exit that only works on two of eleven days has not been shown to work.

★ THIS IS A SCREEN, NOT A VERDICT. One 11-day window, one regime (July gold), in-sample, no slippage.
The only live MGC record we have (433 trades) FAILED strip-best-1 — it was +$1,103 with a single
$1,627 print and −$524 without it — so gold starts from "no demonstrated edge", and a green cell here
is a reason to capture more tape, not to arm anything.

  PYTHONPATH=src .venv/bin/python scripts/mgc_screen.py [--fee 1.50]
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import sys
from collections import defaultdict

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import (  # noqa: E402
    Bar,
    Position,
    compute_features,
    exit_chandelier,
    exit_chandelier_lock,
    gate_capitulation,
    gate_grind,
    gate_reversal_grab,
    gate_thrust,
)
from gazbot7.slot_strategy import scaleout_slots  # noqa: E402

V5 = "/home/alphabot/alphabot2/data"
VPP = 10.0                     # ★ pinned from live fills — NOT MNQ's 2.0
CAP_MIN = 120
GATE_FN = {"grind": gate_grind, "thrust": gate_thrust, "capitulation": gate_capitulation,
           "reversal_grab": gate_reversal_grab}
import inspect as _inspect  # noqa: E402
_ACC = {k: set(_inspect.signature(v).parameters) for k, v in GATE_FN.items()}

# the exit ladder under test — every shape the live desk actually uses, plus the clip
EXITS = [("scalp 1.0R", dict(kind="scalp", r=1.0)),
         ("scalp 1.5R", dict(kind="scalp", r=1.5)),
         ("scalp 2.0R", dict(kind="scalp", r=2.0)),
         ("scalp 2.5R", dict(kind="scalp", r=2.5)),
         ("chand k1.5", dict(kind="chand", k=1.5)),
         ("chand k3.5", dict(kind="chand", k=3.5)),
         ("lock 3.5->0.5", dict(kind="lock",)),
         ("CLIP A $40*", dict(kind="clip_a")),
         ("CLIP B 1.75R*", dict(kind="clip_b"))]


def load():
    con = duckdb.connect()
    con.execute(f"ATTACH '{V5}/alphabot.db' AS a (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{V5}/ticks.db' AS t (TYPE sqlite, READ_ONLY)")
    rows = con.execute("""SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
               arg_max(close,bar_ts) c, sum(volume) v FROM a.bar_history
            WHERE symbol='MGC' AND timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    bars = [Bar(int(m), float(c), float(h), float(lo), float(c), float(v or 0))
            for m, h, lo, c, v in rows]
    tk = con.execute("""SELECT ts_ms, price FROM t.trade_tick WHERE symbol='MGC'
                        ORDER BY ts_ms""").fetchall()
    return bars, [(int(a), float(b)) for a, b in tk]


def run(bars, ticks, tick_ts, sp, ex, fee):
    """One sequential desk: this gate under this exit. Returns [(pnl, day)]."""
    out, busy = [], 0
    fn = GATE_FN[sp.kind]
    for i in range(30, len(bars)):
        w = bars[max(0, i - 60):i + 1]
        if w[-1].ts * 1000 < busy:
            continue
        try:
            kw = dict(sp.params)
            if "tape_net" in _ACC[sp.kind]:
                kw["tape_net"] = 0.0
            f = compute_features(w)
            e = fn(f, **kw)
        except Exception:
            continue
        if not e or f.atr <= 0 or (sp.side and e.side != sp.side):
            continue
        t0 = (w[-1].ts + 60) * 1000
        j = bisect.bisect_left(tick_ts, t0)
        if j >= len(ticks) or ticks[j][0] > t0 + 300_000:     # no tick within 5 min = dead tape
            continue
        entry, atr, side = ticks[j][1], f.atr, e.side
        k = ex["kind"]
        tgt = None
        if k == "scalp":
            tgt = ex["r"] * atr
        elif k == "clip_a":
            tgt = 40.0 / VPP
        elif k == "clip_b":
            tgt = max(1.75 * atr, 60.0 / VPP)
        end, m, peak, res = t0 + CAP_MIN * 60_000, j, 0.0, None
        while m < len(ticks) and ticks[m][0] <= end:
            px = ticks[m][1]
            fav = (px - entry) if side == "LONG" else (entry - px)
            if -fav >= atr:
                res = (-atr * VPP - fee, ticks[m][0])
                break
            peak = max(peak, fav)
            if tgt is not None and fav >= tgt:
                res = (tgt * VPP - fee, ticks[m][0])
                break
            if k in ("chand", "lock"):
                pos = Position(side, entry, atr, peak)
                hit = (exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
                       if k == "lock" else
                       exit_chandelier(pos, px, start_k=ex["k"], min_k=0.5, tighten=0.75))
                if hit:
                    res = (fav * VPP - fee, ticks[m][0])
                    break
            m += 1
        if res is None:
            if m >= len(ticks):
                break
            q = min(m, len(ticks) - 1)
            fav = (ticks[q][1] - entry) if side == "LONG" else (entry - ticks[q][1])
            res = (fav * VPP - fee, ticks[q][0])
        out.append((res[0], dt.datetime.fromtimestamp(res[1] / 1000, dt.UTC).strftime("%m-%d")))
        busy = res[1]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee", type=float, default=1.50, help="MGC round-trip fee (UNKNOWN — see header)")
    a = ap.parse_args()
    bars, ticks = load()
    tick_ts = [t for t, _ in ticks]
    days = sorted({dt.datetime.fromtimestamp(t / 1000, dt.UTC).strftime("%m-%d") for t, _ in ticks})
    print(f"MGC tape: {len(bars):,} minute bars, {len(ticks):,} trade ticks, {len(days)} days "
          f"({days[0]} -> {days[-1]})")
    print(f"VPP ${VPP:.2f}/pt (pinned from 433 live fills) | fee ${a.fee:.2f}/RT (ASSUMED — see --fee)\n")

    specs = [s for s in scaleout_slots() if s.kind in GATE_FN and s.tag.endswith("_A")]
    print(f"{'gate':<20}{'exit':<16}{'n':>5}{'net$':>10}{'$/tr':>8}{'win%':>7}{'days green':>12}")
    best = []
    for sp in specs:
        for label, ex in EXITS:
            tr = run(bars, ticks, tick_ts, sp, ex, a.fee)
            if len(tr) < 5:
                continue
            net = sum(x[0] for x in tr)
            wins = sum(1 for x in tr if x[0] > 0)
            byday = defaultdict(float)
            for p, d in tr:
                byday[d] += p
            dg = sum(1 for v in byday.values() if v > 0)
            print(f"{sp.tag.replace('_A',''):<20}{label:<16}{len(tr):>5}{net:>+10.0f}"
                  f"{net/len(tr):>8.2f}{100*wins/len(tr):>6.0f}%{f'{dg}/{len(byday)}':>12}")
            best.append((net, sp.tag.replace("_A", ""), label, len(tr), dg, len(byday)))
    print("-" * 78)
    best.sort(reverse=True)
    print("TOP 5 cells:")
    for net, g, lab, n, dg, nd in best[:5]:
        print(f"   {g:<18}{lab:<16}{n:>4}tr  ${net:>+8.0f}   days green {dg}/{nd}")
    print("\nBOTTOM 3:")
    for net, g, lab, n, dg, nd in best[-3:]:
        print(f"   {g:<18}{lab:<16}{n:>4}tr  ${net:>+8.0f}   days green {dg}/{nd}")
    print("\n★ 'days green' is the honest column. A cell that is green on 2 of 11 days is one or two")
    print("  trades, not an edge — the same trap as the single $1,627 print in the live MGC record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
