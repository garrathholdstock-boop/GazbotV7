#!/usr/bin/env python3
"""V7 RUN CENSUS — the Friday report's "big runs → did we show up?" engine (MNQ, L1+L2 deep).

Reproduces the V5 footprint_scorecard `missed` census on the LIVE V7 data (the V5 tool is hardcoded
to the retired alphabot.db/ticks.db). Cold, tape-first: ignores what the desk did mid-week and asks
where the money was and whether we showed up. A "big run" = a 15-min close-to-close move >= min_atr ×
MNQ's TYPICAL 15-min range (median hi-lo). FULL census, every run, no top-N cap (the thing 07-17
dropped). Per run: direction, move, $ 1-lot ceiling, participation (which GATE fired + its real $),
net aggressor FLOW (ticks), pre-run amplitude, L2 far-side depletion (book), and a cause-CLUSTER.

Data (gazbot7): capture.db (bars 5s · ticks aggressor · book L2 depth) + gazbot7.db (trades: gate/
side/pnl for participation). DuckDB. Read-only. Feeds the report's closing greenfield section.

  PYTHONPATH=src python scripts/run_census.py [--days 7] [--min-atr 1.5]
"""
from __future__ import annotations

import argparse
import datetime as dt

import duckdb

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
VPP = 2.0   # MNQ $/point (1 lot)
W = 180     # 15-min window in 5s bars
STEP = 12   # slide every 60s


