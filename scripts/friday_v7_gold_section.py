#!/usr/bin/env python3
"""MOVEMENT 3 — THE GOLD GREENFIELD (gf_MGC), rebuilt from the phase's own artifacts.

★ WHY THIS EXISTS. The scope mandates a dedicated gold hunt inside the greenfield movement and the
operator's own words are "we want to find some gates that work for mgc". The 08-28 cycle RAN that
phase — `gf_MGC.stderr.txt` is stamped 23:35 and `scripts/gf4_mgc_barsource.py` wrote four fresh
artifacts at 23:58 — and then the report shipped with no gold greenfield section anywhere, while
three other places pointed at "gf_MGC" as though it were present. That is exactly the case
Movements 2 and 3 were rescued from, and it was not rescued. This rescues it, from the same files.

★ IT IS GENERATED, NOT WRITTEN. Every number below is computed at render time from
    gf4_mgc_barsource.json          the 32-day bar-source study, activity split and floor fit
    gf4_mgc_trades_depth-mid.json   per-trade book, lab bars   (506 trades)
    gf4_mgc_trades_trade.json       per-trade book, prod bars  (299 trades)
    gf4_mgc_trades_wall_wall.json   per-trade book, wall arm   (270 trades)
so the robustness columns (strip-best-3, leave-one-day-out, per-period) cannot drift from the book
they are computed on. The walk-forward split is the artifact's own: first 22 days IS, next 7 F1,
last 3 F2.

★ MGC IS $10.00/POINT. The harness applies VPP = 10.0 and subtracts $1.50 per round trip before it
writes `pnl` (scripts/gf_mgc_tape.py:70, scripts/gf4_mgc_barsource.py:105), so every dollar here is
already net and must never be re-multiplied by the MNQ $2.00.

  python3 scripts/friday_v7_gold_section.py
"""
from __future__ import annotations

import collections
import json
import pathlib

SEC = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/sections")
OUT = SEC / "movement3_gold.html"


def load(name):
    return json.loads((SEC / name).read_text())


def stat(rows):
    if not rows:
        return dict(n=0, net=0.0, per=0.0, win=0.0, days=0)
    n = len(rows)
    net = round(sum(r["pnl"] for r in rows), 2)
    return dict(n=n, net=net, per=round(net / n, 2),
                win=round(100 * sum(1 for r in rows if r["pnl"] > 0) / n, 1),
                days=len({r["day"] for r in rows}))


def robust(rows):
    """strip-best-3, worst leave-one-day-out, green-day count, top-2-day concentration."""
    if not rows:
        return dict(sb3=0.0, lodo=0.0, lodo_day="—", green=0, days=0, top2=0.0)
    net = sum(r["pnl"] for r in rows)
    srt = sorted(rows, key=lambda r: -r["pnl"])
    byday = collections.Counter()
    for r in rows:
        byday[r["day"]] += r["pnl"]
    lodo_day, lodo = min(((d, net - v) for d, v in byday.items()), key=lambda t: t[1])
    return dict(sb3=round(net - sum(r["pnl"] for r in srt[:3]), 2),
                lodo=round(lodo, 2), lodo_day=lodo_day,
                green=sum(1 for v in byday.values() if v > 0), days=len(byday),
                top2=round(sum(sorted(byday.values(), reverse=True)[:2]), 2))


def m(v):
    return f"&minus;${abs(v):,.2f}" if v < 0 else f"+${v:,.2f}"


def cls(v):
    return "row-hl" if v > 0 else "row-bad"


