#!/usr/bin/env python3
"""FULL 3-WEEK re-test of the two OPEN-NEWS greenfield gates + full filter suite.

The 1-week greenfield graves (grave_donchian.py / grave_newsfade.py) flagged these as the only
"positive" open-news detectors.  The 1-week kill-tests found:
  * Donchian breakout = cooldown-artifact + a B5 knife-edge buffer spike (curve-fit tell);
    neither side is independently +EV under side-isolation.
  * Impulse-fades = down-week short-beta (short green only in down-trends).

This script re-runs BOTH gates on the FULL 3-week stitched archive (07-05..07-24, 15 trading days,
~3x the news windows of the 1-week dig) using the shared loader A.load(), and re-applies the whole
filter battery plus the specific kill-tests each gate demands.  Honest, READ-ONLY, no live service.

  cd /home/alphabot/gazbot7 && .venv/bin/python scripts/full_opennews.py
"""
from __future__ import annotations

import sys
import datetime as dt

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import archive_data as A

FEE, VPP = 1.50, 2.0   # ★2026-08-02 COST FIX (operator): FEE was 5.0 — 3.3x the real commission.
# Venue truth: MNQ is $1.50 per ROUND TRIP ($0.75/side) — all 487 closed trades in data/gazbot7.db carry
# fees_usd = 1.50 exactly. The 5.0 is a legacy figure that folded unmodelled STOP slippage into the fee
# (see scripts/grave_newsfade.py, which documents the same fix on 2026-07-25 and keeps slippage a SEPARATE
# explicit term). A fixed per-trade fee is a REGRESSIVE tax on thin-edge/high-fire ideas: the same wrong
# constant made the NIPC replay read +$264 when the true figure was +$820, and flipped its verdict.
# ⚠ ANY CONCLUSION THIS SCRIPT PRODUCED BEFORE THIS DATE WAS COMPUTED AT $5/RT — re-run before citing it.
# Revert: FEE, VPP = 5.0, 2.0.
NEWS_LO, NEWS_HI = 13, 15                 # 13:00 <= hour_UTC < 15:00

# ── Gate 1 (Donchian) config A ──
G1_L, G1_B = 24, 5.0
G1_STOP, G1_ARM, G1_TRAIL = 40.0, 20.0, 20.0
G1_CAP_S, G1_COOL = 900, 900              # 15-min cap, 15-min cooldown

# ── Gate 2 (impulse fade) config ──
G2_L, G2_TH = 30, 30.0
G2_STOP, G2_TGT = 40.0, 40.0
G2_CAP_S, G2_COOL = 600, 120             # 10-min cap
G2_GRID = 1                              # per-second displacement, per task


# ───────────────────────────────── helpers ─────────────────────────────────
def hour_utc(sec):
    return (int(sec) % 86400) // 3600


