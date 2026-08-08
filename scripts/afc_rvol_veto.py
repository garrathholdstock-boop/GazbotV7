"""AFC + RVOL floor + absorption veto — the combination cut. RVOL≥2 alone was the only slice with a
>50% win (53%, −$3.9/fire); the follow-through veto alone halved the loss. Neither rescued it apart.
Test them TOGETHER: enter only if (a) trailing-5min RVOL ≥ floor at the signal AND (b) the burst
followed through by T+N. Grid = veto delay × RVOL floor. Any green cell with real n = a survivor.

Same AFC reconstruction (validates 1512 fires / −$7797). Tick-honest, capture.db.

  PYTHONPATH=src python scripts/afc_rvol_veto.py
"""
from __future__ import annotations

import duckdb
import numpy as np

CAP = "/home/alphabot/gazbot7/data/capture.db"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
W, TH, STOP, ARM, TRAIL, HOLD_CAP = 60, 150.0, 20.0, 12.0, 12.0, 1200
FEE, VPP = 1.50, 2.0   # ★2026-08-02 COST FIX (operator): FEE was 5.0 — 3.3x the real commission.
# Venue truth: MNQ is $1.50 per ROUND TRIP ($0.75/side) — all 487 closed trades in data/gazbot7.db carry
# fees_usd = 1.50 exactly. The 5.0 folded unmodelled STOP slippage into the fee; keep slippage a SEPARATE
# explicit term (scripts/grave_newsfade.py documents the same fix on 2026-07-25).
# ⚠ ANY CONCLUSION THIS SCRIPT PRODUCED BEFORE THIS DATE WAS COMPUTED AT $5/RT — re-run before citing it.
# Revert: set FEE back to 5.0.
DELAYS = [0, 15, 30, 45, 55]
RVOL_FLOORS = [0.0, 1.2, 1.5, 1.8, 2.0]


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
    bdf = con.execute(f"""
        WITH b AS (SELECT (bar_ts-bar_ts%60) m, SUM(volume) v FROM c.bars
                   WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={lo-5400} AND bar_ts<{hi} GROUP BY 1)
        SELECT m, v FROM b ORDER BY m""").df()
    con.close()
    mins = bdf.m.values.astype(np.int64)
    vv = bdf.v.values.astype(float)
    idx = {int(mn): i for i, mn in enumerate(mins)}
    v5 = np.array([vv[max(0, i - 4):i + 1].sum() for i in range(len(mins))])

    def rvol_at(ts):
        i = idx.get(int((ts // 1000) - ((ts // 1000) % 60)))
        if i is None or i < 60:
            return None
        base = np.median(v5[i - 60:i])
        return (v5[i] / base) if base > 0 else None

    def walk(ei, entry_px, d):
        peak, armed, entry_ts, j = 0.0, False, int(tts[ei]), ei + 1
        while j < len(tts):
            px, t = tpx[j], int(tts[j])
            fav = (px - entry_px) * d
            if -fav >= STOP:
                return entry_px - d * STOP, t
            if fav > peak:
                peak = fav
            if not armed and peak >= ARM:
                armed = True
            if armed and (peak - fav) >= TRAIL:
                return px, t
            if t - entry_ts >= HOLD_CAP * 1000:
                return px, t
            j += 1
        return tpx[-1], int(tts[-1])

    def run(N):
        trades = []
        i, n = 1, len(secs)
        while i < n:
            if over[i] and not over[i - 1]:
                d = 1.0 if F[i] > 0 else -1.0
                si = int(np.searchsorted(tts, (secs[i] + 1) * 1000, "left"))
                if si >= len(tts):
                    break
                rv = rvol_at(int(tts[si]))
                if N > 0:
                    ei = int(np.searchsorted(tts, (secs[i] + N) * 1000, "left"))
                    if ei >= len(tts):
                        break
                    if (tpx[ei] - tpx[si]) * d <= 0:
                        tn = int(tts[ei] // 1000)
                        while i < n and secs[i] <= tn:
                            i += 1
                        continue
                else:
                    ei = si
                entry_px = tpx[ei]
                exit_px, exit_ts = walk(ei, entry_px, d)
                trades.append(((exit_px - entry_px) * d * VPP - FEE, rv))
                while i < n and secs[i] <= exit_ts // 1000:
                    i += 1
                continue
            i += 1
        return trades

    print("AFC + RVOL floor + absorption veto — net$ / n (win%), keep entries with RVOL ≥ floor\n")
    print(f"  {'veto':>6}" + "".join(f"{('rvol '+ ('all' if r == 0 else f'≥{r}')):>16}" for r in RVOL_FLOORS))
    for N in DELAYS:
        tr = run(N)
        row = []
        for rf in RVOL_FLOORS:
            g = [p for p, rv in tr if rv is not None and rv >= rf]
            if not g:
                row.append(f"{'—':>16}")
                continue
            net = sum(g)
            w = 100 * sum(1 for p in g if p > 0) / len(g)
            row.append(f"{f'${net:+.0f}/{len(g)}({w:.0f}%)':>16}")
        print(f"  {('RAW' if not N else f'{N}s'):>6}" + "".join(row))
    print("\n(top-left = raw/all = the −$7797 baseline. bottom-right = slowest veto + highest RVOL = the "
          "cleanest corner. a GREEN cell with n≥~30 = the combination finally isolates an edge. "
          "⚠ 1wk, in-sample, thin at the corners.)")


if __name__ == "__main__":
    main()
