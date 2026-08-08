#!/usr/bin/env python3
"""FULL-WINDOW (3-week, 07-05..07-24) MNQ "big runs" census — READ-ONLY, do NOT commit.

Extends scripts/run_census.py (the 1-week Friday-report engine) over the whole archive window using the
shared 3-week loader archive_data.py. Reuses run_census's detection / cluster() / book / ceiling logic,
but on the loader's 1-MINUTE bars (run_census uses 5s bars) so run counts won't match exactly — this is
reported as a 1-min-bar census. Granularity note is printed.

  detection : a run = a 15-min close-to-close move >= min_atr x MNQ's TYPICAL 15-min range (median hi-lo),
              same unit as run_census. On 1-min bars: W=15 bars, slide 1 bar (60s). Gap-guarded (a 15-bar
              window must span <= 20 real minutes, else it straddles an overnight/weekend gap -> dropped).
  cluster() : copied verbatim from run_census (hour+flow+amp -> OPEN/NEWS / VACUUM / FLOW-LED /
              VOL-EXPANSION / UNCLASS).
  book      : far-side top-3 depth share, 30s pre-run. 07-09+ from depth.db (richer, 10 lvl, thru 07-24);
              runs before 07-09 have no book -> "-".
  particip. : gazbot7.db trades cover the V7 live period only. Per the task, caught/fought is computed
              ONLY for runs on/after 07-19; every run before 07-19 is "sat out" (no live V7 desk).

  /home/alphabot/gazbot7/.venv/bin/python scripts/run_census_full.py [--min-atr 1.5]
"""
from __future__ import annotations
import argparse, datetime as dt, sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import numpy as np
import duckdb
import archive_data as A

DEPTH = "/home/alphabot/gazbot7/data/depth.db"
GDB = "/home/alphabot/gazbot7/data/gazbot7.db"
VPP = 2.0                 # MNQ $/point (1 lot)
W = 15                    # 15-min window in 1-min bars
GAP_MAX = 20 * 60         # a W-bar window must span <= 20 real minutes (else it straddles a gap)
AMP_PRE = 5               # pre-run amplitude window (min) = 5 x 1-min bars
DEPTH_START = dt.datetime(2026, 7, 9, tzinfo=dt.UTC).timestamp()   # depth.db book coverage begins
LIVE_START = dt.datetime(2026, 7, 19, tzinfo=dt.UTC).timestamp()   # V7 live participation begins


FLOW_Z = 1.0                  # ★2026-08-01: |z| >= this is a real flow event (was: raw |flow| > 50)
FLOW_Z_LOOKBACK = 2 * 3600    # standardise against the trailing 2 hours of the SAME statistic
FLOW_Z_MIN_BUCKETS = 30       # need >= 30 one-minute buckets of history before a z means anything


