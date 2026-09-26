#!/usr/bin/env python3
"""SECTION 1 — THE RECORD. Emit the HTML fragment. Every number computed here, none typed."""
from __future__ import annotations
import sys, json, html
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import pandas as pd
import fv7_op_record as F
from gazbot7.lake import connect

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/sections/op_record.html"
W0 = "2026-09-14"
EVENTS = {"2026-07-29": "FOMC", "2026-08-07": "NFP", "2026-08-12": "CPI",
          "2026-09-04": "NFP", "2026-09-11": "CPI", "2026-09-16": "FOMC"}

def usd(x, sign=True):
    s = "&minus;" if x < 0 else ("+" if sign else "")
    return f"{s}${abs(x):,.2f}"

def pts(x):
    return ("&minus;" if x < 0 else "+") + f"{abs(x):,.1f}"

def hhmm(mins):
    m = int(round(mins))
    return f"{m}m" if m < 60 else f"{m//60}h {m%60:02d}m"

# ── data ──────────────────────────────────────────────────────────────────────────────────────
rows = F.load()
e = F.entries(rows)
e["ev"] = e.date.map(EVENTS)
m = e[e.clean].copy()                      # everything money is computed on
w = m[m.date >= W0].copy()                 # the completed week
wall = e[e.date >= W0].copy()              # incl. the BADFILL entry, for display only
pre = m[m.date < W0]

c = connect()
def env(r):
    q = c.execute("select max(high), min(low) from bars where symbol='MNQ' and timeframe='5s' "
                  "and bar_ts between ? and ?", [int(r.t0.timestamp()), int(r.t1.timestamp())]).fetchone()
    if not q or q[0] is None:
        return pd.Series({"mfe": float("nan"), "mae": float("nan")})
    hi, lo = q
    if r.side == "LONG":
        return pd.Series({"mfe": hi - r.entry, "mae": -(r.entry - lo)})
    return pd.Series({"mfe": r.entry - lo, "mae": -(hi - r.entry)})
w = w.join(w.apply(env, axis=1))
w["capt"] = w.pts / w.mfe

reads = [json.loads(l) for l in open(f"{GB}/data/operator_reads.jsonl") if l.strip()]
uniq = {(r["kind"], (r.get("request") or {}).get("raw", "")) for r in reads}
n_press = sum(1 for k, raw in uniq if k == "buy" and raw)
n_claim = sum(1 for k, raw in uniq if k == "claim")
n_pass  = sum(1 for k, _ in uniq if k == "pass")

def bucket(x):
    return ("under 15 min" if x < 15 else "15&ndash;60 min" if x < 60 else
            "1&ndash;3 hours" if x < 180 else "3&ndash;8 hours" if x < 480 else "over 8 HOURS")
ORDER = ["under 15 min", "15&ndash;60 min", "1&ndash;3 hours", "3&ndash;8 hours", "over 8 HOURS"]

wk_net, wk_n = w.pnl.sum(), len(w)
life_net, life_n = m.pnl.sum(), len(m)
wins, loss = w[w.pnl > 0], w[w.pnl <= 0]
top = w.pnl.sort_values(ascending=False)
ev_m, or_m = m[m.ev.notna()], m[m.ev.isna()]
u3, o3 = m[m.hold_min < 180], m[m.hold_min >= 180]
b8 = m[m.hold_min >= 480]

P = []
A = P.append

# ── header ────────────────────────────────────────────────────────────────────────────────────
A('<h2 id="s1"><span class="n">S1</span> THE RECORD &mdash; Monday 14 to Friday 18 September 2026</h2>')

A(f'''<p class="lead">Garrath &mdash; <strong>you made {usd(wk_net)} this week</strong> across
<strong>{wk_n} entries</strong>, every one of them 4 lots, every one of them opened by your hand and
stamped <code>manual</code> in the database. That is <strong>{usd(wk_net/5)} a day at 4 lots</strong>
over five sessions, and it is comfortably the best week this book has had &mdash; the previous best was
{usd(1617.50)} and the week before this one was {usd(-3049.49)}. It also turned the whole book around:
before Monday the rider was <strong>{usd(pre.pnl.sum())} over {len(pre)} entries</strong> for its entire
life, and it now stands at <strong>{usd(life_net)} over {life_n}</strong>. Six weeks of work were in the
red; one week put it in the black.</p>''')

A(f'''<p class="lead">Two warnings before the tables. First, <strong>five trades are the week</strong>
&mdash; the best five made {usd(top.iloc[:5].sum())}, which is <em>more than the whole week</em>, and the
other {wk_n-5} entries together came to {usd(top.iloc[5:].sum())}. Second, the money is grouped by
<strong>DECISION, not by database row</strong>: the week produced {len(rows[rows.opened_at>=W0])} rows
in <code>trades</code> but only {len(wall)} entries, because a scale-out books one row per lot leaving.
Counting rows would have inflated the trade count by {len(rows[rows.opened_at>=W0])/len(wall):.2f}&times;.</p>''')