def build_5s_bars(tts, tpx):
    """Aggregate the raw tick array into 5s OHLC bars (tick-derived, spans the whole archive).
    Returns (bt, bh, bl, bc): bucket-start-second, high, low, close arrays."""
    s = (tts // 1000).astype(np.int64)
    bucket = s - (s % 5)
    df = pd.DataFrame({"b": bucket, "px": tpx})
    g = df.groupby("b", sort=True)["px"].agg(["max", "min", "last"])
    return (g.index.values.astype(np.int64), g["max"].values.astype(float),
            g["min"].values.astype(float), g["last"].values.astype(float))


# ───────────────────────── Gate 1: Donchian trail replay ─────────────────────────
def replay_trail(tts, tpx, ei, d, stop, arm, trail, cap_s):
    """Tick-honest chandelier-trail exit. Stop checked BEFORE trail within a tick (conservative)."""
    entry_px, entry_ts = tpx[ei], int(tts[ei])
    peak, armed = 0.0, False
    j = ei + 1
    n = len(tts)
    while j < n:
        px, t = tpx[j], int(tts[j])
        fav = (px - entry_px) * d
        if -fav >= stop:
            return (-stop) * VPP - FEE, "stop", t
        if fav > peak:
            peak = fav
        if not armed and peak >= arm:
            armed = True
        if armed and (peak - fav) >= trail:
            return fav * VPP - FEE, "trail", t
        if t - entry_ts >= cap_s * 1000:
            return fav * VPP - FEE, "time", t
        j += 1
    return (tpx[-1] - entry_px) * d * VPP - FEE, "time", int(tts[-1])


def donchian_trades(D, b5, L=G1_L, B=G1_B, side=None,
                    stop=G1_STOP, arm=G1_ARM, trail=G1_TRAIL, cap_s=G1_CAP_S, cool=G1_COOL):
    """Donchian breakout on 5s bars, news window only. side=None both; +1/-1 = standalone one-side gate."""
    bt, bh, bl, bc = b5
    tts, tpx = D.tts, D.tpx
    trades = []
    busy_until_ms = -1
    n = len(bt)
    for i in range(L, n):
        t0 = int(bt[i])
        if not (NEWS_LO <= hour_utc(t0) < NEWS_HI):
            continue
        entry_ms = (t0 + 5) * 1000                       # first tick after 5s bar close
        if entry_ms <= busy_until_ms:
            continue
        hiL = bh[i - L:i].max()                           # prior L bars, excl current
        loL = bl[i - L:i].min()
        cl = bc[i]
        d = 0.0
        if cl > hiL + B:
            d = 1.0
        elif cl < loL - B:
            d = -1.0
        if d == 0.0:
            continue
        if side is not None and d != side:
            continue
        ei = int(np.searchsorted(tts, entry_ms, "left"))
        if ei >= len(tts):
            break
        pnl, reason, exit_ts = replay_trail(tts, tpx, ei, d, stop, arm, trail, cap_s)
        ts = int(tts[ei])
        trades.append({"d": d, "pnl": pnl, "reason": reason, "ts": ts, "exit_ts": exit_ts,
                       "er": D.er_for(ts), "atr": D.atr_for(ts), "net30": D.net30_for(ts)})
        busy_until_ms = exit_ts + cool * 1000
    return trades


# ───────────────────────── Gate 2: impulse-fade replay ─────────────────────────
def fade_trades(D, L=G2_L, TH=G2_TH, stop=G2_STOP, tgt=G2_TGT,
                cap_s=G2_CAP_S, cool=G2_COOL, grid=G2_GRID):
    """Fade the trailing L-second displacement in the news window.  Fixed STOP/TGT, tick-honest."""
    secs, price, tts, tpx = D.secs, D.price, D.tts, D.tpx
    s0 = int(secs[0])
    trades = []
    busy_until = -1
    n = len(secs)
    for i in range(L, n, grid):
        s = int(secs[i])
        if s < busy_until:
            continue
        if not (NEWS_LO <= hour_utc(s) < NEWS_HI):
            continue
        Ddisp = price[i] - price[i - L]
        if abs(Ddisp) < TH:
            continue
        d = -1.0 if Ddisp > 0 else 1.0                    # FADE: up impulse -> SHORT, down -> LONG
        ei = int(np.searchsorted(tts, (s + 1) * 1000, "left"))
        if ei >= len(tts):
            break
        ep, et = tpx[ei], int(tts[ei])
        exit_px, exit_t, reason = None, None, None
        j = ei + 1
        while j < len(tts):
            px, t = tpx[j], int(tts[j])
            fav = (px - ep) * d
            if -fav >= stop:
                exit_px, exit_t, reason = ep - d * stop, t, "stop"
                break
            if fav >= tgt:
                exit_px, exit_t, reason = ep + d * tgt, t, "tgt"
                break
            if t - et >= cap_s * 1000:
                exit_px, exit_t, reason = px, t, "time"
                break
            j += 1
        if exit_px is None:
            exit_px, exit_t, reason = tpx[-1], int(tts[-1]), "time"
        pnl = (exit_px - ep) * d * VPP - FEE
        trades.append({"ts": et, "d": d, "pnl": pnl, "reason": reason,
                       "er": D.er_for(et), "atr": D.atr_for(et), "net30": D.net30_for(et)})
        busy_until = (exit_t // 1000) + cool
    return trades


# ───────────────────────────────── reporting ─────────────────────────────────
def st(rows):
    n = len(rows)
    net = sum(r["pnl"] for r in rows)
    w = 100 * sum(1 for r in rows if r["pnl"] > 0) / n if n else 0
    return n, net, w


def per_day(trades):
    days = {}
    for t in trades:
        d = dt.datetime.fromtimestamp(t["ts"] / 1000, dt.UTC).strftime("%m-%d")
        days[d] = days.get(d, 0.0) + t["pnl"]
    return days


def raw_line(label, trades, report):
    n, net, w = st(trades)
    rc = {}
    for t in trades:
        rc[t["reason"]] = rc.get(t["reason"], 0) + 1
    dp = per_day(trades)
    lose = sum(1 for d in dp if dp[d] < 0)
    print(f"── {label}")
    print(f"   RAW: {n}tr · net ${net:+.0f} · ${net/n if n else 0:+.1f}/tr · {w:.0f}%w · "
          f"exits {rc} · losing days {lose}/{len(dp)}")
    print(f"   1wk report was: {report}")
    print("   per-day: " + "  ".join(f"{d} ${dp[d]:+.0f}" for d in sorted(dp)))


def side_isolation(D, b5):
    print("\n   SIDE-ISOLATION (each side re-run as its OWN standalone gate, not a partition):")
    for lbl, sd in [("long-only ", 1.0), ("short-only", -1.0)]:
        g = donchian_trades(D, b5, side=sd)
        n, net, w = st(g)
        dp = per_day(g)
        lose = sum(1 for d in dp if dp[d] < 0)
        print(f"       {lbl}: {n}tr · ${net:+.0f} · ${net/n if n else 0:+.1f}/tr · {w:.0f}%w · lose-days {lose}/{len(dp)}")
    print("   (1wk kill: long-only -$32 / short-only +$36 = neither independently +EV)")


def buffer_razor(D, b5):
    print("\n   BUFFER RAZOR at L24/STOP40/TRAIL20/ARM20 (does the B5 spike reproduce or was it 1wk-only?):")
    print(f"       {'B':>4}{'tr':>5}{'net$':>10}{'$/tr':>9}{'win%':>6}")
    for Bb in [0, 2, 3, 5, 7, 10]:
        g = donchian_trades(D, b5, B=float(Bb))
        n, net, w = st(g)
        print(f"       {Bb:>4}{n:>5}${net:>+9.0f}${net/n if n else 0:>+8.1f}{w:>5.0f}%")
    print("   (1wk: B0 +$22 · B2 -$25 · B3 -$278 · B5 +$570 · B7 +$305 · B10 -$181 = knife-edge)")


def beta_diag(trades):
    print("\n   BETA-vs-EDGE (side × concurrent 30-min trend dir via net30 sign):")
    core = [t for t in trades if t.get("net30") is not None]

    def q(rows):
        n, net, w = st(rows)
        return f"{n:>2}tr ${net:+6.0f} {w:>3.0f}%w"
    for side, dv in [("LONG ", 1.0), ("SHORT", -1.0)]:
        g = [t for t in core if t["d"] == dv]
        up = [t for t in g if t["net30"] > 0]
        dn = [t for t in g if t["net30"] <= 0]
        print(f"       {side}:  UP-trend {q(up)}   |   DOWN-trend {q(dn)}")
    print("   (real edge = winning side wins in BOTH trend dirs; beta = short green only in DOWN-trend)")


def hold_at_n_fade(D):
    print("\n   HOLD-at-n (lower TH to grow n; does a green side hold or decay to ~coin-flip?):")
    print("       TH     n    net$   win%  |  LONG net$  win% (n)  |  SHORT net$  win% (n)")
    for th in [50, 40, 30, 25, 20, 15]:
        g = fade_trades(D, TH=float(th))
        n, net, w = st(g)
        gl = [t for t in g if t["d"] > 0]
        gs = [t for t in g if t["d"] < 0]
        ln, lnet, lw = st(gl)
        sn, snet, sw = st(gs)
        mark = "  <- base" if th == G2_TH else ""
        print(f"       {th:>3}  {n:>4} {net:>+7.0f} {w:>4.0f}%  | {lnet:>+7.0f} {lw:>4.0f}% ({ln:>3}) "
              f"| {snet:>+7.0f} {sw:>4.0f}% ({sn:>3}){mark}")


# ───────────────────────────────── main ─────────────────────────────────
def main():
    print("=" * 92)
    print("FULL 3-WEEK OPEN-NEWS RE-TEST — Donchian breakout + impulse fade + full battery")
    print("=" * 92)
    print("Loading stitched archive (V5 ticks.db UNION V7 capture.db, READ-ONLY) ...")
    D = A.load()
    print(f"loaded: {D.n_ticks:,} ticks · span {D.span[0]} -> {D.span[1]} · cutover {D.cutover}")
    ndays = len({dt.datetime.fromtimestamp(int(m), dt.UTC).strftime('%m-%d')
                 for m in D.mins if NEWS_LO <= hour_utc(m) < NEWS_HI})
    print(f"news-window trading days in archive: {ndays}   (1wk dig had ~5)")

    print("\nBuilding 5s bars from the tick array (spans whole archive) ...")
    b5 = build_5s_bars(D.tts, D.tpx)
    print(f"5s bars: {len(b5[0]):,}")

    # ══════════════════════════ GATE 1 — Donchian ══════════════════════════
    print("\n" + "#" * 92)
    print("# GATE 1 — News-Window Range Breakout (Donchian)  L24/B5/STOP40/TRAIL20/ARM20 · 5s bars")
    print("#" * 92)
    g1 = donchian_trades(D, b5)
    raw_line("Donchian config A (both sides, single-position + 15min cooldown)", g1,
             "27tr / +$570 / 85%w / 0 losing days")
    A.battery(g1, "donchian-3wk")
    side_isolation(D, b5)
    buffer_razor(D, b5)

    # ══════════════════════════ GATE 2 — Impulse Fade ══════════════════════════
    print("\n" + "#" * 92)
    print("# GATE 2 — News-Window Impulse Fade  L30/TH30/STOP40/TGT40 · per-second displacement")
    print("#" * 92)
    g2 = fade_trades(D)
    raw_line("Impulse fade base (both sides)", g2,
             "top15 L30/TH30: 54tr / +$791 / 63%w (LONG +$490 / SHORT +$301)")
    A.battery(g2, "impulse-fade-3wk")
    beta_diag(g2)
    hold_at_n_fade(D)

    print("\n" + "=" * 92)
    print("(FULL 3-week archive, tick-honest $5/RT $2/pt, READ-ONLY, no live service. Verdict in stdout.)")
    print("=" * 92)


if __name__ == "__main__":
    main()
