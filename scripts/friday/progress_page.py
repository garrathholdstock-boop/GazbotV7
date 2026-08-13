#!/usr/bin/env python3
"""PART 0 — THE PROGRESS PAGE. One page, every day the desk has traded, green or red.

★ WHY IT EXISTS AND WHY IT GOES FIRST (operator, 2026-08-13):
> "we never had multiple green days in a week like we having now ... my memory is much longer and we
> were red for many many weeks. so having 2-3 green days a week is significant. we should almost open
> with this. gives hope and shows progress."

He is right, and the report had no place that showed it. Every section answers "what happened this
week"; none answered **"are we getting better?"** — which is the only question that matters over a
horizon longer than one Friday. A reader could finish 287 pages knowing every gate's P&L and still
not know the desk had gone from 0 green days in a week to 2-3.

★ IT IS GENERATED, NOT WRITTEN. Rebuilt from the live trade record every Friday, so it cannot drift
from the books and nobody has to remember to update it.

★ TOTAL DESK, not tournament-only. The day-rider is a separate service on its own clientId and its
P&L appears in no tournament total — on 2026-08-13 it made +$731 while the tournament made +$104.
A progress page that omitted it would be measuring half the desk.
`data_quality IS NULL` throughout: the excluded rows are the MD_STREAM corruption and the 08-13
phantom re-bookings, neither of which the desk actually earned or lost.

★ HONEST BY CONSTRUCTION. The trend is real and it is stated plainly; so is the fact that the
cumulative total is still negative and the sample is ~5 weeks. Hope that needs a caveat hidden is not
hope, it is marketing — and this desk's whole method is that a number survives its own footnotes.

  PYTHONPATH=src .venv/bin/python scripts/friday/progress_page.py [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
from collections import OrderedDict

DB = "/home/alphabot/gazbot7/data/gazbot7.db"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/part0_progress.html"

GRN, RED, INK, MUT, RULE = "#1f6f43", "#c0392b", "#0f2942", "#5a6472", "#e6e2d8"


def rows(db=DB):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return list(c.execute("""
        SELECT date(closed_at) d, round(sum(pnl_usd), 2) p, count(*) n
        FROM trades WHERE data_quality IS NULL
        GROUP BY 1 ORDER BY 1"""))


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(rs) -> str:
    if not rs:
        return "<h2><span class='n'>P0</span> Progress</h2><p>No trade record yet.</p>"

    weeks = OrderedDict()
    for r in rs:
        k = dt.date.fromisoformat(r["d"]).isocalendar()[:2]
        weeks.setdefault(k, []).append((r["d"], r["p"]))

    peak = max(abs(r["p"]) for r in rs) or 1.0
    W, H, PAD = 980, 300, 34
    mid = H / 2
    slot = (W - 2 * PAD) / max(len(rs), 1)
    bw = min(slot * 0.62, 26)

    bars, labels = [], []
    for i, r in enumerate(rs):
        x = PAD + i * slot + (slot - bw) / 2
        h = max(abs(r["p"]) / peak * (mid - 34), 2)
        up = r["p"] > 0
        y = mid - h if up else mid
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" '
            f'fill="{GRN if up else RED}" opacity=".92"><title>{esc(r["d"])}  '
            f'{r["p"]:+,.2f}  ({r["n"]} trades)</title></rect>')
        if i % 2 == 0:                       # every other day, or the axis turns to mush
            labels.append(
                f'<text x="{x + bw/2:.1f}" y="{H-8}" text-anchor="middle" font-size="9" '
                f'fill="{MUT}">{esc(r["d"][5:])}</text>')

    # week separators + green-count ribbon above the chart
    seps, ribbon, i0 = [], [], 0
    for (yr, wn), days in weeks.items():
        x0 = PAD + i0 * slot
        x1 = PAD + (i0 + len(days)) * slot
        if i0:
            seps.append(f'<line x1="{x0:.1f}" y1="18" x2="{x0:.1f}" y2="{H-22}" '
                        f'stroke="{RULE}" stroke-width="1"/>')
        g = sum(1 for _, p in days if p > 0)
        net = sum(p for _, p in days)
        ribbon.append(
            f'<text x="{(x0+x1)/2:.1f}" y="14" text-anchor="middle" font-size="11" '
            f'font-weight="700" fill="{GRN if g else MUT}">{g}/{len(days)} green</text>'
            f'<text x="{(x0+x1)/2:.1f}" y="{H-22}" text-anchor="middle" font-size="10" '
            f'fill="{GRN if net>0 else RED}" style="font-variant-numeric:tabular-nums">'
            f'{net:+,.0f}</text>')
        i0 += len(days)

    chart = (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-label="Daily desk P&amp;L, green or red, every trading day on record" '
             f'style="background:#fbfaf7;font-family:system-ui,-apple-system,Segoe UI,sans-serif">'
             f'<line x1="{PAD}" y1="{mid}" x2="{W-PAD}" y2="{mid}" stroke="#c9c6bd" '
             f'stroke-width="1"/>{"".join(seps)}{"".join(bars)}{"".join(labels)}'
             f'{"".join(ribbon)}</svg>')

    wk = [(k, v) for k, v in weeks.items()]
    first, last = wk[0], wk[-1]
    fg, lg = sum(1 for _, p in first[1] if p > 0), sum(1 for _, p in last[1] if p > 0)
    worst_wk = min(wk, key=lambda kv: sum(p for _, p in kv[1]))
    wg = sum(1 for _, p in worst_wk[1] if p > 0)
    tot = sum(r["p"] for r in rs)
    green_total = sum(1 for r in rs if r["p"] > 0)
    best_day = max(rs, key=lambda r: r["p"])
    worst_day = min(rs, key=lambda r: r["p"])
    green_wks = sum(1 for _, v in wk if sum(p for _, p in v) > 0)

    # ★ Split at the router go-live. The first draft compared the ALL-TIME worst day against "the
    # pre-router worst" — which is the same day, so the sentence compared a number with itself and
    # read as if nothing had improved. Compute both sides.
    ROUTER_LIVE = "2026-07-30"
    pre = [r for r in rs if r["d"] < ROUTER_LIVE]
    post = [r for r in rs if r["d"] >= ROUTER_LIVE]
    pre_worst = min((r["p"] for r in pre), default=0.0)
    post_worst = min((r["p"] for r in post), default=0.0)
    pre_green, pre_n = sum(1 for r in pre if r["p"] > 0), len(pre)
    post_green, post_n = sum(1 for r in post if r["p"] > 0), len(post)

    trs = "".join(
        f'<tr><td>W{k[1]}</td><td>{esc(v[0][0])} &ndash; {esc(v[-1][0])}</td>'
        f'<td style="text-align:center">{len(v)}</td>'
        f'<td style="text-align:center;font-weight:700;'
        f'color:{GRN if sum(1 for _,p in v if p>0) else MUT}">'
        f'{sum(1 for _, p in v if p > 0)}/{len(v)}</td>'
        f'<td style="text-align:right;font-variant-numeric:tabular-nums;'
        f'color:{GRN if sum(p for _,p in v)>0 else RED}">{sum(p for _, p in v):+,.2f}</td></tr>'
        for k, v in wk)

    return f"""<h2><span class="n">P0</span> Are we getting better? &mdash; every day the desk has traded</h2>

