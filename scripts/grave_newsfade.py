#!/usr/bin/env python3
"""News-Window Impulse Fade (NWIF) — greenfield GRAVE reconstruction + FULL filter battery.

Reconstructs the two OPEN-NEWS graves (gf_top15 / gf_top25) tick-honest on GAZBOT V7 and runs the
whole battery on each so the "positive" can be dissected: RAW+validation, LONG/SHORT split, ER/ATR
bands, strip-best, beta-vs-edge (side x concurrent 30-min trend), hold-at-n.

Signal (both gates, "fade" family): active ONLY 13:00<=hour_UTC<15:00. On a 5s grid, when flat and
past cooldown, D = price(t)-price(t-L). If |D|>=TH -> FADE: D>0 (up impulse) -> SHORT, D<0 -> LONG.
Entry = first tick after the trigger second. Hard STOP pts; exit either (a) fixed TGT pts or
(b) "ride" = no target, hold reversion to CAP-sec time-cap. Tick-honest (stop checked before target
within a tick = conservative), $5/RT, MNQ $2/pt.

Machinery (loading + tick-honest exit + ER/ATR/net30-per-minute) copied from afc_er_sweep.py /
trap_reclaim_sweep.py. READ-ONLY DBs, no live service touched, 1 week in-sample.

  cd /home/alphabot/gazbot7 && .venv/bin/python scripts/grave_newsfade.py
"""
from __future__ import annotations

import datetime as dt

import duckdb
import numpy as np
import pandas as pd

import os
CAP_DB = "/home/alphabot/gazbot7/data/capture.db"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
# COST FIX (2026-07-25): real MNQ commission is $1.50/RT (live ledger, cost_waterfall.py), NOT $5.
# $5 partly stood in for unmodeled STOP slippage. All-in: FEE=1.5/RT commission (env GF_FEE) +
# explicit STOP-slippage STOP_SLIP $ on stop exits only (env GF_STOP_SLIP; 4pt=$8 realistic, $0 bound).
FEE = float(os.environ.get("GF_FEE", "1.5"))
VPP = 2.0
STOP_SLIP = float(os.environ.get("GF_STOP_SLIP", "0.0"))
GRID = 5           # evaluate the trigger every GRID seconds while flat
NEWS_LO, NEWS_HI = 13, 15   # 13:00 <= hour_UTC < 15:00


