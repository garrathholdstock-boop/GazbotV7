#!/usr/bin/env python3
"""ATR_SPLIT SWEEP v2 — CLIP vs the LIVE exit, each arm running its OWN desk.

Operator pushed back on v1: "no way. every time i've watched it live it wins. its cashing in profits."
That objection was right, and checking it found TWO defects in v1 that both biased AGAINST the clip:

★ DEFECT 1 — FROZEN ENTRIES REMOVED THE CLIP'S WHOLE POINT.
v1 generated one entry set and scored both exit rules on the same trades. That is clean for locating a
threshold, but it deletes the clip's actual mechanism: it banks SOONER, frees the slot SOONER, and takes
the NEXT signal. A desk that clips is a higher-frequency desk. Holding entries fixed measures the clip
with its main benefit switched off — which is exactly the "cashing in profits" the operator watches.
v2 runs each arm as its OWN sequential desk with its own occupancy, so the trade COUNTS differ, as they
do in reality. (Same effect moved grind_A from 141 to 128 entries in the stop-width dry-run.)

★ DEFECT 2 — THE WRONG COUNTERFACTUAL FOR THE B LOTS.
v1 scored every B lot against a FIXED R-target. Live, 3 of 5 B lots run a CHANDELIER
(grind_long_B chandelier_lock, capitulation_long_B and rgv_short_B chandelier). Comparing a clip against
a fixed R that the desk does not use answers a question nobody asked. v2 uses each slot's REAL exit as
the control: chandelier where live is chandelier, fixed R where live is scalp.

★ AND IT REPORTS WIN RATE + $/day, not just net.
"It wins" is a claim about FREQUENCY, and v1 only printed net dollars. A clip that wins far more often
while netting slightly less is a real and defensible preference — smoother equity, less give-back, and
it is what a human watching the tape actually experiences. Both numbers now appear so the trade-off is
visible instead of being collapsed into one figure.

Costs $1.50/RT, $2/pt, first-touch race on 250ms ticks, 120-min cap, stop always 1xATR. No slippage, so
both arms are equally optimistic ceilings.

  PYTHONPATH=src .venv/bin/python scripts/atr_split_sweep2.py
"""
from __future__ import annotations

import argparse
import bisect
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

GB = "/home/alphabot/gazbot7"
VPP, FEE_RT = 2.0, 1.50
CAP_MIN = 120
ATR_MAX = 22.0          # only the regime where the clip is LIVE
GATE_FN = {"grind": gate_grind, "thrust": gate_thrust, "capitulation": gate_capitulation,
           "reversal_grab": gate_reversal_grab}
import inspect as _inspect  # noqa: E402
_ACCEPTS = {k: set(_inspect.signature(v).parameters) for k, v in GATE_FN.items()}


def load(con):
    rows = con.execute("""SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
               arg_max(close,bar_ts) c, sum(volume) v FROM cap.bars
            WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= (
                SELECT min(ts_ms)/1000 FROM cap.ticks WHERE symbol='MNQ')
            GROUP BY 1 ORDER BY 1""").fetchall()
    bars = [Bar(int(m), float(c), float(h), float(lo), float(c), float(v or 0))
            for m, h, lo, c, v in rows]
    t = con.execute("SELECT ts_ms, price FROM cap.ticks WHERE symbol='MNQ' ORDER BY ts_ms").fetchall()
    return bars, [(int(a), float(b)) for a, b in t]