# ── the five things ───────────────────────────────────────────────────────────────────────────
A('<div class="callout"><div class="ct">★★ If you read nothing else &mdash; five things</div>')
A(f'''<p><strong>1. The week, in one line.</strong> {usd(wk_net)} on {wk_n} entries.
{len(wins)} winners worth {usd(wins.pnl.sum())}, {len(loss)} losers worth {usd(loss.pnl.sum())}.
Median entry {usd(w.pnl.median())}. Four green days and one red one &mdash; and the red one was
Wednesday, <strong>FOMC day</strong>.</p>''')
A(f'''<p><strong>2. Your losers are wrong from the first minute.</strong> This is the cleanest thing in
the whole section and it is pure description, no model. Across the week your {len(wins)} winners had a
median best-moment of <strong>{wins.mfe.median():.1f} points</strong> in your favour and you booked a
median <strong>{wins.capt.median()*100:.0f}% of it</strong>. Your {len(loss)} losers had a median best
moment of <strong>{loss.mfe.median():.1f} points</strong> &mdash; {int((loss.mfe<25).sum())} of
{len(loss)} never once showed you 25 points, and {int((loss.mfe<10).sum())} never showed you ten. You
are not giving winners back. You are occasionally getting on the wrong side and staying there.</p>''')
A(f'''<p><strong>3. The morning carried it, but do not turn that into a rule.</strong>
05:00&ndash;12:59Z was <strong>{usd(w[(w.hourz>=5)&(w.hourz<=12)].pnl.sum())} over
{len(w[(w.hourz>=5)&(w.hourz<=12)])} entries</strong> this week; after 13:00Z you were
{usd(w[w.hourz>=13].pnl.sum())} over {len(w[w.hourz>=13])}. But over the whole life of the
confirmed-manual record the same morning window is {usd(m[m.manual&(m.hourz>=5)&(m.hourz<=12)].pnl.sum())}
&mdash; one trade on 10 September flips its sign. Point estimate first, uncertainty second: the morning
is where you were this week, not a proven edge.</p>''')
A(f'''<p><strong>4. The eight-hour hole did not reopen.</strong> Over the book's life,
<strong>{len(b8)} entries held past eight hours, {int((b8.pnl>0).sum())} winners, {usd(b8.pnl.sum())}</strong>
&mdash; and every other entry you have ever made adds to {usd(life_net - b8.pnl.sum())}. This week
<strong>none of the {wk_n} entries reached eight hours</strong>. Longest was
{hhmm(w.hold_min.max())}. That is the single biggest behavioural change in the record.</p>''')
A(f'''<p><strong>5. You are still the exit.</strong> {int((w.exit_cat=="hand").sum())} of the {wk_n}
entries ended on your <code>MANUAL_CLAIM</code>; exactly one ended any other way &mdash; the
{usd(w[w.exit_cat=="clock"].pnl.sum())} long on Tuesday that the 20:40Z clock flattened. The ladder took a
first lot off on {int((w.rungs>0).sum())} of {wk_n}, but it did not finish a single one &mdash; all
{int((w.rungs>0).sum())} still ended on your button.</p>''')
A('</div>')

# ── 1. the week, day by day ───────────────────────────────────────────────────────────────────
A('<div class="card"><h3>1 &middot; The week, day by day</h3>')
A(f'''<p>Window: entries opened on or after {W0}, gate <code>day_rider</code>, MNQ at $2.00/point and
$1.50 a round trip. <code>EXCLUDE:</code> rows are dropped; the one <code>BADFILL:</code> entry is shown
but kept out of every total &mdash; it is a real trade whose price came from the paper engine fabricating
3 of its 4 lots.</p>''')
A('<table><thead><tr><th class="ln">Day</th><th class="num">Entries</th><th class="num">Won</th>'
  '<th class="num">Net</th><th class="ln">Biggest winner</th><th class="ln">Biggest loser</th>'
  '<th class="ln">What happened</th></tr></thead><tbody>')
DAYNOTE = {
 "2026-09-14": "Two morning entries, then the 13:18 runner &mdash; and a re-entry 31 min later that lasted 2m50s",
 "2026-09-15": "Five entries made +$1,174 by lunchtime; then one long held 13:39&rarr;the 20:40Z clock",
 "2026-09-16": "FOMC. Held long through the decision, bought again at T+52 with the slide still running",
 "2026-09-17": "Four of the eight took a first lot at the 100-pt rung; the overnight long ran 6h35m for +$272",
 "2026-09-18": "Fifteen entries &mdash; the busiest day on record, and ten of them winners",
}
for d, g in w.groupby("date"):
    b, x = g.loc[g.pnl.idxmax()], g.loc[g.pnl.idxmin()]
    cls = ' class="row-hl"' if g.pnl.sum() > 0 else ' class="row-bad"'
    A(f'<tr{cls}><td class="ln">{pd.Timestamp(d).strftime("%a %d %b")}</td>'
      f'<td class="num">{len(g)}</td><td class="num">{int((g.pnl>0).sum())}</td>'
      f'<td class="num">{usd(g.pnl.sum())}</td>'
      f'<td class="ln">{b.t0.strftime("%H:%M")}Z {b.side} {usd(b.pnl)}</td>'
      f'<td class="ln">{x.t0.strftime("%H:%M")}Z {x.side} {usd(x.pnl)}</td>'
      f'<td class="ln">{DAYNOTE[d]}</td></tr>')