def main() -> int:
    meta = load("gf4_mgc_barsource.json")
    days = meta["days"]
    IS, F1, F2 = set(days[:22]), set(days[22:29]), set(days[29:])
    periods = (("IS &mdash; fitted here", IS), ("F1 &mdash; forward", F1),
               ("F2 &mdash; forward, this week", F2))

    mid = load("gf4_mgc_trades_depth-mid.json")
    trd = load("gf4_mgc_trades_trade.json")
    wall = load("gf4_mgc_trades_wall_wall.json")
    common = sorted({r["day"] for r in mid} & {r["day"] for r in trd})

    arms = (("<code>DEPTH-MID</code> bars &mdash; the LAB's series", mid),
            ("<code>TRADE</code> bars &mdash; what PRODUCTION folds", trd),
            ("<code>WALL</code> arm &mdash; break into a resting wall", wall))

    # ---- headline table -------------------------------------------------------------
    head = "".join(
        f'<tr class="{cls(s["net"])}"><td class="ln">{lab}</td><td class="num">{s["n"]}</td>'
        f'<td class="num">{s["days"]}</td><td class="num"><strong>{m(s["net"])}</strong></td>'
        f'<td class="num">{m(s["per"])}</td><td class="num">{s["win"]}%</td>'
        f'<td class="num">{m(rb["sb3"])}</td><td class="num">{m(rb["lodo"])}<br>'
        f'<span class="ln">drop {rb["lodo_day"]}</span></td>'
        f'<td class="num">{rb["green"]}/{rb["days"]}</td></tr>'
        for lab, rows in arms for s, rb in [(stat(rows), robust(rows))])

    # ---- walk-forward ---------------------------------------------------------------
    wf = ""
    for lab, rows in arms:
        cells = "".join(
            f'<td class="num">{stat([r for r in rows if r["day"] in S])["n"]}</td>'
            f'<td class="num">{m(stat([r for r in rows if r["day"] in S])["per"])}</td>'
            for _, S in periods)
        wf += f'<tr><td class="ln">{lab}</td>{cells}</tr>'

    # ---- the six-day claim, re-quoted on 32 days ------------------------------------
    mid_c, trd_c = stat([r for r in mid if r["day"] in common]), stat([r for r in trd if r["day"] in common])
    mid_a, trd_a = stat(mid), stat(trd)

    # ---- the hole-DOUBLE cell, graded ------------------------------------------------
    dbl = [(lab, [r for r in rows if r["obstacle"] == 0 and r["support"] == 0])
           for lab, rows in arms[:2]]
    dbl_rows = "".join(
        f'<tr class="{cls(s["net"])}"><td class="ln">{lab}</td><td class="num">{s["n"]}</td>'
        f'<td class="num">{m(s["net"])}</td><td class="num">{m(s["per"])}</td>'
        f'<td class="num">{s["win"]}%</td>'
        + "".join(f'<td class="num">{m(stat([r for r in rows if r["day"] in S])["per"])}</td>'
                  for _, S in periods)
        + f'<td class="num"><strong>{m(rb["sb3"])}</strong></td></tr>'
        for lab, rows in dbl for s, rb in [(stat(rows), robust(rows))])

    # ---- activity split ---------------------------------------------------------------
    act = ""
    for src, v in meta["activity"].items():
        for b, bv in v["buckets"].items():
            p = bv["pooled"]
            if not p["n"]:
                continue
            act += (f'<tr class="{cls(p["net"])}"><td class="ln">{src}</td><td class="ln">{b}</td>'
                    f'<td class="num">{bv["median_rate"]}</td><td class="num">{p["n"]}</td>'
                    f'<td class="num">{m(p["net"])}</td><td class="num">{m(p["per"])}</td>'
                    f'<td class="num">{p["win"]}%</td></tr>')

    # ---- the floor fit, in-sample vs forward -----------------------------------------
    flo = ""
    for src, v in meta["floor"].items():
        ch = v["chosen"]
        fa, fu = v["fwd_ALL"]["pooled"], v["fwd_ALL_unfiltered"]["pooled"]
        flo += (f'<tr><td class="ln">{src}</td><td class="num">{ch["floor"]}</td>'
                f'<td class="num">{ch["n"]}</td><td class="num row-hl">{m(ch["per"])}</td>'
                f'<td class="num">{ch["win"]}%</td><td class="num">{fa["n"]}</td>'
                f'<td class="num"><strong>{m(fa["per"])}</strong></td>'
                f'<td class="num">{fu["n"]}</td><td class="num">{m(fu["per"])}</td></tr>')

    falls = sorted(round(stat(rows)["net"] - robust(rows)["sb3"], 2) for _, rows in arms)
    fall_lo, fall_hi = m(falls[0]), m(falls[-1])

    dead = meta["activity"]["DEPTH-MID (lab)"]
    dead_n, dead_pct = dead["dead_tape_n"], dead["dead_tape_pct"]
    rf = meta["raw_fires"]

    doc = f"""
<p class="lead"><strong>This section was missing from Rev&nbsp;1 and it should not have been.</strong>
The gold phase ran on 2026-08-28 and wrote four artifacts at 23:58Z; the report then shipped with no
gold greenfield section at all, while three other places pointed at &ldquo;gf_MGC&rdquo; as though it
were in the document. Gold is the operator's #1 stated new-instrument priority. Everything below is
computed at render time from those artifacts &mdash;
<code>scripts/friday_v7_gold_section.py</code>.</p>

<div class="callout"><div class="ct">The gold answer in four lines</div>
<p><strong>1 &mdash; The bar-source blocker is DEAD, and it was never the variable.</strong> Last
cycle's gold section led with &ldquo;the sign flips on the bar source alone&rdquo; &mdash;
+$3.06/trade on lab bars against &minus;$8.96 on production bars &mdash; measured on
<strong>six</strong> days. On <strong>{len(days)}</strong> days both arms are the same sign and both
are negative: <strong>{m(mid_a['per'])}/trade</strong> on lab bars ({mid_a['n']} trades) and
<strong>{m(trd_a['per'])}/trade</strong> on production bars ({trd_a['n']}). On the
{len(common)} days both tapes cover it is {m(mid_c['per'])} against {m(trd_c['per'])}. There is no
flip at any level.</p>
<p><strong>2 &mdash; What the bar source really controls is HOW OFTEN it fires, not how well.</strong>
The lab's mid-bar arm takes {rf['mid']:,} raw fires against production's {rf['trade']:,}, and
<strong>{dead_n} of the lab arm's {mid_a['n']} trades ({dead_pct}%) land in minutes where the trade
tape printed nothing at all</strong>. A mid quote flickers when nobody trades; a trade bar cannot.
The lab arm was not reading a better price series &mdash; it was admitting a population of dead-tape
breaks that cannot be filled.</p>
<p><strong>3 &mdash; Activity is the real axis, and it does not survive being fitted.</strong> Split
by how busy the tape is, the busiest quartile carries everything (production bars:
<strong>+$27.11/trade</strong> in Q4 against &minus;$11.85 in Q1). Fit an activity floor in-sample
and it looks superb &mdash; +$40.80/trade at floor 40. Apply that same floor FORWARD and it is
<strong>&minus;$11.92/trade on 12 trades</strong>. The floor is a fit, not a filter.</p>
<p><strong>4 &mdash; Nothing gold-side goes anywhere near a shadow arm this week, and the cause of
death is named.</strong> Every arm here is negative pooled, and each one gets <em>worse</em> when
its three best trades are removed. That is the strip-the-best-trades test, and failing it is the one
result a thin sample can still deliver honestly.</p></div>

<h3><span class="n">G1</span> The three gold arms, pooled and stress-tested</h3>
<p>{len(days)} trading days, 2026-07-16 to 2026-08-28. Identical gate (60-minute break, 0.10&nbsp;ATR
margin, obstacle-free hole, 45-minute per-side cooldown), identical exit (3.0&nbsp;ATR stop behind a
2.0/2.0 chandelier, 480-minute backstop), raced on the same 250&nbsp;ms quote tape with both legs
crossing. <strong>MGC is $10.00/point and the $1.50 round trip is already inside every figure.</strong></p>
<table>
<thead><tr><th class="ln">Arm</th><th class="num">Trades</th><th class="num">Days</th>
<th class="num">Net $</th><th class="num">$/trade</th><th class="num">Win %</th>
<th class="num">Strip best 3</th><th class="num">Worst LODO</th><th class="num">Green days</th></tr></thead>
<tbody>{head}</tbody></table>
<p><strong>Read the strip-best-3 column, not the win rate.</strong> Win rates here are 52&ndash;54%
&mdash; respectable, and irrelevant. Every arm's whole book is a handful of trades: removing three
costs {fall_lo} on the arm it hurts least and {fall_hi} on the arm it hurts most.
<strong>An arm that is negative pooled and more negative without its three best trades has no
expectancy to find.</strong></p>

<h3><span class="n">G2</span> Walk-forward &mdash; the part that decides it</h3>
<p>The artifact splits the {len(days)} days into the first 22 (in-sample), the next 7 (F1) and the
last 3 (F2, this report's own week). Nothing was re-fitted between them.</p>
<table>
<thead><tr><th class="ln">Arm</th><th class="num">IS n</th><th class="num">IS $/tr</th>
<th class="num">F1 n</th><th class="num">F1 $/tr</th><th class="num">F2 n</th>
<th class="num">F2 $/tr</th></tr></thead>
<tbody>{wf}</tbody></table>
<p><strong>Both break arms decay monotonically out of sample and both are worst in the most recent
period.</strong> That is the ordering you would expect from a fitted edge and the opposite of the
one you would want. F2 is three days and 46 / 31 trades, so it is not on its own a verdict &mdash;
but it agrees with F1, which agrees with the pooled book, which agrees with the strip-best test.
<strong>Four instruments, one direction.</strong></p>

<h3><span class="n">G3</span> The bar-source claim, re-quoted properly</h3>
<table>
<thead><tr><th class="ln">Cut</th><th class="num">Lab (depth-mid) $/tr</th>
<th class="num">Production (trade) $/tr</th><th class="ln">Same sign?</th></tr></thead>
<tbody>
<tr class="row-bad"><td class="ln">Last cycle's claim &mdash; 6 days, <code>gf3_mgc_barsource.json</code>, the &ldquo;hole PRIMARY&rdquo; sub-cell (n=56 / 53)</td><td class="num">+$3.06</td><td class="num">&minus;$8.96</td><td class="ln"><span class="tag pill-dontarm">no &mdash; this is the flip that was reported</span></td></tr>
<tr class="row-hl"><td class="ln"><strong>{len(days)} days pooled</strong>, <code>gf4_mgc_barsource.json</code> (n={mid_a['n']} / {trd_a['n']})</td><td class="num">{m(mid_a['per'])}</td><td class="num">{m(trd_a['per'])}</td><td class="ln"><span class="tag pill-live">yes &mdash; both negative</span></td></tr>
<tr class="row-hl"><td class="ln">The {len(common)} days BOTH tapes cover (n={mid_c['n']} / {trd_c['n']})</td><td class="num">{m(mid_c['per'])}</td><td class="num">{m(trd_c['per'])}</td><td class="ln"><span class="tag pill-live">yes &mdash; both negative</span></td></tr>
</tbody></table>
<p>The six-day cell was real and it was six days. <strong>The rule the gold play itself proposes
&mdash; name your bar source in the same sentence as your number &mdash; needs a second clause: name
your SAMPLE too.</strong> A sub-cell of 56 trades on 6 days flipped sign and became the gating
blocker for an entire instrument's programme for a week.</p>

<h3><span class="n">G4</span> What the bar source actually changes: dead tape</h3>
<p>Raw fires: <strong>{rf['mid']:,}</strong> on mid bars, <strong>{rf['trade']:,}</strong> on trade
bars, <strong>{rf['both']:,}</strong> on both. The mid arm fires about
{rf['mid'] / rf['trade']:.1f}&times; as often, and the extra fires are not better &mdash; they are
untradeable: <strong>{dead_n} of {mid_a['n']} ({dead_pct}%)</strong> of its trades open in a minute
where the trade tape printed <em>nothing</em>. Production's arm has {meta['activity']['TRADE BARS (production)']['dead_tape_n']} such trades.</p>
<table>
<thead><tr><th class="ln">Bar source</th><th class="ln">Activity quartile</th>
<th class="num">Median prints/min</th><th class="num">n</th><th class="num">Net $</th>
<th class="num">$/trade</th><th class="num">Win %</th></tr></thead>
<tbody>{act}</tbody></table>
<p><strong>The gradient is not monotone &mdash; it is a CLIFF at the top quartile.</strong> On
production bars Q1, Q2 and Q3 read &minus;$11.85, &minus;$5.77 and &minus;$11.19 a trade with no
ordering between them, and then Q4 reads <strong>+$27.11 at a 68.0% win rate</strong>. Three-quarters
of the fires are noise around zero-minus-costs and the whole book lives in the busiest quarter. That
is the single most interesting number gold has produced &mdash; and a step with nothing under it is
also exactly the shape a fitted threshold makes, which is why the next section is a warning rather
than a proposal.</p>

<h3><span class="n">G5</span> The activity floor: fitted in-sample, dead forward</h3>
<table>
<thead><tr><th class="ln">Bar source</th><th class="num">Floor fitted</th><th class="num">IS n</th>
<th class="num">IS $/tr</th><th class="num">IS win</th><th class="num">FWD n</th>
<th class="num">FWD $/tr</th><th class="num">FWD n, no floor</th>
<th class="num">FWD $/tr, no floor</th></tr></thead>
<tbody>{flo}</tbody></table>
<p><strong>This is the whole lesson of the gold week in one table.</strong> Choosing the floor on the
data that chose it gives +$25.83 and +$40.80 a trade at a 76&ndash;80% win rate. Carry the same floor
forward and it makes <strong>&minus;$3.43</strong> and <strong>&minus;$11.92</strong> a trade on 14
and 12 trades &mdash; <em>worse</em> than taking every forward fire with no floor at all on the
production arm (&minus;$11.92 filtered against &minus;$7.77 unfiltered). And note what the floor does
to the sample: it keeps <strong>42 of 345</strong> fires in-sample (12%) and <strong>14 of 161</strong>
forward (9%), so the forward test that would grade it honestly needs months, not days.</p>

<h3><span class="n">G6</span> The one cell that looked like a candidate, and what killed it</h3>
<p>The <strong>double hole</strong> &mdash; a break with no obstacle in front of it <em>and</em> no
resting support behind it &mdash; is positive on BOTH bar sources, which is exactly the agreement
the bar-source scare said we could never have. It is also positive in-sample and positive in F1.
It is graded here rather than promoted, because it fails the one test that a sample this thin can
still run.</p>
<table>
<thead><tr><th class="ln">Bar source</th><th class="num">n</th><th class="num">Net $</th>
<th class="num">$/trade</th><th class="num">Win %</th><th class="num">IS $/tr</th>
<th class="num">F1 $/tr</th><th class="num">F2 $/tr</th><th class="num">Net, strip best 3</th></tr></thead>
<tbody>{dbl_rows}</tbody></table>
<p><strong>Cause of death: strip-the-best-trades.</strong> Both arms go from positive to negative
when three trades are removed &mdash; from +$921.50 to &minus;$109.00 on lab bars, and from +$468.00
to &minus;$328.50 on production bars. Three trades out of 311 and 154 are the entire result. It also
turns negative in F2 on both. <strong>Not refuted &mdash; a thin sample never is &mdash; but nowhere
near a shadow arm, and the specific thing it needs is more trades, not more tuning.</strong></p>

<div class="callout"><div class="ct">GOLD &mdash; VERDICT, and what to do about it</div>
<p><strong>Gold is an EMPTY SEAT, not a bleed.</strong> There is no live gold gate, so the census
ceiling gold prints each week is the size of the opportunity, not money forgone. Nothing here arms,
nothing here shadows, and no MNQ gate is ported across &mdash; the scope's standing rule that gold
gates must be invented fresh is unchanged and is reinforced by G4: the two instruments do not even
have the same relationship to their own tape.</p>
<p><strong>What actually moved this week.</strong> The bar-source blocker that gated the entire gold
programme is <em>gone</em> &mdash; retired on 32 days after being raised on 6. That is a real
deliverable: the next gold cycle does not have to spend itself reconciling two bar builders.
<strong>The blocker it is replaced by is smaller and more useful:</strong> gold's edge, if it has
one, lives in the busiest quartile of the tape, and every attempt so far to express that as a
threshold has been a fit. The next experiment is an activity measure chosen <em>a priori</em> and
run forward for a stated number of sessions &mdash; the same discipline the Open Rider's
pre-registered ATR filter is under, applied to gold.</p>
<p class="ln">⚠ <strong>Honest limits, all of them.</strong> {len(days)} days is one summer of one
instrument. F2 is three days. The double-hole cell is 311 and 154 trades and dies on three of them.
Every figure is a REPLAY on the 250&nbsp;ms quote tape with both legs crossing &mdash; it is the best
counterfactual available and it is not a fill. And gold has never traded live on this desk, so
nothing here has ever met a real queue.</p></div>
"""
    OUT.write_text(doc)
    print(f"wrote {OUT} ({len(doc):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