def run_arm(bars, ticks, tick_ts, sp, mode: str):
    """One sequential desk for this slot under `mode` ('clip' or 'live'). Returns trade list."""
    out = []
    busy = 0
    fn = GATE_FN[sp.kind]
    for i in range(30, len(bars)):
        w = bars[max(0, i - 60):i + 1]
        if w[-1].ts * 1000 < busy:
            continue
        try:
            f = compute_features(w)
            kw = dict(sp.params)
            if "tape_net" in _ACCEPTS[sp.kind]:
                kw["tape_net"] = 0.0
            e = fn(f, **kw)
        except Exception:
            continue
        if not e or f.atr <= 0 or f.atr >= ATR_MAX:
            continue
        if sp.side and e.side != sp.side:
            continue
        t0 = (w[-1].ts + 60) * 1000
        j = bisect.bisect_left(tick_ts, t0)
        if j >= len(ticks):
            continue
        entry, atr, side = ticks[j][1], f.atr, e.side
        stp = atr
        # target / trail for this mode
        if mode == "clip":
            tgt = ((sp.lo_target_usd or 40.0) / VPP) if sp.tag.endswith("_A") else \
                  max((sp.lo_target_r or 1.75) * atr, (sp.lo_floor_usd or 60.0) / VPP)
            chand = None
        else:
            # ★ the LIVE control: chandelier where live is chandelier, fixed R where live is scalp
            chand = sp.exit if sp.exit in ("chandelier", "chandelier_lock") else None
            tgt = None if chand else sp.target_r * atr
        end = t0 + CAP_MIN * 60_000
        k, peak, res = j, 0.0, None
        while k < len(ticks) and ticks[k][0] <= end:
            px = ticks[k][1]
            fav = (px - entry) if side == "LONG" else (entry - px)
            if -fav >= stp:
                res = (-stp * VPP - FEE_RT, "STOP", ticks[k][0])
                break
            peak = max(peak, fav)
            if tgt is not None and fav >= tgt:
                res = (tgt * VPP - FEE_RT, "TARGET", ticks[k][0])
                break
            if chand:
                pos = Position(side, entry, atr, peak)
                hit = (exit_chandelier_lock(pos, px, start_k=sp.chandelier_start_k,
                                            lock_r=sp.lock_r, lock_k=sp.lock_k)
                       if chand == "chandelier_lock" else
                       exit_chandelier(pos, px, start_k=sp.chandelier_start_k,
                                       min_k=sp.chandelier_min_k, tighten=sp.chandelier_tighten))
                if hit:
                    res = (fav * VPP - FEE_RT, "CHANDELIER", ticks[k][0])
                    break
            k += 1
        if res is None:
            if k >= len(ticks):
                continue
            m = min(k, len(ticks) - 1)
            fav = (ticks[m][1] - entry) if side == "LONG" else (entry - ticks[m][1])
            res = (fav * VPP - FEE_RT, "CAP", ticks[m][0])
        out.append(res)
        busy = res[2]        # ★ own occupancy: this arm is busy until ITS OWN exit
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", default="grind_long,abs_veto_long,abs_veto_short,capitulation_long,rgv_short")
    a = ap.parse_args()
    con = duckdb.connect()
    con.execute(f"ATTACH '{GB}/data/capture.db' AS cap (TYPE sqlite, READ_ONLY)")
    bars, ticks = load(con)
    tick_ts = [t for t, _ in ticks]
    days = len({t // 86400000 for t, _ in ticks})
    print(f"tape {len(bars):,} bars / {len(ticks):,} ticks / {days} days — ATR < {ATR_MAX:.0f} only "
          f"(the regime where the clip is LIVE)\n")
    specs = {s.tag: s for s in scaleout_slots()}

    print(f"{'slot':<20}{'live exit':<16}{'':>2}{'n':>5}{'net$':>9}{'win%':>7}{'$/tr':>7}{'$/day':>7}")
    tot = defaultdict(lambda: [0, 0.0, 0])
    for g in [x.strip() for x in a.gates.split(",")]:
        for lot in ("A", "B"):
            sp = specs.get(f"{g}_{lot}")
            if not sp or sp.kind not in GATE_FN:
                continue
            for mode in ("live", "clip"):
                tr = run_arm(bars, ticks, tick_ts, sp, mode)
                if not tr:
                    continue
                net = sum(x[0] for x in tr)
                wins = sum(1 for x in tr if x[0] > 0)
                label = f"{sp.exit}" if mode == "live" else "CLIP"
                print(f"{sp.tag if mode=='live' else '':<20}{label:<16}{'':>2}{len(tr):>5}"
                      f"{net:>+9.0f}{100*wins/len(tr):>6.0f}%{net/len(tr):>7.1f}{net/days:>7.1f}")
                t = tot[mode]
                t[0] += len(tr)
                t[1] += net
                t[2] += wins
    print("-" * 74)
    for mode in ("live", "clip"):
        n, net, w = tot[mode]
        if n:
            print(f"{'TOTAL '+('LIVE exits' if mode=='live' else 'CLIP exits'):<38}{n:>5}"
                  f"{net:>+9.0f}{100*w/n:>6.0f}%{net/n:>7.1f}{net/days:>7.1f}")
    ln, lnet, lw = tot["live"]
    cn, cnet, cw = tot["clip"]
    if ln and cn:
        print(f"\nCLIP vs LIVE:  net ${cnet-lnet:+.0f}  |  win rate {100*cw/cn:.0f}% vs {100*lw/ln:.0f}%"
              f"  |  trades {cn} vs {ln} ({cn-ln:+d})")
        print("  ('it wins' is a WIN-RATE claim; net dollars and frequency can disagree — both shown.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