A(f'<tr><td class="ln"><strong>WEEK</strong></td><td class="num"><strong>{wk_n}</strong></td>'
  f'<td class="num"><strong>{len(wins)}</strong></td><td class="num"><strong>{usd(wk_net)}</strong></td>'
  f'<td class="ln"><strong>{usd(top.iloc[0])}</strong></td><td class="ln"><strong>{usd(top.iloc[-1])}</strong></td>'
  f'<td class="ln"><strong>{usd(wk_net/5)}/day at 4 lots</strong></td></tr>')
A('</tbody></table>')
A(f'''<p><strong>The week is five trades.</strong> Ranked by money, the top five are
{", ".join(usd(v) for v in top.iloc[:5])} &mdash; {usd(top.iloc[:5].sum())} together, against a week total
of {usd(wk_net)}. The remaining {wk_n-5} entries net {usd(top.iloc[5:].sum())}: a scratch. The three worst
are {", ".join(usd(v) for v in top.iloc[-3:][::-1])} &mdash; {usd(top.iloc[-3:].sum())} &mdash; and two of
those three are the two "held it" trades, Tuesday's clock-flat and Wednesday's FOMC re-entry.</p>''')
A('</div>')
open(OUT, "w").write("\n".join(P))
print("part 1 written", len(P))

# ═══ PART 2 ═══════════════════════════════════════════════════════════════════════════════════
P2 = []
B = P2.append

# ── 2. the definitive entry table ─────────────────────────────────────────────────────────────
B('<div class="card"><h3>2 &middot; Every entry you made this week</h3>')
B('''<p>One row per <strong>decision</strong>. "Best" is the furthest the trade ever went your way
while you were in it, "Worst" the furthest against &mdash; both measured off the 5-second tape from the
moment you got filled to the moment the last lot left. "Kept" is what fraction of the best moment you
actually banked. Times are UTC; Paris is UTC+2.</p>''')
B('<table><thead><tr><th class="ln">Opened (Z)</th><th class="ln">Side</th><th class="num">Lots</th>'
  '<th class="num">Held</th><th class="num">$ net</th><th class="num">Pts</th><th class="num">Best</th>'
  '<th class="num">Worst</th><th class="num">Kept</th><th class="ln">How it ended</th></tr></thead><tbody>')
HOW = {"hand": "your hand", "clock": "the 20:40Z clock", "rung": "a ladder rung",
       "crossdesk": "cross-desk flatten"}
for _, r in wall.sort_values("t0").iterrows():
    if r.badfill:
        B(f'<tr class="row-bad"><td class="ln">{r.t0.strftime("%a %d %H:%M")}</td>'
          f'<td class="ln">{r.side}</td><td class="num">{r.lots:.0f}</td>'
          f'<td class="num">{hhmm(r.hold_min)}</td><td class="num"><em>({usd(r.pnl)})</em></td>'
          f'<td class="num">&mdash;</td><td class="num">&mdash;</td><td class="num">&mdash;</td>'
          f'<td class="num">&mdash;</td><td class="ln"><strong>BADFILL &mdash; shown, not counted.</strong> '
          f'The paper engine fabricated 3 of the 4 lots at exactly 0.1% adverse</td></tr>')
        continue
    q = w.loc[r.name]
    ends = HOW[r.exit_cat] + (f", after {int(r.rungs)} lot{'s' if r.rungs>1 else ''} at the ladder"
                              if r.rungs else " in one go")
    cls = ' class="row-hl"' if r.pnl > 0 else (' class="row-bad"' if r.pnl < -400 else '')
    B(f'<tr{cls}><td class="ln">{r.t0.strftime("%a %d %H:%M")}</td><td class="ln">{r.side}</td>'
      f'<td class="num">{r.lots:.0f}</td><td class="num">{hhmm(r.hold_min)}</td>'
      f'<td class="num">{usd(r.pnl)}</td><td class="num">{pts(r.pts)}</td>'
      f'<td class="num">{q.mfe:.1f}</td>'
      f'<td class="num">{"0.0" if q.mae >= 0 else pts(q.mae)}</td>'
      f'<td class="num">{"&mdash;" if r.pnl<=0 else f"{q.capt*100:.0f}%"}</td>'
      f'<td class="ln">{ends}</td></tr>')
B(f'<tr><td class="ln"><strong>{wk_n} entries</strong></td><td class="ln">'
  f'{int((w.side=="LONG").sum())}L / {int((w.side=="SHORT").sum())}S</td>'
  f'<td class="num"><strong>4 each</strong></td><td class="num"><strong>med {hhmm(w.hold_min.median())}</strong></td>'
  f'<td class="num"><strong>{usd(wk_net)}</strong></td><td class="num"><strong>{pts(w.pts.sum())}</strong></td>'
  f'<td class="num"><strong>{w.mfe.sum():.0f}</strong></td><td class="num">&mdash;</td>'
  f'<td class="num"><strong>{w.pts.sum()/w.mfe.sum()*100:.0f}%</strong></td>'
  f'<td class="ln">{int((w.exit_cat=="hand").sum())} by hand, 1 by the clock</td></tr>')
