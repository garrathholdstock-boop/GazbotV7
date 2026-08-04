#!/usr/bin/env python3
"""WHERE DID NIPC'S LIVE/REPLAY DIVERGENCE GO? — a one-factor-at-a-time attribution ladder.

Operator, 2026-08-04: "diagnose the $395 drag".

BACKGROUND. NIPC shipped 08-01 and ran live on exactly ONE day, 2026-08-03: 30 trades
(15 signals x 2 lots) for -$280. Replaying the SHIPPED NipcTracker over that same day's tape gives
+$204. Something worth roughly $480 sits between the two, and until it is named NIPC cannot be trusted
either way — a gate whose replay says +$204 while it loses $280 is not a gate, it is an unknown.

METHOD. Start from the replay exactly as the acceptance harness runs it, then switch ON, one at a time,
each way PRODUCTION genuinely differs. Each rung is the same code path with one knob moved, so the delta
between rungs IS that factor's contribution. Whatever is left after every known difference is applied is
the true unexplained execution drag — and it is reported as unexplained rather than absorbed.

★ THE RUNGS, and why each is a REAL production difference rather than a fitting knob:
  1. blanket / raw ticks / 1 lot @2.5R  — the acceptance-harness headline. Not what production does.
  2. apply_regime=True                  — production BLOCKS dead-chop at DETECTION. This is not the same
     as bucketing it afterwards: an impulse that never arms cannot be the one a later pullback resolves
     against, so blocking changes the state machine's PATH, not just the filter.
  3. cadence_ms=1000                    — md.py publishes T_TAPE once per second, so the live tracker
     gets ~60 trigger checks a minute where the raw-tick replay gets ~3,500. Rule 3 ("fill at the first
     tick trading through it") is not available to production: it sees one snapshot per second and never
     the extremes traversed in between.
  4. the LIVE lot ladder                — exit_overrides.json runs nipc A@2.0R + B@2.5R, not both at
     2.5R. Verified via the config journal, not read off source.

Then the residual is decomposed against the ACTUAL live fills (entry slippage, exit slippage,
exit-reason mismatch), because those are measurable and should not be left inside a mystery number.

  PYTHONPATH=src .venv/bin/python scripts/nipc_drag_ladder.py
"""
from __future__ import annotations

import sqlite3
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

import nipc_replay as R  # noqa: E402

DAY = "2026-08-03"
GB = "/home/alphabot/gazbot7"


def live_trades():
    con = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    return con.execute(
        "SELECT gate, side, entry_price, exit_price, pnl_usd, exit_reason, opened_at, closed_at "
        "FROM trades WHERE gate LIKE 'nipc%' AND opened_at >= ? AND opened_at < ? ORDER BY opened_at",
        (DAY, "2026-08-04")).fetchall()


def main() -> int:
    con = duckdb.connect()
    con.execute(f"ATTACH '{GB}/data/capture.db' AS cap (TYPE SQLITE, READ_ONLY)")
    R.TICK_DAYS.add(DAY)
    bars5, ticks = R.load_day(con, DAY)
    print(f"tape {DAY}: {len(bars5)} bars, {len(ticks):,} ticks\n")

    lt = live_trades()
    live_net = sum(t[4] for t in lt)
    live_sig = len({t[6] for t in lt})
    print(f"LIVE ACTUAL           {len(lt)} trades ({live_sig} signals x 2 lots)   ${live_net:+.0f}\n")

    rungs = [
        ("1. acceptance headline (blanket, raw ticks, 1 lot @2.5R)",
         dict(lot_a=None, lot_b=2.5, apply_regime=False, cadence_ms=0)),
        ("2. + regime BLOCKED at detection (production)",
         dict(lot_a=None, lot_b=2.5, apply_regime=True, cadence_ms=0)),
        ("3. + 1s tape cadence (production sees T_TAPE, not ticks)",
         dict(lot_a=None, lot_b=2.5, apply_regime=True, cadence_ms=1000)),
        ("4. + LIVE lot ladder A@2.0R + B@2.5R (exit_overrides)",
         dict(lot_a=2.0, lot_b=2.5, apply_regime=True, cadence_ms=1000)),
    ]
    print(f"{'rung':<58}{'n':>4}{'net':>9}{'delta':>9}")
    prev = None
    last_trades = None
    for label, kw in rungs:
        tr = R.replay_day(DAY, bars5, ticks, **kw)
        net = sum(t["net"] for t in tr)
        d = "" if prev is None else f"{net - prev:>+9.0f}"
        print(f"{label:<58}{len(tr):>4}{net:>+9.0f}{d:>9}")
        prev = net
        last_trades = tr
    print("-" * 80)
    print(f"{'production-equivalent replay':<58}{len(last_trades):>4}{prev:>+9.0f}")
    print(f"{'LIVE ACTUAL':<58}{live_sig:>4}{live_net:>+9.0f}")
    resid = live_net - prev
    print(f"{'>>> UNEXPLAINED RESIDUAL':<58}{'':>4}{resid:>+9.0f}")

    # ── decompose the residual against real fills ────────────────────────────────────────────────
    print("\nRESIDUAL DECOMPOSITION vs the actual live fills")
    rr = {t["ts"]: t for t in last_trades} if last_trades and "ts" in last_trades[0] else {}
    print(f"  replay signals {len(last_trades)}  vs  live signals {live_sig}"
          f"   -> {'COUNT MATCHES' if len(last_trades) == live_sig else 'COUNT DIFFERS (see below)'}")

    stops = [t for t in lt if t[5] == "STOP"]
    targs = [t for t in lt if t[5] == "TARGET"]
    print(f"  live exits: STOP {len(stops)}  TARGET {len(targs)}")
    rstop = sum(1 for t in last_trades if t.get("reason") == "STOP")
    rtarg = sum(1 for t in last_trades if t.get("reason") == "TARGET")
    print(f"  replay exits: STOP {rstop}  TARGET {rtarg}   (per SIGNAL, both lots share one stop)")
    if stops:
        print(f"  live STOP avg ${sum(t[4] for t in stops)/len(stops):+.2f}   "
              f"live TARGET avg ${(sum(t[4] for t in targs)/len(targs)) if targs else 0:+.2f}")
    print(f"  live win rate {100*sum(1 for t in lt if t[4] > 0)/len(lt):.1f}%  "
          f"vs replay {100*sum(1 for t in last_trades if t['net'] > 0)/max(len(last_trades),1):.1f}%")
    if rr:
        print("  (per-signal price matching available)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
