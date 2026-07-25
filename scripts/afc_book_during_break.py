"""Book behaviour DURING the breakout — the order-flow tell. For each breakout-confirm entry (price
broke +M in the flow dir), measure the FAR-side top-3 depth at the signal vs at the +M break: did it
REFILL (absorb the push → likely revert) or keep VANISHING (→ likely run)? Compare runs vs reverting
pops. This is the one feature the tape footprint couldn't see; the resting LEVEL was flat, but the
RESPONSE during the push is where genuine vs spoofy momentum should differ.

Book coverage starts 07-21 21:33 UTC, so only breakouts after that are scored. capture.db + census.

  PYTHONPATH=src python scripts/afc_book_during_break.py [--m 16]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re

import duckdb
import numpy as np
import pandas as pd

CAP = "/home/alphabot/gazbot7/data/capture.db"
CENSUS = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
W, TH, STOP, ARM, TRAIL, HOLD_CAP, ARM_TO = 60, 150.0, 20.0, 12.0, 12.0, 1200, 300
FEE, VPP = 5.0, 2.0
WIN_PRE, WIN_POST = 600, 300


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m", type=float, default=16.0)
    M = ap.parse_args().m
    runs = []
    for ln in open(CENSUS):
        if ln.rstrip().endswith("FLOW-LED"):
            g = re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)", ln)
            if g:
                ep = int(dt.datetime.strptime("2026-" + g.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())
                runs.append({"ep": ep, "d": 1.0 if g.group(2) == "UP" else -1.0})

    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo = int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0])
    hi = int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])
    bstart = int(con.execute("SELECT min(ts_ms) FROM c.book WHERE symbol='MNQ'").fetchone()[0])
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

    def is_run(ts_s, d):
        return any(r["d"] == d and (r["ep"] - WIN_PRE) <= ts_s <= (r["ep"] + WIN_POST) for r in runs)

    def exit_pnl(ei, d):
        entry_px = tpx[ei]
        peak, armed, entry_ts, j = 0.0, False, int(tts[ei]), ei + 1
        while j < len(tts):
            px, t = tpx[j], int(tts[j])
            fav = (px - entry_px) * d
            if -fav >= STOP:
                return -STOP * VPP - FEE
            if fav > peak:
                peak = fav
            if not armed and peak >= ARM:
                armed = True
            if armed and (peak - fav) >= TRAIL:
                return fav * VPP - FEE
            if t - entry_ts >= HOLD_CAP * 1000:
                return fav * VPP - FEE
            j += 1
        return (tpx[-1] - entry_px) * d * VPP - FEE

    ev = []          # (sig_ms, brk_ms, d, is_run_or_win)
    i, n = 1, len(secs)
    while i < n:
        if over[i] and not over[i - 1]:
            d = 1.0 if F[i] > 0 else -1.0
            si = int(np.searchsorted(tts, (secs[i] + 1) * 1000, "left"))
            if si >= len(tts):
                break
            sig_px, sig_ts, ei, j = tpx[si], int(tts[si]), -1, si + 1
            while j < len(tts):
                fav = (tpx[j] - sig_px) * d
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
            if sig_ts >= bstart:
                ran = is_run(int(secs[i]), d) or exit_pnl(ei, d) > 0
                ev.append((sig_ts, brk_ts, d, ran))
            while i < n and secs[i] <= brk_ts // 1000:
                i += 1
            continue
        i += 1

    # ASOF the top-3 depth at every signal + break timestamp
    con.execute("CREATE TABLE snap AS SELECT ts_ms, COALESCE(SUM(CASE WHEN side='bid' THEN size END),0) bid, "
                "COALESCE(SUM(CASE WHEN side='ask' THEN size END),0) ask FROM c.book WHERE symbol='MNQ' "
                "AND level<=3 GROUP BY ts_ms HAVING bid>0 AND ask>0")
    q = pd.DataFrame({"qid": range(len(ev) * 2),
                      "ts": [e[0] for e in ev] + [e[1] for e in ev]})
    con.register("q", q)
    dep = con.execute("SELECT q.qid, s.bid, s.ask FROM q ASOF JOIN snap s ON s.ts_ms <= q.ts").df()
    con.close()
    dmap = {int(r.qid): (r.bid, r.ask) for r in dep.itertuples()}

    ran_rows, rev_rows = [], []
    for k, (sig_ts, brk_ts, d, ran) in enumerate(ev):
        if k not in dmap or (k + len(ev)) not in dmap:
            continue
        bs, as_ = dmap[k]
        bb, ab = dmap[k + len(ev)]
        far0 = (as_ if d > 0 else bs)
        far1 = (ab if d > 0 else bb)
        if far0 <= 0:
            continue
        row = {"far_chg_pct": 100 * (far1 - far0) / far0,          # >0 = far side REFILLED during push (absorb)
               "far0": far0, "far1": far1}
        (ran_rows if ran else rev_rows).append(row)

    print(f"BOOK DURING BREAK (M={M:.0f}pt, book-covered breakouts) — far side refill vs vanish\n")
    print(f"  RAN/won: {len(ran_rows)}   REVERTED/lost: {len(rev_rows)}\n")
    print(f"  {'feature':>28}{'RAN median':>13}{'REVERTED median':>18}{'separates?':>12}")
    for name, k in [("far-side depth at signal", "far0"), ("far-side depth at +M", "far1"),
                    ("far-side change during break %", "far_chg_pct")]:
        a = np.array([r[k] for r in ran_rows], float)
        b = np.array([r[k] for r in rev_rows], float)
        if len(a) < 3 or len(b) < 3:
            continue
        ma, mb = np.median(a), np.median(b)
        sep = "← YES" if abs(ma - mb) > 0.25 * (abs(mb) + 1e-9) else ""
        print(f"  {name:>28}{ma:>13.1f}{mb:>18.1f}{sep:>12}")
    print("\n(if 'far-side change during break' diverges — runs' far side VANISHES (neg) while pops' REFILLS "
          "(pos) — that's the order-flow discriminator to add to the breakout-confirm. flat = the book "
          "responds the same to a run and a pop. ⚠ book only from 07-21, small n, in-sample.)")


if __name__ == "__main__":
    main()