def cluster(hour, flow, mv, amp, fz=None):   # keep in sync with run_census.py
    """★2026-08-01 FIX — the flow test is a Z-SCORE now, not a raw threshold.

    The old rule (`abs(flow) > 50`) fired on 66.5% of ALL bars, making FLOW-LED and VACUUM two names
    for one coin and splitting the tape into 21/17 runs that meant nothing. 50 contracts of net
    aggressor flow in 60s is unremarkable on MNQ — the desk's own measurement is ~2,664 contracts a
    minute — so the threshold labelled ordinary tape as an event. Standardising against the trailing
    2 hours asks what was intended: is THIS minute's flow unusual *for right now*?

    `flow` is still used for its SIGN (does flow agree with the move); `fz` carries the magnitude
    test. fz=None (insufficient history) withholds the flow verdict and falls through — better
    UNCLASS than a fake label. Revert: drop fz, restore `abs(flow) > 50`."""
    if 13 <= hour < 15:
        return "OPEN/NEWS"
    if flow is not None and fz is not None and abs(fz) >= FLOW_Z:
        return "FLOW-LED" if (flow > 0) == (mv > 0) else "VACUUM"
    if amp is not None and amp > 0.30:
        return "VOL-EXPANSION"
    return "UNCLASS"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-atr", type=float, default=1.5)
    a = ap.parse_args()

    D = A.load()
    mins, cls, hh, ll = D.mins, D.cls, D.hh, D.ll
    s0 = D.s0
    N = len(mins)

    # typical 15-min range (the ATR-like unit), over gap-clean windows only
    rng = []
    for i in range(0, N - W):
        if mins[i + W] - mins[i] <= GAP_MAX:
            rng.append(hh[i:i + W + 1].max() - ll[i:i + W + 1].min())
    typ = float(np.median(rng)) if rng else 0.0
    thr = a.min_atr * typ

    # candidate runs: gap-clean 15-min move >= thr, dedup overlaps keep-strongest
    cands = []
    for i in range(0, N - W):
        if mins[i + W] - mins[i] > GAP_MAX:
            continue
        mv = cls[i + W] - cls[i]
        if abs(mv) >= thr:
            cands.append((abs(mv), i, mv))
    cands.sort(reverse=True)
    runs, used = [], []
    for _, i, mv in cands:
        if not any(abs(i - j) < W for j in used):
            used.append(i)
            runs.append((i, mv))
    runs.sort()

    # ---- flow / amp helpers on the per-second arrays ----
    flow = D.flow

    def flow_pre(start):        # net aggressor (buy-sell) in the 60s before the run start
        k = int(start - s0)
        if k <= 0:
            return None
        return float(flow[max(0, k - 60):k].sum())

    def flow_z_pre(start, cur):
        """★2026-08-01 — standardise `cur` (the 60s net-aggressor sum) against the distribution of the
        SAME statistic over the trailing FLOW_Z_LOOKBACK. Non-overlapping 60s buckets so the comparison
        population is like-for-like with the value being scored. None => not enough history or a
        degenerate spread; cluster() then withholds a flow verdict rather than inventing one."""
        if cur is None:
            return None
        k = int(start - s0)
        lo = k - FLOW_Z_LOOKBACK
        if lo < 0:
            return None
        win = flow[lo:k]
        nb = win.size // 60
        if nb < FLOW_Z_MIN_BUCKETS:
            return None
        buckets = win[:nb * 60].reshape(nb, 60).sum(axis=1)
        sd = float(buckets.std(ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            return None
        return (cur - float(buckets.mean())) / sd

    def amp_pre(i):             # pre-run amplitude % over AMP_PRE 1-min bars
        j0 = max(0, i - AMP_PRE)
        if j0 >= i or cls[i] == 0:
            return None
        return float(100 * (hh[j0:i].max() - ll[j0:i].min()) / cls[i])

    # ---- book (far-side top-3 depth share) from depth.db, 07-09+ ----
    dcon = duckdb.connect()
    dcon.execute(f"ATTACH '{DEPTH}' AS d (TYPE sqlite, READ_ONLY)")

    def book_far(start, direction):
        if start < DEPTH_START:
            return None
        lo, hiw = int((start - 30) * 1000), int(start * 1000)
        row = dcon.execute(f"""
            SELECT COALESCE(SUM(bid1s+bid2s+bid3s),0), COALESCE(SUM(ask1s+ask2s+ask3s),0)
            FROM d.depth_snap WHERE symbol='MNQ' AND ts_ms>={lo} AND ts_ms<{hiw}""").fetchone()
        bid, ask = row
        far = ask if direction == "UP" else bid     # price ran UP -> into the asks
        near = bid if direction == "UP" else ask
        if far + near == 0:
            return None
        return far / (far + near)                    # <0.5 = far side thin (depleted) = telegraphed

    # ---- trades (V7 live) ----
    tcon = duckdb.connect()
    tcon.execute(f"ATTACH '{GDB}' AS g (TYPE sqlite, READ_ONLY)")
    trades = tcon.execute("""
        SELECT epoch(opened_at::TIMESTAMPTZ) te, side, gate, pnl_usd FROM g.trades
        WHERE symbol='MNQ' ORDER BY te""").fetchall()
    tcon.close()

    print(f"=== MNQ RUN CENSUS (FULL 3-week 07-05..07-24, 1-min bars) - {len(runs)} runs >= {a.min_atr}xATR ===")
    print(f"    (15-min move >= {thr:.0f}pt; typical 15m range = {typ:.0f}pt; gap-guarded; "
          f"granularity=1-min NOT run_census's 5s -> counts differ by design)\n")

    caught = fought = sat = 0
    ceil_caught = real_caught = ceil_fought = real_fought = ceil_sat = 0.0
    cc = {}
    per_day = {}
    crows = []
    print(f"{'time UTC':<14}{'dir':>4}{'move':>7}{'$ceil':>7}  {'us':<8}{'gate':<14}{'real$':>7}{'flow':>8}{'amp%':>7}  {'book':>5}  cluster")
    for i, mv in runs:
        start = int(mins[i])
        direction = "UP" if mv > 0 else "DN"
        ceil = abs(mv) * VPP
        f = flow_pre(start)
        amp = amp_pre(i)
        hour = dt.datetime.fromtimestamp(start, dt.UTC).hour
        cl = cluster(hour, f, mv, amp, flow_z_pre(start, f))
        cc[cl] = cc.get(cl, 0) + 1
        day = dt.datetime.fromtimestamp(start, dt.UTC).strftime("%m-%d")
        per_day[day] = per_day.get(day, 0) + 1
        book = book_far(start, direction)

        # participation only in the V7 live window
        us, gate, realv = "sat out", "-", 0.0
        if start >= LIVE_START:
            lo, hiw = start - 300, start + 300
            near = [(sd, gt, p) for te, sd, gt, p in trades if lo <= te <= hiw]
            took = [(gt, p) for sd, gt, p in near if (sd == "LONG" and mv > 0) or (sd == "SHORT" and mv < 0)]
            against = [(gt, p) for sd, gt, p in near if (sd == "LONG" and mv < 0) or (sd == "SHORT" and mv > 0)]
            if took:
                us, gate, realv = "caught", took[0][0], sum(p for _, p in took)
                caught += 1; ceil_caught += ceil; real_caught += realv
            elif against:
                us, gate, realv = "FOUGHT", against[0][0], sum(p for _, p in against)
                fought += 1; ceil_fought += ceil; real_fought += realv
            else:
                sat += 1; ceil_sat += ceil
        else:
            sat += 1; ceil_sat += ceil

        tm = dt.datetime.fromtimestamp(start, dt.UTC).strftime("%m-%d %H:%M")
        bs = f"{book:.2f}" if book is not None else "  -"
        fs = f"{f:+.0f}" if f is not None else "  -"
        as_ = f"{amp:.2f}" if amp is not None else "  -"
        print(f"{tm:<14}{direction:>4}{mv:>+7.0f}{ceil:>7.0f}  {us:<8}{gate:<14}{realv:>+7.0f}{fs:>8}{as_:>7}  {bs:>5}  {cl}")
        crows.append((start, tm, direction, mv, ceil, us, gate, realv, f, amp, book, cl, day))

    print("\n-- CLUSTERS (full 3-week) --")
    for cl, n in sorted(cc.items(), key=lambda x: -x[1]):
        print(f"   {cl:<14} {n:>3} runs")

    print("\n-- RUNS PER DAY --")
    for day in sorted(per_day):
        print(f"   {day}  {per_day[day]:>2}  {'#'*per_day[day]}")

    print("\n-- TOP 15 RUNS BY MOVE (pts) --")
    print(f"   {'time UTC':<14}{'dir':>4}{'move':>7}{'$ceil':>7}  {'far-book':>8}  cluster")
    for start, tm, d, mv, ceil, us, gate, realv, f, amp, book, cl, day in sorted(crows, key=lambda r: -abs(r[3]))[:15]:
        bs = f"{book:.2f}" if book is not None else "   -"
        print(f"   {tm:<14}{d:>4}{mv:>+7.0f}{ceil:>7.0f}  {bs:>8}  {cl}")

    print("\n-- HONEST MONEY (ceiling = hindsight 1-lot; real = what a gate banked; particip. 07-19+ only) --")
    print(f"   CAUGHT  {caught:>3} runs - ceiling ${ceil_caught:>7.0f} - real ${real_caught:>+7.0f}"
          f"  ({100*real_caught/ceil_caught if ceil_caught else 0:.0f}% of ceiling)")
    print(f"   FOUGHT  {fought:>3} runs - ceiling ${ceil_fought:>7.0f} - real ${real_fought:>+7.0f}")
    print(f"   SAT OUT {sat:>3} runs - ceiling ${ceil_sat:>7.0f} - real $      0  <- money on the table")
    print(f"\n   [note] trades table also has early paper trades 07-16..07-18; per task these runs are counted SAT OUT.")

    # book-depletion signature on the bigger sample
    bks = [r[10] for r in crows if r[10] is not None]
    thin = sum(1 for b in bks if b < 0.5)
    print(f"\n-- BOOK-DEPLETION SIGNATURE (07-09+ runs w/ book, n={len(bks)}) --")
    if bks:
        print(f"   far-side share <0.50 (thin/telegraphed): {thin}/{len(bks)} ({100*thin/len(bks):.0f}%)  median far-share={np.median(bks):.2f}")
    dcon.close()


if __name__ == "__main__":
    main()
