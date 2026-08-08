#!/usr/bin/env python3
"""RUN CHARTS — inline self-contained SVG price charts with entry/exit markers.

Operator, 2026-08-01: "charts are ok for the runs... I love seeing the chart and when we
jumped and when we exited."  Stats stay as fact-tables; THIS is visual trade review — the
real price path of a run / session with every fill marked on it.

Design decisions that are NOT free to change (validated, not eyeballed):
  * win #0ca30c / loss #b3211f — this exact pair clears the CVD gate at deutan dE 11.3
    (>=8 target). The obvious green/red (#0ca30c/#d03b3b) FAILS at dE 4.1: a deuteranope
    cannot tell a winning trade from a losing one. Re-run the dataviz validator before
    touching these.
  * Colour is NEVER the only carrier: marker SHAPE gives direction (triangle up = LONG,
    down = SHORT) and role (circle = exit), and every exit carries a signed $ direct label.
  * Text wears ink tokens, never the series colour.
  * Self-contained SVG: no JS, no CDN, no external image. The report is one HTML file and
    also renders to PDF, so interactivity is limited to native <title> tooltips.

Usage:
  run_charts.py --from "2026-07-30T13:00" --to "2026-07-30T21:00" --title "Thursday" --out c.svg
  run_charts.py --fragment out.html --spec specs.json     # many charts -> one HTML fragment
"""
import argparse, json, sqlite3, sys
from datetime import datetime, timezone

GB = "/home/alphabot/gazbot7"
CAPTURE, DESK = f"{GB}/data/capture.db", f"{GB}/data/gazbot7.db"

# ── palette (dataviz reference instance; light surface) ────────────────────────────────
SURFACE, GRID, AXIS, MUTED = "#fcfcfb", "#e1e0d9", "#c3c2b7", "#898781"
INK, INK2 = "#0b0b0b", "#52514e"
WIN, LOSS = "#0ca30c", "#b3211f"       # validated pair — see module docstring
PRICE = "#52514e"                       # neutral ink: the path is context, fills are the message

W, H = 980, 380
PAD_L, PAD_R, PAD_T, PAD_B = 62, 20, 34, 30


def _ms(s):
    if isinstance(s, (int, float)):
        return int(s)
    s = s.strip().replace(" ", "T")
    if not s.endswith("Z") and "+" not in s[10:]:
        s += "+00:00"
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


def load_ticks(symbol, t0, t1, buckets=900):
    """Last price per time-bucket — a faithful path at a size the SVG can carry."""
    con = sqlite3.connect(f"file:{CAPTURE}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT ts_ms, price FROM ticks WHERE symbol=? AND ts_ms BETWEEN ? AND ? ORDER BY ts_ms",
        (symbol, t0, t1)).fetchall()
    con.close()
    if not rows:
        return []
    span = max(1, t1 - t0)
    out, seen = [], {}
    for ts, px in rows:
        b = int((ts - t0) * buckets / span)
        seen[b] = (ts, px)
    for b in sorted(seen):
        out.append(seen[b])
    return out


def load_trades(symbol, t0, t1):
    """Closed trades overlapping the window.

    ★2026-08-08: `data_quality IS NULL` is REQUIRED, not optional. Rows carrying a
    data_quality tag are known-bad and are excluded from every honest P&L on the desk —
    e.g. the two 08-04 rows tagged `EXCLUDE:md_stream_atr_corruption_20260804`, worth
    -$255.50, booked when the multi-symbol MD stream made ATR read 1848 against a true 15.
    Without this filter the chart plots them as real fills, so the picture disagrees with
    the report printed beside it: the week is -$772.50 on 110 clean trades, not -$1,028.00
    on 112. `desk_view` and `recent_trades` were fixed on 08-06 (d0f5bbd); this reader was
    missed, because the convention lived in the reporting layer rather than in the schema.
    """
    con = sqlite3.connect(f"file:{DESK}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT side, entry_price, exit_price, opened_at, closed_at, pnl_usd, gate, exit_reason "
        "FROM trades WHERE symbol=? AND closed_at IS NOT NULL AND data_quality IS NULL "
        "ORDER BY opened_at", (symbol,)).fetchall()
    con.close()
    out = []
    for side, ep, xp, oa, ca, pnl, gate, reason in rows:
        try:
            o, c = _ms(oa), _ms(ca)
        except Exception:
            continue
        if o > t1 or c < t0:          # keep any trade overlapping the window
            continue
        out.append(dict(side=side, ep=ep, xp=xp, o=o, c=c, pnl=pnl or 0.0,
                        gate=gate or "?", reason=reason or ""))
    return out


