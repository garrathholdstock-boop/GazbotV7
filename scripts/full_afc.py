#!/usr/bin/env python3
"""FULL 3-week AFC (Aggressor-Flow-Continuation) replay + full filter battery.

The 1-week test (07-19..07-24) found flow-continuation a directionless coin-flip:
1512tr / -$7797 / 49%w, both polarities x ER x ATR x veto all dead. Does 3x the data
(07-05..07-24, 22.6M ticks) confirm the null or reveal a real edge?

Signal (verbatim mechanics from afc_er_sweep.py): fire on the rising edge of |nf|>=150
while flat, enter WITH the flow (continuation). Entry = first tick after the signal
second. Tick-honest exit: hard STOP 20pt, chandelier ARM 12 / TRAIL 12, CAP 1200s.
$5/RT, $2/pt. One position at a time; fresh cross re-arms via the flat rising-edge check.

  PYTHONPATH=src python scripts/full_afc.py     (read-only DBs; no live service touched)
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import numpy as np
import archive_data as A

import os
TH, STOP, ARM, TRAIL, HOLD_CAP = 150.0, 20.0, 12.0, 12.0, 1200
# COST FIX (2026-07-25): real MNQ commission is $1.50/RT (live ledger, cost_waterfall.py),
# NOT $5. $5 was partly standing in for unmodeled STOP slippage. All-in model:
#   FEE = 1.5/RT commission (env GF_FEE), entries/exits already tick-honest (spread captured),
#   + explicit STOP-slippage charge STOP_SLIP $ on stop/flush exits only (env GF_STOP_SLIP;
#   4pt=$8 realistic, $0 optimistic bound). Non-stop exits get no extra slippage.
FEE = float(os.environ.get("GF_FEE", "1.5"))
VPP = 2.0
STOP_SLIP = float(os.environ.get("GF_STOP_SLIP", "0.0"))


def build_trades(D, fade=False):
    """Replay AFC. fade=False -> continuation (with flow); fade=True -> flip d."""
    nf, secs, tts, tpx = D.nf, D.secs, D.tts, D.tpx
    over = np.abs(nf) >= TH
    trades = []
    i, n = 1, len(secs)
    while i < n:
        if over[i] and not over[i - 1]:
            d = 1.0 if nf[i] > 0 else -1.0
            if fade:
                d = -d
            ei = int(np.searchsorted(tts, (secs[i] + 1) * 1000, "left"))
            if ei >= len(tts):
                break
            entry_px, entry_ts = tpx[ei], int(tts[ei])
            peak, armed = 0.0, False
            exit_px = exit_ts = reason = None
            j = ei + 1
            while j < len(tts):
                px, t = tpx[j], int(tts[j])
                fav = (px - entry_px) * d
                if -fav >= STOP:
                    exit_px, exit_ts, reason = entry_px - d * STOP, t, "stop"
                    break
                if fav > peak:
                    peak = fav
                if not armed and peak >= ARM:
                    armed = True
                if armed and (peak - fav) >= TRAIL:
                    exit_px, exit_ts, reason = px, t, "trail"
                    break
                if t - entry_ts >= HOLD_CAP * 1000:
                    exit_px, exit_ts, reason = px, t, "time"
                    break
                j += 1
            if exit_px is None:
                exit_px, exit_ts, reason = tpx[-1], int(tts[-1]), "time"
            pnl = (exit_px - entry_px) * d * VPP - FEE - (STOP_SLIP if reason == "stop" else 0.0)
            trades.append({"ts": entry_ts, "d": d, "pnl": pnl, "reason": reason,
                           "er": D.er_for(entry_ts), "atr": D.atr_for(entry_ts),
                           "net30": D.net30_for(entry_ts)})
            exit_sec = exit_ts // 1000
            while i < n and secs[i] <= exit_sec:
                i += 1
            continue
        i += 1
    return trades


def floor_sweep(trades, key, floors, unit=""):
    have = [t for t in trades if t.get(key) is not None]
    print(f"   {key}-floor sweep (cumulative, keep >= floor; {len(have)}/{len(trades)} have {key}):")
    for f in floors:
        keep = [t for t in have if t[key] >= f]
        if not keep:
            continue
        n = len(keep)
        net = sum(t["pnl"] for t in keep)
        w = 100 * sum(1 for t in keep if t["pnl"] > 0) / n
        flag = "  <-- GREEN" if net > 0 else ""
        print(f"      >={f:<5}{unit:<3} {n:>5}tr ${net:>+8.0f} {w:>4.0f}%w  ${net/n:>+6.1f}/tr{flag}")


def main():
    D = A.load()
    print(f"loaded: {D.n_ticks:,} ticks  span {D.span[0]} .. {D.span[1]}  cutover {D.cutover}\n")

    cont = build_trades(D, fade=False)
    n = len(cont)
    net = sum(t["pnl"] for t in cont)
    w = 100 * sum(1 for t in cont if t["pnl"] > 0) / n
    rc = {}
    for t in cont:
        rc[t["reason"]] = rc.get(t["reason"], 0) + 1
    print("=" * 78)
    print(f"CONTINUATION (with-flow)   {n}tr  ${net:+.0f}  {w:.0f}%w   exits {rc}")
    print(f"   1-week baseline was:    1512tr  -$7797  49%w")
    print("=" * 78)
    A.battery(cont, "AFC-3wk CONTINUATION")

    print("\n" + "-" * 78)
    print("FLOOR SWEEPS (continuation) — does any floor firm up green with real n?")
    floor_sweep(cont, "er", [0.0, 0.08, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30, 0.40, 0.50])
    floor_sweep(cont, "atr", [0, 8, 12, 16, 20, 25, 30], unit="pt")

    fade = build_trades(D, fade=True)
    fn = len(fade)
    fnet = sum(t["pnl"] for t in fade)
    fw = 100 * sum(1 for t in fade if t["pnl"] > 0) / fn
    print("\n" + "=" * 78)
    print(f"FADE (against-flow)        {fn}tr  ${fnet:+.0f}  {fw:.0f}%w")
    print("=" * 78)
    A.battery(fade, "AFC-3wk FADE")
    print("\n" + "-" * 78)
    print("FLOOR SWEEPS (fade)")
    floor_sweep(fade, "er", [0.0, 0.08, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30, 0.40, 0.50])
    floor_sweep(fade, "atr", [0, 8, 12, 16, 20, 25, 30], unit="pt")

    # hold-at-n note: per-week split so we can see if the extra data steadied or scattered
    print("\n" + "-" * 78)
    print("HOLD-AT-N (continuation) — weekly split, does the null hold across weeks?")
    import datetime
    def wk(ts):
        d = datetime.datetime.utcfromtimestamp(ts / 1000).date()
        return d.isocalendar()[1]
    weeks = {}
    for t in cont:
        weeks.setdefault(wk(t["ts"]), []).append(t)
    for k in sorted(weeks):
        g = weeks[k]
        gn = len(g); gnet = sum(t["pnl"] for t in g)
        gw = 100 * sum(1 for t in g if t["pnl"] > 0) / gn
        print(f"   ISO-week {k}: {gn:>5}tr ${gnet:>+8.0f} {gw:>4.0f}%w")


if __name__ == "__main__":
    main()