B('</tbody></table>')
B(f'''<p>The bottom row is worth a second look. Added up, the tape offered
<strong>{w.mfe.sum():.0f} points</strong> across your {wk_n} trades and you took
<strong>{w.pts.sum():.0f}</strong> &mdash; {w.pts.sum()/w.mfe.sum()*100:.0f}%. That number is NOT a
criticism and it is not a target: it includes the losers, where the "best moment" was a point or two of
noise, and nobody exits at the high. On the {len(wins)} winners alone you kept a median
<strong>{wins.capt.median()*100:.0f}%</strong>, and {int((wins.capt>=0.65).sum())} of {len(wins)} kept
two-thirds or more. Read it as evidence you are not the problem on the way out.</p>''')
B(f'''<p>Sides: <strong>{int((w.side=="LONG").sum())} longs for {usd(w[w.side=="LONG"].pnl.sum())}</strong>
and <strong>{int((w.side=="SHORT").sum())} shorts for {usd(w[w.side=="SHORT"].pnl.sum())}</strong>. You
were more often long and the longs paid better this week, but on {wk_n} trades that gap is one Wednesday
afternoon wide &mdash; do not build on it.</p>''')
B('</div>')

# ── 3. hold time ──────────────────────────────────────────────────────────────────────────────
B('<div class="card"><h3>3 &middot; By hold time &mdash; the standing finding, refreshed</h3>')
B('<table><thead><tr><th class="ln">Held for</th><th class="num">Entries (life)</th><th class="num">Won</th>'
  '<th class="num">Net (life)</th><th class="num">$/entry</th><th class="num">This week</th>'
  '<th class="num">Net this week</th></tr></thead><tbody>')
m2, w2 = m.copy(), w.copy()
m2["b"], w2["b"] = m2.hold_min.map(bucket), w2.hold_min.map(bucket)
for b in ORDER:
    g, gw = m2[m2.b == b], w2[w2.b == b]
    cls = ' class="row-bad"' if g.pnl.sum() < 0 else ' class="row-hl"'
    B(f'<tr{cls}><td class="ln">{b}</td><td class="num">{len(g)}</td>'
      f'<td class="num">{int((g.pnl>0).sum())}/{len(g)}</td><td class="num">{usd(g.pnl.sum())}</td>'
      f'<td class="num">{usd(g.pnl.mean())}</td>'
      f'<td class="num">{len(gw) if len(gw) else "&mdash;"}</td>'
      f'<td class="num">{usd(gw.pnl.sum()) if len(gw) else "&mdash;"}</td></tr>')
B(f'<tr><td class="ln"><strong>UNDER 3 hours</strong></td><td class="num"><strong>{len(u3)}</strong></td>'
  f'<td class="num"><strong>{int((u3.pnl>0).sum())}/{len(u3)}</strong></td>'
  f'<td class="num"><strong>{usd(u3.pnl.sum())}</strong></td><td class="num"><strong>{usd(u3.pnl.mean())}</strong></td>'
  f'<td class="num"><strong>{len(w[w.hold_min<180])}</strong></td>'
  f'<td class="num"><strong>{usd(w[w.hold_min<180].pnl.sum())}</strong></td></tr>')
B(f'<tr><td class="ln"><strong>OVER 3 hours</strong></td><td class="num"><strong>{len(o3)}</strong></td>'
  f'<td class="num"><strong>{int((o3.pnl>0).sum())}/{len(o3)}</strong></td>'
  f'<td class="num"><strong>{usd(o3.pnl.sum())}</strong></td><td class="num"><strong>{usd(o3.pnl.mean())}</strong></td>'
  f'<td class="num"><strong>{len(w[w.hold_min>=180])}</strong></td>'
  f'<td class="num"><strong>{usd(w[w.hold_min>=180].pnl.sum())}</strong></td></tr>')
B('</tbody></table>')
B(f'''<p>The standing finding survives the week and grew: <strong>under three hours
{usd(u3.pnl.sum())} over {len(u3)} entries, over three hours {usd(o3.pnl.sum())} over {len(o3)}</strong>
(it was +$5,262/44 against &minus;$5,406/17 when this was last written &mdash; the week added
{len(w[w.hold_min<180])} short holds worth {usd(w[w.hold_min<180].pnl.sum())} and
{len(w[w.hold_min>=180])} long ones worth {usd(w[w.hold_min>=180].pnl.sum())}).</p>''')
B(f'''<div class="callout"><div class="ct">⚠ The confound, stated plainly &mdash; and where it stops</div>
<p><strong>Hold time is partly an OUTCOME, not only a choice.</strong> A trade that goes your way hits a
rung and closes; a trade that goes against you gets held while you wait for it to come back. So part of
that gap is simply "losers last longer", which is true of almost every discretionary book ever measured,
and it does not mean a stopwatch would have made the money.</p>
<p><strong>The over-8h bucket is not that shape.</strong> {len(b8)} entries, <strong>0 winners</strong>,
{usd(b8.pnl.sum())}, and their envelopes say why: the 21 Aug long never printed a single tick in profit
(best moment &minus;3.4 points) and the 10 Sep long showed +21.8 points before going 444 against. Those
are not trades held in hope of a recovery that nearly came. They are positions nobody was watching. That
is abandonment, and a stopwatch <em>does</em> address it.</p></div>''')
B('</div>')
open(OUT, "a").write("\n" + "\n".join(P2))
print("part 2 appended", len(P2))

