#!/usr/bin/env python3
"""OPEN-NEWS greenfield — the run charts, plus the last concentration numbers.

Self-contained inline SVG built from the lake's own 5s bars and the backtest's REAL simulated fills.
No external image, no CDN, no JS. Two panels:
  * 2026-08-13 — the census's biggest sat-out OPEN/NEWS run (+236pt) and the ONE time POPSAR was there
  * 2026-08-14 — a day the census recorded two sat-out runs and POPSAR never fired, so the misses are
    as visible as the hit
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_engine as E  # noqa: E402
import gf_on_popgo as P  # noqa: E402
import gf_on_popsar as SAR  # noqa: E402
import gf_on_sweep as S  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CENSUS = {
    "2026-08-13": [("13:32", +236), ("14:20", +75), ("14:41", -45)],
    "2026-08-14": [("13:22", -80), ("14:13", -98), ("14:48", -48)],
}
W, H, PADL, PADR, PADT, PADB = 980, 300, 62, 18, 26, 30


def panel(days, d, legs, runs, y0):
    b = days[d]["bars5"]
    m = (b["sod"].values >= 12 * 3600 + 1800) & (b["sod"].values < 16 * 3600)
    sod = b["sod"].values[m]
    px = b["close"].values[m]
    hi, lo = float(px.max()), float(px.min())
    pad = (hi - lo) * 0.08 or 1
    hi, lo = hi + pad, lo - pad
    x0, x1 = float(sod.min()), float(sod.max())

    def X(s):
        return PADL + (s - x0) / (x1 - x0) * (W - PADL - PADR)

    def Y(p):
        return y0 + PADT + (hi - p) / (hi - lo) * (H - PADT - PADB)

    out = [f'<text x="{PADL}" y="{y0 + 17}" class="ttl">{d} · MNQ 5s close · 12:30–16:00Z</text>']
    # the 13:30-15:00 hunt window
    out.append(f'<rect x="{X(13 * 3600 + 1800):.1f}" y="{y0 + PADT}" '
               f'width="{X(E.WIN_HI) - X(13 * 3600 + 1800):.1f}" height="{H - PADT - PADB}" '
               f'class="win"/>')
    for gs in range(13 * 3600, 16 * 3600 + 1, 1800):
        if x0 <= gs <= x1:
            out.append(f'<line x1="{X(gs):.1f}" y1="{y0 + PADT}" x2="{X(gs):.1f}" '
                       f'y2="{y0 + H - PADB}" class="grid"/>')
            out.append(f'<text x="{X(gs):.1f}" y="{y0 + H - PADB + 14}" class="ax" '
                       f'text-anchor="middle">{gs // 3600:02d}:{gs % 3600 // 60:02d}</text>')
    for k in range(4):
        p = lo + (hi - lo) * k / 3
        out.append(f'<line x1="{PADL}" y1="{Y(p):.1f}" x2="{W - PADR}" y2="{Y(p):.1f}" class="grid"/>')
        out.append(f'<text x="{PADL - 6}" y="{Y(p) + 4:.1f}" class="ax" text-anchor="end">{p:,.0f}</text>')
    pts = " ".join(f"{X(s):.1f},{Y(p):.1f}" for s, p in zip(sod, px))
    out.append(f'<polyline points="{pts}" class="px"/>')

    # the census's sat-out runs on this day
    for hm, mv in runs:
        h, mi = hm.split(":")
        t0 = int(h) * 3600 + int(mi) * 60
        if not (x0 <= t0 <= x1):
            continue
        out.append(f'<line x1="{X(t0):.1f}" y1="{y0 + PADT}" x2="{X(t0):.1f}" y2="{y0 + H - PADB}" '
                   f'class="run"/>')
        out.append(f'<text x="{X(t0) + 3:.1f}" y="{y0 + PADT + 12}" class="runlbl">'
                   f'sat-out {mv:+d}pt</text>')

    # our real simulated fills
    for lg in legs:
        cls = "up" if lg["dir"] > 0 else "dn"
        out.append(f'<circle cx="{X(lg["entry_sod"]):.1f}" cy="{Y(lg["entry"]):.1f}" r="4.5" '
                   f'class="ent {cls}"/>')
        out.append(f'<circle cx="{X(lg["exit_sod"]):.1f}" cy="{Y(lg["exit"]):.1f}" r="4.5" '
                   f'class="ext"/>')
        out.append(f'<line x1="{X(lg["entry_sod"]):.1f}" y1="{Y(lg["entry"]):.1f}" '
                   f'x2="{X(lg["exit_sod"]):.1f}" y2="{Y(lg["exit"]):.1f}" class="trd {cls}"/>')
        out.append(f'<text x="{X(lg["entry_sod"]) + 6:.1f}" y="{Y(lg["entry"]) - 7:.1f}" '
                   f'class="lbl">{"LONG" if lg["dir"] > 0 else "SHORT"} {lg["net"]:+.0f}</text>')
    if not legs:
        out.append(f'<text x="{W / 2:.0f}" y="{y0 + H - PADB - 8}" class="none" '
                   f'text-anchor="middle">POPSAR did not fire on this day — no 1-min bar cleared '
                   f'2×ATR closing on its own extreme after 13:30Z</text>')
    return "\n".join(out)


def main():
    days = E.load_days()
    E.attach_regimes(days)
    sigs = S.gen_signals(days, P.sig_popgo, dict(k=2.0, close_frac=0.70, max_trades=3))
    base = SAR.run(days, sigs, stop_k=1.0, max_rev=1)

    # re-walk the chosen days to recover the individual LEGS with prices
    legs_by_day = {}
    for d, sod, direction, meta in sigs:
        if d not in CENSUS:
            continue
        dd = days[d]
        mkey = sod // 60 * 60 - 60
        atr = dd["amap"].get(mkey, np.nan)
        if np.isnan(atr) or atr <= 0:
            continue
        dcur, t0 = direction, sod
        for _ in range(2):
            t = E.simulate_fast(dd["ticks"], t0, dcur, stop_pt=max(1.0 * atr, 4 * E.TICK),
                                time_stop_sod=E.WIN_HI, slip_ticks=1.0)
            if t is None:
                break
            legs_by_day.setdefault(d, []).append(t)
            if t["reason"] != "STOP" or t["exit_sod"] >= E.WIN_HI - 5:
                break
            dcur, t0 = -dcur, t["exit_sod"]

    css = """
    .bg{fill:#fbfbfd}.ttl{font:600 13px system-ui,sans-serif;fill:#1c1c22}
    .ax{font:11px system-ui,sans-serif;fill:#77778a}
    .grid{stroke:#e6e6ee;stroke-width:1}
    .win{fill:#4c6ef5;opacity:.055}
    .px{fill:none;stroke:#2b2b38;stroke-width:1.35}
    .run{stroke:#e8590c;stroke-width:1.4;stroke-dasharray:4 3;opacity:.85}
    .runlbl{font:10px system-ui,sans-serif;fill:#e8590c}
    .ent.up{fill:#2f9e44}.ent.dn{fill:#c92a2a}.ext{fill:#fff;stroke:#1c1c22;stroke-width:1.6}
    .trd{stroke-width:2;opacity:.5}.trd.up{stroke:#2f9e44}.trd.dn{stroke:#c92a2a}
    .lbl{font:600 10px system-ui,sans-serif;fill:#1c1c22}
    .none{font:italic 11px system-ui,sans-serif;fill:#8a8a99}
    """
    body = []
    for k, d in enumerate(sorted(CENSUS)):
        body.append(panel(days, d, legs_by_day.get(d, []), CENSUS[d], k * H))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H * len(CENSUS)}" '
           f'viewBox="0 0 {W} {H * len(CENSUS)}" role="img" '
           f'aria-label="POPSAR entries and exits against the census sat-out OPEN/NEWS runs">'
           f'<style>{css}</style><rect width="{W}" height="{H * len(CENSUS)}" class="bg"/>'
           + "\n".join(body) + "</svg>")
    open(f"{SEC}/gf_on_charts.svg.html", "w").write(svg)
    print(f"→ {SEC}/gf_on_charts.svg.html  ({len(svg)} bytes)")

    # ── the last concentration numbers ────────────────────────────────────────────────────
    bd = E.by(base, lambda t: t["day"])
    order = sorted(bd.items(), key=lambda x: -x[1]["net"])
    conc = {"headline": E.score(base),
            "best_days": [{"day": d, "net": v["net"], "n": v["n"]} for d, v in order[:5]],
            "worst_days": [{"day": d, "net": v["net"], "n": v["n"]} for d, v in order[-5:]],
            "strip_best_day": E.score([t for t in base if t["day"] != order[0][0]]),
            "strip_best_2_days": E.score([t for t in base if t["day"] not in
                                          {order[0][0], order[1][0]}]),
            "strip_best_3_days": E.score([t for t in base if t["day"] not in
                                          {order[0][0], order[1][0], order[2][0]}]),
            "green_days": sum(1 for _, v in bd.items() if v["net"] > 0), "days": len(bd)}
    print(f"\npositive days {conc['green_days']}/{conc['days']}")
    print("best days: " + ", ".join(f"{x['day'][5:]} ${x['net']:+.0f}" for x in conc["best_days"]))
    print(f"strip best DAY  ${conc['strip_best_day']['net']:+.0f} (n={conc['strip_best_day']['n']})")
    print(f"strip best 2 DAYS ${conc['strip_best_2_days']['net']:+.0f}")
    print(f"strip best 3 DAYS ${conc['strip_best_3_days']['net']:+.0f}")
    json.dump(conc, open(f"{SEC}/gf_on_conc.json", "w"), indent=1, default=float)
    print(f"→ {SEC}/gf_on_conc.json")


if __name__ == "__main__":
    main()