def cluster(hour, flow, mv, amp):
    if 13 <= hour < 15:
        return "OPEN/NEWS"
    if flow is not None and abs(flow) > 50 and (flow > 0) == (mv > 0):
        return "FLOW-LED"
    if flow is not None and abs(flow) > 50 and (flow > 0) != (mv > 0):
        return "VACUUM"
    if amp is not None and amp > 0.30:
        return "VOL-EXPANSION"
    return "UNCLASS"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-atr", type=float, default=1.5)
    a = ap.parse_args()
    t1 = dt.datetime.now(dt.UTC).timestamp()
    t0 = t1 - a.days * 86400

    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    bars = con.execute(f"""
        SELECT bar_ts, open, high, low, close FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={t0} AND bar_ts<={t1} ORDER BY bar_ts""").fetchall()
    if len(bars) < 400:
        print("too few 5s bars")
        return
    trades = con.execute(f"""
        SELECT epoch(opened_at::TIMESTAMPTZ) te, side, gate, pnl_usd FROM g.trades
        WHERE symbol='MNQ' AND epoch(opened_at::TIMESTAMPTZ)>={t0 - 600} ORDER BY te""").fetchall()

    # typical 15-min range (the ATR-like unit) + threshold
    rng = [max(x[2] for x in bars[i:i + W]) - min(x[3] for x in bars[i:i + W]) for i in range(0, len(bars) - W, STEP)]
    typ = sorted(rng)[len(rng) // 2] if rng else 0.0
    thr = a.min_atr * typ
    # candidate runs (15-min move >= thr), dedup overlaps keep-strongest
    cands = sorted(((abs(bars[i + W][4] - bars[i][4]), i, bars[i + W][4] - bars[i][4])
                    for i in range(0, len(bars) - W, STEP) if abs(bars[i + W][4] - bars[i][4]) >= thr),
                   reverse=True)
    runs, used = [], []
    for _, i, mv in cands:
        if not any(abs(i - j) < W for j in used):
            used.append(i)
            runs.append((i, mv))
    runs.sort()

    def flow_at(ts):  # net aggressor (buy-sell) in the 60s before the run
        r = con.execute(f"""SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END),0)
            FROM c.ticks WHERE symbol='MNQ' AND ts_ms<{ts * 1000} AND ts_ms>={(ts - 60) * 1000}""").fetchone()[0]
        return r

    def book_depletion(ts, direction):  # far-side (the side price ran toward) depth vs near-side, pre-run
        row = con.execute(f"""
            WITH b AS (SELECT side, size FROM c.book WHERE symbol='MNQ' AND ts_ms<{ts * 1000}
                       AND ts_ms>={(ts - 30) * 1000} AND level<=3)
            SELECT COALESCE(SUM(CASE WHEN side='bid' THEN size END),0), COALESCE(SUM(CASE WHEN side='ask' THEN size END),0) FROM b""").fetchone()
        bid, ask = row
        far = ask if direction == "UP" else bid   # price ran UP → into the asks
        near = bid if direction == "UP" else ask
        if far + near == 0:
            return None
        return far / (far + near)   # <0.5 = far side thin (depleted) = telegraphed the run

    print(f"═══ MNQ RUN CENSUS — last {a.days}d · {len(runs)} runs ≥ {a.min_atr}×ATR "
          f"(15-min move ≥ {thr:.0f}pt; typical 15m range = {typ:.0f}pt) ═══\n")
    caught = fought = sat = 0
    ceil_caught = real_caught = ceil_fought = real_fought = ceil_sat = 0.0
    gate_pnl = {}
    print(f"{'time UTC':<14}{'dir':>4}{'move':>7}{'$ceil':>7}  {'us':<8}{'gate':<14}{'real$':>7}{'flow':>7}{'amp%':>6}  {'book':>5}  cluster")
    for i, mv in runs:
        b0 = bars[i]
        start = b0[0]
        direction = "UP" if mv > 0 else "DN"
        ceil = abs(mv) * VPP
        lo, hi = start - 300, start + 300
        near_trades = [(sd, gt, p) for te, sd, gt, p in trades if lo <= te <= hi]
        took = [(gt, p) for sd, gt, p in near_trades
                if (sd in ("LONG", "BUY") and mv > 0) or (sd in ("SHORT", "SELL") and mv < 0)]
        against = [(gt, p) for sd, gt, p in near_trades
                   if (sd in ("LONG", "BUY") and mv < 0) or (sd in ("SHORT", "SELL") and mv > 0)]
        flow = flow_at(start)
        seg = bars[max(0, i - 60):i]
        amp = (100 * (max(x[2] for x in seg) - min(x[3] for x in seg)) / b0[4]) if seg and b0[4] else None
        hour = dt.datetime.fromtimestamp(start, dt.UTC).hour
        cl = cluster(hour, flow, mv, amp)
        book = book_depletion(start, direction)
        if took:
            us, gate = "caught", took[0][0]
            realv = sum(p for _, p in took)
            caught += 1
            ceil_caught += ceil
            real_caught += realv
        elif against:
            us, gate = "FOUGHT", against[0][0]
            realv = sum(p for _, p in against)
            fought += 1
            ceil_fought += ceil
            real_fought += realv
        else:
            us, gate, realv = "sat out", "—", 0.0
            sat += 1
            ceil_sat += ceil
        for gt, p in took + against:
            gate_pnl[gt] = gate_pnl.get(gt, 0.0) + p
        tm = dt.datetime.fromtimestamp(start, dt.UTC).strftime("%m-%d %H:%M")
        bs = f"{book:.2f}" if book is not None else "  —"
        fs = f"{flow:+.0f}" if flow is not None else "  —"
        as_ = f"{amp:.2f}" if amp is not None else "  —"
        print(f"{tm:<14}{direction:>4}{mv:>+7.0f}{ceil:>7.0f}  {us:<8}{gate:<14}{realv:>+7.0f}{fs:>7}{as_:>6}  {bs:>5}  {cl}")

    print("\n── CLUSTERS ──")
    cc = {}
    for i, mv in runs:
        b0 = bars[i]
        f = flow_at(b0[0])
        seg = bars[max(0, i - 60):i]
        amp = (100 * (max(x[2] for x in seg) - min(x[3] for x in seg)) / b0[4]) if seg and b0[4] else None
        cl = cluster(dt.datetime.fromtimestamp(b0[0], dt.UTC).hour, f, mv, amp)
        cc[cl] = cc.get(cl, 0) + 1
    for cl, n in sorted(cc.items(), key=lambda x: -x[1]):
        print(f"   {cl:<14} {n:>3} runs")

    print("\n── HONEST MONEY (ceiling = hindsight 1-lot; real = what a gate actually banked) ──")
    print(f"   CAUGHT  {caught:>3} runs · ceiling ${ceil_caught:>6.0f} · real ${real_caught:>+6.0f}"
          f"  ({100*real_caught/ceil_caught if ceil_caught else 0:.0f}% of ceiling)")
    print(f"   FOUGHT  {fought:>3} runs · ceiling ${ceil_fought:>6.0f} · real ${real_fought:>+6.0f}")
    print(f"   SAT OUT {sat:>3} runs · ceiling ${ceil_sat:>6.0f} · real $     0  ← the money on the table")
    print("\n── real $ by gate (near the runs) ──")
    for gt, p in sorted(gate_pnl.items(), key=lambda x: x[1]):
        print(f"   {gt:<16} ${p:>+7.0f}")
    con.close()


if __name__ == "__main__":
    main()
