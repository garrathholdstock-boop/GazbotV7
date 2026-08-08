"""The footprint INSIDE the first ~20% of the move — what separates a real run from a pop that breaks
+M then reverts? For every breakout-confirm entry (price broke +M pts in the flow dir), measure the
footprint DURING that break (signal → +M tick): how fast it broke, flow sustained vs fading through
the break, tick velocity, and how clean (max adverse pullback before breaking). Then split entries by
outcome — RAN (caught a FLOW-LED run) vs REVERTED (no run, lost) — and compare. A feature that
separates them is the discriminator to bolt onto the breakout-confirm: keep runs, drop the reverting pops.

  PYTHONPATH=src python scripts/afc_run_footprint.py [--m 16]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re

import duckdb
import numpy as np

CAP = "/home/alphabot/gazbot7/data/capture.db"
CENSUS = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
W, TH, STOP, ARM, TRAIL, HOLD_CAP, ARM_TO = 60, 150.0, 20.0, 12.0, 12.0, 1200, 300
FEE, VPP = 1.50, 2.0   # ★2026-08-02 COST FIX (operator): FEE was 5.0 — 3.3x the real commission.
# Venue truth: MNQ is $1.50 per ROUND TRIP ($0.75/side) — all 487 closed trades in data/gazbot7.db carry
# fees_usd = 1.50 exactly. The 5.0 is a legacy figure that folded unmodelled STOP slippage into the fee
# (see scripts/grave_newsfade.py, which documents the same fix on 2026-07-25 and keeps slippage a SEPARATE
# explicit term). A fixed per-trade fee is a REGRESSIVE tax on thin-edge/high-fire ideas: the same wrong
# constant made the NIPC replay read +$264 when the true figure was +$820, and flipped its verdict.
# ⚠ ANY CONCLUSION THIS SCRIPT PRODUCED BEFORE THIS DATE WAS COMPUTED AT $5/RT — re-run before citing it.
# Revert: FEE, VPP = 5.0, 2.0.
WIN_PRE, WIN_POST = 600, 300


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m", type=float, default=16.0, help="breakout-confirm distance (pts)")
    M = ap.parse_args().m
    runs = []
    for ln in open(CENSUS):
        if ln.rstrip().endswith("FLOW-LED"):
            m = re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]?\d+)", ln)
            if m:
                ep = int(dt.datetime.strptime("2026-" + m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())
                runs.append({"ep": ep, "d": 1.0 if m.group(2) == "UP" else -1.0})

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
    csum = np.concatenate([[0], np.cumsum(flow)])          # prefix sums of per-sec flow
    F = np.convolve(flow, np.ones(W), "full")[:len(flow)]
    secs = np.arange(s0, s1 + 1)
    over = np.abs(F) >= TH
    tk = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
        AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts, tpx = tk.ts_ms.values.astype(np.int64), tk.price.values.astype(float)
    con.close()

    def flow_dir(a_sec, b_sec, d):                          # net signed flow in [a,b) toward d
        a, b = max(0, a_sec - s0), max(0, b_sec - s0)
        return (csum[min(b, len(csum) - 1)] - csum[min(a, len(csum) - 1)]) * d

    def is_run(ts_s, d):
        return any(r["d"] == d and (r["ep"] - WIN_PRE) <= ts_s <= (r["ep"] + WIN_POST) for r in runs)

    def exit_walk(ei, entry_px, d):
        peak, armed, entry_ts, j = 0.0, False, int(tts[ei]), ei + 1
        while j < len(tts):
            px, t = tpx[j], int(tts[j])
            fav = (px - entry_px) * d
            if -fav >= STOP:
                return entry_px - d * STOP
            if fav > peak:
                peak = fav
            if not armed and peak >= ARM:
                armed = True
            if armed and (peak - fav) >= TRAIL:
                return px
            if t - entry_ts >= HOLD_CAP * 1000:
                return px
            j += 1
        return tpx[-1]

    ran, rev = [], []
    i, n = 1, len(secs)
    while i < n:
        if over[i] and not over[i - 1]:
            d = 1.0 if F[i] > 0 else -1.0
            si = int(np.searchsorted(tts, (secs[i] + 1) * 1000, "left"))
            if si >= len(tts):
                break
            sig_px, sig_ts = tpx[si], int(tts[si])
            ei, j, pull = -1, si + 1, 0.0
            while j < len(tts):
                fav = (tpx[j] - sig_px) * d
                pull = max(pull, -fav)
                if fav >= M:
                    ei = j
                    break
                if fav <= -M or (int(tts[j]) - sig_ts) >= ARM_TO * 1000:
                    break
                j += 1
            if ei < 0:
                tnsec = int(tts[j] // 1000) if j < len(tts) else secs[i]
                while i < n and secs[i] <= tnsec:
                    i += 1
                continue
            brk_ts = int(tts[ei])
            # footprint DURING the break (signal → +M)
            dtM = (brk_ts - sig_ts) / 1000.0
            fdur = flow_dir(sig_ts // 1000, brk_ts // 1000 + 1, d)
            fpre = flow_dir(sig_ts // 1000 - 60, sig_ts // 1000, d)
            fp = {"dtM": dtM, "vel": M / dtM if dtM > 0 else 0, "ticks": ei - si,
                  "flow_dur": fdur, "flow_rate": fdur / dtM if dtM > 0 else 0,
                  "accel": (fdur / dtM) / (fpre / 60) if (dtM > 0 and fpre > 0) else np.nan, "pull": pull}
            exit_px = exit_walk(ei, tpx[ei], d)
            pnl = (exit_px - tpx[ei]) * d * VPP - FEE
            (ran if is_run(int(secs[i]), d) else (rev if pnl < 0 else ran)).append(fp)
            while i < n and secs[i] <= brk_ts // 1000:      # advance past break (exit-skip approx)
                i += 1
            continue
        i += 1

    def col(rows, k):
        v = np.array([r[k] for r in rows if not (isinstance(r[k], float) and np.isnan(r[k]))], float)
        return v

    print(f"BREAKOUT FOOTPRINT (M={M:.0f}pt) — the first-20% tape of RUNS vs REVERTING POPS\n")
    print(f"  RAN (caught a run or profitable): {len(ran)}   REVERTED (broke +M, no run, lost): {len(rev)}\n")
    print(f"  {'feature':>26}{'RAN median':>14}{'REVERTED median':>18}{'separates?':>12}")
    feats = [("time to +M (s)", "dtM", "{:.0f}"), ("break velocity (pt/s)", "vel", "{:.2f}"),
             ("ticks in break", "ticks", "{:.0f}"), ("flow during break (dir)", "flow_dur", "{:+.0f}"),
             ("flow rate (/s, dir)", "flow_rate", "{:+.1f}"), ("accel (break/pre)", "accel", "{:.2f}"),
             ("max pullback before +M", "pull", "{:.1f}")]
    for name, k, fm in feats:
        a, b = col(ran, k), col(rev, k)
        if len(a) < 3 or len(b) < 3:
            continue
        ma, mb = np.median(a), np.median(b)
        sep = "← yes" if abs(ma - mb) > 0.3 * (abs(mb) + 1e-9) else ""
        print(f"  {name:>26}{fm.format(ma):>14}{fm.format(mb):>18}{sep:>12}")
    print("\n(a feature where RAN and REVERTED medians clearly diverge is the discriminator to add to the "
          "breakout-confirm. no divergence anywhere = even the break itself looks identical run-vs-pop. "
          "⚠ small n on the RAN side, 1wk in-sample.)")


if __name__ == "__main__":
    main()
