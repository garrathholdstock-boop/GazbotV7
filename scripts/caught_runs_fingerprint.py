#!/usr/bin/env python3
"""Fingerprint the FLOW-LED big runs the flow signal caught (15/17) — what does the tape look like
JUST BEFORE entry? ER, ATR, 60s flow, pre-run amplitude, far-side book share — per run + the summary.
If the winners share a distinctive pre-entry signature, THAT is the filter to isolate them from the
1,465 look-alikes (the losers were uniform on ER/ATR alone, so the tell is likely a COMBINATION).

Runs from the frozen census (reports/friday_v7/sections/census_stdout.txt), FLOW-LED cluster. Metrics
recomputed fresh at each run-start minute from capture.db. Baseline = median over all covered minutes.

  PYTHONPATH=src python scripts/caught_runs_fingerprint.py
"""
from __future__ import annotations

import datetime as dt
import re

import duckdb
import numpy as np

CAP = "/home/alphabot/gazbot7/data/capture.db"
CENSUS = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"


def main():
    # 1. parse the FLOW-LED run rows (time, dir, move, us) from the frozen census
    runs = []
    for ln in open(CENSUS):
        if not ln.rstrip().endswith("FLOW-LED"):
            continue
        m = re.match(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]?\d+)\s+\d+\s+(caught|FOUGHT|sat out)", ln)
        if not m:
            continue
        tm, d, mv, us = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        ep = int(dt.datetime.strptime("2026-" + tm, "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())
        runs.append({"tm": tm, "dir": d, "mv": mv, "us": us, "ep": ep})
    if not runs:
        print("no FLOW-LED runs parsed — check census_stdout.txt")
        return

    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo = min(r["ep"] for r in runs) - 3600
    hi = max(r["ep"] for r in runs) + 600
    # 1-min OHLC → ER(30) + ATR(14) per minute
    bdf = con.execute(f"""
        WITH b AS (SELECT (bar_ts-bar_ts%60) m, max(high) h, min(low) l, arg_max(close,bar_ts) cl, SUM(volume) v
                   FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={lo-5400} AND bar_ts<{hi} GROUP BY 1)
        SELECT m, h, l, cl, v FROM b ORDER BY m""").df()
    mins = bdf.m.values.astype(np.int64)
    cls, hh, ll = bdf.cl.values.astype(float), bdf.h.values.astype(float), bdf.l.values.astype(float)
    vv = bdf.v.values.astype(float)
    idx = {int(mn): i for i, mn in enumerate(mins)}
    tr = np.zeros(len(mins))
    for i in range(1, len(mins)):
        tr[i] = max(hh[i] - ll[i], abs(hh[i] - cls[i - 1]), abs(ll[i] - cls[i - 1]))
    v5 = np.array([vv[max(0, i - 4):i + 1].sum() for i in range(len(mins))])   # trailing 5-min volume

    def er_atr_amp(ep):
        m = ep - ep % 60
        i = idx.get(int(m))
        if i is None or i < 30:
            return None, None, None, None
        seg = cls[i - 30:i + 1]
        tot = np.abs(np.diff(seg)).sum()
        er = (abs(seg[-1] - seg[0]) / tot) if tot > 0 else 0.0
        atr = float(tr[i - 13:i + 1].mean()) if i >= 14 else None
        amp = (float(hh[i - 60:i].max() - ll[i - 60:i].min()) / atr) if (i >= 60 and atr) else None
        # RVOL = trailing-5min volume vs the median trailing-5min volume over the prior 60 min
        base = np.median(v5[i - 60:i]) if i >= 60 else np.median(v5[max(0, i - 20):i]) if i >= 20 else None
        rvol = (v5[i] / base) if (base and base > 0) else None
        return er, atr, amp, rvol

    def flow60(ep):
        r = con.execute(f"""SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell'
            THEN -size END),0) FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={(ep-60)*1000} AND ts_ms<{ep*1000}""").fetchone()[0]
        return float(r)

    def book_share(ep, d):
        r = con.execute(f"""WITH b AS (SELECT side,size FROM c.book WHERE symbol='MNQ'
            AND ts_ms<{ep*1000} AND ts_ms>={(ep-30)*1000} AND level<=3)
            SELECT COALESCE(SUM(CASE WHEN side='bid' THEN size END),0),
                   COALESCE(SUM(CASE WHEN side='ask' THEN size END),0) FROM b""").fetchone()
        bid, ask = r
        far = ask if d == "UP" else bid
        near = bid if d == "UP" else ask
        return (far / (far + near)) if (far + near) else None

    # 2. per-run fingerprint
    print(f"FLOW-LED big runs — pre-entry fingerprint ({len(runs)} runs; the flow signal caught ~15)\n")
    print(f"  {'time UTC':<12}{'dir':>4}{'move':>6}{'ER':>6}{'ATR':>6}{'RVOL':>6}{'flow60':>8}{'amp':>6}{'far-bk':>8}{'us':>9}")
    for r in runs:
        er, atr, amp, rvol = er_atr_amp(r["ep"])
        fl = flow60(r["ep"])
        bk = book_share(r["ep"], r["dir"])
        r.update(er=er, atr=atr, amp=amp, rvol=rvol, flow=fl, book=bk)
        print(f"  {r['tm']:<12}{r['dir']:>4}{r['mv']:>+6}{_f(er,2):>6}{_f(atr,0):>6}{_f(rvol,1):>6}"
              f"{_f(fl,0,True):>8}{_f(amp,2):>6}{_f(bk,2):>8}{r['us']:>9}")

    # 3. summary vs baseline
    def summ(key, fmt="{:.2f}"):
        vals = [r[key] for r in runs if r.get(key) is not None]
        if not vals:
            return "n/a"
        vals = np.array(vals, float)
        return f"med {fmt.format(np.median(vals))} · IQR {fmt.format(np.percentile(vals,25))}–{fmt.format(np.percentile(vals,75))} · rng {fmt.format(vals.min())}–{fmt.format(vals.max())}"

    # tape-wide baselines (median ER / ATR over all covered minutes)
    er_all = [(abs(cls[i]-cls[i-30])/max(np.abs(np.diff(cls[i-30:i+1])).sum(),1e-9)) for i in range(30, len(mins))]
    atr_all = [float(tr[i-13:i+1].mean()) for i in range(14, len(mins))]
    print("\n  ── the winners' signature vs the whole tape ──")
    rvol_all = [v5[i] / np.median(v5[i - 60:i]) for i in range(60, len(mins)) if np.median(v5[i - 60:i]) > 0]
    print(f"  ER    : {summ('er')}   |  tape median {np.median(er_all):.2f}")
    print(f"  ATR   : {summ('atr','{:.0f}')}pt   |  tape median {np.median(atr_all):.0f}pt")
    print(f"  RVOL  : {summ('rvol','{:.1f}')}x   |  tape median {np.median(rvol_all):.1f}x  (>1 = busier than recent)")
    print(f"  flow60: {summ('flow','{:+.0f}')}   (aligned with dir by construction)")
    print(f"  amp   : {summ('amp')}")
    print(f"  far-book share: {summ('book')}   (<0.50 = far side thin)")
    con.close()
    print("\n(look for what CLUSTERS: if the winners share e.g. high ATR + thin far-book + strong flow but "
          "the losers don't, that COMBINATION is the filter the single-axis sweeps missed. ⚠ ~1wk, small n.)")


def _f(v, nd, sign=False):
    if v is None:
        return "—"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


if __name__ == "__main__":
    main()
