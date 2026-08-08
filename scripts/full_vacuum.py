"""FULL 3-week (07-05..07-24) re-test of the THREE VACUUM greenfield gates + full filter suite.
On 1 week all three were graves (curve-fit / beta / small-n). 3x data is the honest re-test.

Read-only. No live service. Do NOT commit.

  /home/alphabot/gazbot7/.venv/bin/python scripts/full_vacuum.py

Gates (evaluate at each 1-min bar close = secs s0+59, s0+119, ...; entry = first tick after;
tick-honest STOP/TGT exits; $5/RT $2/pt; single position + cooldown):
 1. Absorption Fade      F150/P8/STOP25/TGT90  cap 15m cool 15m
 2. Trap-Reclaim scalp   F300/STOP40/TGT30/RECLAIM6  cap 15m cool 60s  (+ counter-trend LONG win%)
 3. Trapped-Flow Reversal W60/F200/H6/STOP25/TGT45  cap 10m cool 180s (load + break trigger)
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import numpy as np
import archive_data as A

import os
# COST FIX (2026-07-25): real MNQ commission is $1.50/RT (live ledger, cost_waterfall.py), NOT $5.
# $5 partly stood in for unmodeled STOP slippage. All-in: FEE=1.5/RT commission (env GF_FEE) +
# explicit STOP-slippage STOP_SLIP $ on stop exits only (env GF_STOP_SLIP; 4pt=$8 realistic, $0 bound).
FEE = float(os.environ.get("GF_FEE", "1.5"))
VPP = 2.0
STOP_SLIP = float(os.environ.get("GF_STOP_SLIP", "0.0"))


def scalp(D, ei, d, STOP, TGT, CAP_S):
    """Tick-honest exit from entry tick index ei, direction d. STOP/TGT in points, CAP_S seconds.
    Returns (pnl, reason). STOP_SLIP charged only on stop exits."""
    tts, tpx = D.tts, D.tpx
    ep, et = tpx[ei], int(tts[ei])
    j = ei + 1
    n = len(tts)
    while j < n:
        px, t = tpx[j], int(tts[j])
        fav = (px - ep) * d
        if -fav >= STOP:
            return -STOP * VPP - FEE - STOP_SLIP, "stop"
        if fav >= TGT:
            return TGT * VPP - FEE, "tgt"
        if t - et >= CAP_S * 1000:
            return fav * VPP - FEE, "cap"
        j += 1
    return (tpx[-1] - ep) * d * VPP - FEE, "eod"


def run_gate(D, signal, STOP, TGT, CAP_S, COOL):
    """signal(i) -> direction (1.0 long / -1.0 short / 0 none). Returns trades list."""
    s0, s1 = D.s0, D.s1
    nf, price, tts = D.nf, D.price, D.tts
    trades = []
    busy_until = -1
    for s in range(s0 + 59, s1, 60):          # each 1-min bar close
        i = s - s0
        if i < 0 or i >= len(price) or s < busy_until:
            continue
        d = signal(i)
        if d == 0:
            continue
        ei = int(np.searchsorted(tts, (s + 1) * 1000, "left"))   # first tick AFTER close
        if ei >= len(tts):
            break
        pnl, reason = scalp(D, ei, d, STOP, TGT, CAP_S)
        ts = int(tts[ei])
        trades.append({"d": d, "pnl": pnl, "reason": reason, "er": D.er_for(ts), "atr": D.atr_for(ts),
                       "net30": D.net30_for(ts), "ts": ts})
        busy_until = s + COOL
    return trades


def _st(rows):
    n = len(rows); net = sum(r["pnl"] for r in rows)
    w = 100 * sum(1 for r in rows if r["pnl"] > 0) / n if n else 0
    return n, net, w


def er_floor_sweep(trades, label):
    """Cumulative ER-floor sweep: does ANY floor go green at real n?"""
    have = [t for t in trades if t.get("er") is not None]
    print(f"   ER-floor sweep [{label}] (ER>=floor, cumulative):")
    for fl in [0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        g = [t for t in have if t["er"] >= fl]
        n, net, w = _st(g)
        flag = "  <- GREEN" if net > 0 and n >= 15 else ("  (thin)" if 0 < n < 15 else "")
        print(f"     ER>={fl:.2f}: {n:>4}tr  ${net:>+7.0f}  ${net/n if n else 0:>+6.1f}/tr  {w:>3.0f}%w{flag}")


def verdict(trades, label):
    n, net, w = _st(trades)
    L = [t for t in trades if t["d"] > 0]; S = [t for t in trades if t["d"] < 0]
    ln, lnet, lw = _st(L); sn, snet, sw = _st(S)
    have = [t for t in trades if t.get("er") is not None]
    # best ER band
    bands = [(0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, 9)]
    best = None
    for a, b in bands:
        g = [t for t in have if a <= t["er"] < b]
        gn, gnet, gw = _st(g)
        if gn and (best is None or gnet > best[1]):
            best = (f"{a:.1f}-{b:.1f}", gnet, gn, gw)
    srt = sorted(t["pnl"] for t in trades)
    s1 = sum(srt[:len(srt) - 1]) if len(srt) > 1 else 0
    s3 = sum(srt[:len(srt) - 3]) if len(srt) > 3 else 0
    print(f"\n   ══ VERDICT [{label}] ══")
    print(f"     RAW {n}tr ${net:+.0f} {w:.0f}%w | LONG {ln}tr ${lnet:+.0f} {lw:.0f}%w | SHORT {sn}tr ${snet:+.0f} {sw:.0f}%w")
    if best:
        print(f"     best ER band [{best[0]}] ${best[1]:+.0f}/{best[2]}tr {best[3]:.0f}%w")
    print(f"     strip-best: s0 ${net:+.0f}  s1 ${s1:+.0f}  s3 ${s3:+.0f}")
    # robustness of the ONLY plausibly-green cut: ER>=0.35, strip-best + with/against trend beta
    hi = [t for t in have if t["er"] >= 0.35]
    hn, hnet, hw = _st(hi)
    hsrt = sorted(t["pnl"] for t in hi)
    hs1 = sum(hsrt[:len(hsrt) - 1]) if len(hsrt) > 1 else 0
    hs3 = sum(hsrt[:len(hsrt) - 3]) if len(hsrt) > 3 else 0
    beta = [t for t in hi if t["net30"] is not None]
    wt = [t for t in beta if t["d"] * (1 if t["net30"] > 0 else -1) > 0]     # trade WITH 30-min trend
    at = [t for t in beta if t["d"] * (1 if t["net30"] > 0 else -1) <= 0]    # trade AGAINST it
    wn, wnet, ww = _st(wt); an, anet, aw = _st(at)
    print(f"     ER>=0.35 cut: {hn}tr ${hnet:+.0f} {hw:.0f}%w | strip-best s1 ${hs1:+.0f} s3 ${hs3:+.0f}")
    print(f"       beta split: WITH-trend {wn}tr ${wnet:+.0f} {ww:.0f}%w | AGAINST-trend {an}tr ${anet:+.0f} {aw:.0f}%w"
          f"   {'<- pure BETA (only with-trend green)' if anet <= 0 < wnet else ''}")


def main():
    print("Loading FULL 3-week archive (07-05..07-24)...", flush=True)
    D = A.load()
    print(f"loaded: {D.n_ticks:,} ticks  span {D.span[0]} .. {D.span[1]}  cutover {D.cutover}\n")
    nf, price, hi60, lo60 = D.nf, D.price, D.hi60, D.lo60

    # ============================================================ GATE 1: Absorption Fade
    F1, P1, STOP1, TGT1 = 150.0, 8.0, 25.0, 90.0
    CAP1, COOL1 = 900, 900

    def g1(i):
        if i < 60:
            return 0
        disp = price[i] - price[i - 60]
        if nf[i] <= -F1 and disp >= -P1:      # heavy sell flow, price refused to fall -> LONG
            return 1.0
        if nf[i] >= F1 and disp <= P1:        # heavy buy flow, price refused to rise -> SHORT
            return -1.0
        return 0

    print("=" * 78)
    print("GATE 1  ABSORPTION FADE  F150/P8/STOP25/TGT90  cap15m cool15m")
    print("=" * 78)
    t1 = run_gate(D, g1, STOP1, TGT1, CAP1, COOL1)
    A.battery(t1, "absorption-fade-3wk")
    er_floor_sweep(t1, "absorption-fade")
    verdict(t1, "absorption-fade")

    # ============================================================ GATE 2: Trap-Reclaim scalp
    F2, STOP2, TGT2, RECLAIM2 = 300.0, 40.0, 30.0, 6.0
    CAP2, COOL2 = 900, 60

    def g2(i):
        if nf[i] <= -F2 and price[i] >= hi60[i] - RECLAIM2:   # sellers trapped, reclaims 60s high -> LONG
            return 1.0
        if nf[i] >= F2 and price[i] <= lo60[i] + RECLAIM2:    # buyers trapped, reclaims 60s low -> SHORT
            return -1.0
        return 0

    print("\n" + "=" * 78)
    print("GATE 2  TRAP-RECLAIM SCALP  F300/STOP40/TGT30/RECLAIM6  cap15m cool60s")
    print("=" * 78)
    t2 = run_gate(D, g2, STOP2, TGT2, CAP2, COOL2)
    A.battery(t2, "trap-reclaim-3wk")
    er_floor_sweep(t2, "trap-reclaim")
    verdict(t2, "trap-reclaim")
    # counter-trend (down-trend) LONG win% over the full window
    L = [t for t in t2 if t["d"] > 0 and t["net30"] is not None]
    Lup = [t for t in L if t["net30"] > 0]; Ldn = [t for t in L if t["net30"] <= 0]
    print("\n   ── TRAP-RECLAIM counter-trend LONG diagonal (operator's key question) ──")
    for lbl, g in [("LONG in UP-trend (with-trend beta)", Lup),
                   ("LONG in DOWN-trend (COUNTER-TREND edge)", Ldn)]:
        n, net, w = _st(g)
        print(f"     {lbl:<42}: {n:>3}tr ${net:+.0f} {w:.0f}%w")
    nall, netall, wall = _st(L)
    print(f"     LONG total: {nall}tr ${netall:+.0f} {wall:.0f}%w")
    print("     (edge = wins in DOWN-trend too; beta = only wins WITH the trend / in UP-trend)")

    # ============================================================ GATE 3: Trapped-Flow Reversal
    F3, H3, STOP3, TGT3 = 200.0, 6.0, 25.0, 45.0
    CAP3, COOL3 = 600, 180

    def g3(i):
        if i < 60:
            return 0
        disp = price[i] - price[i - 60]
        # LONG: heavy sell flow (shorts loaded), price held (disp>=-H), TRIGGER break above 60s high
        if nf[i] <= -F3 and disp >= -H3 and price[i] >= hi60[i]:
            return 1.0
        # SHORT mirror: heavy buy flow, price capped, break below 60s low
        if nf[i] >= F3 and disp <= H3 and price[i] <= lo60[i]:
            return -1.0
        return 0

    print("\n" + "=" * 78)
    print("GATE 3  TRAPPED-FLOW REVERSAL  W60/F200/H6/STOP25/TGT45  cap10m cool180s")
    print("=" * 78)
    t3 = run_gate(D, g3, STOP3, TGT3, CAP3, COOL3)
    A.battery(t3, "trapped-flow-reversal-3wk")
    er_floor_sweep(t3, "trapped-flow-reversal")
    verdict(t3, "trapped-flow-reversal")

    # ============================================================ SUMMARY
    print("\n" + "#" * 78)
    print("# ONE-LINE VERDICTS")
    print("#" * 78)
    print(f"  COST MODEL: FEE=${FEE}/RT  STOP_SLIP=${STOP_SLIP}/stop-exit  VPP=${VPP}/pt")
    for lbl, tr in [("1 absorption-fade", t1), ("2 trap-reclaim", t2), ("3 trapped-flow-rev", t3)]:
        n, net, w = _st(tr)
        nstop = sum(1 for t in tr if t.get("reason") == "stop")
        srt = sorted(t["pnl"] for t in tr)
        s1 = sum(srt[:len(srt) - 1]) if len(srt) > 1 else 0
        s3 = sum(srt[:len(srt) - 3]) if len(srt) > 3 else 0
        alive = "ALIVE?" if net > 0 and s3 > 0 else "GRAVE"
        print(f"  GATE {lbl:<20}: {n:>4}tr ${net:>+7.0f} {w:>3.0f}%w  stops={nstop:>4}  strip3 ${s3:>+7.0f}  -> {alive}")


if __name__ == "__main__":
    main()
