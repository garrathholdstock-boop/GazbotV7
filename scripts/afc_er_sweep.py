#!/usr/bin/env python3
"""AFC (Aggressor-Flow-Continuation) greenfield gate — ER band sweep.

The Movement-3 flow-continuation gate caught 15/17 big FLOW-LED runs but bled −$7,907 unfiltered
(negative-EV entry, 50% coin-flip). The lab stopped there. Operator ask: condition it on the
efficiency ratio (ER = trend vs chop) — does it get killed in the chop bands and survive in the
trend bands? This replays the EXACT AFC spec tick-honest and buckets every fire by its entry-ER
into 0.1 bands.

AFC spec (from gf_full_FLOW-LED.md): F = trailing W=60s net signed aggressor vol (Σbuy−Σsell) per 1s;
fire WITH the flow on the rising edge of |F|≥TH=150 while flat (fresh cross to re-arm); entry = first
tick after the trigger second; hard STOP=20pt; chandelier ARM=12/TRAIL=12; CAP=1200s; $5/RT, $2/pt.
ER = Kaufman 30-bar efficiency ratio on 1-min closes (deciders/run_census convention).

  PYTHONPATH=src python scripts/afc_er_sweep.py
"""
from __future__ import annotations

import duckdb
import numpy as np

CAP_DB = "/home/alphabot/gazbot7/data/capture.db"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
W, TH, STOP, ARM, TRAIL, HOLD_CAP = 60, 150.0, 20.0, 12.0, 12.0, 1200
FEE, VPP = 5.0, 2.0


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP_DB}' AS c (TYPE sqlite, READ_ONLY)")
    lo = con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0]
    hi = con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0]

    # per-second signed aggressor flow → dense series → trailing W-sec rolling sum = F
    fdf = con.execute(f"""
        SELECT CAST(ts_ms/1000 AS BIGINT) s,
               SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={int(lo)*1000} AND ts_ms<{int(hi)*1000}
        GROUP BY s ORDER BY s""").df()
    s0, s1 = int(fdf.s.min()), int(fdf.s.max())
    flow = np.zeros(s1 - s0 + 1)
    flow[(fdf.s.values - s0).astype(int)] = fdf.net.values
    F = np.convolve(flow, np.ones(W), "full")[:len(flow)]      # trailing W-sec sum at each second
    secs = np.arange(s0, s1 + 1)

    # raw tick path for tick-honest entry/exit
    tk = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
        AND ts_ms>={int(lo)*1000} AND ts_ms<{int(hi)*1000} ORDER BY ts_ms""").df()
    tts, tpx = tk.ts_ms.values.astype(np.int64), tk.price.values.astype(float)

    # 1-min closes → Kaufman 30-bar ER per minute
    bdf = con.execute(f"""
        WITH b AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl FROM c.bars
                   WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={int(lo)} AND bar_ts<{int(hi)} GROUP BY 1)
        SELECT m, cl FROM b ORDER BY m""").df()
    mins, cls = bdf.m.values.astype(np.int64), bdf.cl.values.astype(float)
    er_at = {}
    for i in range(len(mins)):
        if i < 30:
            continue
        seg = cls[i - 30:i + 1]
        tot = np.abs(np.diff(seg)).sum()
        er_at[int(mins[i])] = (abs(seg[-1] - seg[0]) / tot) if tot > 0 else 0.0

    def er_for(ts_ms):
        m = (ts_ms // 1000) - ((ts_ms // 1000) % 60)
        # nearest minute at or before
        return er_at.get(int(m))

    # state machine: rising-edge fire while flat, one position, tick-honest exit
    over = np.abs(F) >= TH
    trades = []
    i, n = 1, len(secs)
    while i < n:
        if over[i] and not over[i - 1]:
            d = 1.0 if F[i] > 0 else -1.0
            ei = int(np.searchsorted(tts, (secs[i] + 1) * 1000, "left"))
            if ei >= len(tts):
                break
            entry_px, entry_ts = tpx[ei], int(tts[ei])
            peak = 0.0
            armed = False
            exit_px, exit_ts, reason = None, None, None
            j = ei + 1
            while j < len(tts):
                px, t = tpx[j], int(tts[j])
                fav = (px - entry_px) * d
                if -fav >= STOP:                       # hard stop → fill at the stop level
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
            trades.append({"ts": entry_ts, "dir": d, "pnl": pnl, "reason": reason,
                           "er": er_for(entry_ts)})
            exit_sec = exit_ts // 1000
            while i < n and secs[i] <= exit_sec:       # skip seconds held; fresh cross needed to re-arm
                i += 1
            continue
        i += 1

    # totals (validate vs the report: n≈1482, net≈−$7907, 50%w, stop~556/trail~910/time~16)
    net = sum(t["pnl"] for t in trades)
    w = sum(1 for t in trades if t["pnl"] > 0)
    rc = {}
    for t in trades:
        rc[t["reason"]] = rc.get(t["reason"], 0) + 1
    print(f"AFC reconstruction — {len(trades)} fires · net ${net:+.0f} · win {100*w/len(trades):.0f}% "
          f"· exits {rc}   (report: 1482 / −$7907 / 50% / stop556·trail910·time16)\n")

    # ER 0.1-band sweep
    print("ER BAND SWEEP (0.1 bands · ER = 30-min Kaufman efficiency, chop<0.08 · mixed .08–.18 · trend≥.18)")
    print(f"  {'ER band':>10}{'fires':>7}{'net$':>9}{'$/fire':>8}{'win%':>6}{'stop%':>7}{'trail$':>9}{'stop$':>9}")
    bands = [(round(x / 10, 1), round(x / 10 + 0.1, 1)) for x in range(0, 10)]
    have_er = [t for t in trades if t["er"] is not None]
    print(f"  (fires with an ER value: {len(have_er)}/{len(trades)}; rest lacked 30-bar history)\n")
    cum = []
    for lo_b, hi_b in bands:
        grp = [t for t in have_er if lo_b <= t["er"] < hi_b or (hi_b == 1.0 and t["er"] >= 1.0)]
        if not grp:
            print(f"  {f'{lo_b:.1f}-{hi_b:.1f}':>10}{0:>7}{'—':>9}")
            continue
        gnet = sum(t["pnl"] for t in grp)
        gw = sum(1 for t in grp if t["pnl"] > 0)
        gstop = [t["pnl"] for t in grp if t["reason"] == "stop"]
        gtrail = [t["pnl"] for t in grp if t["reason"] == "trail"]
        cum.append((f"{lo_b:.1f}-{hi_b:.1f}", len(grp), gnet, gnet / len(grp), 100 * gw / len(grp),
                    100 * len(gstop) / len(grp), sum(gtrail), sum(gstop)))
        print(f"  {f'{lo_b:.1f}-{hi_b:.1f}':>10}{len(grp):>7}${gnet:>+8.0f}${gnet/len(grp):>+7.1f}"
              f"{100*gw/len(grp):>5.0f}%{100*len(gstop)/len(grp):>6.0f}%${sum(gtrail):>+8.0f}${sum(gstop):>+8.0f}")

    # cumulative view: keep only fires with ER >= floor (does a trend floor rescue it?)
    print("\n  ── cumulative: keep fires with ER ≥ floor (is there a trend-floor that turns it green?) ──")
    print(f"  {'ER floor':>9}{'fires':>7}{'net$':>9}{'$/fire':>8}{'win%':>6}")
    for floor in [0.0, 0.08, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30, 0.40, 0.50]:
        keep = [t for t in have_er if t["er"] >= floor]
        if not keep:
            continue
        knet = sum(t["pnl"] for t in keep)
        kw = sum(1 for t in keep if t["pnl"] > 0)
        print(f"  {f'≥{floor:.2f}':>9}{len(keep):>7}${knet:>+8.0f}${knet/len(keep):>+7.1f}{100*kw/len(keep):>5.0f}%")
    con.close()
    print("\n(⚠ one week, in-sample, tick-honest at $5/RT. If NO band is green, the entry is dead across "
          "regimes; if a high-ER band is green, that's the conditioned survivor to carry forward.)")


if __name__ == "__main__":
    main()
