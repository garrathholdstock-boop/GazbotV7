#!/usr/bin/env python3
"""GF_MGC SKEPTIC — try to break the two survivors before the operator does.

    PYTHONPATH=src .venv/bin/python scripts/gf_mgc_skeptic.py

Five ways the vacuum-break fade could be an artefact rather than an edge, each tested:

  1. IS `obstacle == 0` JUST A THIN-BOOK CLOCK? If the empty far side only ever happens overnight,
     the cut is a session proxy wearing a microstructure hat.
  2. IS IT A STALE-SNAPSHOT ARTEFACT? A book that reads empty because the feed dropped is not a
     vacuum. Compare total resting size and snapshot age across the two groups.
  3. DOES IT SURVIVE WITHOUT THE BOOK AT ALL? If the plain break-fade in the same regime does as
     well, the L2 read has added nothing and we should not build a depth dependency for it.
  4. IS IT ONE WEEK? Per-day and per-week ledger, and the two capture blocks scored separately.
  5. DOES THE COOLDOWN CARRY IT? 45 minutes was chosen to keep trades independent, not tuned.

Plus the run chart: the real MGC price path with every fade entry and exit marked on it.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_cells import (  # noqa: E402
    Racer, battery, break_entries, five_second, line, run_entries, side_split, stat,
)
from gf_mgc_l2 import attach, load_book_5s  # noqa: E402
from gf_mgc_tape import VPP, build_tape  # noqa: E402

pd.set_option("display.width", 260)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
R: dict = {}


def svg_day(m: pd.DataFrame, trades: pd.DataFrame, day: str, title: str) -> str:
    """Inline, self-contained SVG of one gold session with the fills marked. No CDN, no JS."""
    d = m[m["day"] == day]
    t = trades[trades["day"] == day]
    if d.empty:
        return ""
    W, H, PL, PR, PT, PB = 1180, 420, 66, 22, 40, 46
    px = d["close"].to_numpy()
    xs = np.arange(len(px))
    lo, hi = float(px.min()), float(px.max())
    pad = (hi - lo) * 0.08 or 1.0
    lo, hi = lo - pad, hi + pad

    def X(i):
        return PL + (i / max(len(px) - 1, 1)) * (W - PL - PR)

    def Y(p):
        return PT + (1 - (p - lo) / (hi - lo)) * (H - PT - PB)

    path = " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f},{Y(p):.1f}" for i, p in enumerate(px))
    idx = {ts: i for i, ts in enumerate(d.index)}

    def nearest(ts):
        ts = pd.Timestamp(ts)
        if ts in idx:
            return idx[ts]
        j = int(np.searchsorted(d.index.to_numpy(), np.datetime64(ts.tz_localize(None))))
        return min(max(j, 0), len(px) - 1)

    marks = []
    for r in t.itertuples():
        i0 = nearest(r.ts)
        i1 = min(i0 + int(round(r.minutes)), len(px) - 1)
        green = r.true_pnl > 0
        col = "#1a7f4b" if green else "#b3261e"
        arrow = "▼" if r.side < 0 else "▲"
        marks.append(
            f'<line x1="{X(i0):.1f}" y1="{Y(r.fill_in):.1f}" x2="{X(i1):.1f}" y2="{Y(r.fill_out):.1f}" '
            f'stroke="{col}" stroke-width="2" stroke-dasharray="4 3" opacity="0.85"/>'
            f'<text x="{X(i0):.1f}" y="{Y(r.fill_in) - 7:.1f}" font-size="13" fill="{col}" '
            f'text-anchor="middle">{arrow}</text>'
            f'<circle cx="{X(i1):.1f}" cy="{Y(r.fill_out):.1f}" r="3.6" fill="{col}"/>'
            f'<text x="{X(i1) + 6:.1f}" y="{Y(r.fill_out) + 4:.1f}" font-size="11" fill="{col}">'
            f'{r.true_pnl:+.0f}</text>')
    ticks = ""
    for k in range(5):
        p = lo + (hi - lo) * k / 4
        ticks += (f'<line x1="{PL}" y1="{Y(p):.1f}" x2="{W - PR}" y2="{Y(p):.1f}" stroke="#e6e6e6"/>'
                  f'<text x="{PL - 8}" y="{Y(p) + 4:.1f}" font-size="11" fill="#666" '
                  f'text-anchor="end">{p:.1f}</text>')
    for k in range(0, len(px), max(len(px) // 8, 1)):
        ticks += (f'<text x="{X(k):.1f}" y="{H - PB + 18}" font-size="11" fill="#666" '
                  f'text-anchor="middle">{d.index[k].strftime("%H:%M")}</text>')
    net = float(t["true_pnl"].sum()) if not t.empty else 0.0
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" '
            f'style="background:#fff;border:1px solid #ddd">'
            f'<text x="{PL}" y="24" font-size="14" font-weight="600" fill="#111">{title}</text>'
            f'<text x="{W - PR}" y="24" font-size="13" fill="{"#1a7f4b" if net >= 0 else "#b3261e"}" '
            f'text-anchor="end">{len(t)} fades · net {net:+.0f} USD</text>'
            f'{ticks}<path d="{path}" fill="none" stroke="#1f3b73" stroke-width="1.4"/>'
            f'{"".join(marks)}</svg>')


def main() -> None:
    m, q = build_tape()
    racer = Racer(five_second(q))
    bk = load_book_5s()
    e_all = attach(break_entries(m, fade=True), bk)
    ev = e_all[e_all["obstacle"] == 0].reset_index(drop=True)
    rv = run_entries(racer, ev, **CHAND)
    r_all = run_entries(racer, e_all, **CHAND)

    print("=" * 126)
    print("[1] IS AN EMPTY FAR SIDE JUST THE OVERNIGHT CLOCK?")
    print("=" * 126)
    tab = e_all.assign(empty=e_all["obstacle"] == 0).groupby("session")["empty"].agg(["mean", "size"])
    tab["pct_empty"] = (100 * tab["mean"]).round(1)
    print(tab[["size", "pct_empty"]].to_string())
    print("  -> if this were a clock proxy the empty share would be ~100% in ASIA and ~0% in US.")
    R["empty_by_session"] = tab[["size", "pct_empty"]].to_dict("index")

    print("\n" + "=" * 126)
    print("[2] IS IT A STALE / DROPPED SNAPSHOT? total resting size on BOTH sides, by group")
    print("=" * 126)
    g = e_all.assign(empty=e_all["obstacle"] == 0)
    print(g.groupby("empty")[["obstacle", "support", "obst_pre"]].median().round(2).to_string())
    print(f"  rows where BOTH sides read 0 within 1pt: "
          f"{int(((e_all['obstacle'] == 0) & (e_all['support'] == 0)).sum())} of {len(e_all)}")
    print("  -> a dropped feed would empty BOTH sides; a vacuum empties only the one price ran into.")
    R["both_empty"] = int(((e_all["obstacle"] == 0) & (e_all["support"] == 0)).sum())

    print("\n" + "=" * 126)
    print("[3] DOES THE BOOK ADD ANYTHING THE REGIME DOES NOT ALREADY SAY?")
    print("=" * 126)
    for lbl, sub in (("all breaks", r_all),
                     ("vacuum breaks (book)", rv),
                     ("CLEAN_TREND breaks (no book)", r_all[r_all["regime"] == "CLEAN_TREND"]),
                     ("CLEAN_TREND AND vacuum", rv[rv["regime"] == "CLEAN_TREND"]),
                     ("CLEAN_TREND AND NOT vacuum",
                      r_all[(r_all["regime"] == "CLEAN_TREND") & (r_all["obstacle"] > 0)])):
        print(line(lbl, stat(sub)))
        R.setdefault("book_vs_regime", {})[lbl] = stat(sub)

    print("\n" + "=" * 126)
    print("[4] THE LEDGER — every day the vacuum fade traded")
    print("=" * 126)
    byday = rv.groupby("day").agg(n=("true_pnl", "size"), net=("true_pnl", "sum"),
                                  win=("true_pnl", lambda s: round(100 * (s > 0).mean(), 0)))
    byday["cum"] = byday["net"].cumsum().round(0)
    print(byday.round(0).to_string())
    R["ledger"] = byday.round(2).to_dict("index")
    wk = rv.assign(wk=pd.to_datetime(rv["day"]).dt.isocalendar().week).groupby("wk")["true_pnl"].agg(["size", "sum"])
    print("\n  by ISO week:")
    print(wk.round(0).to_string())
    R["by_week"] = wk.round(2).to_dict("index")

    print("\n" + "=" * 126)
    print("[5] DOES THE 45-MINUTE COOLDOWN CARRY IT?")
    print("=" * 126)
    rows = []
    for cd in (0, 15, 30, 45, 90, 180):
        e2 = attach(break_entries(m, cool=cd, fade=True), bk)
        e2 = e2[e2["obstacle"] == 0]
        r2 = run_entries(racer, e2, **CHAND)
        ss = side_split(r2)
        rows.append({"cooldown_min": cd, **stat(r2), "LONG$/tr": ss["LONG"]["per"],
                     "SHORT$/tr": ss["SHORT"]["per"]})
    print(pd.DataFrame(rows).to_string(index=False))
    R["cooldown"] = rows

    print("\n" + "=" * 126)
    print("[6] LEAVE-ONE-DAY-OUT, EVERY DAY (not just the best) — how concentrated is it really?")
    print("=" * 126)
    tot = float(rv["true_pnl"].sum())
    bd = rv.groupby("day")["true_pnl"].sum().sort_values()
    loo = pd.DataFrame({"day_net": bd.round(0), "book_without_it": (tot - bd).round(0)})
    print(loo.to_string())
    print(f"  the book stays green dropping ANY single day: "
          f"{bool((tot - bd > 0).all())}   (worst residual ${float((tot - bd).min()):,.0f})")
    R["loo_all"] = {"all_green": bool((tot - bd > 0).all()),
                    "worst_residual": round(float((tot - bd).min()), 0)}

    # ── the chart ────────────────────────────────────────────────────────────────────────────────
    best = rv.groupby("day")["true_pnl"].sum().idxmax()
    svgs = []
    for day in [best, "2026-08-13"]:
        if day in set(rv["day"]):
            svgs.append(svg_day(m, rv, day,
                                f"MGC {day} — the vacuum-break fade, every fill marked "
                                f"(▲ long / ▼ short, dot = exit)"))
    open(f"{OUT}/gf_mgc_charts.svg.html", "w").write("\n".join(dict.fromkeys(svgs)))
    print(f"\ncharts -> {OUT}/gf_mgc_charts.svg.html  ({len(svgs)} sessions)")

    json.dump(R, open(f"{OUT}/gf_mgc_skeptic.json", "w"), indent=1, default=str)
    print(f"JSON -> {OUT}/gf_mgc_skeptic.json")


if __name__ == "__main__":
    main()