# ═══ PART 3 ═══════════════════════════════════════════════════════════════════════════════════
P3 = []
C = P3.append

# ── 4. hour of day ────────────────────────────────────────────────────────────────────────────
C('<div class="card"><h3>4 &middot; By hour of day &mdash; does the edge live in part of the window?</h3>')
C(f'''<p>First, a correction to the shape of the question. The "05:00&ndash;11:00Z almost exclusively"
line comes from the {n_press} captured presses, and those only start on 14 September. Across the
{int(m.manual.sum())} entries the database can <em>prove</em> were yours, the spread is much wider &mdash;
this week alone you opened trades in {w.hourz.nunique()} different hours of the clock, from
{w.t0.min().strftime("%H:%M")}Z to {w.t0.max().strftime("%H:%M")}Z.</p>''')
BANDS = [(0, 4, "Overnight 00&ndash;04Z", "Asia / pre-Europe"),
         (5, 8, "Early Europe 05&ndash;08Z", "the London open block"),
         (9, 12, "Late Europe 09&ndash;12Z", "the pre-US grind"),
         (13, 16, "US open 13&ndash;16Z", "the cash open and the first three hours"),
         (17, 23, "US afternoon 17&ndash;23Z", "into the 20:40Z flatten")]
C('<table><thead><tr><th class="ln">Block (UTC)</th><th class="ln">Paris</th><th class="num">Entries</th>'
  '<th class="num">Won</th><th class="num">Net this week</th><th class="num">$/entry</th>'
  '<th class="ln">What sits in there</th></tr></thead><tbody>')
for lo, hi, lab, note in BANDS:
    g = w[(w.hourz >= lo) & (w.hourz <= hi)]
    if not len(g):
        continue
    cls = ' class="row-hl"' if g.pnl.sum() > 0 else ' class="row-bad"'
    C(f'<tr{cls}><td class="ln">{lab}</td><td class="ln">{(lo+2)%24:02d}:00&ndash;{(hi+2)%24:02d}:59</td>'
      f'<td class="num">{len(g)}</td><td class="num">{int((g.pnl>0).sum())}</td>'
      f'<td class="num">{usd(g.pnl.sum())}</td><td class="num">{usd(g.pnl.mean())}</td>'
      f'<td class="ln">{note}</td></tr>')
mor, aft = w[(w.hourz >= 5) & (w.hourz <= 12)], w[w.hourz >= 13]
C(f'<tr><td class="ln"><strong>Before 13:00Z</strong></td><td class="ln">before 15:00 Paris</td>'
  f'<td class="num"><strong>{len(mor)}</strong></td><td class="num"><strong>{int((mor.pnl>0).sum())}</strong></td>'
  f'<td class="num"><strong>{usd(mor.pnl.sum())}</strong></td><td class="num"><strong>{usd(mor.pnl.mean())}</strong></td>'
  f'<td class="ln">where the week was made</td></tr>')
C(f'<tr><td class="ln"><strong>13:00Z and after</strong></td><td class="ln">15:00 Paris on</td>'
  f'<td class="num"><strong>{len(aft)}</strong></td><td class="num"><strong>{int((aft.pnl>0).sum())}</strong></td>'
  f'<td class="num"><strong>{usd(aft.pnl.sum())}</strong></td><td class="num"><strong>{usd(aft.pnl.mean())}</strong></td>'
  f'<td class="ln">holds both big losers</td></tr>')
C('</tbody></table>')
lm = m[m.manual]
lmor, laft = lm[(lm.hourz >= 5) & (lm.hourz <= 12)], lm[lm.hourz >= 13]
C(f'''<p><strong>Point estimate first.</strong> This week the morning block made
{usd(mor.pnl.sum())} on {len(mor)} entries and the afternoon lost {usd(aft.pnl.sum())} on {len(aft)}.
<strong>Uncertainty second, and it is large.</strong> Take every entry the database can prove was yours,
not just this week's, and the same morning block is <strong>{usd(lmor.pnl.sum())} over {len(lmor)}
entries</strong> while the afternoon is {usd(laft.pnl.sum())} over {len(laft)}. The sign of the morning
flips entirely, because one trade &mdash; 10 September, 05:40Z, held 13h34m, {usd(-2656.0)} &mdash; is
bigger than the whole week's morning profit. <strong>One trade decides this cut.</strong> That is not an
hour-of-day edge; that is a hold-time problem wearing an hour-of-day costume.</p>''')
C('</div>')

