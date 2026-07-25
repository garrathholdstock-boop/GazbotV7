"""AFC + COOLDOWN × veto — thin the coin-flip re-fires WITHOUT a per-fire feature (which would
kill runs). Cooldown = dead-time (min) after each entry's exit; a run is a single event so it survives,
but the ~766 between-run coin-flips collapse. ALWAYS reports big-runs-retained [X/17]. A filter is only real if the trades it
KEEPS still include the 15/17 FLOW-LED big runs (the whole point). Cutting the loss by dropping the
runs is a fake win. So every cell shows net$ / n / win% AND caught (of the 17 big runs the raw gate
sees). Grid = veto delay × RVOL floor (extend as needed).

A fire "catches" run R if it fires in R's direction within [start−600s, start+300s]. Tick-honest AFC
(validates 1512 / −$7797). capture.db + the frozen census FLOW-LED runs.

  PYTHONPATH=src python scripts/afc_filter_with_runs.py
"""
from __future__ import annotations

import datetime as dt
import re

import duckdb
import numpy as np

CAP = "/home/alphabot/gazbot7/data/capture.db"
CENSUS = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
W, TH, STOP, ARM, TRAIL, HOLD_CAP = 60, 150.0, 20.0, 12.0, 12.0, 1200
FEE, VPP = 5.0, 2.0
VETOS = [0, 30]
COOLDOWNS = [0, 2, 5, 10, 15]   # dead-time minutes after each exit
WIN_PRE, WIN_POST = 600, 300     # a fire catches a run if within [start−600s, start+300s], same dir


def main():
    runs = []
    for ln in open(CENSUS):
        if not ln.rstrip().endswith("FLOW-LED"):
            continue
        m = re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]?\d+)", ln)
        if not m:
            continue
        ep = int(dt.datetime.strptime("2026-" + m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())
        runs.append({"ep": ep, "d": 1.0 if m.group(2) == "UP" else -1.0, "tm": m.group(1), "mv": int(m.group(3))})
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

    def caught_run(ts_s, d):                       # which of the NR runs this fire catches (-1 = none)
        for k, r in enumerate(runs):
            if r["d"] == d and (r["ep"] - WIN_PRE) <= ts_s <= (r["ep"] + WIN_POST):
                return k
        return -1

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

    def run(N, CD=0):
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
                trades.append({"pnl": (exit_px - entry_px) * d * VPP - FEE, "rv": rv,
                               "run": caught_run(int(secs[i]), d)})
                while i < n and secs[i] <= exit_ts // 1000 + CD * 60:
                    i += 1
                continue
            i += 1
        return trades

    raw = run(0)
    base_caught = len({t["run"] for t in raw if t["run"] >= 0})
    print(f"AFC COOLDOWN(min) x veto — net$/n(win%)[caught/17]. raw catches {base_caught}/17. "
          f"want net toward 0 while [ ] stays near {base_caught}.\n")
    print(f"  {'veto':>6}" + "".join(f"{('cd='+str(c)+'min'):>22}" for c in COOLDOWNS))
    for N in VETOS:
        cells = []
        for CD in COOLDOWNS:
            tr = run(N, CD)
            net = sum(t["pnl"] for t in tr)
            w = 100 * sum(1 for t in tr if t["pnl"] > 0) / len(tr) if tr else 0
            caught = len({t["run"] for t in tr if t["run"] >= 0})
            cells.append(f"{f'${net:+.0f}/{len(tr)}({w:.0f}%)[{caught}/17]':>22}")
        print(f"  {('none' if not N else f'{N}s'):>6}" + "".join(cells))
    print("\n(cooldown cuts fires without a per-fire feature, so runs should survive better than the RVOL "
          "filter did. green + [ ] high = a real thin. still red = zero-edge entry, fewer bets. 1wk in-sample.)")


if __name__ == "__main__":
    main()
