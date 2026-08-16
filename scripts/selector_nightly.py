#!/usr/bin/env python3
"""SELECTOR NIGHTLY — post-session review of the regime-3-exit selector (operator 2026-07-28).

For each realised trade on a Paris day, reprice tick-honest under ALL exit modes the selector can
choose (WIDE=lock / TIGHT=k1.5 / MID=k2.0, + SCALP as the pre-selector reference), recompute the mode
the selector actually PICKED (regime-at-entry, deterministic — no drift), and answer:
  · Did the selector pick the BEST-of-3 exit?  (% optimal)
  · REGRET — $ left on the table vs perfect-hindsight mode-picking (best − chosen)
  · Did ADAPTING beat a fixed single exit (always-scalp / always-wide)?  (the value of the selector)
  · Any SYSTEMATIC wrong pick (e.g. chop trades would've done better on scalp than tight this day)

READ-ONLY. Writes data/selector_nightly/<date>.json for the Friday rollup. ⚠ the non-chosen modes are
tick-honest ESTIMATES (only the chosen one actually ran); native 1-ATR stop owns the loss on all.

  PYTHONPATH=src .venv/bin/python scripts/selector_nightly.py [--date YYYY-MM-DD]   (default: just-closed Paris day)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import defaultdict

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import Position, exit_chandelier, exit_chandelier_lock, exit_scalp  # noqa: E402
from gazbot7.slot_strategy import SlotStrategy  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
OUTDIR = "/home/alphabot/gazbot7/data/selector_nightly"
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 90 * 60
MODES = ("wide", "tight", "mid", "scalp")


def mode_exit(mode, pos, px):
    if mode == "wide":
        return exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5) \
            or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0)
    if mode == "scalp":
        return exit_scalp(pos, px, target_r=2.0, stop_atr_mult=1.0)
    k = 1.5 if mode == "tight" else 2.0
    return exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75) \
        or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0)


def reprice_modes(side, entry_px, atr, ticks):
    peak = 0.0
    done = {}
    for _ts, px in ticks:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak:
            peak = fav
        pos = Position(side, entry_px, atr, peak)
        for m in MODES:
            if m not in done and mode_exit(m, pos, px):
                done[m] = px
        if len(done) == len(MODES):
            break
    last = ticks[-1][1]
    out = {}
    for m in MODES:
        xp = done.get(m, last)
        pts = (xp - entry_px) if side == "LONG" else (entry_px - xp)
        out[m] = pts * VPP - FEE
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=(dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
                                       - dt.timedelta(hours=3)).strftime("%Y-%m-%d"))
    date = ap.parse_args().date
    d = dt.date.fromisoformat(date)
    ds = (dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone(dt.timedelta(hours=2)))
          - dt.timedelta(hours=2)).timestamp()

    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    # ★★2026-08-16 SATURDAY #3 — QUARANTINED TRADES MUST NOT BE SCORED.
    # `data_quality` flags rows the desk knows are not real — the 08-13 day-rider bug alone booked
    # $1,551 of profit from trades that never happened. This query had no filter, so every selector
    # verdict since the flag existed was computed over a book containing phantom fills.
    # ⚠ THIS IS THE SECOND TIME FOR THIS FIELD. `pnl.py` filtered it and six `web.py` queries did
    # not, putting a correct header above a fabricated blotter. When you add a flag, AUDIT EVERY
    # CONSUMER — a right number beside a wrong one is worse than either alone.
    trades = con.execute(f"""SELECT gate, side, entry_price, pnl_usd, exit_reason,
        epoch(opened_at::TIMESTAMPTZ) t0 FROM g.trades
        WHERE symbol='MNQ' AND data_quality IS NULL
        AND epoch(opened_at::TIMESTAMPTZ)>={ds} AND epoch(opened_at::TIMESTAMPTZ)<{ds+86400}
        AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY opened_at""").fetchall()

    rows = []
    mode_used = defaultdict(int)
    optimal = 0
    regret = 0.0
    chosen_tot = best_tot = scalp_tot = wide_tot = 0.0
    for (gate, side, ep, pnl, rsn, t0) in trades:
        barrows = con.execute(f"""SELECT arg_max(close,bar_ts) cl, max(high) hi, min(low) lo FROM c.bars
            WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={t0-1800} AND bar_ts<={t0}
            GROUP BY (bar_ts-bar_ts%60) ORDER BY (bar_ts-bar_ts%60)""").fetchall()
        atr = sum(r[1]-r[2] for r in barrows)/len(barrows) if len(barrows) >= 6 else 0.0
        closes = [r[0] for r in barrows]
        if atr <= 0 or len(closes) < 6:
            continue

        class _B:
            def __init__(s, c):
                s.close = c
        chosen = SlotStrategy._regime_mode(side, [_B(c) for c in closes])
        ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={int(t0*1000)}
            AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        if len(ticks) < 2:
            continue
        m = reprice_modes(side, ep, atr, ticks[1:])
        best = max(MODES, key=lambda x: m[x])
        mode_used[chosen] += 1
        optimal += (chosen == best) or (abs(m[chosen] - m[best]) < 1.0)
        regret += m[best] - m[chosen]
        chosen_tot += m[chosen]
        best_tot += m[best]
        scalp_tot += m["scalp"]
        wide_tot += m["wide"]
        rows.append(dict(gate=gate, side=side, chosen=chosen, chosen_pnl=round(m[chosen], 1),
                         best=best, best_pnl=round(m[best], 1), regret=round(m[best]-m[chosen], 1)))
    con.close()

    n = len(rows)
    print(f"SELECTOR NIGHTLY — {date} (Paris)   ·   {n} trades repriced under {MODES}\n")
    print(f"  mode picked: {dict(mode_used)}")
    print(f"  optimal picks (chosen==best, ±$1): {optimal}/{n}"
          + (f" ({100*optimal//n}%)" if n else ""))
    print(f"  REGRET (best − chosen, $ left on the table): ${regret:+.0f}")
    print("\n  value of adapting (repriced totals):")
    print(f"    selector (chosen modes)   ${chosen_tot:+.0f}")
    print(f"    perfect hindsight (best)  ${best_tot:+.0f}")
    print(f"    fixed always-SCALP        ${scalp_tot:+.0f}   (selector − scalp = ${chosen_tot-scalp_tot:+.0f})")
    print(f"    fixed always-WIDE         ${wide_tot:+.0f}   (selector − wide  = ${chosen_tot-wide_tot:+.0f})")
    if rows:
        print("\n  worst picks (biggest regret):")
        for r in sorted(rows, key=lambda x: -x["regret"])[:5]:
            if r["regret"] > 1:
                print(f"    {r['gate']:16} {r['side']:5} chose {r['chosen']:5} ${r['chosen_pnl']:+6.1f}  "
                      f"best {r['best']:5} ${r['best_pnl']:+6.1f}  regret ${r['regret']:+.1f}")

    out = dict(date=date, n=n, mode_used=dict(mode_used), optimal=optimal, regret=round(regret),
               selector_pnl=round(chosen_tot), best_pnl=round(best_tot), scalp_pnl=round(scalp_tot),
               wide_pnl=round(wide_tot), trades=rows)
    os.makedirs(OUTDIR, exist_ok=True)
    with open(f"{OUTDIR}/{date}.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUTDIR}/{date}.json")


if __name__ == "__main__":
    main()