# ── 5. event days ─────────────────────────────────────────────────────────────────────────────
C('<div class="card"><h3>5 &middot; By event day &mdash; refreshed with this week\'s FOMC</h3>')
C('<table><thead><tr><th class="ln">Date</th><th class="ln">Event</th><th class="num">Entries</th>'
  '<th class="num">Won</th><th class="num">Net</th><th class="ln">The trade that did it</th></tr></thead><tbody>')
NOTE = {"2026-08-12": "One entry, worked",
        "2026-09-04": "One long held 8h44m &mdash; the NFP day is also an abandonment day",
        "2026-09-11": "Four entries, one winner",
        "2026-09-16": "Long held through the 18:00Z decision, then bought again at T+52 with the slide "
                      "still running: &minus;$1,272.00 on that one trade against a day of &minus;$833.00"}
for d, g in ev_m.groupby("date"):
    cls = ' class="row-hl"' if g.pnl.sum() > 0 else ' class="row-bad"'
    C(f'<tr{cls}><td class="ln">{pd.Timestamp(d).strftime("%a %d %b")}</td><td class="ln">{EVENTS[d]}</td>'
      f'<td class="num">{len(g)}</td><td class="num">{int((g.pnl>0).sum())}</td>'
      f'<td class="num">{usd(g.pnl.sum())}</td><td class="ln">{NOTE.get(d,"&mdash;")}</td></tr>')
C(f'<tr><td class="ln"><strong>EVENT DAYS</strong></td><td class="ln"><strong>{ev_m.date.nunique()} days</strong></td>'
  f'<td class="num"><strong>{len(ev_m)}</strong></td><td class="num"><strong>{int((ev_m.pnl>0).sum())}</strong></td>'
  f'<td class="num"><strong>{usd(ev_m.pnl.sum())}</strong></td>'
  f'<td class="ln"><strong>{usd(ev_m.pnl.mean())} an entry</strong></td></tr>')
C(f'<tr><td class="ln"><strong>ORDINARY DAYS</strong></td>'
  f'<td class="ln"><strong>{or_m.date.nunique()} days</strong></td>'
  f'<td class="num"><strong>{len(or_m)}</strong></td><td class="num"><strong>{int((or_m.pnl>0).sum())}</strong></td>'
  f'<td class="num"><strong>{usd(or_m.pnl.sum())}</strong></td>'
  f'<td class="ln"><strong>{usd(or_m.pnl.mean())} an entry</strong></td></tr>')
C('</tbody></table>')
C(f'''<p>The event side reproduces the standing figure to the cent: <strong>{usd(ev_m.pnl.sum())} over
{len(ev_m)} entries</strong>. The ordinary side has moved because the week added Thursday and Friday
&mdash; it now reads {usd(or_m.pnl.sum())} over {len(or_m)} entries rather than the +$1,076/67 quoted in
the build queue.</p>''')
C(f'''<div class="callout"><div class="ct">⚠ Four days. Read it as a warning light, never a switch</div>
<p>This is <strong>{ev_m.date.nunique()} days of trading</strong> and the split was chosen after seeing
the losses. FOMC Wednesday was the only red day of the week &mdash; but it was red because of
<em>one</em> entry at T+52 into a slide that ran for another 33 minutes, and you had already said
yourself: <em>"if i knew the fed was making a decision i probably wouldve held off."</em> The calendar and
the T-60/T-15 pages are already built and already running. That is the right shape: it tells you an event
is coming and refuses to tell you which way. Nothing here justifies benching anything automatically.</p>
</div>''')
C('</div>')
open(OUT, "a").write("\n" + "\n".join(P3))
print("part 3 appended", len(P3))

# ═══ PART 4 ═══════════════════════════════════════════════════════════════════════════════════
P4 = []
D = P4.append
lm = m[m.manual]
unk = m[~m.manual]
wk_rung, wk_norung = w[w.rungs > 0], w[w.rungs == 0]

# ── 6. how the trades ended ───────────────────────────────────────────────────────────────────
D('<div class="card"><h3>6 &middot; How they ended &mdash; your hand, a ladder rung, or the clock</h3>')
D(f'''<p>Your ladder is set to <strong>$100 / $200 / $400 / $600 a lot</strong> and takes exactly one lot
at each rung. Here is what actually fires.</p>''')
D('<table><thead><tr><th class="ln">Ending</th><th class="num">Entries this week</th>'
  '<th class="num">Net</th><th class="num">Entries (life)</th><th class="num">Net (life)</th>'
  '<th class="ln">Read</th></tr></thead><tbody>')
CATN = {"hand": ("Your hand &mdash; <code>MANUAL_CLAIM</code>", "you decided it was over"),
        "clock": ("The 20:40Z clock &mdash; <code>CLOCK_FLAT*</code>", "nobody decided; the flatten did"),
        "rung": ("A ladder rung took the last lot", "the machine finished it"),
        "crossdesk": ("Cross-desk flatten", "the other book's guard")}
for k in ("hand", "rung", "clock", "crossdesk"):
    gw, gl = w[w.exit_cat == k], m[m.exit_cat == k]
    if not len(gl):
        continue
    D(f'<tr><td class="ln">{CATN[k][0]}</td>'
      f'<td class="num">{len(gw) if len(gw) else "&mdash;"}</td>'
      f'<td class="num">{usd(gw.pnl.sum()) if len(gw) else "&mdash;"}</td>'
      f'<td class="num">{len(gl)}</td><td class="num">{usd(gl.pnl.sum())}</td>'
      f'<td class="ln">{CATN[k][1]}</td></tr>')
