#!/usr/bin/env python3
"""AFC + ABSORPTION VETO — fast delay sweep (15→60s, 5s steps).

The AFC flow-continuation gate bleeds via 559 identical −$45 stops = flow spikes that fire the gate
then instantly reverse (fakeouts). The abs_veto mechanism that rescued thrust: after the signal, WAIT
N seconds and only enter if the move actually FOLLOWED THROUGH in the flow direction (skip if it
stalled/absorbed/reversed). Operator wants it FAST — sweep the veto delay down to 15s.

Signal = AFC rising-edge (|trailing-60s net aggressor flow| ≥ TH=150) while flat, direction = with the
flow. VETO: at T+N, if price has NOT moved in the flow direction (move_dp ≤ 0), the burst was absorbed
→ skip. Else enter at the T+N tick and run the AFC exit (STOP 20 / chandelier ARM 12 / TRAIL 12 / CAP
1200s), $5/RT, $2/pt. One position at a time; fresh cross to re-arm. Tick-honest on capture.db.

  PYTHONPATH=src python scripts/afc_veto_sweep.py
"""
from __future__ import annotations

import duckdb
import numpy as np

CAP = "/home/alphabot/gazbot7/data/capture.db"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
W, TH, STOP, ARM, TRAIL, HOLD_CAP = 60, 150.0, 20.0, 12.0, 12.0, 1200
FEE, VPP = 1.50, 2.0   # ★2026-08-02 COST FIX (operator): FEE was 5.0 — 3.3x the real commission.
# Venue truth: MNQ is $1.50 per ROUND TRIP ($0.75/side) — all 487 closed trades in data/gazbot7.db carry
# fees_usd = 1.50 exactly. The 5.0 is a legacy figure that folded unmodelled STOP slippage into the fee
# (see scripts/grave_newsfade.py, which documents the same fix on 2026-07-25 and keeps slippage a SEPARATE
# explicit term). A fixed per-trade fee is a REGRESSIVE tax on thin-edge/high-fire ideas: the same wrong
# constant made the NIPC replay read +$264 when the true figure was +$820, and flipped its verdict.
# ⚠ ANY CONCLUSION THIS SCRIPT PRODUCED BEFORE THIS DATE WAS COMPUTED AT $5/RT — re-run before citing it.
# Revert: FEE, VPP = 5.0, 2.0.
DELAYS = [0, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]   # 0 = unvetoed baseline


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo = int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0])
    hi = int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])

    fdf = con.execute(f"""
        SELECT CAST(ts_ms/1000 AS BIGINT) s,
               SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} GROUP BY s ORDER BY s""").df()
    s0, s1 = int(fdf.s.min()), int(fdf.s.max())
    flow = np.zeros(s1 - s0 + 1)
    flow[(fdf.s.values - s0).astype(int)] = fdf.net.values
    F = np.convolve(flow, np.ones(W), "full")[:len(flow)]
    secs = np.arange(s0, s1 + 1)
    over = np.abs(F) >= TH

    tk = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
        AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts, tpx = tk.ts_ms.values.astype(np.int64), tk.price.values.astype(float)
    con.close()

    def walk_exit(ei, entry_px, d):
        peak = 0.0
        armed = False
        entry_ts = int(tts[ei])
        j = ei + 1
        while j < len(tts):
            px, t = tpx[j], int(tts[j])
            fav = (px - entry_px) * d
            if -fav >= STOP:
                return entry_px - d * STOP, t, "stop"
            if fav > peak:
                peak = fav
            if not armed and peak >= ARM:
                armed = True
            if armed and (peak - fav) >= TRAIL:
                return px, t, "trail"
            if t - entry_ts >= HOLD_CAP * 1000:
                return px, t, "time"
            j += 1
        return tpx[-1], int(tts[-1]), "time"

    def run(N):
        trades, vetoed, signals = [], 0, 0
        i, n = 1, len(secs)
        while i < n:
            if over[i] and not over[i - 1]:
                signals += 1
                d = 1.0 if F[i] > 0 else -1.0
                si = int(np.searchsorted(tts, (secs[i] + 1) * 1000, "left"))
                if si >= len(tts):
                    break
                if N > 0:                                   # absorption veto: confirm follow-through at T+N
                    ei = int(np.searchsorted(tts, (secs[i] + N) * 1000, "left"))
                    if ei >= len(tts):
                        break
                    if (tpx[ei] - tpx[si]) * d <= 0:        # no follow-through in the flow dir → absorbed → skip
                        vetoed += 1
                        tn_sec = int(tts[ei] // 1000)       # resume after T+N; fresh cross required to re-arm
                        while i < n and secs[i] <= tn_sec:
                            i += 1
                        continue
                else:
                    ei = si
                entry_px = tpx[ei]
                exit_px, exit_ts, reason = walk_exit(ei, entry_px, d)
                pnl = (exit_px - entry_px) * d * VPP - FEE
                trades.append((pnl, reason))
                while i < n and secs[i] <= exit_ts // 1000:
                    i += 1
                continue
            i += 1
        return trades, vetoed, signals

    print("AFC + ABSORPTION VETO — fast delay sweep (skip if no follow-through in the flow dir by T+N)")
    print(f"  {'veto':>6}{'signals':>9}{'vetoed':>8}{'entered':>9}{'net$':>9}{'$/entry':>9}"
          f"{'win%':>6}{'stop%':>7}{'stops$':>9}")
    for N in DELAYS:
        tr, vetoed, sig = run(N)
        if not tr:
            print(f"  {(str(N)+'s' if N else 'RAW'):>6}{sig:>9}{vetoed:>8}{0:>9}{'—':>9}")
            continue
        net = sum(p for p, _ in tr)
        w = sum(1 for p, _ in tr if p > 0)
        stops = [p for p, r in tr if r == "stop"]
        lbl = f"{N}s" if N else "RAW"
        print(f"  {lbl:>6}{sig:>9}{vetoed:>8}{len(tr):>9}${net:>+8.0f}${net/len(tr):>+8.1f}"
              f"{100*w/len(tr):>5.0f}%{100*len(stops)/len(tr):>6.0f}%${sum(stops):>+8.0f}")
    print("\n(RAW = no veto baseline. A green net at some delay = the fast fakeout-filter rescues AFC; "
          "flat-red across all delays = the entry is dead even with confirmation. ⚠ 1 week, in-sample, $5/RT.)")


if __name__ == "__main__":
    main()
