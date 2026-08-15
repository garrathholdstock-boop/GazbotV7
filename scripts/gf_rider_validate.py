#!/usr/bin/env python3
"""GF RIDER · validation — re-race EVERY trade that has raw tick tape, and chart the biggest run.

Two jobs:
  1. The 5-second racer is the whole study's cost model. Re-price every trade on the days the TICK
     lake covers (28 of the 49 sessions) and report the difference. If the 5s racer is optimistic,
     the number to trust is the tick one.
  2. The operator's favourite artefact: the real price path of a big run with the rider's entry and
     exit marked on it. Inline self-contained SVG, no CDN, no JS.

    PYTHONPATH=src .venv/bin/python scripts/gf_rider_validate.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.lake import connect  # noqa: E402
from gf_rider_engine import FEE, SLIP, VPP, Racer, stat  # noqa: E402
from gf_rider_tape import build  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"


def tick_reprice(con, tr: pd.DataFrame) -> pd.DataFrame:
    """Race the same trade on raw trade prints instead of 5s bars."""
    out = []
    for r in tr.itertuples():
        atr = float(r.atr)
        stop_pt, targ_pt = 3.0 * atr, 6.0 * atr
        t0, t1 = int(r.ts), int(r.ts) + 120 * 60
        q = con.execute("SELECT ts_ms//1000 t, price FROM ticks WHERE ts_ms>=? AND ts_ms<? "
                        "ORDER BY ts_ms", [t0 * 1000, t1 * 1000]).df()
        if len(q) < 10:
            continue
        e = float(r.entry_px)
        fav = ((q["price"] - e) * r.side).to_numpy()
        hs = np.nonzero(-fav >= stop_pt)[0]
        ht = np.nonzero(fav >= targ_pt)[0]
        si = hs[0] if len(hs) else 10**9
        ti = ht[0] if len(ht) else 10**9
        if si <= ti and si < 10**9:
            why, px = "STOP", e - r.side * stop_pt
        elif ti < 10**9:
            why, px = "TARGET", e + r.side * targ_pt
        else:
            why, px = "TIME_CAP", float(q["price"].iloc[-1])
        net = ((px - e) * r.side - SLIP) * VPP - FEE
        out.append(dict(day=r.day, hh=r.hh, side=r.side, bar_why=r.why, bar_net=r.net,
                        tick_why=why, tick_net=round(net, 2), diff=round(net - r.net, 2)))
    return pd.DataFrame(out)


def svg_run(m1, s5, tr, day: str, t_from: int, t_to: int, title: str) -> str:
    """Real MNQ price path over the window with every rider entry/exit marked. Self-contained."""
    b = s5[(s5["ts"] >= t_from) & (s5["ts"] <= t_to)]
    if not len(b):
        return ""
    W, H, PL, PR, PT, PB = 1180, 430, 62, 18, 34, 30
    lo, hi = float(b["l"].min()), float(b["h"].max())
    pad = (hi - lo) * 0.06 or 1.0
    lo, hi = lo - pad, hi + pad

    def X(t):
        return PL + (t - t_from) / max(t_to - t_from, 1) * (W - PL - PR)

    def Y(p):
        return PT + (hi - p) / (hi - lo) * (H - PT - PB)

    pts = " ".join(f"{X(int(r.ts)):.1f},{Y(float(r.c)):.1f}" for r in b.itertuples())
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
         f'style="background:#fff;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">',
         f'<text x="{PL}" y="20" font-size="14" font-weight="600" fill="#111">{title}</text>']
    for i in range(6):
        p = lo + (hi - lo) * i / 5
        y = Y(p)
        s.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="#e8e8e8"/>'
                 f'<text x="{PL-6}" y="{y+4:.1f}" font-size="10" fill="#888" '
                 f'text-anchor="end">{p:,.0f}</text>')
    step = max(1, (t_to - t_from) // 8 // 300 * 300)
    for t in range(t_from - t_from % 300, t_to, step):
        if t < t_from:
            continue
        s.append(f'<text x="{X(t):.1f}" y="{H-10}" font-size="10" fill="#888" '
                 f'text-anchor="middle">{pd.Timestamp(t, unit="s", tz="UTC").strftime("%H:%M")}</text>')
    s.append(f'<polyline points="{pts}" fill="none" stroke="#1a1a1a" stroke-width="1.2"/>')

    sub = tr[(tr["ts"] >= t_from - 3600) & (tr["ts"] <= t_to)]
    for r in sub.itertuples():
        x0, y0 = X(int(r.ts)), Y(float(r.entry_px))
        xe, ye = X(int(r.ts) + int(r.held_s)), Y(float(r.exit_px))
        col = "#1a7f37" if r.net > 0 else "#c1121f"
        arrow = "▲" if r.side > 0 else "▼"
        s.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{min(xe,W-PR):.1f}" y2="{ye:.1f}" '
                 f'stroke="{col}" stroke-width="1.6" stroke-dasharray="4 3" opacity="0.85"/>')
        s.append(f'<text x="{x0:.1f}" y="{y0+4:.1f}" font-size="13" fill="{col}" '
                 f'text-anchor="middle">{arrow}</text>')
        s.append(f'<circle cx="{min(xe,W-PR):.1f}" cy="{ye:.1f}" r="4" fill="none" '
                 f'stroke="{col}" stroke-width="1.8"/>')
        s.append(f'<text x="{min(xe,W-PR)+7:.1f}" y="{ye+4:.1f}" font-size="10.5" '
                 f'font-weight="600" fill="{col}">{r.why} ${r.net:+,.0f}</text>')
    s.append(f'<text x="{PL}" y="{H-10}" font-size="10" fill="#666">'
             f'▲/▼ = rider entry · ○ = exit · green = winner, red = loser · '
             f'MNQ $2.00/pt, $1.50/RT + 0.25pt/side</text>')
    s.append("</svg>")
    return "\n".join(s)


def main():
    m1, s5 = build()
    tr = pd.read_pickle("/home/alphabot/gazbot7/data/gf_rider/tr_final.pkl")
    con = connect(symbol="MNQ")

    print("═══ VALIDATION · re-racing every trade on RAW TICKS where the tick lake reaches ═══\n")
    rp = tick_reprice(con, tr)
    print(f"  trades re-priced on ticks: {len(rp)} of {len(tr)} "
          f"(the rest are on 5s-bar-only sessions)")
    agree = (rp["bar_why"] == rp["tick_why"]).mean()
    print(f"  exit-reason agreement: {100*agree:.1f}%")
    print(f"  5s-bar net over those trades: ${rp['bar_net'].sum():>9,.0f}")
    print(f"  raw-tick net over those trades: ${rp['tick_net'].sum():>9,.0f}")
    print(f"  difference: ${rp['diff'].sum():>9,.0f}  (${rp['diff'].mean():.2f}/trade) "
          f"— {'the 5s racer is CONSERVATIVE' if rp['diff'].sum() > 0 else 'the 5s racer is OPTIMISTIC by this much'}")
    print("\n  disagreements:")
    d = rp[rp["bar_why"] != rp["tick_why"]]
    print(d.to_string(index=False) if len(d) else "    none")
    json.dump(dict(n=len(rp), agree=round(float(agree), 4),
                   bar_net=float(rp["bar_net"].sum()), tick_net=float(rp["tick_net"].sum()),
                   diff=float(rp["diff"].sum())),
              open(f"{OUT}/gf_rider_validate.json", "w"), indent=1)

    # ── the charts ─────────────────────────────────────────────────────────────────────────────
    charts = []
    for day, h0, h1, ttl in (
            ("2026-08-13", 12.5, 17.0, "MNQ 2026-08-13 — the week's biggest sat-out run (+236pt "
                                       "from 13:32Z) with RIDER_ALL's fills marked"),
            ("2026-08-14", 13.0, 16.5, "MNQ 2026-08-14 — the -98pt 14:13Z run the rider DID catch"),
            ("2026-07-31", 13.0, 18.0, "MNQ 2026-07-31 — a typical winning session for the rider")):
        d0 = int(pd.Timestamp(f"{day} 00:00:00", tz="UTC").timestamp())
        t0, t1 = d0 + int(h0 * 3600), d0 + int(h1 * 3600)
        svg = svg_run(m1, s5, tr, day, t0, t1, ttl)
        if svg:
            charts.append(svg)
            print(f"\n  chart built: {ttl[:60]}...")
    open(f"{OUT}/gf_rider_charts.svg.html", "w").write(
        "<div>\n" + "\n<hr style='border:0;border-top:1px solid #eee;margin:26px 0'/>\n".join(charts)
        + "\n</div>\n")
    print(f"\n→ {OUT}/gf_rider_charts.svg.html")
    con.close()


if __name__ == "__main__":
    main()
