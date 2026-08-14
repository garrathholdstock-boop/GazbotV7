#!/usr/bin/env python3
"""MGC RUN CATCHER — find the week's biggest runs, then build a gate that boards them early.

    PYTHONPATH=src .venv/bin/python scripts/mgc_run_catcher.py [--days 7] [--top 5] [--gate]

Operator, 2026-08-14: *"mgc runs are usually strong and smooth. i refuse to believe we cant have a
momentum gate. it just needs to be switched off by the router until conditions are favourable. grab
mgcs top 5 runs this week. analyse them. build a gate that will jump in on the first 20% of the run.
then look at how we can filter it to discard as much other crap as possible."*

★ HE IS ARGUING WITH THE RIGHT HALF OF THE RECORD. Catching gold's runs is a SOLVED problem — the
existing thrust-continuation gate fired during **22 of 22** big runs, median 3 minutes in, with 76%
of the move still available. What killed every gold momentum attempt was never the boarding; it was
that the same trigger fires on ordinary tape and *"the losers are indistinguishable"* (ATR d=+0.21,
ER d=+0.12, thrust size d=+0.02). And the one thing in the whole gold investigation that survived a
robustness test was the ORACLE DAY-FILTER — given foresight of which days contain a run, +$779 with
strip-best-day +$356. That is precisely the operator's "let the router switch it off". So the
question this script asks is NOT "can we board a run" (yes) but:

    **how much of the non-run firing can be discarded, and can the discard rule be computed CAUSALLY?**

★ THREE RULES THIS FILE OBEYS, because they are where the previous attempts died:

 1. **Every filter is computed from information available BEFORE the entry.** A day-filter that peeks
    at the day's range is an oracle and will look wonderful. Where an oracle is shown it is LABELLED
    as an upper bound, never as a result.
 2. **Every filter is PLACEBO-CONTROLLED against discarding the same NUMBER of trades at random.**
    Removing 40% of trades looks brilliant whenever the removed 40% lost.
 3. **The bar-label look-ahead is fixed here from the start**: `resample` stamps a bar with its LEFT
    edge, so a signal read off a bar's close must enter at `ts + 60s`. Getting this wrong halved a
    result on this same tape today.

Costs: MGC is $10/pt (NOT MNQ's $2), fee $1.50/RT. Exits raced on TICKS.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from mgc_session_anchor import Trade, atr, load, minute_bars, race, score  # noqa: E402

VPP, FEE_RT = 10.0, 1.50
RUN_MIN_USD = 300.0        # a "run" is worth trading only if it is worth >= this gross, 1 lot
RETRACE_FRAC = 0.34        # a leg ends when it gives back this much of its extent


def find_runs(m: pd.DataFrame) -> pd.DataFrame:
    """Maximal directional legs, ended by a RETRACEMENT — not by a fixed clock.

    A run is a leg from a swing extreme to the opposite extreme that never gives back more than
    RETRACE_FRAC of its own extent while it is alive. That definition is deliberately about SHAPE
    (how smooth), not duration, because the operator's claim is that gold's runs are *smooth*.
    """
    px = m["close"].to_numpy()
    ts = m.index
    runs = []
    i = 0
    n = len(px)
    while i < n - 1:
        for direction in (1, -1):
            j, ext, ext_j = i + 1, px[i], i
            while j < n:
                if direction * (px[j] - ext) > 0:
                    ext, ext_j = px[j], j
                give = direction * (ext - px[j])
                move = direction * (ext - px[i])
                if move > 0 and give > RETRACE_FRAC * move:
                    break
                j += 1
            move = direction * (ext - px[i])
            if move * VPP >= RUN_MIN_USD:
                runs.append({
                    "start": ts[i], "end": ts[ext_j], "dir": direction,
                    "start_px": float(px[i]), "end_px": float(ext),
                    "pts": float(move), "usd": float(move * VPP),
                    "mins": (ts[ext_j] - ts[i]).total_seconds() / 60.0,
                })
        i += 1
    if not runs:
        return pd.DataFrame()
    r = pd.DataFrame(runs).sort_values("usd", ascending=False)
    # de-overlap: keep the biggest, drop anything sharing time with an already-kept run
    keep = []
    for _, row in r.iterrows():
        if all(row["end"] <= k["start"] or row["start"] >= k["end"] for k in keep):
            keep.append(row)
    return pd.DataFrame(keep).sort_values("usd", ascending=False).reset_index(drop=True)


def anatomy(m: pd.DataFrame, run: pd.Series) -> dict:
    """What did the FIRST 20% of this run look like, and what preceded it?"""
    a = atr(m)
    pre = m.loc[:run["start"]].tail(60)
    mark = run["start_px"] + run["dir"] * 0.20 * run["pts"]
    leg = m.loc[run["start"]:run["end"]]
    hit = leg[(leg["close"] - run["start_px"]) * run["dir"] >= 0.20 * run["pts"]]
    t20 = hit.index[0] if len(hit) else None
    atr_at = float(a.loc[:run["start"]].dropna().iloc[-1]) if len(a.loc[:run["start"]].dropna()) else np.nan
    pre_rng = float(pre["high"].max() - pre["low"].min()) if len(pre) else np.nan
    path = float(leg["close"].diff().abs().sum())
    return {
        "atr_at_start": atr_at,
        "pre60_range_pt": pre_rng,
        "pre60_range_atr": pre_rng / atr_at if atr_at else np.nan,
        "mins_to_20pct": (t20 - run["start"]).total_seconds() / 60.0 if t20 is not None else np.nan,
        "smoothness_ER": abs(run["pts"]) / path if path else np.nan,
        "pts_per_min": run["pts"] / max(run["mins"], 1.0),
        "t20": t20, "mark20": mark,
    }


# ── the gate ─────────────────────────────────────────────────────────────────
THRUST_MIN = 20      # the impulse window, minutes
STOP_ATR = 1.5
TRAIL_ATR = 2.5
CAP_MIN = 180
MIN_GAP_MIN = 45


def gate_signals(m: pd.DataFrame, *, thrust_atr: float, er_min: float,
                 expand_min: float) -> list[tuple]:
    """Board a move already underway: a THRUST_MIN impulse of >= thrust_atr ATR, moving efficiently
    (ER >= er_min) on EXPANDING volatility (>= expand_min x the prior norm).

    Every term is causal: all three are measured over the window ENDING at the signal bar, and the
    entry is at that bar's close (raced from ts+60s).
    ★ Volatility EXPANSION is included because on MNQ it is the leg that actually binds — ER climbing
    without it decayed inside 15-35 min on four separate armings ([[vol-expansion-is-the-binding-leg]]).
    """
    a = atr(m)
    close = m["close"]
    net = close.diff(THRUST_MIN)
    path = close.diff().abs().rolling(THRUST_MIN).sum()
    er = (net.abs() / path).replace([np.inf, -np.inf], np.nan)
    vol_now = a
    vol_ref = a.rolling(120).median()

    out, last = [], None
    for ts in m.index:
        nv, ev, av, vr = net.get(ts), er.get(ts), vol_now.get(ts), vol_ref.get(ts)
        if not all(np.isfinite(x) for x in (nv, ev, av, vr)) or av <= 0 or vr <= 0:
            continue
        if abs(nv) < thrust_atr * av:
            continue
        if ev < er_min:
            continue
        if av < expand_min * vr:
            continue
        if last is not None and (ts - last).total_seconds() < MIN_GAP_MIN * 60:
            continue
        side = 1 if nv > 0 else -1
        entry = float(close[ts])
        out.append((ts, side, entry, entry - side * STOP_ATR * av, av))
        last = ts
    return out


def backtest(m, ticks, sigs) -> list[Trade]:
    tk, px = ticks["ts_ms"].to_numpy(), ticks["price"].to_numpy()
    out = []
    for ts, side, entry, stop, av in sigs:
        e_ms = int(ts.value // 10**6) + 60_000          # bar CLOSE — see module docstring rule 3
        j = np.searchsorted(tk, e_ms)
        k = np.searchsorted(tk, e_ms + CAP_MIN * 60000 + 1)
        xp, why, mins = race(tk[j:k], px[j:k], side, entry, stop, None, TRAIL_ATR * av,
                             CAP_MIN * 60000)
        out.append(Trade(str(ts.date()), "RUNCATCH", side, entry, xp, why, mins))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--gate", action="store_true")
    a = ap.parse_args()

    bars, ticks = load()
    m_all = minute_bars(bars)
    cut = m_all.index.max().normalize() - pd.Timedelta(days=a.days)
    m = m_all.loc[cut:]
    print(f"  MGC last {a.days}d: {m.index.min():%Y-%m-%d %H:%M} .. {m.index.max():%Y-%m-%d %H:%M} "
          f"· {m.index.normalize().nunique()} days · ${VPP:.0f}/pt\n")

    runs = find_runs(m)
    if runs.empty:
        print("  no runs >= $300 in the window")
        return 0
    print(f"  ═══ TOP {a.top} RUNS (>= ${RUN_MIN_USD:.0f}, ended by a {RETRACE_FRAC:.0%} retrace) "
          f"— {len(runs)} found ═══")
    print(f"  {'start (UTC)':<17}{'dir':>4}{'pts':>7}{'$':>8}{'mins':>6}{'pt/min':>8}"
          f"{'ER':>6}{'ATR@0':>7}{'pre60/ATR':>10}{'min→20%':>9}")
    rows = []
    for _, r in runs.head(a.top).iterrows():
        an = anatomy(m, r)
        rows.append(an)
        print(f"  {r['start']:%m-%d %H:%M}      {'UP' if r['dir']>0 else 'DN':>4}"
              f"{r['pts']:>7.1f}{r['usd']:>8.0f}{r['mins']:>6.0f}{an['pts_per_min']:>8.2f}"
              f"{an['smoothness_ER']:>6.2f}{an['atr_at_start']:>7.2f}"
              f"{an['pre60_range_atr']:>10.1f}{an['mins_to_20pct']:>9.0f}")

    df = pd.DataFrame(rows)
    print(f"\n  ANATOMY (median of top {a.top}): ER {df.smoothness_ER.median():.2f} · "
          f"ATR at start {df.atr_at_start.median():.2f}pt · "
          f"pre-60min range {df.pre60_range_atr.median():.1f}xATR · "
          f"reaches 20% in {df.mins_to_20pct.median():.0f} min")
    print(f"  → boarding at the 20% mark still leaves "
          f"{100*(1-0.20):.0f}% of the move, median ${0.8*runs.head(a.top).usd.median():.0f} gross")

    if not a.gate:
        print("\n  (run with --gate to build and filter the entry)")
        return 0

    print(f"\n  ═══ THE GATE: board a {THRUST_MIN}m impulse already underway ═══")
    print(f"  {'thrust':>7}{'ER':>6}{'volx':>6}{'n':>5}{'runs hit':>10}{'win%':>7}"
          f"{'exp$':>9}{'total$':>10}{'stripD$':>10}")
    best = None
    for thrust_atr in (1.5, 2.0, 2.5):
        for er_min in (0.35, 0.50):
            for expand in (1.0, 1.2):
                sigs = gate_signals(m, thrust_atr=thrust_atr, er_min=er_min, expand_min=expand)
                if not sigs:
                    continue
                tr = backtest(m, ticks, sigs)
                s = score(tr)
                hit = sum(1 for _, r in runs.head(a.top).iterrows()
                          if any(r["start"] <= t[0] <= r["end"] for t in sigs))
                print(f"  {thrust_atr:>7.1f}{er_min:>6.2f}{expand:>6.1f}{s['n']:>5}"
                      f"{hit:>7}/{a.top}{s['win']:>7.1f}{s['exp']:>9.2f}"
                      f"{s['total']:>10.2f}{s['strip_best_day']:>10.2f}")
                if best is None or s["total"] > best[0]:
                    best = (s["total"], thrust_atr, er_min, expand, s)
    if best:
        print(f"\n  best cell: thrust {best[1]}xATR · ER {best[2]} · vol {best[3]}x "
              f"→ ${best[0]:,.2f} over {best[4]['n']} trades")
        print("  ⚠ 12 cells were searched. A best-of-12 is not a finding until it is "
              "placebo-controlled and holds out of sample.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
