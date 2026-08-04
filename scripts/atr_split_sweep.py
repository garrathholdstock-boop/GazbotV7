#!/usr/bin/env python3
"""ATR_SPLIT SWEEP — is 22 the right quiet-tape clip boundary, and does the clip help at all?

Operator, 2026-08-04: "run the atr_split sweep".

WHAT IS BEING TESTED. data/exit_overrides.json applies a QUIET-TAPE CLIP: when entry ATR < atr_split,
Lot A abandons its R-target for a flat cash target (a_usd) and Lot B takes b_r floored at b_floor_usd.
atr_split=22 was PICKED, not derived — nothing has ever validated it, and the whole Lot B leg is
unproven. Today it also became clear the clip does opposite things to different lots: it BINDS a high-R
lot (grind_long_A at 2.5R wanted $125 at ATR 25 and got capped at $40) and RESCUES a low-R lot
(abs_veto_long_A at 1.0R would take $22.60 at ATR 11.3 where the clip pays $40). So a single global
threshold is being asked to serve two opposite jobs.

★ WHY THIS IS A CLEAN EXPERIMENT: THE CLIP IS EXIT-ONLY.
Entries do not depend on it, so the entry set is generated ONCE and every exit rule is scored on the
SAME trades. That removes the entry-set confound entirely — unlike the stop-width study, where a wider
stop changed occupancy and therefore which signals each arm could take.

★ STATED LIMIT, so it is not discovered later as a flaw. Holding entries fixed measures the exit rule
PER TRADE. It does NOT capture occupancy: a clip that exits sooner frees the slot sooner and could take
trades the R-target arm never sees. That effect is real (it moved grind_A from 141 to 128 entries in the
stop-width dry-run) but it cannot be measured without re-running the whole desk per cell, and it does
not bear on the question asked here — WHERE IS THE CROSSOVER. Per-trade is the right resolution for that.

METHOD
  * entries: the SHIPPED deciders over 11 days of 250ms tape (07-24..08-04), one position per slot,
    live params read from scaleout_slots() — never from source.
  * exits: first-touch RACE on real ticks, stop always 1xATR, 120-min cap. Whichever of stop/target is
    touched FIRST wins. Never MFE — "reached N R" has produced five wrong answers on this desk.
  * costs: $1.50/RT, $2.00/pt. No slippage term, so every cell is an equally optimistic CEILING and the
    COMPARISON between cells is what matters, not the absolute level.
  * reported per ATR BAND, because the answer to "is 22 right" is a crossover, not a single number. A
    grid over atr_split alone would hide WHY one value wins.

  PYTHONPATH=src .venv/bin/python scripts/atr_split_sweep.py [--gates grind_long,abs_veto_long]
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import (  # noqa: E402
    Bar,
    compute_features,
    gate_capitulation,
    gate_grind,
    gate_reversal_grab,
    gate_thrust,
)
from gazbot7.slot_strategy import scaleout_slots  # noqa: E402

GB = "/home/alphabot/gazbot7"
VPP, FEE_RT = 2.0, 1.50
CAP_MIN = 120
BANDS = [(0, 10), (10, 14), (14, 18), (18, 22), (22, 26), (26, 32), (32, 999)]
# ★ exhaustion is deliberately ABSENT: it is a tick/footprint state machine, not a 1-minute bar gate —
# there is no gate_exhaustion() to call. Including it would have silently produced zero trades and looked
# like "no edge in that band" rather than "not measured", which is the capit_tight pathology.
GATE_FN = {"grind": gate_grind, "thrust": gate_thrust, "capitulation": gate_capitulation,
           "reversal_grab": gate_reversal_grab}


import inspect as _inspect
_ACCEPTS = {k: set(_inspect.signature(v).parameters) for k, v in GATE_FN.items()}


def band(atr: float) -> str:
    for lo, hi in BANDS:
        if lo <= atr < hi:
            return f"{lo}-{hi if hi < 999 else '+'}"
    return "?"


def load_bars(con) -> list[Bar]:
    rows = con.execute("""SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
               arg_max(close,bar_ts) c, sum(volume) v FROM cap.bars
            WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= (
                SELECT min(ts_ms)/1000 FROM cap.ticks WHERE symbol='MNQ')
            GROUP BY 1 ORDER BY 1""").fetchall()
    return [Bar(int(m), float(c), float(h), float(lo), float(c), float(v or 0))
            for m, h, lo, c, v in rows]


def race(ticks, i0, side, entry, atr, tgt_pt, t0_ms):
    """First touch of the 1xATR stop vs tgt_pt, on real ticks. Returns (pnl, reason, exit_ms)."""
    stp = atr
    end = t0_ms + CAP_MIN * 60_000
    i = i0
    n = len(ticks)
    while i < n and ticks[i][0] <= end:
        px = ticks[i][1]
        fav = (px - entry) if side == "LONG" else (entry - px)
        if -fav >= stp:
            return (-stp * VPP - FEE_RT, "STOP", ticks[i][0])
        if fav >= tgt_pt:
            return (tgt_pt * VPP - FEE_RT, "TARGET", ticks[i][0])
        i += 1
    if i0 < n:
        j = min(i, n - 1)
        px = ticks[j][1]
        fav = (px - entry) if side == "LONG" else (entry - px)
        return (fav * VPP - FEE_RT, "CAP", ticks[j][0])
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", default="grind_long,abs_veto_long,abs_veto_short,capitulation_long,rgv_short")
    a = ap.parse_args()
    want = [g.strip() for g in a.gates.split(",") if g.strip()]

    con = duckdb.connect()
    con.execute(f"ATTACH '{GB}/data/capture.db' AS cap (TYPE sqlite, READ_ONLY)")
    bars = load_bars(con)
    ticks = con.execute("""SELECT ts_ms, price FROM cap.ticks WHERE symbol='MNQ'
                           ORDER BY ts_ms""").fetchall()
    ticks = [(int(t), float(p)) for t, p in ticks]
    print(f"tape: {len(bars):,} minute bars, {len(ticks):,} ticks "
          f"({len({t//86400000 for t,_ in ticks})} days)\n")

    specs = {s.tag: s for s in scaleout_slots()}
    tick_ts = [t for t, _ in ticks]
    import bisect

    rows_out = []
    for gname in want:
        for lot in ("A", "B"):
            tag = f"{gname}_{lot}"
            sp = specs.get(tag)
            if sp is None or sp.kind not in GATE_FN:
                continue
            fn = GATE_FN[sp.kind]
            busy_until = 0
            trades = []
            for i in range(30, len(bars)):
                w = bars[max(0, i - 60):i + 1]
                if w[-1].ts * 1000 < busy_until:
                    continue
                try:
                    f = compute_features(w)
                    # gate signatures differ — only gate_grind takes tape_net. Passing it blindly
                    # raises TypeError, which the bare except would have swallowed into "no trades".
                    kw = dict(sp.params)
                    if "tape_net" in _ACCEPTS[sp.kind]:
                        kw["tape_net"] = 0.0
                    e = fn(f, **kw)
                except TypeError as te:
                    print(f"  !! {tag}: gate call failed: {te}", file=sys.stderr)
                    break
                except Exception:
                    continue
                if not e or f.atr <= 0:
                    continue
                if sp.side and e.side != sp.side:
                    continue
                t0 = (w[-1].ts + 60) * 1000            # enter on the NEXT bar's first tick
                j = bisect.bisect_left(tick_ts, t0)
                if j >= len(ticks):
                    continue
                entry = ticks[j][1]
                # --- the two exit rules, raced on the SAME entry ---
                r_pt = sp.target_r * f.atr
                if lot == "A":
                    clip_pt = (sp.lo_target_usd or 40.0) / VPP
                else:
                    clip_pt = max((sp.lo_target_r or 1.75) * f.atr,
                                  (sp.lo_floor_usd or 60.0) / VPP)
                rr = race(ticks, j, e.side, entry, f.atr, r_pt, t0)
                rc = race(ticks, j, e.side, entry, f.atr, clip_pt, t0)
                if not rr or not rc:
                    continue
                trades.append((f.atr, rr, rc))
                busy_until = min(rr[2], rc[2])        # conservative: free the slot at the earlier exit
            if trades:
                rows_out.append((tag, sp, trades))

    print(f"{'slot':<20}{'R':>5}{'band':>8}{'n':>5}{'R-target$':>11}{'clip$':>10}{'clip-R':>9}  winner")
    grand = defaultdict(lambda: [0.0, 0.0, 0])
    for tag, sp, trades in rows_out:
        byb = defaultdict(list)
        for atr, rr, rc in trades:
            byb[band(atr)].append((rr, rc))
        for b, _ in [(f"{lo}-{hi if hi < 999 else '+'}", None) for lo, hi in BANDS]:
            if b not in byb:
                continue
            v = byb[b]
            pr = sum(x[0][0] for x in v)
            pc = sum(x[1][0] for x in v)
            w = "CLIP" if pc > pr else ("R-target" if pr > pc else "tie")
            print(f"{tag:<20}{sp.target_r:>5}{b:>8}{len(v):>5}{pr:>+11.0f}{pc:>+10.0f}"
                  f"{pc - pr:>+9.0f}  {w}")
            g = grand[b]
            g[0] += pr
            g[1] += pc
            g[2] += len(v)
    print("-" * 82)
    print(f"{'ALL SLOTS by band':<33}{'n':>5}{'R-target$':>11}{'clip$':>10}{'clip-R':>9}  winner")
    for lo, hi in BANDS:
        b = f"{lo}-{hi if hi < 999 else '+'}"
        if b not in grand:
            continue
        pr, pc, n = grand[b]
        print(f"{'  ATR '+b:<33}{n:>5}{pr:>+11.0f}{pc:>+10.0f}{pc - pr:>+9.0f}"
              f"  {'CLIP' if pc > pr else 'R-target'}")
    print("\nREADING: the clip should WIN below atr_split and LOSE above it. The band where 'winner'")
    print("flips is the empirical boundary — compare it to the live atr_split=22.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