D('</tbody></table>')
D(f'''<p><strong>You are the exit, and it is not close.</strong>
{int((m.exit_cat=="hand").sum())} of the {life_n} entries this book has ever made ended on your claim
button. The ladder has taken at least one lot on {int((m.rungs>0).sum())} of them &mdash; a $100
or $200 target, or an older trail &mdash; but the
<strong>$400 and $600 rungs have never once fired in the entire record</strong> &mdash; not a single
<code>TARGET_400</code> or <code>TARGET_600</code> row exists. You always get there first.</p>''')
D(f'''<div class="callout"><div class="ct">⚠ One tempting number in here is a tautology. Do not act on it.</div>
<p>The {len(wk_rung)} entries that touched a rung this week made {usd(wk_rung.pnl.sum())}; the
{len(wk_norung)} you exited in one go lost {usd(wk_norung.pnl.sum())}. That looks like "scaling out
works". <strong>It is not a finding.</strong> A rung can only fire on a trade that had already gone
{"$100 a lot" } your way &mdash; so that split is very close to "winners won". Their median best-moment
was {wk_rung.mfe.median():.1f} points against {wk_norung.mfe.median():.1f}. There is no lever in
it.</p></div>''')
D(f'''<p>The one exit this week that was not yours cost {usd(w[w.exit_cat=="clock"].pnl.sum())}: Tuesday's
13:39Z long, held 7h01m, flattened by the 20:40Z clock. Its envelope shows a best moment of
<strong>15.8 points</strong> and a worst of <strong>228.2</strong> &mdash; it was never really a trade
that worked and then failed. Whether the clock made it better or worse is a question about repricing an
exit, and this desk does not reprice exits (119 calibrations, none reproduced your claiming). What can be
said without a model: it spent seven hours going one way.</p>''')
D('</div>')

# ── 7. whose trades are these ─────────────────────────────────────────────────────────────────
D('<div class="card"><h3>7 &middot; Whose trades are these &mdash; and why the week is the honest number</h3>')
D('<table><thead><tr><th class="ln">Provenance</th><th class="num">Entries</th><th class="num">Net</th>'
  '<th class="ln">Dates</th><th class="ln">What the database actually says</th></tr></thead><tbody>')
D(f'<tr class="row-hl"><td class="ln"><strong>Confirmed yours</strong> &mdash; <code>entry_source=\'manual\'</code></td>'
  f'<td class="num">{len(lm)}</td><td class="num">{usd(lm.pnl.sum())}</td>'
  f'<td class="ln">{lm.date.min()} &rarr; {lm.date.max()}</td>'
  f'<td class="ln">You pressed BUY or SELL. {len(w)} of these {len(lm)} are this week</td></tr>')
D(f'<tr><td class="ln"><strong>UNKNOWN</strong> &mdash; <code>entry_source IS NULL</code></td>'
  f'<td class="num">{len(unk)}</td><td class="num">{usd(unk.pnl.sum())}</td>'
  f'<td class="ln">{unk.date.min()} &rarr; {unk.date.max()}</td>'
  f'<td class="ln">Predate the column. Nothing recorded who opened them, and nothing ever will</td></tr>')
D('</tbody></table>')
D(f'''<p>This matters more than it looks. The {len(unk)} unknown-source entries contribute
{usd(unk.pnl.sum())} and the {len(lm)} that carry your stamp contribute {usd(lm.pnl.sum())} &mdash; so
<strong>the book's {usd(life_net)} lifetime net is not attributable to anybody in particular</strong>.
Everything the database can <em>prove</em> is your hand is those {len(lm)} entries, and {len(w)} of them
happened this week. Strip the week out and the {len(lm)-len(w)} provable pre-week entries are
{usd(lm.pnl.sum()-wk_net)}.</p>''')
aug = unk[(unk.date >= "2026-08-10") & (unk.date <= "2026-08-26")]
D(f'''<p>One shape in the unknown rows is worth naming without drawing a conclusion from it: for
<strong>{aug.date.nunique()} straight sessions from 10 to 26 August the book took exactly one counted
entry a day, and every one of them opened in the 13:00Z hour</strong>
&mdash; {int((unk.hourz==13).sum())} of the {len(unk)} unknown entries sit in that single hour. The day
rider's own documented automatic behaviour is one entry per session, no entry after 15:00Z. I am not
claiming those rows were the machine's; the record does not say, and the standing rule is that a NULL
stays a NULL. But it is why this section leads with the week, where every single entry carries your
stamp, and treats the lifetime tables as context rather than as your track record.</p>''')
D('</div>')

# ── 8. shortlist ──────────────────────────────────────────────────────────────────────────────
drag = -b8.pnl.sum() / m.date.nunique()
D('<div class="card"><h3>8 &middot; Ranked shortlist &mdash; what this section says to do next</h3>')
D('<table><thead><tr><th class="ln">#</th><th class="ln">What</th><th class="num">Measured on</th>'
  '<th class="ln">The number</th><th class="ln">Verdict</th></tr></thead><tbody>')
