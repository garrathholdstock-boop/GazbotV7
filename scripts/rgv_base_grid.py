#!/usr/bin/env python3
"""Per-SIDE base-threshold grid for rgv (reversal_grab) — tune the BASE trigger, not the top-filters.

The operator's principle: long and short are different profiles, so the base entry thresholds
(ext_min = how far past VWAP counts as over-extended · turn_atr = how big a turn-back to require ·
flow_min = aggressor-flow confirm) must be swept INDEPENDENTLY per side, not mirrored. This runs the
REAL gate_reversal_grab over this week's tape, TICK-HONEST: entry on the 1-min signal bar (exactly how
the live gate fires, fast_slope+fast_turn+atr_min=13 like the live rgv), EXIT repriced on real trade
ticks (the reversion stack: 2R scalp + native 1-ATR stop, first touch). No ER/absorption filter — pure
base. capture.db bars(5s→1m)+ticks. DuckDB. VPP 2.0, fee 1.5. ⚠ ~1 week, one regime — a LEAD.

  PYTHONPATH=src python scripts/rgv_base_grid.py
"""
from __future__ import annotations

import argparse
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import (  # noqa: E402
    Bar,
    Position,
    compute_features,
    exit_scalp,
    gate_reversal_grab,
)

CAP = "/home/alphabot/gazbot7/data/capture.db"
VPP, FEE, CAP_MIN = 2.0, 1.5, 60
EXT = [1.5, 2.0, 2.5, 3.0]
TURN = [0.15, 0.25, 0.5]
FLOW = [None, 25, 50]
FIXED = dict(fast_slope=True, fast_turn=True, atr_min=13.0, in_rth=True)  # live rgv base config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-20")
    ap.add_argument("--until", default="2026-08-01")
    a = ap.parse_args()
    since, until = a.since, a.until
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    # 1-min bars (aggregate 5s), per calendar day so VWAP/ATR anchor to the session
    rows = con.execute(f"""
        WITH b AS (SELECT (bar_ts-bar_ts%60) m, arg_min(open,bar_ts) o, max(high) h, min(low) l,
                          arg_max(close,bar_ts) cl, SUM(volume) v
                   FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
                     AND bar_ts>=epoch(TIMESTAMP '{since} 00:00:00')
                     AND bar_ts<epoch(TIMESTAMP '{until} 00:00:00') GROUP BY 1)
        SELECT m, o, h, l, cl, v, strftime(to_timestamp(m),'%m-%d') d FROM b ORDER BY m""").fetchall()
    # per-day directional lean (close-open, in points) so we can read the regime of the window
    lean = con.execute(f"""
        WITH b AS (SELECT strftime(to_timestamp(bar_ts),'%m-%d') d, bar_ts, close FROM c.bars
                   WHERE symbol='MNQ' AND timeframe='5s'
                     AND bar_ts>=epoch(TIMESTAMP '{since} 00:00:00')
                     AND bar_ts<epoch(TIMESTAMP '{until} 00:00:00'))
        SELECT d, ROUND(arg_max(close,bar_ts)-arg_min(close,bar_ts),0) net_pts FROM b GROUP BY 1 ORDER BY 1""").fetchall()
    # per-minute net aggressor flow (the tape_net the flow_min confirm reads)
    flowrows = con.execute(f"""
        SELECT (ts_ms//60000)*60 m,
               COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END),0) net
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>=epoch(TIMESTAMP '{since} 00:00:00')*1000
          AND ts_ms<epoch(TIMESTAMP '{until} 00:00:00')*1000
        GROUP BY 1""").fetchall()
    tape_net = {m: n for m, n in flowrows}

    days: dict = {}
    for m, o, h, lo, cl, v, d in rows:
        days.setdefault(d, []).append((m, Bar(m, o, h, lo, cl, v)))

    # exit is param-INDEPENDENT (depends only on entry bar+side) → cache it. entry = first tick after
    # the signal bar closes; replay the reversion exit (2R scalp + 1-ATR stop) on real ticks.
    exit_cache: dict = {}

    def get_exit(m, side, atr):
        key = (m, side)
        if key in exit_cache:
            return exit_cache[key]
        ticks = con.execute(f"""
            SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
              AND ts_ms>={(m+60)*1000} AND ts_ms<{(m+60+CAP_MIN*60)*1000} ORDER BY ts_ms""").fetchall()
        if len(ticks) < 3:
            exit_cache[key] = None
            return None
        entry_px = ticks[0][1]
        peak = 0.0
        exit_px = ticks[-1][1]
        for ts, px in ticks[1:]:
            fav = (px - entry_px) if side == "LONG" else (entry_px - px)
            peak = max(peak, fav)
            if exit_scalp(Position(side, entry_px, atr, peak), px, target_r=2.0, stop_atr_mult=1.0):
                exit_px = px
                break
        pnl = ((exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)) * VPP - FEE
        exit_cache[key] = (entry_px, pnl)
        return exit_cache[key]

    # precompute features per bar (rolling 60 within the day) + fire-check helper
    feats: dict = {}   # (day, i) -> (m, Features, tape_net)
    for d, blist in days.items():
        bars = [b for _m, b in blist]
        for i in range(len(bars)):
            w = bars[max(0, i - 59):i + 1]
            if len(w) < 6:
                continue
            m = blist[i][0]
            feats[(d, i)] = (m, compute_features(w), tape_net.get(m - m % 60, 0.0))

    def run(side, ext_min, turn_atr, flow_min):
        pnls = []
        for d, blist in days.items():
            busy_until = -1
            for i in range(len(blist)):
                fv = feats.get((d, i))
                if fv is None:
                    continue
                m, f, tn = fv
                if m < busy_until:
                    continue
                e = gate_reversal_grab(f, side=side, ext_min=ext_min, turn_atr=turn_atr,
                                       flow_min=flow_min, tape_net=tn, **FIXED)
                if e is None or e.side != side:
                    continue
                ex = get_exit(m, side, f.atr)
                if ex is None:
                    continue
                _entry_px, pnl = ex
                pnls.append(pnl)
                busy_until = m + 60  # ≥1 bar; the tick exit governs real duration, this just bars re-entry same bar
        n = len(pnls)
        net = sum(pnls)
        return n, net, (net / n if n else 0), (100 * sum(1 for p in pnls if p > 0) / n if n else 0)

    print(f"RGV PER-SIDE BASE GRID — real gate_reversal_grab, tick-honest, {since}..{until}")
    print("fixed: fast_slope+fast_turn+atr_min13 (live base) · exit=2R scalp+1-ATR stop on ticks · no ER/abs filter")
    print("window directional lean (end-start close, pts): " + " ".join(f"{d}:{p:+.0f}" for d, p in lean) + "\n")
    for side in ("LONG", "SHORT"):
        print(f"════ rgv {side} ════")
        print(f"  {'ext_min':>7} {'turn':>5} {'flow':>5} {'trades':>7} {'net$':>7} {'$/tr':>7} {'win%':>5}")
        best = None
        for ext_min in EXT:
            for turn_atr in TURN:
                for flow_min in FLOW:
                    n, net, ev, w = run(side, ext_min, turn_atr, flow_min)
                    if n == 0:
                        continue
                    fl = "none" if flow_min is None else str(flow_min)
                    mark = ""
                    if n >= 4 and (best is None or net > best[1]):
                        best = (f"ext{ext_min}/turn{turn_atr}/flow{fl}", net, ev, n, w)
                        mark = " ★"
                    print(f"  {ext_min:>7} {turn_atr:>5} {fl:>5} {n:>7} ${net:>+6.0f} ${ev:>+6.1f} {w:>4.0f}%{mark}")
        if best:
            print(f"  → best (n≥4): {best[0]}  ${best[1]:+.0f} · ${best[2]:+.1f}/tr · {best[3]}tr · {best[4]:.0f}%w")
        print()
    con.close()
    print("(★ = running best-net at that point, n≥4. base only — top-filters (ER/absorption) tune AFTER.\n"
          " ⚠ shadow-free reconstruction on live tape, ~1wk/one regime — a LEAD to carry into Saturday.)")


if __name__ == "__main__":
    main()