def _ticks_nice(lo, hi, n=5):
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / n
    mag = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 0.1
    step = next((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), 10 * mag)
    t, out = (int(lo / step) * step), []
    while t <= hi + step * 0.5:
        if t >= lo - step * 0.01:
            out.append(t)
        t += step
    return out


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(symbol, t0, t1, title, subtitle="", show_trades=True):
    pts = load_ticks(symbol, t0, t1)
    if len(pts) < 2:
        return f'<div class="callout"><div class="ct">No tick data for {_esc(title)} — chart omitted.</div></div>'
    trades = load_trades(symbol, t0, t1) if show_trades else []

    prices = [p for _, p in pts] + [t["ep"] for t in trades] + [t["xp"] for t in trades]
    lo, hi = min(prices), max(prices)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad

    def X(ts):
        return PAD_L + (ts - t0) * (W - PAD_L - PAD_R) / max(1, t1 - t0)

    def Y(px):
        return PAD_T + (hi - px) * (H - PAD_T - PAD_B) / (hi - lo)

    s = [f'<svg class="runchart" viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="{_esc(title)} — price path with trade entries and exits" '
         f'xmlns="http://www.w3.org/2000/svg" style="background:{SURFACE};font-family:system-ui,-apple-system,Segoe UI,sans-serif">']
    s.append(f'<title>{_esc(title)}</title>')

    # gridlines + price axis (recessive)
    for v in _ticks_nice(lo, hi):
        y = Y(v)
        if PAD_T - 2 <= y <= H - PAD_B + 2:
            s.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
            s.append(f'<text x="{PAD_L-8}" y="{y+3.5:.1f}" text-anchor="end" font-size="11" fill="{MUTED}" '
                     f'style="font-variant-numeric:tabular-nums">{v:,.0f}</text>')
    # time axis
    for i in range(5):
        ts = t0 + (t1 - t0) * i / 4
        x = X(ts)
        lbl = datetime.fromtimestamp(ts / 1000, timezone.utc).strftime("%H:%M")
        s.append(f'<text x="{x:.1f}" y="{H-PAD_B+18}" text-anchor="middle" font-size="11" fill="{MUTED}" '
                 f'style="font-variant-numeric:tabular-nums">{lbl}</text>')
    s.append(f'<line x1="{PAD_L}" y1="{H-PAD_B}" x2="{W-PAD_R}" y2="{H-PAD_B}" stroke="{AXIS}" stroke-width="1"/>')

    # price path — 2px, thin, recessive ink
    d = " ".join(f"{'M' if i == 0 else 'L'}{X(ts):.1f},{Y(px):.1f}" for i, (ts, px) in enumerate(pts))
    s.append(f'<path d="{d}" fill="none" stroke="{PRICE}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" opacity="0.85"/>')

    # trades: held segment + entry (direction triangle) + exit (circle) + signed $ label
    for t in trades:
        col = WIN if t["pnl"] >= 0 else LOSS
        x0, y0, x1c, y1 = X(max(t["o"], t0)), Y(t["ep"]), X(min(t["c"], t1)), Y(t["xp"])
        tip = (f'{t["gate"]} {t["side"]} · in {t["ep"]:,.2f} @ '
               f'{datetime.fromtimestamp(t["o"]/1000, timezone.utc):%H:%M:%S} → out {t["xp"]:,.2f} @ '
               f'{datetime.fromtimestamp(t["c"]/1000, timezone.utc):%H:%M:%S} · {t["reason"]} · '
               f'{"+" if t["pnl"] >= 0 else "-"}${abs(t["pnl"]):,.2f}')
        s.append(f'<g><title>{_esc(tip)}</title>')
        s.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1c:.1f}" y2="{y1:.1f}" stroke="{col}" '
                 f'stroke-width="2" opacity="0.55"/>')
        # entry: triangle, apex = trade direction (shape carries side, not colour)
        up = t["side"].upper() == "LONG"
        tri = (f'{x0:.1f},{y0-6:.1f} {x0-5.5:.1f},{y0+4:.1f} {x0+5.5:.1f},{y0+4:.1f}' if up
               else f'{x0:.1f},{y0+6:.1f} {x0-5.5:.1f},{y0-4:.1f} {x0+5.5:.1f},{y0-4:.1f}')
        s.append(f'<polygon points="{tri}" fill="{col}" stroke="{SURFACE}" stroke-width="2"/>')
        # exit: circle
        s.append(f'<circle cx="{x1c:.1f}" cy="{y1:.1f}" r="4.5" fill="{col}" stroke="{SURFACE}" stroke-width="2"/>')
        s.append('</g>')

    # selective direct labels — only the trades worth naming, never a number on every point.
    # De-conflict vertically: a label that would collide with one already placed walks up/down
    # until it finds clear air, so a dense cluster stays readable instead of overprinting.
    placed = []
    for t in sorted(trades, key=lambda z: -abs(z["pnl"]))[:6]:
        x1c, y1 = X(min(t["c"], t1)), Y(t["xp"])
        txt = f'{"+" if t["pnl"] >= 0 else "-"}${abs(t["pnl"]):,.0f}'
        lx0, w = x1c + 8, len(txt) * 6.6
        ly = y1 - 7
        for cand in [ly] + [ly + d for k in range(1, 9) for d in (-13 * k, 13 * k)]:
            if PAD_T + 8 <= cand <= H - PAD_B - 2 and not any(
                    abs(cand - py) < 12 and lx0 < px + pw + 4 and px < lx0 + w + 4 for px, py, pw in placed):
                ly = cand
                break
        placed.append((lx0, ly, w))
        # leader line when the label had to move off its marker
        if abs(ly - (y1 - 7)) > 4:
            s.append(f'<line x1="{x1c+3:.1f}" y1="{y1:.1f}" x2="{lx0-2:.1f}" y2="{ly-3.5:.1f}" '
                     f'stroke="{AXIS}" stroke-width="1"/>')
        s.append(f'<text x="{lx0:.1f}" y="{ly:.1f}" font-size="11" font-weight="600" fill="{INK}" '
                 f'style="font-variant-numeric:tabular-nums">{txt}</text>')

    # title + legend (identity never colour-alone: shape + text)
    # one <text> with tspans: the subtitle FLOWS after the title, so a long title can never
    # overprint it (a measured dx offset does — that bug shipped once already).
    sub = f'<tspan dx="10" font-size="11" font-weight="400" fill="{INK2}">{_esc(subtitle)}</tspan>' if subtitle else ''
    s.append(f'<text x="{PAD_L}" y="16" font-size="13" font-weight="700" fill="{INK}">{_esc(title)}{sub}</text>')
    lx = W - PAD_R - 268
    s.append(f'<polygon points="{lx},{9.5} {lx-5},{18.5} {lx+5},{18.5}" fill="{INK2}"/>')
    s.append(f'<text x="{lx+9}" y="18" font-size="10.5" fill="{INK2}">long in</text>')
    s.append(f'<polygon points="{lx+56},{18.5} {lx+51},{9.5} {lx+61},{9.5}" fill="{INK2}"/>')
    s.append(f'<text x="{lx+65}" y="18" font-size="10.5" fill="{INK2}">short in</text>')
    s.append(f'<circle cx="{lx+119}" cy="14.5" r="4.5" fill="{INK2}"/>')
    s.append(f'<text x="{lx+128}" y="18" font-size="10.5" fill="{INK2}">out</text>')
    s.append(f'<circle cx="{lx+163}" cy="14.5" r="4.5" fill="{WIN}"/>')
    s.append(f'<text x="{lx+172}" y="18" font-size="10.5" fill="{INK2}">win</text>')
    s.append(f'<circle cx="{lx+205}" cy="14.5" r="4.5" fill="{LOSS}"/>')
    s.append(f'<text x="{lx+214}" y="18" font-size="10.5" fill="{INK2}">loss</text>')
    s.append('</svg>')
    return "\n".join(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="MNQ")
    ap.add_argument("--from", dest="t0")
    ap.add_argument("--to", dest="t1")
    ap.add_argument("--title", default="")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--out")
    ap.add_argument("--spec", help="JSON list of {from,to,title,subtitle} -> one HTML fragment")
    ap.add_argument("--fragment", help="output HTML fragment path (with --spec)")
    a = ap.parse_args()

    if a.spec:
        specs = json.load(open(a.spec))
        parts = []
        for sp in specs:
            svg = render(sp.get("symbol", a.symbol), _ms(sp["from"]), _ms(sp["to"]),
                         sp.get("title", ""), sp.get("subtitle", ""))
            note = sp.get("note", "")
            parts.append(f'<div class="card">{svg}' + (f'<p>{_esc(note)}</p>' if note else '') + '</div>')
        out = "\n".join(parts)
        (open(a.fragment, "w") if a.fragment else sys.stdout).write(out)
        print(f"wrote {len(specs)} chart(s) -> {a.fragment}", file=sys.stderr)
        return

    svg = render(a.symbol, _ms(a.t0), _ms(a.t1), a.title, a.subtitle)
    (open(a.out, "w") if a.out else sys.stdout).write(svg)
    if a.out:
        print(f"wrote {a.out} ({len(svg):,} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
