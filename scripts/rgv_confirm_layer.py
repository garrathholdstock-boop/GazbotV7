#!/usr/bin/env python3
"""Layer the LIVE 35s absorption-confirm on top of the per-side rgv BASE — does it STABILISE the
weak/unstable sides across BOTH weeks? (rgv_base_grid showed the raw base optima drift week to week
and the flow-confirm is regime-luck; the real question is whether the top-filter fixes that.)

For a small set of robust base configs per side (flow OFF, per the grid finding), run each on both
windows, BASE vs BASE+CONFIRM. Confirm = deciders.confirm_absorption on [signal, +CONFIRM_SECS]:
enter only if the faded move is being ABSORBED (heavy net-aggressor the wrong way for the fade that
failed to move price), entry repriced at the T+35 tick. Tick-honest exit (2R scalp + 1-ATR stop).

  PYTHONPATH=src python scripts/rgv_confirm_layer.py
"""
from __future__ import annotations

import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import (  # noqa: E402
    CONFIRM_SECS,
    Bar,
    Position,
    compute_features,
    confirm_absorption,
    exit_scalp,
    gate_reversal_grab,
)

CAP = "/home/alphabot/gazbot7/data/capture.db"
VPP, FEE, CAP_MIN = 2.0, 1.5, 60
FIXED = dict(fast_slope=True, fast_turn=True, atr_min=13.0, in_rth=True, flow_min=None)
# (side, ext_min, turn_atr) — robust tight-ext/no-flow bases + each week's own best
CONFIGS = [
    ("LONG", 2.5, 0.25), ("LONG", 3.0, 0.15), ("LONG", 2.0, 0.25),
    ("SHORT", 3.0, 0.15), ("SHORT", 2.5, 0.15), ("SHORT", 2.0, 0.25),
]
WINDOWS = [("LASTwk", "2026-07-15", "2026-07-20"), ("THISwk", "2026-07-20", "2026-08-01")]


def load_window(con, since, until):
    rows = con.execute(f"""
        WITH b AS (SELECT (bar_ts-bar_ts%60) m, arg_min(open,bar_ts) o, max(high) h, min(low) l,
                          arg_max(close,bar_ts) cl, SUM(volume) v FROM c.bars
                   WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>=epoch(TIMESTAMP '{since} 00:00:00')
                     AND bar_ts<epoch(TIMESTAMP '{until} 00:00:00') GROUP BY 1)
        SELECT m, o, h, l, cl, v, strftime(to_timestamp(m),'%m-%d') d FROM b ORDER BY m""").fetchall()
    flow = dict(con.execute(f"""
        SELECT (ts_ms//60000)*60 m,
               COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END),0)
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>=epoch(TIMESTAMP '{since} 00:00:00')*1000
          AND ts_ms<epoch(TIMESTAMP '{until} 00:00:00')*1000 GROUP BY 1""").fetchall())
    days: dict = {}
    for m, o, h, lo, cl, v, d in rows:
        days.setdefault(d, []).append((m, Bar(m, o, h, lo, cl, v)))
    feats: dict = {}
    for d, blist in days.items():
        bars = [b for _m, b in blist]
        for i in range(len(bars)):
            w = bars[max(0, i - 59):i + 1]
            if len(w) >= 6:
                feats[(d, i)] = (blist[i][0], compute_features(w), flow.get(blist[i][0], 0.0))
    return days, feats


def exitfrom(con, start_ms, side, atr):
    ticks = con.execute(f"""
        SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={start_ms}
          AND ts_ms<{start_ms + CAP_MIN * 60 * 1000} ORDER BY ts_ms""").fetchall()
    if len(ticks) < 3:
        return None
    entry_px = ticks[0][1]
    peak = 0.0
    exit_px = ticks[-1][1]
    for _ts, px in ticks[1:]:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        peak = max(peak, fav)
        if exit_scalp(Position(side, entry_px, atr, peak), px, target_r=2.0, stop_atr_mult=1.0):
            exit_px = px
            break
    return ((exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)) * VPP - FEE


def confirm_window(con, sig_ms):
    r = con.execute(f"""
        SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END),0),
               arg_min(price,ts_ms), arg_max(price,ts_ms), COUNT(*)
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={sig_ms} AND ts_ms<{sig_ms + int(CONFIRM_SECS) * 1000}""").fetchone()
    return r  # flow, p_first, p_last, n


def run(con, days, feats, side, ext, turn, confirm):
    excache: dict = {}
    pnls = []
    for d, blist in days.items():
        busy = -1
        for i in range(len(blist)):
            fv = feats.get((d, i))
            if fv is None:
                continue
            m, f, tn = fv
            if m < busy:
                continue
            e = gate_reversal_grab(f, side=side, ext_min=ext, turn_atr=turn, tape_net=tn, **FIXED)
            if e is None or e.side != side:
                continue
            sig_ms = (m + 60) * 1000
            if confirm:
                flow, p0, p1, nt = confirm_window(con, sig_ms)
                if nt < 5 or not confirm_absorption(side, flow, p1 - p0):
                    continue                       # not absorbing → the fade is a falling knife → skip
                start_ms = sig_ms + int(CONFIRM_SECS) * 1000   # enter at T+35
            else:
                start_ms = sig_ms
            key = (m, confirm)
            if key not in excache:
                excache[key] = exitfrom(con, start_ms, side, f.atr)
            pnl = excache[key]
            if pnl is None:
                continue
            pnls.append(pnl)
            busy = m + 60
    n = len(pnls)
    return n, sum(pnls), (100 * sum(1 for p in pnls if p > 0) / n if n else 0)


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    wd = {w[0]: load_window(con, w[1], w[2]) for w in WINDOWS}
    print(f"RGV BASE + {int(CONFIRM_SECS)}s ABSORPTION-CONFIRM — does the top-filter stabilise the base across weeks?")
    print("flow OFF (per grid finding) · exit 2R scalp+1-ATR stop tick-honest · confirm entry repriced at T+35\n")
    print(f"  {'config':<22}{'LASTwk base':>16}{'LASTwk +conf':>16}{'THISwk base':>16}{'THISwk +conf':>16}")
    for side, ext, turn in CONFIGS:
        cells = []
        for wname in ("LASTwk", "THISwk"):
            days, feats = wd[wname]
            for confirm in (False, True):
                n, net, w = run(con, days, feats, side, ext, turn, confirm)
                cells.append(f"${net:+.0f}/{n}t/{w:.0f}%")
        label = f"{side} ext{ext}/turn{turn}"
        print(f"  {label:<22}{cells[0]:>16}{cells[1]:>16}{cells[2]:>16}{cells[3]:>16}")
    con.close()
    print("\n(reading: does '+conf' turn red→green or shrink the week-to-week swing vs 'base'? "
          "esp. the weak LONG side. n shrinks a lot — confirm is selective. ⚠ 2 thin weeks, one regime-ish.)")


if __name__ == "__main__":
    main()