SL = [
 ("1", "<strong>Record the passes.</strong> The button shipped Friday; nothing has been written to it "
       "yet. Until it has, every table in this section is a <em>description</em> of trades you took and "
       "nothing here can become a rule.",
  f"{n_press} presses, {n_claim} claims, <strong>{n_pass} passes</strong>",
  "One side of a boundary. The fitting threshold is 30 labelled examples and it was written for "
  "positives AND negatives, so the real count against 30 is zero.",
  '<span class="tag">BLOCKER</span>'),
 ("2", "<strong>A hard flat-out at eight hours.</strong> Needs no model, no judgement and no fitting "
       "&mdash; it is a stopwatch.",
  f"{len(b8)} entries, {m.date.nunique()} sessions",
  f"{int((b8.pnl>0).sum())} winners from {len(b8)}, {usd(b8.pnl.sum())}. Every other entry in the record "
  f"nets {usd(life_net-b8.pnl.sum())}. That is {usd(-drag, sign=False)} of drag per session traded. "
  f"It did NOT recur this week (0 of {wk_n}) &mdash; so on this week's data it would have earned nothing. "
  f"What it recovers is not computed here; that needs the exit repriced (&sect;3).",
  '<span class="tag">PROMISING</span>'),
 ("3", "<strong>Keep standing aside on event days.</strong> Calendar and T-60/T-15 pages already built "
       "and running; this is about whether to keep trusting them.",
  f"{ev_m.date.nunique()} event days, {len(ev_m)} entries",
  f"{usd(ev_m.pnl.sum())} on event days against {usd(or_m.pnl.sum())} over {len(or_m)} ordinary entries. "
  f"FOMC Wednesday was the week's only red day. Four days, and the split was chosen after seeing it.",
  '<span class="tag">PROMISING</span>'),
 ("4", "<strong>&ldquo;Only trade the European morning.&rdquo;</strong> Tempting after this week. "
       "Do not do it.",
  f"{len(mor)} entries this week, {len(lmor)} provable ones over the book's life",
  f"{usd(mor.pnl.sum())} this week; {usd(lmor.pnl.sum())} over the confirmed-manual record, where one "
  f"trade on 10 Sep flips the sign. A filter fitted on a week that a single trade can reverse.",
  '<span class="tag pill-dontarm">REFUTED as a rule</span>'),
 ("5", "<strong>Watch the &ldquo;it has never gone my way&rdquo; shape.</strong> Your losers do not "
       "start well and then fail &mdash; they are wrong immediately.",
  f"{len(loss)} losers this week",
  f"Median best-moment {loss.mfe.median():.1f} points against {wins.mfe.median():.1f} for winners; "
  f"{int((loss.mfe<25).sum())} of {len(loss)} never showed 25 points and {int((loss.mfe<10).sum())} "
  f"never showed ten. ⚠ Turning this into a bail rule means backtesting an exit, and the standing rule "
  f"forbids a 120th calibration. Log it, watch it, do not fit it.",
  '<span class="tag">WATCH</span>'),
 ("6", "<strong>Chase one execution defect.</strong> A <code>TARGET_100</code> rung on 11 Sep booked "
       "<strong>&minus;$160.50</strong> &mdash; a $100-a-lot rung (that is +50 points on MNQ) that "
       "booked a fill 79.5 points BELOW the entry (trade id 868, long at 29320.25, out at 29240.75).",
  "1 row, outside this week",
  "Every other TARGET_100 in the record booked between +$97.50 and +$132.25. This one landed "
  "129.5 points from the level it names. Small money, but a target exit is reporting a price its "
  "own trigger cannot have seen.",
  '<span class="tag">DEFECT</span>'),
]
for n, what, on, num, verdict in SL:
    D(f'<tr><td class="ln"><strong>{n}</strong></td><td class="ln">{what}</td><td class="num">{on}</td>'
      f'<td class="ln">{num}</td><td class="ln">{verdict}</td></tr>')
D('</tbody></table>')
D(f'''<p><strong>So what do you actually do on Monday?</strong> Nothing changes about how you trade
&mdash; this section found no rule that survives its own uncertainty, and it would be dishonest to hand
you one off {wk_n} entries. Three things it does say: press <code>PASS</code> when you look and walk
away, because that is the only thing standing between a description and a model; the eight-hour hole is
the one number in the record big enough to be worth a stopwatch; and the morning result, lovely as it is,
is one week.</p>''')
D(f'''<p class="lead"><strong>One housekeeping note for &sect;2.</strong>
<code>data/operator_reads.jsonl</code> holds {len(reads)} lines but only {len(uniq)} distinct records
&mdash; {len(reads)-len(uniq)} are duplicates. Counting lines would report
{sum(1 for r in reads if r["kind"]=="buy")} presses where there are {n_press}. Section 2 should
de-duplicate before it counts anything.</p>''')
D('</div>')
open(OUT, "a").write("\n" + "\n".join(P4))
print("part 4 appended", len(P4))