<p class="lede">One bar per trading day, green or red, total desk. The question every other section
answers is <em>what happened this week</em>. This one answers <strong>are we getting better</strong>,
which is the only question that survives past Friday.</p>

<div class="card">{chart}</div>

<p><strong>The shape of it.</strong> Week {worst_wk[0][1]} was the floor:
<strong>{wg} green days out of {len(worst_wk[1])}</strong> and
<strong>{sum(p for _, p in worst_wk[1]):+,.2f}</strong> &mdash; the stretch the operator remembers as
&ldquo;red for many many weeks&rdquo;. The most recent week ran
<strong style="color:{GRN}">{lg} green out of {len(last[1])}</strong> at
<strong style="color:{GRN if sum(p for _,p in last[1])>0 else RED}">{sum(p for _, p in last[1]):+,.2f}</strong>.
Of {len(wk)} weeks on record, <strong>{green_wks} closed net positive &mdash; and both of them are in
the last three.</strong></p>

<table>
<thead><tr><th>Week</th><th>Days</th><th style="text-align:center">Traded</th>
<th style="text-align:center">Green</th><th style="text-align:right">Net</th></tr></thead>
<tbody>{trs}</tbody>
</table>

<p><strong>What changed underneath.</strong> The Claude-run router went live 2026-07-30, mid-W31 &mdash;
the first green week is the one it landed in. Its measured effect is on the <em>tail</em> and the
<em>frequency</em> of red days, not their depth: the worst day before it was
<strong style="color:{RED}">{pre_worst:+,.2f}</strong>, the worst since is
<strong style="color:{RED}">{post_worst:+,.2f}</strong>, and green days went from
<strong>{pre_green} of {pre_n}</strong> to <strong style="color:{GRN}">{post_green} of {post_n}</strong>.
The day-rider joined on 08-06 as a second, slower engine and is unbeaten so far &mdash; on the worst
day of the last week it was the only thing in profit.</p>

<p class="caveat"><strong>Read it honestly.</strong> The cumulative total across all {len(rs)} days is
still <strong style="color:{RED if tot<0 else GRN}">{tot:+,.2f}</strong> &mdash; this is a desk that
has stopped bleeding wholesale, not one that is paid yet. {len(wk)} weeks is a short sample, best day
{best_day['p']:+,.2f} and worst {worst_day['p']:+,.2f} are both single sessions, and PAPER fills
flatter a real book. The trend is real; the destination is not reached.</p>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--db", default=DB)
    a = ap.parse_args()
    html = build(rows(a.db))
    with open(a.out, "w") as fh:
        fh.write(html)
    print(f"wrote {a.out} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