# ─────────────────────────────────────────── shared load ───────────────────────────────────────
def load():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP_DB}' AS c (TYPE sqlite, READ_ONLY)")
    lo = int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0])
    hi = int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])

    # per-second last price -> dense ffill'd series (for the displacement D)
    pdf = con.execute(f"""
        SELECT CAST(ts_ms/1000 AS BIGINT) s, arg_max(price, ts_ms) px
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000}
        GROUP BY s ORDER BY s""").df()
    s0, s1 = int(pdf.s.min()), int(pdf.s.max())
    price = np.full(s1 - s0 + 1, np.nan)
    price[(pdf.s.values - s0).astype(int)] = pdf.px.values
    price = pd.Series(price).ffill().bfill().values
    secs = np.arange(s0, s1 + 1)

    # raw tick path for tick-honest entry/exit
    tk = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
        AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts, tpx = tk.ts_ms.values.astype(np.int64), tk.price.values.astype(float)

    # 1-min OHLC -> Kaufman 30-bar ER + 14-bar ATR + signed 30-min move (net30 = trend dir)
    bdf = con.execute(f"""
        WITH b AS (SELECT (bar_ts-bar_ts%60) m, max(high) h, min(low) l, arg_max(close,bar_ts) cl
                   FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
                   AND bar_ts>={lo-2400} AND bar_ts<{hi} GROUP BY 1)
        SELECT m, h, l, cl FROM b ORDER BY m""").df()
    con.close()
    mins = bdf.m.values.astype(np.int64)
    cls, hh, ll = bdf.cl.values.astype(float), bdf.h.values.astype(float), bdf.l.values.astype(float)
    idx = {int(m): i for i, m in enumerate(mins)}
    tr = np.zeros(len(mins))
    for i in range(1, len(mins)):
        tr[i] = max(hh[i] - ll[i], abs(hh[i] - cls[i - 1]), abs(ll[i] - cls[i - 1]))

    def er_atr_net(ts_ms):
        i = idx.get(int((ts_ms // 1000) - ((ts_ms // 1000) % 60)))
        if i is None or i < 30:
            return None, None, None
        seg = cls[i - 30:i + 1]
        tot = np.abs(np.diff(seg)).sum()
        er = abs(seg[-1] - seg[0]) / tot if tot > 0 else 0.0
        atr = float(tr[i - 13:i + 1].mean()) if i >= 14 else None
        net30 = float(seg[-1] - seg[0])
        return er, atr, net30

    return secs, s0, price, tts, tpx, er_atr_net


# ─────────────────────────────────────────── engine ────────────────────────────────────────────
def hour_utc(sec):
    return (sec % 86400) // 3600


def replay(secs, s0, price, tts, tpx, er_atr_net, L, TH, STOP, TGT, ride, CAP_S, COOL):
    """Fade trailing displacement D in the news window. Returns list of trades."""
    trades, busy_until = [], -1
    n = len(secs)
    for i in range(L, n, GRID):
        s = secs[i]
        if s < busy_until:
            continue
        if not (NEWS_LO <= hour_utc(s) < NEWS_HI):
            continue
        D = price[i] - price[i - L]
        if abs(D) < TH:
            continue
        d = -1.0 if D > 0 else 1.0                     # FADE: up impulse -> SHORT, down -> LONG
        ei = int(np.searchsorted(tts, (s + 1) * 1000, "left"))
        if ei >= len(tts):
            break
        ep, et = tpx[ei], int(tts[ei])
        exit_px, exit_t, reason = None, None, None
        j = ei + 1
        while j < len(tts):
            px, t = tpx[j], int(tts[j])
            fav = (px - ep) * d
            if -fav >= STOP:                           # stop first (conservative)
                exit_px, exit_t, reason = ep - d * STOP, t, "stop"
                break
            if (not ride) and fav >= TGT:
                exit_px, exit_t, reason = ep + d * TGT, t, "tgt"
                break
            if t - et >= CAP_S * 1000:
                exit_px, exit_t, reason = px, t, "time"
                break
            j += 1
        if exit_px is None:
            exit_px, exit_t, reason = tpx[-1], int(tts[-1]), "time"
        pnl = (exit_px - ep) * d * VPP - FEE - (STOP_SLIP if reason == "stop" else 0.0)
        er, atr, net30 = er_atr_net(et)
        trades.append({"ts": et, "d": d, "pnl": pnl, "reason": reason,
                       "er": er, "atr": atr, "net30": net30})
        # single slot: block re-arm until exit second + cooldown
        busy_until = (exit_t // 1000) + COOL
    return trades


# ─────────────────────────────────────────── battery ───────────────────────────────────────────
def stat(rows):
    n = len(rows)
    net = sum(r["pnl"] for r in rows)
    w = 100 * sum(1 for r in rows if r["pnl"] > 0) / n if n else 0
    return n, net, w


def battery(name, spec, rep, LD, secs, s0, price, tts, tpx, er_atr_net):
    L, TH, STOP, TGT, ride, CAP_S, COOL = spec
    tr = replay(secs, s0, price, tts, tpx, er_atr_net, L, TH, STOP, TGT, ride, CAP_S, COOL)
    ex = "RIDE(no tgt)" if ride else f"TGT{TGT:.0f}"
    print("=" * 96)
    print(f"{name}   L{L}/TH{TH:.0f}/STOP{STOP:.0f}/{ex}/cap{CAP_S}s/cool{COOL}s  (news 13-15 UTC, grid {GRID}s)")
    print("=" * 96)

    # 1. RAW + validation
    n, net, w = stat(tr)
    rc = {}
    for t in tr:
        rc[t["reason"]] = rc.get(t["reason"], 0) + 1
    print(f"\n[1] RAW  {n}tr · net ${net:+.0f} · ${net/n if n else 0:+.1f}/tr · win {w:.0f}% · exits {rc}")
    print(f"    REPORT: {rep}")
    print(f"    -> {'MATCH-ish' if abs(n-LD)<=LD*0.5 else 'DIVERGES on n'} (recon n={n} vs reported n~{LD})")

    # 2. LONG vs SHORT split
    L_ = [t for t in tr if t["d"] > 0]
    S_ = [t for t in tr if t["d"] < 0]
    print("\n[2] LONG vs SHORT split (report: reduces to short-only down-week drift?)")
    for lbl, g in [("LONG (fade down-impulse = buy dip)", L_), ("SHORT (fade up-impulse)", S_)]:
        gn, gnet, gw = stat(g)
        print(f"    {lbl:<38} {gn:>3}tr · ${gnet:+6.0f} · {gw:.0f}%w")

    # 3. ER bands + ATR bands
    print("\n[3] ER bands (0.1)          tr    net$   $/tr  win%")
    have = [t for t in tr if t["er"] is not None]
    for a, b in [(0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, 1.01)]:
        g = [t for t in have if a <= t["er"] < b]
        if not g:
            continue
        gn, gnet, gw = stat(g)
        print(f"    {a:.1f}-{b:.1f}              {gn:>4} {gnet:>+7.0f} {gnet/gn:>+6.1f} {gw:>4.0f}%")
    print("    ATR bands (pt)          tr    net$   $/tr  win%")
    ha = [t for t in tr if t["atr"] is not None]
    for a, b in [(0, 12), (12, 16), (16, 20), (20, 25), (25, 99)]:
        g = [t for t in ha if a <= t["atr"] < b]
        if not g:
            continue
        gn, gnet, gw = stat(g)
        print(f"    {a}-{b}{'':<14} {gn:>4} {gnet:>+7.0f} {gnet/gn:>+6.1f} {gw:>4.0f}%")

    # 4. strip-best
    print("\n[4] strip-best (fluke test) — report says top15 strip-3 -> +$278 (55% is 3 trades)")
    srt = sorted(t["pnl"] for t in tr)
    for k in [0, 1, 2, 3, 5]:
        kept = srt[:len(srt) - k] if k else srt
        tot = sum(kept)
        share = 100 * (net - tot) / net if net and k else 0
        print(f"    strip {k}: {len(kept)}tr · ${tot:+.0f}"
              + (f"  ({share:.0f}% of net in {k})" if k else "")
              + ("  <- GONE" if tot < 0 else ""))

    # 5. beta-vs-edge: side x concurrent 30-min trend direction
    print("\n[5] BETA-vs-EDGE  side x concurrent 30-min trend dir (net30) — the smoking gun")
    core = [t for t in tr if t["net30"] is not None]

    def q(rows):
        gn, gnet, gw = stat(rows)
        return f"{gn:>2}tr ${gnet:+6.0f} {gw:>3.0f}%w"
    for side, dv in [("LONG ", 1.0), ("SHORT", -1.0)]:
        g = [t for t in core if t["d"] == dv]
        up = [t for t in g if t["net30"] > 0]
        dn = [t for t in g if t["net30"] <= 0]
        print(f"    {side}:  UP-trend {q(up)}   |   DOWN-trend {q(dn)}")
    print("    (SHORT green only in DOWN-trend + dead/red in UP-trend = down-week beta, not an edge.)")

    # 6. hold-at-n: lower TH to grow n, does any green side/band hold or decay to ~50%?
    print("\n[6] HOLD-at-n  (lower TH to grow n; does a green side hold or decay to ~50%?)")
    print("    TH    n    net$   win%  | LONG net$  win%  | SHORT net$  win%")
    for th in [50, 40, 30, 25, 20, 15, 10]:
        g = replay(secs, s0, price, tts, tpx, er_atr_net, L, th, STOP, TGT, ride, CAP_S, COOL)
        gn, gnet, gw = stat(g)
        gl = [t for t in g if t["d"] > 0]
        gs = [t for t in g if t["d"] < 0]
        ln, lnet, lw = stat(gl)
        sn, snet, sw = stat(gs)
        mark = " <-recon cell" if th == TH else ""
        print(f"    {th:>2}  {gn:>4} {gnet:>+7.0f} {gw:>4.0f}%  | {lnet:>+7.0f} {lw:>4.0f}% ({ln}) "
              f"| {snet:>+7.0f} {sw:>4.0f}% ({sn}){mark}")
    return tr


def main():
    print("Loading capture.db (READ-ONLY) ...")
    secs, s0, price, tts, tpx, er_atr_net = load()
    print(f"loaded: {len(tts):,} ticks · {len(secs):,} seconds · window {SINCE} -> {UNTIL} UTC\n")

    # GATE 1 — top15 leading cell: L30 / TH30 / STOP40 / TGT40 (fixed target)
    battery("GATE 1  NWIF top15 (fixed-target fade)",
            (30, 30.0, 40.0, 40.0, False, 600, 120),
            "n=54 · net +$791 · win 63% · LONG $490 / SHORT $301 (both green)", 54,
            secs, s0, price, tts, tpx, er_atr_net)

    print("\n")

    # GATE 2 — top25 best-looking positive: RIDE L60 / TH40 / STOP50 (no target, ride to cap)
    battery("GATE 2  NWIF top25 (RIDE — best-looking +$1534)",
            (60, 40.0, 50.0, 0.0, True, 600, 120),
            "RIDE L60/TH40/s50 net +$1534 · win 64% · n25 · long -$156 / short +$338", 25,
            secs, s0, price, tts, tpx, er_atr_net)

    # GATE 2 alt — the symmetric fixed-target candidate B (L60/TH40/s30/t60) for cross-check
    print("\n")
    battery("GATE 2b NWIF top25 (fixed candidate B)",
            (60, 40.0, 30.0, 60.0, False, 600, 120),
            "B L60/TH40/s30/t60 net +$901 · win 50% · n40 · long +$291 / short +$202", 40,
            secs, s0, price, tts, tpx, er_atr_net)

    print("\n" + "=" * 96)
    print("(1 week in-sample, tick-honest $5/RT, read-only DBs, no live service touched.)")


if __name__ == "__main__":
    main()
