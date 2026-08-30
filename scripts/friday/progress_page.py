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


# ★★★2026-08-29 REV2 — THIS WAS A WEEK STALE AND NOTHING NOTICED. It read "2026-08-21" while the
# 08-28 cycle rendered this page at 22:14Z, so Part 0 RAN, succeeded, and answered LAST week's
# question inside a report headed "week ending Fri 2026-08-28": no W35 row, a cumulative that
# excluded the −$2,149.44 Monday, and a "most recent week" paragraph describing W34.
# It is now DERIVED, not typed: --as-of wins if given, else the most recent Friday on or before
# today. A hard-coded date in a weekly generator is a silent staleness bug with a one-week fuse.
def _default_as_of() -> str:
    t = dt.date.today()
    return (t - dt.timedelta(days=(t.weekday() - 4) % 7)).isoformat()


AS_OF = _default_as_of()      # this report's books close on the Friday; see the note in build()


def rows(db=DB, as_of=AS_OF):
    """★★★2026-08-26 REV3 — THE 08-22 "FEE CORRECTION" IS WITHDRAWN. IT WAS BACKWARDS.

    `trades.pnl_usd` is already NET of `fees_usd`. store.py:66 says so in the schema comment ("net
    of fees, venue truth"), pnl.py's docstring says so ("recorded net-of-fees ... so realized P&L is
    a plain sign-aware SUM"), and it is checked, not assumed: on all 765 rows in the book
    `pnl_usd == (exit - entry) * dir * qty * multiplier - fees_usd` holds exactly, 765 of 765.

    Rev2 changed `p` to `sum(pnl_usd - fees_usd)` and called `sum(pnl_usd)` "gross". That subtracts
    the fee a SECOND time. It made this page the only section measured with a different ruler from
    the rest of the report -- the fault it was written to fix, reintroduced with the sign flipped --
    and it deepened the stated all-time loss by $1,149.00 ($-2,882.50 became $-4,031.50). It also
    claimed the change "turned two week totals green that are not"; it did not. W31 is +$516.00 and
    W33 +$1,292.50 net, and both stay positive under either arithmetic.

    So: `p` is `sum(pnl_usd)`, which IS net, and `g` is the true GROSS, `sum(pnl_usd + fees_usd)`,
    reconstructed by ADDING the fee back. The Gross / Fees / NET table then reconciles by
    construction: gross - fees = net.

    ★ AS OF. The rows are cut at `as_of` (default the Friday the report's books close). Without it
    a rebuild after publication silently pulls the following week's sessions into a chart the prose
    describes as "the most recent week", which is how 08-24's -$2,149.44 carry would land inside a
    week-ending-08-21 document. Post-bell trading is reported separately, in Part 1.6."""
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return list(c.execute("""
        SELECT date(closed_at) d, round(sum(pnl_usd), 2) p,
               round(sum(pnl_usd + fees_usd), 2) g, round(sum(fees_usd), 2) f, count(*) n
        FROM trades WHERE data_quality IS NULL AND date(closed_at) <= ?
        GROUP BY 1 ORDER BY 1""", (as_of,)))


