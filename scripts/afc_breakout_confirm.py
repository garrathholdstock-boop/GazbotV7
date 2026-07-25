"""AFC BREAKOUT-CONFIRM (operator idea) — don't enter on the flow spike (a coin-flip); ARM on it, then
enter ONLY if price breaks +M points in the flow direction first (the run proves itself). If it breaks
−M first (or times out), CANCEL — no entry, no fee. You sacrifice the first M points (~20% of a run)
but you filter every fakeout BEFORE it costs anything, and ride the remaining ~80%.

This attacks the real problem: prior filters still ENTERED every fire (1500 × $5 fee = the whole loss).
Here the fakeouts cancel pre-entry, so fees only hit confirmed runs. Sweep M. ALWAYS reports the big
runs kept [X/17] — a confirm that filters the fakeouts but also drops the runs is a fake win.

Entry at the +M tick; exit = chandelier (ARM 12 / TRAIL 12) + STOP 20 from entry + CAP 1200s. $5/RT,
$2/pt. Tick-honest, capture.db + frozen FLOW-LED runs.

  PYTHONPATH=src python scripts/afc_breakout_confirm.py
"""
from __future__ import annotations

import datetime as dt
import re

import duckdb
import numpy as np

CAP = "/home/alphabot/gazbot7/data/capture.db"
CENSUS = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
W, TH, STOP, ARM, TRAIL, HOLD_CAP, ARM_TO = 60, 150.0, 20.0, 12.0, 12.0, 1200, 300
FEE, VPP = 5.0, 2.0
MS = [8, 12, 16, 20, 25, 30]           # breakout-confirm distance (pts) — the sacrificed head of the run
WIN_PRE, WIN_POST = 600, 300


def main():
    runs = []
    for ln in open(CENSUS):
        if not ln.rstrip().endswith("FLOW-LED"):
            continue
        m = re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]?\d+)", ln)
        if m:
            ep = int(dt.datetime.strptime("2026-" + m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())
            runs.append({"ep": ep, "d": 1.0 if m.group(2) == "UP" else -1.0, "mv": abs(int(m.group(3)))})
    NR = len(runs)

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

    def which_run(ts_s, d):
        for k, r in enumerate(runs):
            if r["d"] == d and (r["ep"] - WIN_PRE) <= ts_s <= (r["ep"] + WIN_POST):
                return k
        return -1

    def exit_walk(ei, entry_px, d):
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

    def run_M(M):
        trades, armed_sig, cancelled = [], 0, 0
        i, n = 1, len(secs)
        while i < n:
            if over[i] and not over[i - 1]:
                armed_sig += 1
                d = 1.0 if F[i] > 0 else -1.0
                si = int(np.searchsorted(tts, (secs[i] + 1) * 1000, "left"))
                if si >= len(tts):
                    break
                sig_px, sig_ts = tpx[si], int(tts[si])
                # arm-walk: first to +M (enter) or −M / timeout (cancel)
                ei, j = -1, si + 1
                while j < len(tts):
                    fav = (tpx[j] - sig_px) * d
                    if fav >= M:
                        ei = j
                        break
                    if fav <= -M or (int(tts[j]) - sig_ts) >= ARM_TO * 1000:
                        break
                    j += 1
                if ei < 0:
                    cancelled += 1
                    tnsec = int(tts[j] // 1000) if j < len(tts) else secs[i]
                    while i < n and secs[i] <= tnsec:
                        i += 1
                    continue
                entry_px = tpx[ei]
                exit_px, exit_ts = exit_walk(ei, entry_px, d)
                trades.append({"pnl": (exit_px - entry_px) * d * VPP - FEE, "run": which_run(int(secs[i]), d)})
                while i < n and secs[i] <= exit_ts // 1000:
                    i += 1
                continue
            i += 1
        return trades, armed_sig, cancelled

    print(f"AFC BREAKOUT-CONFIRM — arm on the flow spike, enter only if price breaks +M pts first "
          f"(else cancel, no fee). {NR} FLOW-LED runs to keep.\n")
    print(f"  {'M(pt)':>6}{'armed':>8}{'cancelled':>11}{'entered':>9}{'net$':>9}{'$/entry':>9}{'win%':>6}"
          f"{'runs kept':>11}")
    for M in MS:
        tr, arm, canc = run_M(M)
        if not tr:
            print(f"  {M:>6}{arm:>8}{canc:>11}{0:>9}")
            continue
        net = sum(t["pnl"] for t in tr)
        w = 100 * sum(1 for t in tr if t["pnl"] > 0) / len(tr)
        caught = len({t["run"] for t in tr if t["run"] >= 0})
        print(f"  {M:>6}{arm:>8}{canc:>11}{len(tr):>9}${net:>+8.0f}${net/len(tr):>+8.1f}{w:>5.0f}%"
              f"{f'{caught}/{NR}':>11}")
    print("\n(the win: cancelled fakeouts pay NO fee, so the fee drag collapses — only confirmed runs cost. "
          f"a GREEN net with runs-kept near {NR} = the breakout-confirm is the mechanism. watch the runs-kept "
          "column: if a big M filters fakeouts but also drops runs, that's the sacrifice cost. ⚠ 1wk in-sample.)")


if __name__ == "__main__":
    main()
