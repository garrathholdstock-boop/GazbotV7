#!/usr/bin/env python3
"""GF4_MGC — THE BAR-SOURCE VERDICT, and the stone that turned under it.

    PYTHONPATH=src .venv/bin/python scripts/gf4_mgc_barsource.py

★ WHY THIS RUN EXISTS. Last Friday's gold section led with one claim: the live MGC shadow was losing
because the lab measured its 60-minute break on bars built from the DEPTH MID while production folds
md's TRADE bars, and on the six forward days both tapes covered, the sign flipped on that alone
(+$3.06/trade on mid bars, -$8.96 on trade bars). The recommendation that followed — the gating
BUILD item for the whole gold line — was "point the shadow's bar builder at the depth mid".

That claim was measured on SIX DAYS. This re-runs it on THIRTY-TWO, adds the three trading days that
did not exist last Friday (08-26/27/28), and asks the question the six-day cut could not:

    IS THE BAR SOURCE THE VARIABLE, OR IS IT A PROXY FOR SOMETHING ELSE?

★ WHAT IT MEASURES. Identical gate (60-min break, margin 0.10 ATR, obstacle==0 hole, 45-min per-side
cooldown), identical exit (3.0 ATR stop behind a 2.0/2.0 chandelier, 480-min backstop), identical
race on the SAME 250ms quote tape with both legs crossing and $1.50 commission. The ONLY difference
between the two arms is which minute-bar series the trigger reads. Anything else would confound it.

★ AND THEN THE ACTIVITY SPLIT. `rev2_mgc_hole_by_rate.py` (08-26) noticed that the depth-mid arm
fires roughly twice as often as production's, and that a large block of its extra fires land in
minutes where the trade tape printed NOTHING for a quarter of an hour. A mid quote flickers when
nobody trades; a trade bar cannot. So the two arms may not differ by "quality of price series" at
all — the mid arm may simply be admitting a population of dead-tape breaks. That is testable, and it
is tested here, per period, with the floor FITTED IN-SAMPLE and applied forward.

MGC = $10.00/point. Fee $1.50 per ROUND TRIP on top of two crossed legs (~0.30pt spread) = the
$4.50-from-mid convention in src/gazbot7/levelbreak.py.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")

from gf_mgc_barsource import atr14, book_rows, fires, trade_bars      # noqa: E402
from gf_mgc_tape import VPP, load_quotes, minute_bars, race           # noqa: E402
from gazbot7.levelbreak import read_book                              # noqa: E402

OUT = f"{GB}/reports/friday_v7/sections"
FEE = 1.50
IS_END = "2026-08-15"       # last week's fit ended 08-14 inclusive
F2_START = "2026-08-26"     # the three days that did not exist last Friday
R: dict = {}


def line(t: str) -> None:
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100, flush=True)


def raced(hits, q, bk, bk_ts, bars, *, band=1.0, stop_atr=3.0, trail_atr=2.0, arm_atr=2.0,
          cap_min=480, cooldown_min=45, hole=True, fade=True):
    """Race every fire that clears the book condition. Returns one row per trade.

    ⚠ The 45-min PER-BREAK-DIRECTION cooldown is applied on TAKEN trades only, exactly as the
    shipped variant does — a fire refused by the book must not consume the cooldown, or the gate
    being measured is not the gate being shipped.
    """
    qt = (q.index.tz_convert("UTC").tz_localize(None)
          .astype("datetime64[ms]").astype("int64").to_numpy())
    bid, ask = q["bid1p"].to_numpy(), q["ask1p"].to_numpy()
    a = atr14(bars)
    out, cool = [], {1: -1, -1: -1}
    for ts, brk, level in hits:
        if ts - cool[brk] < cooldown_min * 60_000:
            continue
        j = np.searchsorted(bk_ts, ts, side="right") - 1
        if j < 0 or ts - bk_ts[j] > 5_000:
            continue
        b = read_book(bk.iloc[j].to_dict(), brk, level, band)
        if hole and b.obstacle != 0:
            continue
        if (not hole) and not (b.obstacle > b.support):     # the WALL / momentum arm
            continue
        i = np.searchsorted(qt, ts, side="left")
        if i >= len(qt) - 2:
            continue
        side = (-brk) if fade else brk
        k = a.index.get_indexer([pd.Timestamp(ts - 60_000, unit="ms", tz="UTC")], method="ffill")[0]
        atr = float(a.iloc[k]) if k >= 0 else 0.0
        if not (atr > 0):
            continue
        fill_in = ask[i] if side > 0 else bid[i]
        mid_in = (bid[i] + ask[i]) / 2.0
        stop = mid_in - side * stop_atr * atr
        fo, mo, reason, mins, mfe, mae = race(qt[i:], bid[i:], ask[i:], side, fill_in=fill_in,
                                              mid_in=mid_in, stop=stop, target=None,
                                              trail=trail_atr * atr, cap_ms=cap_min * 60_000,
                                              arm_at=arm_atr * atr)
        cool[brk] = ts
        out.append({"ts": ts, "side": side, "brk": brk, "atr": atr, "level": level,
                    "obstacle": b.obstacle, "support": b.support,
                    "day": pd.Timestamp(ts, unit="ms", tz="UTC").strftime("%Y-%m-%d"),
                    "hour": pd.Timestamp(ts, unit="ms", tz="UTC").hour,
                    "reason": reason, "minutes": mins, "mfe_pt": mfe, "mae_pt": mae,
                    "pnl": round(side * (fo - fill_in) * VPP - FEE, 2)})
    return pd.DataFrame(out)


def prints_per_min(ts_ms, window_min=15):
    """MGC trade prints per minute over the `window_min` minutes ENDING at each fire. Causal."""
    from gazbot7 import lake
    c = lake.connect(symbol="MGC")
    arr = c.execute("SELECT ts_ms FROM ticks WHERE symbol='MGC' ORDER BY ts_ms").df()["ts_ms"].to_numpy()
    lo = np.searchsorted(arr, np.asarray(ts_ms) - window_min * 60_000, side="left")
    hi = np.searchsorted(arr, np.asarray(ts_ms), side="right")
    return (hi - lo) / float(window_min)


def s(d: pd.DataFrame) -> dict:
    if d is None or d.empty:
        return {"n": 0, "net": 0.0, "per": 0.0, "win": 0.0, "days": 0}
    v = d["pnl"]
    return {"n": int(len(v)), "net": round(float(v.sum()), 0), "per": round(float(v.mean()), 2),
            "win": round(100.0 * float((v > 0).mean()), 1), "days": int(d["day"].nunique())}


def show(tag: str, d: pd.DataFrame) -> dict:
    r = s(d)
    lo = s(d[d["side"] > 0]) if not d.empty else r
    sh = s(d[d["side"] < 0]) if not d.empty else r
    print(f"  {tag:<44} n={r['n']:<5} net={r['net']:>+8.0f}  $/tr={r['per']:>+7.2f}  "
          f"win={r['win']:>5.1f}%  d={r['days']:<3} | LONG {lo['n']:>3}/{lo['per']:>+7.2f}"
          f"  SHORT {sh['n']:>3}/{sh['per']:>+7.2f}")
    return {"pooled": r, "long": lo, "short": sh}


def period(d: pd.DataFrame, which: str) -> pd.DataFrame:
    if d.empty:
        return d
    if which == "IS":
        return d[d["day"] < IS_END]
    if which == "F1":
        return d[(d["day"] >= IS_END) & (d["day"] < F2_START)]
    return d[d["day"] >= F2_START]


def main() -> None:
    q = load_quotes()
    mid = minute_bars(q, col="mid")
    t0 = int(q.index[0].value // 10**6)
    t1 = int(q.index[-1].value // 10**6)
    trd = trade_bars(t0, t1)
    trd = trd[(trd.index >= mid.index[0]) & (trd.index <= mid.index[-1])]
    print(f"quote tape  {q.index[0]} .. {q.index[-1]}   {len(q):,} snapshots")
    print(f"mid bars    {len(mid):,} minutes   trade bars {len(trd):,} minutes   "
          f"in both {len(mid.index.intersection(trd.index)):,}")
    days = sorted(set(mid.index.strftime('%Y-%m-%d')))
    print(f"days {len(days)}  {days[0]} .. {days[-1]}   "
          f"IS<{IS_END} = {sum(x < IS_END for x in days)}  "
          f"F1 = {sum(IS_END <= x < F2_START for x in days)}  "
          f"F2 = {sum(x >= F2_START for x in days)}")
    R["days"] = days

    bk = book_rows()
    bk_ts = bk["ts_ms"].to_numpy()
    print(f"book {len(bk):,} depth snapshots", flush=True)

    fm, ft = fires(mid), fires(trd)
    sm = {(t // 60_000, b) for t, b, _ in fm}
    st = {(t // 60_000, b) for t, b, _ in ft}
    both = sm & st
    print(f"\nRAW BREAK FIRES (before book/cooldown)   mid {len(sm)}   trade {len(st)}   "
          f"both {len(both)}   mid-only {len(sm - both)}   trade-only {len(st - both)}")
    R["raw_fires"] = {"mid": len(sm), "trade": len(st), "both": len(both)}

    arms = {}
    for lbl, bars, hits in (("DEPTH-MID (lab)", mid, fm), ("TRADE BARS (production)", trd, ft)):
        d = raced(hits, q, bk, bk_ts, bars)
        d = d.assign(rate=prints_per_min(d["ts"].to_numpy()))
        arms[lbl] = d

    line("★★★ THE BAR-SOURCE A/B ON THE FULL 32 DAYS — the claim that led last week's section")
    R["barsource"] = {}
    for lbl, d in arms.items():
        R["barsource"][lbl] = {"ALL": show(f"{lbl}  ALL 32 days", d)}
        for w, nm in (("IS", "in-sample  <08-15"), ("F1", "forward-1  08-15..08-25"),
                      ("F2", "forward-2  08-26..08-28  ★NEW")):
            R["barsource"][lbl][w] = show(f"{lbl}  {nm}", period(d, w))
        print()

    line("THE ACTIVITY SPLIT — trade prints per minute in the 15 minutes BEFORE the fire")
    R["activity"] = {}
    for lbl, d in arms.items():
        if d.empty:
            continue
        qs = np.quantile(d["rate"], [0.25, 0.5, 0.75])
        print(f"\n  {lbl}   quartile cuts {qs.round(1)}   "
              f"fires on a DEAD tape (<1 print/min): {int((d['rate'] < 1).sum())} of {len(d)} "
              f"({100 * (d['rate'] < 1).mean():.0f}%)")
        b = np.digitize(d["rate"], qs)
        rec = {"cuts": [round(float(x), 1) for x in qs],
               "dead_tape_n": int((d["rate"] < 1).sum()),
               "dead_tape_pct": round(100.0 * float((d["rate"] < 1).mean()), 1), "buckets": {}}
        for i in range(4):
            g = d[b == i]
            nm = ["Q1 quietest", "Q2", "Q3", "Q4 busiest"][i]
            rec["buckets"][nm] = show(f"  {nm}", g)
            rec["buckets"][nm]["median_rate"] = round(float(g["rate"].median()), 1) if len(g) else None
        R["activity"][lbl] = rec

    line("★★ THE ACTIVITY FLOOR — fitted on the IN-SAMPLE block only, then applied FORWARD")
    R["floor"] = {}
    for lbl, d in arms.items():
        if d.empty:
            continue
        ins = period(d, "IS")
        best, grid = None, []
        for f in (0, 2, 5, 8, 10, 12, 15, 20, 25, 30, 40):
            g = ins[ins["rate"] >= f]
            row = {"floor": f, **s(g)}
            grid.append(row)
            if len(g) >= 25 and (best is None or row["per"] > best["per"]):
                best = row
        print(f"\n  {lbl} — in-sample grid (floor = min prints/min):")
        for row in grid:
            print(f"    >= {row['floor']:>3}/min   n={row['n']:>4}  net={row['net']:>+8.0f}  "
                  f"$/tr={row['per']:>+7.2f}  win={row['win']:>5.1f}%")
        R["floor"][lbl] = {"grid": grid, "chosen": best}
        if best is None:
            print("    no cell keeps n>=25 — no floor chosen")
            continue
        f = best["floor"]
        print(f"    CHOSEN in-sample floor: >= {f} prints/min  ({best['n']} trades, "
              f"${best['per']:+.2f}/tr in-sample)")
        for w, nm in (("F1", "forward-1  08-15..08-25"), ("F2", "forward-2  08-26..08-28  ★NEW"),
                      ("ALL", "both forward blocks")):
            g = (d[d["day"] >= IS_END] if w == "ALL" else period(d, w))
            R["floor"][lbl][f"fwd_{w}"] = show(f"    floor>={f}  {nm}", g[g["rate"] >= f])
            R["floor"][lbl][f"fwd_{w}_unfiltered"] = show(f"    NO floor  {nm}", g)

    line("THE WALL / MOMENTUM ARM ON BOTH BAR SOURCES — the two cells still on probation")
    R["wall"] = {}
    for lbl, bars, hits in (("DEPTH-MID (lab)", mid, fm), ("TRADE BARS (production)", trd, ft)):
        d = raced(hits, q, bk, bk_ts, bars, hole=False, fade=False)
        if d.empty:
            continue
        d = d.assign(rate=prints_per_min(d["ts"].to_numpy()))
        R["wall"][lbl] = {"ALL": show(f"{lbl}  wall_go ALL", d)}
        for w, nm in (("IS", "in-sample"), ("F1", "forward-1"), ("F2", "forward-2 ★NEW")):
            R["wall"][lbl][w] = show(f"{lbl}  wall_go {nm}", period(d, w))
        arms[f"WALL {lbl}"] = d
        print()

    for lbl, d in arms.items():
        if not d.empty:
            d.to_json(f"{OUT}/gf4_mgc_trades_{lbl.split()[0].lower()}"
                      f"{'_wall' if lbl.startswith('WALL') else ''}.json", orient="records")
    with open(f"{OUT}/gf4_mgc_barsource.json", "w") as fh:
        json.dump(R, fh, indent=1, default=str)
    print(f"\nwrote {OUT}/gf4_mgc_barsource.json")


if __name__ == "__main__":
    main()