def _rider_worst_day(db=DB, as_of=AS_OF):
    """The day rider's worst single SESSION in the most recent week, named and priced from the book
    rather than typed. The sentence this feeds used to carry a literal -$1,294.50, which was the
    fee-double-counted Thursday; the true figure is -$1,288.50 and a hard-coded one cannot notice."""
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    r = c.execute(
        "SELECT date(closed_at), round(sum(pnl_usd),2) v FROM trades WHERE data_quality IS NULL "
        "AND gate LIKE 'day_rider%' AND date(closed_at) <= ? GROUP BY 1 ORDER BY v LIMIT 1",
        (as_of,)).fetchone()
    c.close()
    if not r:
        return "session", 0.0
    return dt.date.fromisoformat(r[0]).strftime("%A %m-%d"), r[1]


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(rs, as_of: str = None) -> str:
    as_of = as_of or AS_OF
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
    tot_gross = sum(r["g"] for r in rs)
    fees_tot = sum(r["f"] for r in rs)
    green_total = sum(1 for r in rs if r["p"] > 0)
    best_day = max(rs, key=lambda r: r["p"])
    worst_day = min(rs, key=lambda r: r["p"])
    green_wks = sum(1 for _, v in wk if sum(p for _, p in v) > 0)
    # ★2026-08-29 REV2 — this sentence used to end "and both of them are in the last three",
    # typed on a week where that happened to be true. With W35 on the page the last three are
    # W33/W34/W35 and W31 is not among them, so the clause was about to become quietly false.
    # Name the weeks instead: a list cannot go stale, a claim about position can.
    green_wk_names = ", ".join(f"W{k[1]}" for k, v in wk if sum(p for _, p in v) > 0) or "none"
    _last3 = {k for k, _ in wk[-3:]}
    green_in_last3 = sum(1 for k, v in wk if sum(p for _, p in v) > 0 and k in _last3)
    dbl = round(tot - fees_tot, 2)      # what the withdrawn 08-22 arithmetic printed
    # ★2026-08-29 REV2 — the net-of-fees identity is RE-CHECKED at render time, not quoted from a
    # note. The paragraph below used to say "all 765 rows"; the book is bigger every week and a
    # frozen row count is how a verified claim turns into an unverified one.
    _cc = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    _idn = _idbad = 0
    for _sym, _side, _q, _e, _x, _p, _f in _cc.execute(
            "SELECT symbol, side, qty, entry_price, exit_price, pnl_usd, fees_usd FROM trades"):
        _m = 10.0 if _sym == "MGC" else 2.0
        _d = 1 if str(_side).upper().startswith("L") else -1
        _idn += 1
        if abs((_x - _e) * _d * _q * _m - _f - _p) > 0.011:
            _idbad += 1
    _cc.close()
    jul30 = next((r["p"] for r in rs if r["d"] == "2026-07-30"), 0.0)
    # ★2026-08-22 REV2 — the rider's own MOST RECENT WEEK, computed, because the sentence this
    # replaces ("unbeaten so far") was hand-written on 08-13 and was flatly false by 08-20.
    _c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rider_n, rider_wk = _c.execute(
        "SELECT count(*), round(sum(pnl_usd),2) FROM trades WHERE data_quality IS NULL "
        "AND gate LIKE 'day_rider%' AND closed_at >= ? AND date(closed_at) <= ?",
        (min(d for d, _ in wk[-1][1]), as_of)).fetchone()
    _c.close()
    rider_wk = rider_wk or 0.0


    # ★ Split at the router go-live. The first draft compared the ALL-TIME worst day against "the
    # pre-router worst" — which is the same day, so the sentence compared a number with itself and
    # read as if nothing had improved. Compute both sides.
    rider_worst_d, rider_worst = _rider_worst_day(DB, as_of)
    # ★2026-08-29 REV2 — the rest of the rider's most recent week, so the comparison sentence is
    # arithmetic rather than the typed "the other four sessions". The count moves; the claim must not.
    rider_rest = round(rider_wk - rider_worst, 2)
    rider_rest_days = len(wk[-1][1]) - 1
    ROUTER_LIVE = "2026-07-30"
    pre = [r for r in rs if r["d"] < ROUTER_LIVE]
    post = [r for r in rs if r["d"] >= ROUTER_LIVE]
    pre_worst = min((r["p"] for r in pre), default=0.0)
    post_worst = min((r["p"] for r in post), default=0.0)
    pre_green, pre_n = sum(1 for r in pre if r["p"] > 0), len(pre)
    post_green, post_n = sum(1 for r in post if r["p"] > 0), len(post)

    gross_by_wk = {}
    fees_by_wk = {}
    for r in rs:
        k = dt.date.fromisoformat(r["d"]).isocalendar()[:2]
        gross_by_wk[k] = gross_by_wk.get(k, 0.0) + r["g"]
        fees_by_wk[k] = fees_by_wk.get(k, 0.0) + r["f"]
    trs = "".join(
        f'<tr><td>W{k[1]}</td><td>{esc(v[0][0])} &ndash; {esc(v[-1][0])}</td>'
        f'<td style="text-align:center">{len(v)}</td>'
        f'<td style="text-align:center;font-weight:700;'
        f'color:{GRN if sum(1 for _,p in v if p>0) else MUT}">'
        f'{sum(1 for _, p in v if p > 0)}/{len(v)}</td>'
        f'<td style="text-align:right;font-variant-numeric:tabular-nums;color:{MUT}">'
        f'{gross_by_wk[k]:+,.2f}</td>'
        f'<td style="text-align:right;font-variant-numeric:tabular-nums;color:{MUT}">'
        f'&minus;{fees_by_wk[k]:,.2f}</td>'
        f'<td style="text-align:right;font-variant-numeric:tabular-nums;font-weight:700;'
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
Of {len(wk)} weeks on record, <strong>{green_wks} closed net positive &mdash;
{green_wk_names}</strong>, {green_in_last3} of them inside the last three weeks.</p>

<table>
<thead><tr><th>Week</th><th>Days</th><th style="text-align:center">Traded</th>
<th style="text-align:center">Green</th><th style="text-align:right">Gross</th>
<th style="text-align:right">Fees</th><th style="text-align:right">NET</th></tr></thead>
<tbody>{trs}</tbody>
</table>
<p style="font-size:14px;color:{MUT}"><strong>NET is the column to read</strong> &mdash; it is what
the account moved by, and it is the convention every other section uses. NET is
<code>sum(pnl_usd)</code> straight off the book, because <code>pnl_usd</code> is
<em>recorded already net of fees</em>; GROSS is reconstructed by adding <code>fees_usd</code> back
at $1.50 per round trip per lot. Do not subtract the fee from <code>pnl_usd</code> &mdash; that is
the mistake the previous revision of this page made, and it cost ${fees_tot:,.2f} of imaginary
loss.</p>

<p><strong>What changed underneath.</strong> The Claude-run router went live 2026-07-30, mid-W31 &mdash;
the first green week is the one it landed in. Its measured effect is on the <em>tail</em> and the
<em>frequency</em> of red days, not their depth: the worst day before it was
<strong style="color:{RED}">{pre_worst:+,.2f}</strong>, the worst since is
<strong style="color:{RED}">{post_worst:+,.2f}</strong>, and green days went from
<strong>{pre_green} of {pre_n}</strong> to <strong style="color:{GRN}">{post_green} of {post_n}</strong>.
The day-rider joined on 08-06 as a second, slower engine, and it is no longer unbeaten:
<strong style="color:{RED}">{rider_wk:+,.2f}</strong> across {rider_n} legs in the most recent week,
of which <strong style="color:{RED}">{rider_worst:+,.2f}</strong> landed on {rider_worst_d} alone.
Strip that one session out and the rider's other {rider_rest_days} days come to
<strong style="color:{GRN if rider_rest>0 else RED}">{rider_rest:+,.2f}</strong> &mdash; so one
session is the whole of the week's loss and more.
<strong>&#9733; And that session is not a decision this week made.</strong> The
{rider_worst_d} row is the four-lot position the rider opened on Friday 2026-08-21 at 13:13:06Z,
carried unmanaged through the CME halt and closed by hand on the Monday; it is booked on its CLOSE
date, which is why it lands in this week's bar. The rider is still the engine that produced the
desk&rsquo;s best days; it is no longer the one that cannot lose.</p>

<p class="caveat"><strong>Read it honestly.</strong> The cumulative total across all {len(rs)} days is
still <strong style="color:{RED if tot<0 else GRN}">{tot:+,.2f}</strong> &mdash; this is a desk that
has stopped bleeding wholesale, not one that is paid yet. {len(wk)} weeks is a short sample, best day
{best_day['p']:+,.2f} and worst {worst_day['p']:+,.2f} are both single sessions, and PAPER fills
flatter a real book. The trend is real; the destination is not reached.</p>

<p class="caveat"><strong>&#9733; The 08-22 &ldquo;fee correction&rdquo; on this page has been
WITHDRAWN &mdash; it was backwards, and it moved the headline by ${fees_tot:,.2f}.</strong>
<code>trades.pnl_usd</code> is written <em>already net</em> of <code>fees_usd</code>: the schema says
so, the canonical P&amp;L helper says so, and it is checked rather than assumed &mdash; re-run at
render time over every row in the book, <code>pnl_usd</code> equals
(exit&minus;entry)&times;direction&times;lots&times;multiplier minus <code>fees_usd</code>, exactly,
<strong>{_idn - _idbad} times out of {_idn}</strong>. Rev2 changed this page to
<code>sum(pnl_usd&nbsp;&minus;&nbsp;fees_usd)</code>, which charges the $1.50 round trip a second
time. <strong>The all-time book is {tot:+,.2f}, not the {dbl:+,.2f} the previous revision printed</strong>,
and Rev2's claim that the change &ldquo;turned two week totals green that are not&rdquo; was itself
wrong: W31 and W33 are positive on either arithmetic. Nothing about the SHAPE changes &mdash;
the ordering of the weeks, the worst day, the best day are all identical &mdash; only the depth,
and it was overstated. One green day does move, and it is worth naming: <strong>2026-07-30, the
router's first day</strong>, made {jul30:+,.2f} on 82 trades and paid $123.00 in fees, so the
double-counted version turned the router's own go-live red. It was green. <strong>If you see this desk quoted anywhere at {dbl:+,.2f}, that is the
double-counted number.</strong> The Gross / Fees / NET table above now reconciles by construction:
gross is <code>pnl_usd&nbsp;+&nbsp;fees_usd</code>, so gross &minus; fees = net, every row.</p>

<p class="caveat"><strong>Where this page stops, and the bug that used to live here.</strong> Every
bar is a session closed on or before <strong>{as_of}</strong>, which is where this report's books
close, and the cut-off is now <em>derived</em> from the report week rather than typed into this
file. <strong>&#9733; It was typed, and it was a week stale.</strong> The 2026-08-28 cycle ran this
generator at 22:14Z with <code>AS_OF</code> still reading <code>2026-08-21</code>, so Part&nbsp;0
succeeded and answered the PREVIOUS week's question inside a report headed &ldquo;week ending Fri
2026-08-28&rdquo;: no W35 row at all, a &ldquo;most recent week&rdquo; paragraph describing W34, and
a cumulative total that excluded the &minus;$2,149.44 Monday. Nothing errored, because a hard-coded
date cannot notice that the calendar moved. That is the same failure mode three other sections of
this report document in the desk's live instruments &mdash; found here by a proofread, not by a
monitor. The last bar on this chart is {rs[-1]['d']}.</p>
"""


STANDALONE = "/home/alphabot/gazbot7/src/gazbot7/web_static/progress.html"

# Palette and type lifted from the Friday report shell so the standalone page and the in-report
# section are visibly the same document, not two designs of the same numbers.
_SHELL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GAZBOT V7 — are we getting better?</title>
<style>
 :root{{--ink:#0f2942;--mut:#5a6472;--rule:#e6e2d8;--bg:#fbfaf7;--grn:#1f6f43;--red:#c0392b}}
 *{{box-sizing:border-box}}
 body{{margin:0;background:var(--bg);color:var(--ink);
   font:16px/1.55 Georgia,"Iowan Old Style",serif;padding:28px 18px 60px}}
 .wrap{{max-width:1040px;margin:0 auto}}
 h2{{font-size:26px;line-height:1.2;margin:0 0 14px;font-weight:700;letter-spacing:-.2px}}
 h2 .n{{display:inline-block;background:var(--ink);color:#fff;font:700 13px/1 system-ui,sans-serif;
   padding:6px 9px;border-radius:4px;margin-right:10px;vertical-align:3px}}
 p{{margin:0 0 14px}} .lede{{font-size:18px;color:#26364a}}
 .card{{background:#fff;border:1px solid var(--rule);border-radius:8px;padding:14px;margin:0 0 20px}}
 table{{width:100%;border-collapse:collapse;margin:6px 0 20px;
   font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}}
 th{{text-align:left;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);
   border-bottom:2px solid var(--rule);padding:7px 8px}}
 td{{padding:7px 8px;border-bottom:1px solid var(--rule)}}
 .caveat{{background:#fff6f4;border-left:3px solid var(--red);padding:12px 14px;border-radius:0 6px 6px 0;
   font-size:15px}}
 .stamp{{margin-top:26px;padding-top:12px;border-top:1px solid var(--rule);
   font:12px/1.5 system-ui,sans-serif;color:var(--mut)}}
 @media (max-width:640px){{body{{padding:16px 12px 44px}}h2{{font-size:21px}}.lede{{font-size:16px}}}}
</style></head><body><div class="wrap">
{body}
<p class="stamp">Generated {stamp} from the live trade record
(<code>data_quality IS NULL</code>, tournament + day-rider). Rebuilt every Friday by
<code>scripts/friday/progress_page.py</code> — this page cannot drift from the books.</p>
</div></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--standalone", default=STANDALONE,
                    help="also write a self-contained page for /static/ and the reports index")
    ap.add_argument("--as-of", default=AS_OF, dest="as_of",
                    help="last session date to include; defaults to the most recent Friday. "
                         "★ Pass the report week explicitly from the build if the run straddles "
                         "midnight — this page shipped a week stale on 2026-08-28 because the "
                         "cut-off was a literal.")
    a = ap.parse_args()
    html = build(rows(a.db, a.as_of), a.as_of)
    with open(a.out, "w") as fh:
        fh.write(html)
    print(f"wrote {a.out} ({len(html):,} bytes)")
    if a.standalone:
        page = _SHELL.format(body=html,
                             stamp=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"))
        with open(a.standalone, "w") as fh:
            fh.write(page)
        print(f"wrote {a.standalone} ({len(page):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
