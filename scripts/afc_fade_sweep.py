#!/usr/bin/env python3
"""AFF — Aggressor-Flow FADE (the polarity flip). The forward corr is slightly NEGATIVE
(flow −0.012, book −0.005): the |F|≥150 spike leads mild REVERSION, not continuation. So flip AFC —
enter AGAINST the flow burst (heavy buying → SHORT, heavy selling → LONG) — and run the same lenses.

Same trigger (rising edge |trailing-60s net flow| ≥ TH=150, flat, fresh cross), direction = −sign(F).
Same tick-honest exit (STOP 20 / chandelier ARM 12 / TRAIL 12 / CAP 1200s), $5/RT, $2/pt. Reports RAW
fade vs the −$7,797 continuation baseline, then ER + ATR bands, then a fade-confirm delay sweep (enter
only if the reversion has started by T+N — price moved the fade's way).

  PYTHONPATH=src python scripts/afc_fade_sweep.py
"""
from __future__ import annotations

import duckdb
import numpy as np

CAP = "/home/alphabot/gazbot7/data/capture.db"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
W, TH, STOP, ARM, TRAIL, HOLD_CAP = 60, 150.0, 20.0, 12.0, 12.0, 1200
FEE, VPP = 5.0, 2.0
DELAYS = [0, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]


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
        WITH b AS (SELECT (bar_ts-bar_ts%60) m, max(high) h, min(low) l, arg_max(close,bar_ts) cl
                   FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={lo} AND bar_ts<{hi} GROUP BY 1)
        SELECT m, h, l, cl FROM b ORDER BY m""").df()
    mins = bdf.m.values.astype(np.int64)
    cls, hh, ll = bdf.cl.values.astype(float), bdf.h.values.astype(float), bdf.l.values.astype(float)
    tr = np.zeros(len(mins))
    for k in range(1, len(mins)):
        tr[k] = max(hh[k] - ll[k], abs(hh[k] - cls[k - 1]), abs(ll[k] - cls[k - 1]))
    er_at, atr_at = {}, {}
    for k in range(len(mins)):
        if k >= 30:
            seg = cls[k - 30:k + 1]
            tot = np.abs(np.diff(seg)).sum()
            er_at[int(mins[k])] = (abs(seg[-1] - seg[0]) / tot) if tot > 0 else 0.0
        if k >= 14:
            atr_at[int(mins[k])] = float(tr[k - 13:k + 1].mean())
    con.close()

    def minute(ts):
        return int((ts // 1000) - ((ts // 1000) % 60))

    def walk_exit(ei, entry_px, d):
        peak, armed, entry_ts, j = 0.0, False, int(tts[ei]), ei + 1
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

    def run(N, collect=False):
        trades, vetoed, signals = [], 0, 0
        i, n = 1, len(secs)
        while i < n:
            if over[i] and not over[i - 1]:
                signals += 1
                d = -1.0 if F[i] > 0 else 1.0                # FADE: against the flow
                si = int(np.searchsorted(tts, (secs[i] + 1) * 1000, "left"))
                if si >= len(tts):
                    break
                if N > 0:                                    # fade-confirm: enter only if reversion started by T+N
                    ei = int(np.searchsorted(tts, (secs[i] + N) * 1000, "left"))
                    if ei >= len(tts):
                        break
                    if (tpx[ei] - tpx[si]) * d <= 0:         # price hasn't turned the fade's way → skip
                        vetoed += 1
                        tn = int(tts[ei] // 1000)
                        while i < n and secs[i] <= tn:
                            i += 1
                        continue
                else:
                    ei = si
                entry_px = tpx[ei]
                exit_px, exit_ts, reason = walk_exit(ei, entry_px, d)
                pnl = (exit_px - entry_px) * d * VPP - FEE
                rec = {"pnl": pnl, "reason": reason}
                if collect:
                    rec["er"] = er_at.get(minute(int(tts[ei])))
                    rec["atr"] = atr_at.get(minute(int(tts[ei])))
                trades.append(rec)
                while i < n and secs[i] <= exit_ts // 1000:
                    i += 1
                continue
            i += 1
        return trades, vetoed, signals

    def stat(rows):
        net = sum(r["pnl"] for r in rows)
        w = sum(1 for r in rows if r["pnl"] > 0)
        st = sum(1 for r in rows if r["reason"] == "stop")
        return net, (100 * w / len(rows) if rows else 0), (100 * st / len(rows) if rows else 0)

    raw, _, sig = run(0, collect=True)
    net, win, stp = stat(raw)
    print("AFF — AGGRESSOR-FLOW FADE (enter AGAINST the |F|≥150 spike)\n")
    print(f"RAW FADE: {len(raw)} fires · net ${net:+.0f} · ${net/len(raw):+.1f}/fire · win {win:.0f}% · stop {stp:.0f}%"
          f"   (continuation RAW was −$7797 / 49% — a mirror-ish flip is expected)\n")

    print("── ER bands (RAW fade) ──")
    print(f"  {'ER band':>10}{'fires':>7}{'net$':>9}{'$/fire':>8}{'win%':>6}")
    for x in range(8):
        b0, b1 = x / 10, x / 10 + 0.1
        g = [r for r in raw if r["er"] is not None and b0 <= r["er"] < b1]
        if not g:
            continue
        gn, gw, _ = stat(g)
        print(f"  {f'{b0:.1f}-{b1:.1f}':>10}{len(g):>7}${gn:>+8.0f}${gn/len(g):>+7.1f}{gw:>5.0f}%")

    print("\n── ATR bands (RAW fade) ──")
    print(f"  {'ATR band':>10}{'fires':>7}{'net$':>9}{'$/fire':>8}{'win%':>6}")
    for a0, a1, name in [(0, 8, "0-8"), (8, 12, "8-12"), (12, 16, "12-16"), (16, 20, "16-20"),
                         (20, 25, "20-25"), (25, 30, "25-30"), (30, 100, "30+")]:
        g = [r for r in raw if r["atr"] is not None and a0 <= r["atr"] < a1]
        if not g:
            continue
        gn, gw, _ = stat(g)
        print(f"  {name:>10}{len(g):>7}${gn:>+8.0f}${gn/len(g):>+7.1f}{gw:>5.0f}%")

    print("\n── fade-confirm delay sweep (enter only if the reversion started by T+N) ──")
    print(f"  {'delay':>6}{'signals':>9}{'skipped':>9}{'entered':>9}{'net$':>9}{'$/entry':>9}{'win%':>6}")
    for N in DELAYS:
        t2, vet, s2 = run(N)
        if not t2:
            continue
        n2, w2, _ = stat(t2)
        print(f"  {('RAW' if not N else f'{N}s'):>6}{s2:>9}{vet:>9}{len(t2):>9}${n2:>+8.0f}"
              f"${n2/len(t2):>+8.1f}{w2:>5.0f}%")
    print("\n(if a fade band/delay is solidly GREEN, the flow's mild-reversion tilt is real & tradeable; "
          "if it just mirrors the continuation bleed near breakeven, the signal is simply dead both ways. "
          "⚠ 1 week, in-sample, $5/RT.)")


if __name__ == "__main__":
    main()
