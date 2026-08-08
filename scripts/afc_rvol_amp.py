"""AFC + RVOL×amp combination filter. The fingerprint showed the big FLOW-LED runs don't stand out on
ER/ATR/book, but a SUBSET ignited on high RVOL (2.0–2.4) and the winners skewed higher on pre-run amp.
Single-axis filters failed because losers were uniform — so test the COMBINATION: tag every AFC fire
with RVOL (trailing-5min vol / median trailing-5min over 60min) and amp (60-bar range / ATR), then
sweep RVOL-floor × amp-floor. Does any cell keep the winners and dump the coin-flips → net green?

Same AFC reconstruction as afc_er_sweep (validates 1512 fires / −$7797). Tick-honest, capture.db.

  PYTHONPATH=src python scripts/afc_rvol_amp.py
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
        WITH b AS (SELECT (bar_ts-bar_ts%60) m, max(high) h, min(low) l, arg_max(close,bar_ts) cl, SUM(volume) v
                   FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={lo-5400} AND bar_ts<{hi} GROUP BY 1)
        SELECT m, h, l, cl, v FROM b ORDER BY m""").df()
    con.close()
    mins = bdf.m.values.astype(np.int64)
    cls, hh, ll = bdf.cl.values.astype(float), bdf.h.values.astype(float), bdf.l.values.astype(float)
    vv = bdf.v.values.astype(float)
    idx = {int(mn): i for i, mn in enumerate(mins)}
    trr = np.zeros(len(mins))
    for i in range(1, len(mins)):
        trr[i] = max(hh[i] - ll[i], abs(hh[i] - cls[i - 1]), abs(ll[i] - cls[i - 1]))
    v5 = np.array([vv[max(0, i - 4):i + 1].sum() for i in range(len(mins))])

    def feats(ts):
        i = idx.get(int((ts // 1000) - ((ts // 1000) % 60)))
        if i is None or i < 60:
            return None, None
        atr = float(trr[i - 13:i + 1].mean())
        amp = (float(hh[i - 60:i].max() - ll[i - 60:i].min()) / atr) if atr else None
        base = np.median(v5[i - 60:i])
        rvol = (v5[i] / base) if base > 0 else None
        return rvol, amp

    trades = []
    i, n = 1, len(secs)
    while i < n:
        if over[i] and not over[i - 1]:
            d = 1.0 if F[i] > 0 else -1.0
            ei = int(np.searchsorted(tts, (secs[i] + 1) * 1000, "left"))
            if ei >= len(tts):
                break
            entry_px, entry_ts = tpx[ei], int(tts[ei])
            peak, armed, exit_px, reason, j = 0.0, False, None, None, ei + 1
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
            pnl = (exit_px - entry_px) * d * VPP - FEE
            rvol, amp = feats(entry_ts)
            trades.append({"pnl": pnl, "rvol": rvol, "amp": amp})
            while i < n and secs[i] <= exit_ts // 1000:
                i += 1
            continue
        i += 1

    net = sum(t["pnl"] for t in trades)
    print(f"AFC reconstruction — {len(trades)} fires · net ${net:+.0f}  (validate vs −$7797)\n")

    def line(rows, label):
        if not rows:
            return f"  {label:>12}{0:>7}{'—':>10}"
        nn = len(rows)
        nt = sum(r["pnl"] for r in rows)
        w = sum(1 for r in rows if r["pnl"] > 0)
        return f"  {label:>12}{nn:>7}${nt:>+9.0f}${nt/nn:>+7.1f}{100*w/nn:>5.0f}%"

    have = [t for t in trades if t["rvol"] is not None and t["amp"] is not None]
    print(f"({len(have)}/{len(trades)} fires have RVOL+amp)\n")
    print("── RVOL band (alone) ──   " + f"{'band':>10}{'fires':>7}{'net$':>10}{'$/f':>8}{'win%':>6}")
    for a, b in [(0, .8), (.8, 1.2), (1.2, 1.6), (1.6, 2.0), (2.0, 99)]:
        print(line([t for t in have if a <= t["rvol"] < b], f"{a:.1f}-{b:.1f}"))
    print("\n── amp band (alone) ──    " + f"{'band':>10}{'fires':>7}{'net$':>10}{'$/f':>8}{'win%':>6}")
    for a, b in [(0, 4), (4, 6), (6, 8), (8, 10), (10, 99)]:
        print(line([t for t in have if a <= t["amp"] < b], f"{a}-{b}"))

    print("\n── RVOL-floor × amp-floor GRID (net$ / n · keep fires ≥ both floors) ──")
    rvf = [1.0, 1.2, 1.5, 1.8, 2.0]
    apf = [0, 4, 6, 8, 10]
    print("   amp↓ / rvol→ " + "".join(f"{f'≥{r}':>13}" for r in rvf))
    for af in apf:
        cells = []
        for rf in rvf:
            g = [t for t in have if t["rvol"] >= rf and t["amp"] >= af]
            cells.append(f"{('$'+format(sum(t['pnl'] for t in g),'+.0f')+'/'+str(len(g))) if g else '—':>13}")
        print(f"   amp≥{af:<3}     " + "".join(cells))
    print("\n(a GREEN cell with enough n = the fingerprint COMBINATION isolates winners where single axes "
          "couldn't. all-red = the winners aren't separable even on RVOL×amp. ⚠ 1wk, in-sample, thin at the corners.)")


if __name__ == "__main__":
    main()
