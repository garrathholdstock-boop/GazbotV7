#!/usr/bin/env python3
"""FLOW-LED greenfield — the run charts + the concentration numbers for FBREAK.

Self-contained inline SVG built from the lake's own 5s bars and the backtest's REAL simulated fills —
no external image, no CDN, no JS. Three panels, each a US-session afternoon:
  * 2026-08-13 — the census's biggest sat-out run of the week (+236pt at 13:32)
  * 2026-08-11 — the day the census logged the -137pt and +124pt pair either side of 13:30
  * 2026-08-14 — a day with three sat-out runs, so the MISSES are as visible as the hits
Entries are dots (green long / red short), exits hollow, the line between them is the trade.

Writes reports/friday_v7/sections/fl/gf_fl_charts.svg.html and fl/conc.json
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"
CENSUS = {
    "2026-08-13": [("13:32", +236), ("13:56", +79), ("14:20", +75), ("15:22", -98)],
    "2026-08-11": [("13:24", -137), ("13:51", +124), ("14:55", -89)],
    "2026-08-14": [("13:22", -80), ("14:13", -98), ("15:11", -73)],
}
W, H, PADL, PADR, PADT, PADB = 980, 300, 62, 18, 26, 30
T0, T1 = 12 * 3600 + 1800, 17 * 3600     # 12:30-17:00Z


def panel(bars, day, legs, runs, y0):
    sod = bars["sod"].to_numpy(float)
    px = bars["close"].to_numpy(float)
    m = (sod >= T0) & (sod < T1)
    sod, px = sod[m], px[m]
    if len(sod) < 10:
        return ""
    hi, lo = float(px.max()), float(px.min())
    pad = (hi - lo) * 0.08 or 1
    hi, lo = hi + pad, lo - pad
    x0, x1 = float(sod.min()), float(sod.max())

    def X(s):
        return PADL + (s - x0) / (x1 - x0) * (W - PADL - PADR)

    def Y(p):
        return y0 + PADT + (hi - p) / (hi - lo) * (H - PADT - PADB)

    out = [f'<text x="{PADL}" y="{y0 + 17}" class="ttl">{day} · MNQ 5s close · 12:30–17:00Z '
           f'· FBREAK fills marked</text>']
    out.append(f'<rect x="{X(13 * 3600 + 1800):.1f}" y="{y0 + PADT}" '
               f'width="{X(min(x1, 20 * 3600)) - X(13 * 3600 + 1800):.1f}" '
               f'height="{H - PADT - PADB}" class="win"/>')
    for gs in range(13 * 3600, 17 * 3600 + 1, 1800):
        if x0 <= gs <= x1:
            out.append(f'<line x1="{X(gs):.1f}" y1="{y0 + PADT}" x2="{X(gs):.1f}" '
                       f'y2="{y0 + H - PADB}" class="grid"/>')
            out.append(f'<text x="{X(gs):.1f}" y="{y0 + H - PADB + 14}" class="ax" '
                       f'text-anchor="middle">{gs // 3600:02d}:{gs % 3600 // 60:02d}</text>')
    for k in range(4):
        p = lo + (hi - lo) * k / 3
        out.append(f'<line x1="{PADL}" y1="{Y(p):.1f}" x2="{W - PADR}" y2="{Y(p):.1f}" class="grid"/>')
        out.append(f'<text x="{PADL - 6}" y="{Y(p) + 4:.1f}" class="ax" text-anchor="end">{p:,.0f}</text>')
    out.append('<polyline points="' + " ".join(f"{X(s):.1f},{Y(p):.1f}" for s, p in zip(sod, px))
               + '" class="px"/>')
    for hm, mv in runs:
        h, mi = hm.split(":")
        t0 = int(h) * 3600 + int(mi) * 60
        if not (x0 <= t0 <= x1):
            continue
        out.append(f'<line x1="{X(t0):.1f}" y1="{y0 + PADT}" x2="{X(t0):.1f}" '
                   f'y2="{y0 + H - PADB}" class="run"/>')
        out.append(f'<text x="{X(t0) + 3:.1f}" y="{y0 + PADT + 12}" class="runlbl">'
                   f'census run {mv:+d}pt</text>')
    for lg in legs:
        cls = "up" if lg["dir"] > 0 else "dn"
        es, xs = lg["entry_sod"], lg["exit_sod"]
        if not (x0 <= es <= x1):
            continue
        xs = min(xs, x1)
        out.append(f'<line x1="{X(es):.1f}" y1="{Y(lg["entry"]):.1f}" x2="{X(xs):.1f}" '
                   f'y2="{Y(lg["exit"]):.1f}" class="trd {cls}"/>')
        out.append(f'<circle cx="{X(es):.1f}" cy="{Y(lg["entry"]):.1f}" r="4.5" class="ent {cls}"/>')
        out.append(f'<circle cx="{X(xs):.1f}" cy="{Y(lg["exit"]):.1f}" r="4.5" class="ext"/>')
        out.append(f'<text x="{X(es) + 6:.1f}" y="{Y(lg["entry"]) - 7:.1f}" class="lbl">'
                   f'{"LONG" if lg["dir"] > 0 else "SHORT"} {lg["net"]:+.0f}</text>')
    if not legs:
        out.append(f'<text x="{W / 2:.0f}" y="{y0 + H - PADB - 8}" class="none" text-anchor="middle">'
                   f'FBREAK did not fire in this window on {day}</text>')
    return "\n".join(out)


def main():
    tr = pd.read_csv(f"{DIR}/trades_abl_FBREAK.csv")
    con = connect(symbol="MNQ")
    body = []
    for k, day in enumerate(sorted(CENSUS)):
        bars = con.execute(f"""
            SELECT bar_ts, close FROM bars WHERE timeframe='5s'
              AND strftime(to_timestamp(bar_ts),'%Y-%m-%d')='{day}' ORDER BY bar_ts""").fetchdf()
        bars["sod"] = bars["bar_ts"] % 86400
        legs = []
        for _, r in tr[tr["day"] == day].iterrows():
            legs.append({"dir": int(r["dir"]), "entry": float(r["entry"]), "exit": float(r["exit"]),
                         "net": float(r["net"]),
                         "entry_sod": (int(r["ts"]) + 60) % 86400,
                         "exit_sod": (int(r["ts"]) + 60 + int(r["held_min"] * 60)) % 86400})
        body.append(panel(bars, day, legs, CENSUS[day], k * H))
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
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H * len(CENSUS)}" '
           f'viewBox="0 0 {W} {H * len(CENSUS)}" role="img" '
           f'aria-label="FBREAK entries and exits against the census sat-out runs">'
           f'<style>{css}</style><rect width="{W}" height="{H * len(CENSUS)}" class="bg"/>'
           + "\n".join(body) + "</svg>")
    open(f"{DIR}/gf_fl_charts.svg.html", "w").write(svg)
    print(f"→ {DIR}/gf_fl_charts.svg.html ({len(svg)} bytes)")

    # ── concentration, on the US home segment ────────────────────────────────────────────────
    us = tr[tr["session"] == "US"]
    bd = us.groupby("day")["net"].agg(["size", "sum"]).sort_values("sum", ascending=False)
    order = bd.index.tolist()
    conc = {
        "us_headline": {"n": int(len(us)), "net": round(float(us["net"].sum()), 2),
                        "per_trade": round(float(us["net"].mean()), 2)},
        "green_days": int((bd["sum"] > 0).sum()), "days": int(len(bd)),
        "best_days": [{"day": d, "n": int(bd.loc[d, "size"]), "net": round(float(bd.loc[d, "sum"]), 2)}
                      for d in order[:5]],
        "worst_days": [{"day": d, "n": int(bd.loc[d, "size"]), "net": round(float(bd.loc[d, "sum"]), 2)}
                       for d in order[-5:]],
    }
    for k in (1, 2, 3):
        sub = us[~us["day"].isin(order[:k])]
        conc[f"strip_best_{k}_days"] = {"n": int(len(sub)), "net": round(float(sub["net"].sum()), 2),
                                        "per_trade": round(float(sub["net"].mean()), 2)}
    # excursion killer statistic
    win = us[us["net"] > 0]
    los = us[us["net"] <= 0]
    conc["excursion"] = {
        "winner_median_mfe_pt": round(float(win["mfe"].median()), 2),
        "loser_median_mfe_pt": round(float(los["mfe"].median()), 2),
        "loser_pct_never_1atr_green": round(100 * float((los["mfe"] < los["atr"]).mean()), 1),
        "winner_median_hold_min": round(float(win["held_min"].median()), 1),
        "loser_median_hold_min": round(float(los["held_min"].median()), 1),
    }
    # cumulative curve (US book), for the report table
    cum = us.sort_values("ts")["net"].cumsum()
    conc["equity_curve_by_day"] = {d: round(float(v), 2) for d, v in
                                   us.sort_values("ts").groupby("day")["net"].sum().cumsum().items()}
    conc["max_drawdown"] = round(float((cum.cummax() - cum).max()), 2)
    json.dump(conc, open(f"{DIR}/conc.json", "w"), indent=1)
    print(json.dumps(conc, indent=1))


if __name__ == "__main__":
    main()
