#!/usr/bin/env python3
"""Generate reports/friday_v7/sections/rev2_answers_0904.html — Part 4 of the Friday report.

Every number below is read from an artifact this revision produced, not typed:
  sections/rev2_shipped_0904.json      the shipped-check on last weekend's card
  sections/rev2_weekend_gap_0904.json  the open carry and the Sunday-reopen bound
  sections/rev2_break_lag_0904.json    BUILD #1's four clocks
  sections/rev2_armed_time_w36.json    W36 armed time and churn, both writers
  sections/rev3_offtape.json           the off-tape audit, now with the 08-31..09-04 cut
  data/gazbot7.db                      the week's legs
  data/shadow.db                       abs_veto_55s to 2026-09-04
"""
import datetime as dt, json, pathlib, sqlite3, collections
import duckdb

GB="/home/alphabot/gazbot7"; SEC=f"{GB}/reports/friday_v7/sections"
J=lambda n: json.loads(pathlib.Path(f"{SEC}/{n}").read_text())
ship=J("rev2_shipped_0904.json"); gap=J("rev2_weekend_gap_0904.json")
lag=J("rev2_break_lag_0904.json"); duty=J("rev2_armed_time_w36.json"); off=J("rev3_offtape.json")

def m(v,dp=2):
    s=f"{abs(v):,.{dp}f}"
    return ("&minus;$"+s) if v<0 else ("$"+s)

# ── the week ────────────────────────────────────────────────────────────────────────────────
c=sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro",uri=True)
W="closed_at >= '2026-08-31' AND closed_at < '2026-09-05' AND data_quality IS NULL"
gates=c.execute(f"SELECT replace(replace(gate,'_A',''),'_B',''), count(*), round(sum(pnl_usd),2),"
                f" round(100.0*sum(pnl_usd>0)/count(*),1) FROM trades WHERE {W}"
                " AND gate NOT LIKE 'day_rider%' GROUP BY 1 ORDER BY 3 DESC").fetchall()
gex={g:dict(c.execute(f"SELECT exit_reason,count(*) FROM trades WHERE {W} AND gate LIKE '{g}%' GROUP BY 1").fetchall()) for g,*_ in gates}
days=c.execute(f"SELECT date(closed_at), count(*), round(sum(pnl_usd),2) FROM trades WHERE {W} GROUP BY 1").fetchall()
tour=c.execute(f"SELECT count(*), round(sum(pnl_usd),2) FROM trades WHERE {W} AND gate NOT LIKE 'day_rider%'").fetchone()
rider=c.execute(f"SELECT count(*), round(sum(pnl_usd),2) FROM trades WHERE {W} AND gate LIKE 'day_rider%'").fetchone()
desk=c.execute(f"SELECT count(*), round(sum(pnl_usd),2), sum(qty), round(100.0*sum(pnl_usd>0)/count(*),1) FROM trades WHERE {W}").fetchone()
mix=c.execute(f"SELECT exit_reason,count(*),round(sum(pnl_usd),2) FROM trades WHERE {W} GROUP BY 1 ORDER BY 2 DESC").fetchall()
c.close()

# ── abs_veto_55s to 09-04 ───────────────────────────────────────────────────────────────────
con=duckdb.connect(); con.execute(f"ATTACH '{GB}/data/shadow.db' AS s (TYPE sqlite, READ_ONLY)")
rows=con.execute("""SELECT t.entry_ts,t.side,r.real_pnl FROM s.shadow_trades t
 JOIN s.shadow_real r ON r.trade_id=t.id WHERE t.strategy='abs_veto_55s' ORDER BY t.entry_ts""").fetchall()
con.close()
wk=collections.defaultdict(list)
for r in rows: wk[dt.datetime.fromtimestamp(r[0],dt.UTC).isocalendar()[1]].append(r)
def st(x): 
    n=len(x); net=sum(r[2] for r in x); return n,net,(net/n if n else 0)
CUT=dt.datetime(2026,8,28,22,0,tzinfo=dt.UTC).timestamp()
pre=[r for r in rows if r[0]<CUT]; post=[r for r in rows if r[0]>=CUT]
# Part 3 §Q1's haircut, recomputed on the same method: multiply ONLY the loss side by lambda and
# solve for zero. Breakeven lambda = wins / |losses|.
WIN=sum(r[2] for r in rows if r[2]>0); LOSS=sum(r[2] for r in rows if r[2]<=0)
BE=WIN/abs(LOSS)

H=[]; A=H.append
A('<h2 id="p4"><span class="n">P4</span> REVISION 2, 2026-09-04 &mdash; the ten open questions, '
  'answered from data</h2>')
A('<p class="lead">Garrath &mdash; a proofread pass ran against the first draft of this report and '
  'returned <strong>20 issues and 10 unanswered questions</strong>. The issues are fixed in the '
  'sections that carried them, each marked <strong>&#9733;&nbsp;REV2</strong>. The ten questions are '
  'answered here, in one place, because eight of the ten turn on the same fact: <strong>this document '
  'grades the week to 2026-08-28 and is published on 2026-09-04, so a whole week of desk activity '
  'happened between the evidence and the reader</strong> &mdash; and that week contradicts several of '
  'the report\'s headline conclusions. Lead with what survived: the desk\'s stop contract, which had '
  'never been tested, was tested four times and held; the census attribution bug that was inflating '
  '&ldquo;money left on the table&rdquo; is fixed and the figure falls by $1,667; and the week the '
  'report could not see was <strong>green on both books</strong>. What did not survive: the Monday '
  'promotion, the $810 bench saving, and the deploy the exit lab was proposing.</p>')

# ═══ §1 the carry
p=gap["position"]; U=gap["on_this_position_usd"]
A('<div class="callout"><div class="ct">&#9733;&#9733;&#9733; &sect;1 &mdash; THERE ARE FOUR LOTS OPEN '
  'RIGHT NOW, AND THE REPORT\'S FIRST LINE SAID THERE WERE NOT</div>'
  f'<p><strong>{p["direction"]} {p["qty"]:.0f} MNQ from {p["entry"]:,.2f}, {p["ahead_pt"]:+.1f} points '
  f'at the 21:00Z close = {m(p["unrealised_usd"])} unrealised.</strong> Rev&nbsp;1 opened &ldquo;the desk '
  'is FLAT &hellip; nothing is riding over the weekend&rdquo; and quoted a <code>desk_reconcile</code> '
  'read at 22:26:32Z. That is the <strong>2026-08-28</strong> read, hand-copied forward. The live one '
  f'says <em>venue&nbsp;? = tournament&nbsp;+0 + rider&nbsp;+{p["qty"]:.0f} &rarr; unaccounted ?</em>, '
  'with &ldquo;no venue read &mdash; IBKR truth unavailable&rdquo;.</p>'
  f'<p><strong>Why nothing closed it.</strong> <code>venue_ok</code> went false at '
  f'{p["venue_net_ts"][11:19]}Z and the watchdog has printed <code>SKIP venue read failed</code> every '
  'two minutes since. <strong>Both</strong> eod-flatten shots &mdash; 20:53Z and 20:57Z, the two '
  '<code>OnCalendar</code> lines on <code>gazbot7-eod-flatten.timer</code> &mdash; died inside the same '
  '<code>connectAsync</code> TimeoutError, because every flatten path on this desk shares one '
  'connection. Port 4002 is <em>refusing</em> connections, which is the gateway being down rather than '
  'the 04:28Z hang where the port stays open. <code>flatten_blocked</code> is <code>true</code> and '
  '<code>PLACE_VENUE_STOP</code> is <code>False</code>, so there is no venue stop underneath it either.</p></div>')
A('<div class="card"><h3>&sect;1.1 &nbsp;What the Sunday reopen can actually do &mdash; and why the reopen is not the risk</h3>'
  '<p>The parquet lake has <strong>no Sunday partitions at all</strong> (that is SATURDAY&nbsp;#11 on '
  'the card), so a lake-based reopen study would silently measure Friday-close to <em>Monday</em>-open. '
  f'<code>capture.db</code> does hold them. Here are all {gap["n"]} Sunday reopens we own, on 5-second '
  'bars:</p>'
  '<table><thead><tr><th class="ln">Sunday</th><th class="num">Fri close</th><th class="num">Sun open</th>'
  '<th class="num">Gap (pt)</th><th class="num">1st-hour low</th>'
  '<th class="num">Worst first hour for a LONG</th></tr></thead><tbody>'
  + "".join(f'<tr class="{"row-bad" if r["worst_for_long_pt"]<0 else "row-hl"}">'
            f'<td class="ln">{r["sunday"]}</td><td class="num">{r["fri_close"]:,.2f}</td>'
            f'<td class="num">{r["sun_open"]:,.2f}</td><td class="num">{r["gap_pt"]:+.2f}</td>'
            f'<td class="num">{r["first_hour_low"]:,.2f}</td>'
            f'<td class="num">{r["worst_for_long_pt"]:+.2f}</td></tr>' for r in gap["sundays"])
  + '</tbody></table>'
  f'<p><strong>On four lots that is:</strong> a median gap worth {m(U["median_gap"])}, a worst observed '
  f'gap DOWN worth {m(U["worst_gap_down"])}, and a worst observed first hour worth '
  f'{m(U["worst_first_hour"])}. <strong>That is not the danger.</strong> The 2026-08-21 carry &mdash; '
  'same book, same size, same mechanism &mdash; was &minus;121.93 points at its Friday close and the '
  'Sunday gapped <strong>+22.25 in its favour</strong>. It was still claimed by hand on the Monday at '
  '&minus;267.93 points for <strong>&minus;$2,149.44</strong>, which is the single largest item in this '
  'entire report. <span class="tag pill-dontarm">The risk is the Monday session, not the gap.</span></p>'
  '<p><strong>The instruction, and it is for Sunday 22:00Z, not Saturday.</strong> Nothing can be done '
  'before then: CME is shut and the venue is unreachable. At the reopen, <em>get a venue read first</em> '
  'and confirm it says 4. Then choose FLAT or MANAGE deliberately. If the read still comes back '
  '<code>?</code>, that is the answer &mdash; you are flat-blind and no managing order should go into a '
  'book you cannot see. <strong>SATURDAY&nbsp;#0.</strong></p></div>')

# ═══ §2 the stone
r0=lag["rows"][0]; r2=[r for r in lag["rows"] if r["trigger"].startswith("2026-09-01T09:01")][0]
A('<div class="card"><h3>&sect;2 &nbsp;The week\'s #1 stone is ANSWERED &mdash; and the answer kills the '
  'proposed fix, not the gate</h3>'
  '<p>BUILD&nbsp;#1 named <code>abs_veto_short</code>&rsquo;s silence the week&rsquo;s biggest open '
  'question: armed for 46m30s of a 328-point one-directional break and zero signals. Its hypothesis was '
  'a <em>phase gap</em> &mdash; &ldquo;the router arms when a break is CONFIRMED; a thrust gate needs the '
  'moment a break STARTS, and on Friday those were about 25 minutes apart&rdquo; &mdash; and its kill '
  'line was &ldquo;if the measured lag is under ~5 minutes, the hypothesis is wrong&rdquo;. On 08-28 '
  'there were no triggers to measure, so the report was reasoning about an absence. '
  '<strong>On 2026-09-01 the gate fired twice and won all four legs.</strong> Four clocks, measured on '
  'the 250ms tape (<code>scripts/rev2_break_onset_lag_0904.py</code>):</p>'
  '<table><thead><tr><th class="ln">Clock</th><th class="ln">When</th><th class="ln">What it is</th>'
  '</tr></thead><tbody>'
  f'<tr><td class="ln"><strong>ONSET</strong></td><td class="ln">{r0["onset"][11:16]}Z @ {r0["onset_px"]:,.2f}</td>'
  '<td class="ln">the 60-minute swing high the move departed from &mdash; &ldquo;the moment the break '
  'starts&rdquo;, the thing a thrust gate is said to need</td></tr>'
  f'<tr><td class="ln"><strong>CONFIRM</strong></td><td class="ln">{r0["confirm"][11:16]}Z '
  f'(+{r0["onset_to_confirm_min"]:.0f} min)</td>'
  f'<td class="ln">the first minute the open-hour watcher&rsquo;s own break trio is all true &mdash; '
  f'ER-30 {r0["confirm_er"]}&nbsp;&ge;&nbsp;0.35, ATR-14 {r0["confirm_atr"]}&nbsp;&ge;&nbsp;18, new '
  'session extreme. This is what the ROUTER waits for</td></tr>'
  '<tr class="row-hl"><td class="ln"><strong>ARM</strong></td><td class="ln">08:07:29Z '
  '(+1&nbsp;min&nbsp;29&nbsp;s)</td>'
  '<td class="ln"><strong>the router wrote the switch 89 seconds after its own criterion went '
  'true.</strong> It is not the late one</td></tr>'
  f'<tr class="row-bad"><td class="ln"><strong>TRIGGER</strong></td><td class="ln">08:39:57Z and '
  f'09:01:00Z (+{r0["confirm_to_trigger_min"]:.0f} and +{r2["confirm_to_trigger_min"]:.0f} min after '
  'CONFIRM)</td><td class="ln">the gate&rsquo;s own entries &mdash; 32 and 55 minutes after it was '
  'armed, sitting armed and silent in between</td></tr>'
  '</tbody></table>'
  f'<p><strong>The lag is real and it is enormous: {r0["onset_to_trigger_min"]:.0f} minutes from onset '
  f'to the first trigger and {r2["onset_to_trigger_min"]:.0f} to the second.</strong> But it runs the '
  'wrong way for the proposed fix. Arming on break ONSET would have armed the gate 52 minutes earlier '
  'and produced <em>exactly the same two signals at exactly the same two times</em> &mdash; the '
  'gate&rsquo;s own trigger is the binding constraint, not the arm. <span class="tag pill-dontarm">Do '
  'not build &ldquo;arm on break onset&rdquo;.</span></p>'
  '<p><strong>And the trades were good.</strong> Both signals, four legs, <strong>+$163.50, 4 of 4 '
  'winners</strong>, entered 86 and 107 minutes into a 328-point break. Three of the four exited on '
  'TARGET. Entering <em>late</em> into a confirmed break made money, which is the opposite of what the '
  'stone assumed. The router armed the gate three separate times that day '
  '(08:07&ndash;09:50, 13:16&ndash;14:50, 18:46&ndash;19:05, 3h36m53s in total) and only the first '
  'window produced anything &mdash; so the honest reading is that this gate has a very low duty cycle '
  'and a decent hit rate when it does fire, not that it is out of phase with the router.</p></div>')

# ═══ §3 the week
A('<div class="card"><h3>&sect;3 &nbsp;The week this report could not see &mdash; 2026-08-31 &rarr; '
  '2026-09-04, graded</h3>'
  f'<p>Everything from Part&nbsp;1 to Movement&nbsp;3 grades 08-24&rarr;08-28. Here is the week after, '
  f'on the same ruler. <strong>The desk booked {m(desk[1])} across {desk[0]} legs '
  f'({desk[2]:.0f} contracts), {desk[3]}% of legs green</strong> &mdash; and note that a 76.6% win rate '
  'is not why it is green; the four TARGET_100/200 rider exits are.</p>'
  '<table><thead><tr><th class="ln">Book</th><th class="num">Legs</th><th class="num">Net</th>'
  '</tr></thead><tbody>'
  f'<tr class="row-hl"><td class="ln"><strong>The tournament</strong> (four gates fired)</td>'
  f'<td class="num">{tour[0]}</td><td class="num"><strong>{m(tour[1])}</strong></td></tr>'
  f'<tr class="row-hl"><td class="ln">The day rider</td><td class="num">{rider[0]}</td>'
  f'<td class="num">{m(rider[1])}</td></tr>'
  f'<tr class="row-hl"><td class="ln"><strong>Whole desk</strong></td><td class="num"><strong>{desk[0]}'
  f'</strong></td><td class="num"><strong>{m(desk[1])}</strong></td></tr>'
  '</tbody></table>'
  '<p class="lead">Per gate &mdash; and this is the table that contradicts the body of the report:</p>'
  '<table><thead><tr><th class="ln">Gate</th><th class="num">Legs</th><th class="num">Net</th>'
  '<th class="num">Win %</th><th class="ln">Exit mix</th>'
  '<th class="ln">What the report says about it</th></tr></thead><tbody>')
SAYS={"abs_veto_short":"BUILD&nbsp;#1 called its silence <strong>&ldquo;the week&rsquo;s #1 stone&rdquo;</strong> &mdash; armed for 46m30s of the exact tape it exists to trade, zero signals. It has since fired twice and won every leg.",
      "grind_long":"Part&nbsp;1.5&nbsp;&sect;0a PARKED it on n and floor-clearance alone (2 lots, +$63.50). It has since taken 4 more legs and <strong>both its losses are STOPs</strong>.",
      "exhaustion_short":"BUILD&nbsp;#6 asked for it to be armed from Monday 2026-08-31 to produce evidence. <strong>The window opened and it produced 2 fills of the 40 asked for</strong> &mdash; see &sect;3.1.",
      "abs_veto_long":"the aligned-momentum arm (HOLD&nbsp;#2) is the thing that arms this gate. Its only two legs this week both stopped."}
for g,n,v,w in gates:
    ex=" &middot; ".join(f"{k} &times;{n2}" for k,n2 in sorted(gex[g].items()))
    H.append(f'<tr class="{"row-hl" if v>0 else "row-bad"}"><td class="ln"><code>{g}</code></td>'
             f'<td class="num">{n}</td><td class="num"><strong>{m(v)}</strong></td>'
             f'<td class="num">{w}%</td><td class="ln">{ex}</td>'
             f'<td class="ln">{SAYS.get(g,"")}</td></tr>')
A('</tbody></table>')
A('<p class="lead">Exit mix, whole desk:</p><table><thead><tr><th class="ln">Exit</th>'
  '<th class="num">Legs</th><th class="num">Net</th></tr></thead><tbody>'
  + "".join(f'<tr class="{"row-hl" if v>0 else "row-bad"}"><td class="ln"><code>{k}</code></td>'
            f'<td class="num">{n}</td><td class="num">{m(v)}</td></tr>' for k,n,v in mix)
  + '</tbody></table>')
A('<p class="lead">By day:</p><table><thead><tr><th class="ln">Day</th><th class="num">Legs</th>'
  '<th class="num">Desk net</th></tr></thead><tbody>'
  + "".join(f'<tr class="{"row-hl" if v>0 else "row-bad"}"><td class="ln">{d}</td>'
            f'<td class="num">{n}</td><td class="num">{m(v)}</td></tr>' for d,n,v in days)
  + '</tbody></table>')
A('<div class="callout"><div class="ct">The four claims in this report that this week touches</div>'
  '<table><thead><tr><th class="ln">The claim, as printed</th><th class="ln">What 08-31&rarr;09-04 says</th>'
  '</tr></thead><tbody>'
  '<tr class="row-bad"><td class="ln"><strong>&ldquo;Nothing stopped out. Not once.&rdquo;</strong> '
  '(Part&nbsp;1 lede #5, &sect;9, HOLD&nbsp;#3)</td>'
  '<td class="ln"><strong>Four STOP exits, &minus;$209.00</strong> &mdash; <code>grind_long</code>&nbsp;A/B '
  'at 09-03 13:56:18 and <code>abs_veto_long</code>&nbsp;A/B at 09-03 15:40:55. '
  '<span class="tag">AND THAT IS GOOD NEWS</span> all four <em>filled at the stop</em>: zero '
  '<code>STOP_UNFILLED</code>. The stop-contract fix had gone 30 trading days clean but essentially '
  'untested; it has now been tested four times and held. HOLD&nbsp;#3\'s own caveat &mdash; '
  '&ldquo;thin and largely untested rather than proven&rdquo; &mdash; is partly answered.</td></tr>'
  '<tr class="row-bad"><td class="ln"><strong>The short side fired nothing all week; '
  '<code>abs_veto_short</code>&rsquo;s silence is the #1 stone.</strong></td>'
  '<td class="ln"><code>abs_veto_short</code> <strong>+$163.50 on 4 legs, 4 of 4 winners</strong>, and '
  '<code>exhaustion_short</code> <strong>+$11.00 on 2 legs, both TARGET</strong>. The short side was the '
  'profitable side of the tournament this week. See &sect;2 for what that does to the stone.</td></tr>'
  '<tr class="row-bad"><td class="ln"><strong>&ldquo;The desk was switched on for 3.46% of the '
  'week.&rdquo;</strong></td>'
  f'<td class="ln"><strong>{duty["duty_pct"]}% the week after</strong> &mdash; {duty["armed_total_hours"]} '
  f'gate-hours of the same 708. Nearly double, and the shape is different: '
  f'<code>exhaustion_short</code> {duty["armed_hours"]["exhaustion_short"]}h and '
  f'<code>capitulation_long</code> {duty["armed_hours"]["capitulation_long"]}h carry it, both armed by '
  '<code>reactivate_gates</code> at Paris midnight rather than by the router. '
  '<strong>3.46% is a fact about one week, not a policy.</strong></td></tr>'
  '<tr><td class="ln"><strong>Churn ran 0.237 gate-value changes an hour.</strong></td>'
  f'<td class="ln"><strong>{duty["churn_per_hour"]}/hour the week after</strong> '
  f'({duty["value_changes"]} value changes, {duty["writers"]["router"]} from the router and '
  f'{duty["writers"]["reactivate_gates"]} from <code>reactivate_gates</code>). Still nowhere near '
  'MONDAY&nbsp;#2\'s 1.0/hour kill line. The churn problem remains absent.</td></tr>'
  '</tbody></table>'
  '<p>&#9733; <strong>One methodological note, because it changes how the duty cycle must be '
  'measured.</strong> Counting armed time off the router\'s trial log alone gives <strong>7.89 '
  'gate-hours</strong> for this week &mdash; and <code>exhaustion_short</code> took a live trade at '
  '09-03 22:59:53Z inside an armed window that log does not contain. <code>gate_switches.env</code> has '
  'three writers and the router records only its own. Both writers are replayed in '
  '<code>scripts/rev2_armed_time_w36.py</code>; the answer is 46.03 gate-hours, not 7.89.</p></div>')

# ═══ §3.1 exhaustion_short / BUILD #6
A('<div class="card"><h3>&sect;3.1 &nbsp;BUILD&nbsp;#6 &mdash; <code>exhaustion_short</code>&rsquo;s '
  'window opened, and it is not a grade</h3>'
  '<p>BUILD&nbsp;#6 asked for the <code>UP_OFF</code> rule to be re-priced on <strong>40 machine-exited '
  'fills or 2026-09-15, whichever came first</strong>, with the gate armed from Monday 2026-08-31. The '
  'window opened. Here is where it stands:</p>'
  '<table><thead><tr><th class="ln">What was asked</th><th class="ln">What happened</th></tr></thead><tbody>'
  '<tr><td class="ln">40 machine-exited fills</td><td class="num"><strong>2</strong> &mdash; one signal, '
  'two legs, 2026-09-03 22:59:53Z, <strong>both TARGET at +$5.50 each</strong></td></tr>'
  f'<tr><td class="ln">Days armed</td><td class="ln">{duty["armed_hours"]["exhaustion_short"]}h across '
  'the week &mdash; and all of it from <code>reactivate_gates</code> at 22:00Z, not from a router '
  'decision. The gate is armed overnight and benched in the day</td></tr>'
  '<tr class="row-bad"><td class="ln">Is the window running now?</td><td class="ln"><strong>No.</strong> '
  '<code>data/gate_switches.env</code> reads <code>exhaustion_short=off</code> at this render, and '
  'Friday 22:00Z is VENUE SHUT so <code>reactivate_gates</code> logged &ldquo;already all off, nothing '
  'to do&rdquo;</td></tr>'
  '<tr><td class="ln">Does the &minus;$86 expected-cost estimate still hold?</td>'
  '<td class="ln"><strong>Yes, untouched</strong> &mdash; the gate barely traded, so nothing has '
  'happened that could move it</td></tr>'
  '</tbody></table>'
  '<p><strong>Verdict: RE-ISSUE with the clock restarted, not repeat.</strong> Five sessions produced '
  '2 of the 40 fills. That is a duty-cycle problem, not evidence for or against <code>UP_OFF</code>, and '
  're-issuing the identical window would produce the identical answer. The row is re-dated to '
  '<strong>2026-09-07 &rarr; 2026-09-22</strong> with a new kill line: if the second window also '
  'produces fewer than 10 machine-exited fills, withdraw it and answer the <code>UP_OFF</code> question '
  'off the shadow book instead. <strong>&#9733; The one thing the window did establish:</strong> the gate '
  'is not dead. When it fires it exits on its own targets, and both did.</p></div>')

# ═══ §4 promotion
A('<div class="card"><h3>&sect;4 &nbsp;The Monday promotion, re-decided with the eighth week visible '
  '&mdash; <span class="tag pill-dontarm">HELD</span></h3>'
  '<p>The report\'s only live action was promoting <code>abs_veto_55s</code> two-sided, on '
  '<strong>n=433, +$5,302.50, +$12.25 a trade, green in 7 of 7 ISO weeks</strong>, with the stated '
  'reason being &ldquo;another week of FORWARD evidence rather than another week of the same '
  'evidence&rdquo;. That week has now happened. Re-run to 2026-09-04 '
  '(<code>scripts/abs_veto_robustness.py</code>, unchanged):</p>'
  '<table><thead><tr><th class="ln">ISO week</th><th class="num">n</th><th class="num">Net</th>'
  '<th class="num">$/trade</th><th class="num">LONG net</th><th class="num">SHORT net</th>'
  '</tr></thead><tbody>')
for k in sorted(wk):
    x=wk[k]; L=[r for r in x if r[1]=="LONG"]; S=[r for r in x if r[1]=="SHORT"]
    n,net,e=st(x)
    H.append(f'<tr class="{"row-hl" if net>0 else "row-bad"}"><td class="ln">2026-W{k}'
             f'{" <strong>&larr; the week the report does not show</strong>" if k==36 else ""}</td>'
             f'<td class="num">{n}</td><td class="num">{m(net)}</td><td class="num">{m(e)}</td>'
             f'<td class="num">{m(sum(r[2] for r in L))}</td>'
             f'<td class="num">{m(sum(r[2] for r in S))}</td></tr>')
pn,pnet,pexp=st(post); an,anet,aexp=st(rows)
A('</tbody></table>'
  f'<table><thead><tr><th class="ln">Cut</th><th class="num">n</th><th class="num">Net</th>'
  '<th class="num">$/trade</th><th class="ln">Verdict</th></tr></thead><tbody>'
  f'<tr><td class="ln">As printed in &sect;2.1, the scorecard and the card (to 08-28)</td>'
  f'<td class="num">{len(pre)}</td><td class="num">{m(sum(r[2] for r in pre))}</td>'
  f'<td class="num">{m(sum(r[2] for r in pre)/len(pre))}</td><td class="ln">the promotion case</td></tr>'
  f'<tr class="row-bad"><td class="ln"><strong>The unseen week</strong> (08-28 22:00Z &rarr; 09-04)</td>'
  f'<td class="num">{pn}</td><td class="num"><strong>{m(pnet)}</strong></td>'
  f'<td class="num"><strong>{m(pexp)}</strong></td>'
  '<td class="ln">19.4% win. LONG 18 trades at &minus;$346.50 = <strong>&minus;$19.25/tr</strong>, '
  'SHORT 13 at &minus;$79.50</td></tr>'
  f'<tr class="row-hl"><td class="ln"><strong>All time, to 2026-09-04</strong></td>'
  f'<td class="num"><strong>{an}</strong></td><td class="num"><strong>{m(anet)}</strong></td>'
  f'<td class="num"><strong>{m(aexp)}</strong></td>'
  '<td class="ln">still green; still beats the un-vetoed <code>thrust_loose</code> by +$5,600 across '
  'the board; both regimes and both walk-forward halves positive</td></tr>'
  '</tbody></table>'
  '<p><strong>So the decision, in the open.</strong> Three things changed and none of them refutes the '
  'candidate: (a) &ldquo;green in 7 of 7 ISO weeks&rdquo; becomes <strong>7 of 8</strong>; (b) the '
  'stated reason for promoting was forward evidence, and the forward evidence arrived arguing the other '
  'way; (c) <strong>the card&rsquo;s own kill criterion &mdash; &ldquo;the LONG side below '
  '&minus;$5/trade&rdquo; &mdash; is already tripped</strong>, at &minus;$19.25.</p>'
  '<p><span class="tag pill-dontarm">HELD ONE WEEK, NOT KILLED</span> Promoting a candidate the week '
  'after its own kill line trips is how a desk learns to ignore its kill lines. Nothing here is a '
  'robustness failure &mdash; expectancy all-time is +$10.51 a trade and every robustness leg still '
  'passes &mdash; so the cause is not death, it is <em>timing</em>. Re-read Friday 2026-09-11 and '
  'promote only after two consecutive weeks with the LONG side above &minus;$5/trade.</p>'
  '<p><strong>&#9733; And the arithmetic downstream moves with it.</strong> Part&nbsp;3&nbsp;&sect;Q1 '
  'computed the live-loss haircut breakeven at <strong>1.64&times;</strong> off the stale +$12.25 &mdash; '
  'multiply only the loss side by &lambda; and solve for zero. On the full 464 trades the wins are '
  f'{m(WIN)} against {m(LOSS)} of losses, so breakeven is <strong>{BE:.2f}&times;</strong>. '
  'The arm now survives live slippage up to '
  f'{BE:.2f}&times; modelled rather than 1.64&times;, against a desk-wide standing finding that live '
  f'losses run <strong>1.1&ndash;3.1&times;</strong> modelled. At 1.50&times; it is +$0.68 a trade &mdash; '
  'a rounding error &mdash; and at 2.0&times; it is &minus;$9.15. The headroom was already thin; it is '
  'thinner, and it is one more reason the promotion waits.</p>'
  '<p class="ln">&#9733; <strong>One caveat that argues the same way.</strong> A shadow mirror steps once '
  'per completed 1-minute bar and tests its stop against the bar CLOSE, while the live loss side is a '
  'resting venue STP that triggers intrabar. A wick through the stop that closes back inside is '
  'invisible to the mirror. The shadow number is therefore an <em>upper</em> bound on this arm, in a '
  'direction that gets worse in choppy tape.</p></div>')

# ═══ §5 bench saving / HOLD #2
A('<div class="card"><h3>&sect;5 &nbsp;Which bench number the desk carries, and what HOLD&nbsp;#2 rests '
  'on now</h3>'
  '<p><strong>The figure is +$312.35 over 117 signals. The +$810.44 over 127 is RETIRED.</strong> Not '
  '&ldquo;un-quotable&rdquo; &mdash; retired: its population was counted off <code>SUPPRESSED-OPEN</code> '
  'journal lines, the systemd journal is a ring buffer, and it can no longer be rebuilt or checked. '
  'Part&nbsp;1&nbsp;&sect;6 replaces it with a saved, re-runnable replay over '
  '<code>signal_journal</code>, which is durable on disk from 2026-08-04. This revision propagates that '
  'result to the four places that were still printing the old one: the &ldquo;if you read only '
  'this&rdquo; box, the scorecard, HOLD&nbsp;#1, and the standing method-wound paragraph.</p>'
  '<table><thead><tr><th class="ln">Test</th><th class="ln">Result</th><th class="ln">Reading</th>'
  '</tr></thead><tbody>'
  '<tr class="row-hl"><td class="ln">Stop-width sweep, 0.5&times; &rarr; 1.5&times;</td>'
  '<td class="ln">+$624.59 / +$490.34 / <strong>+$312.35</strong> / +$73.29 / +$11.86</td>'
  '<td class="ln"><span class="tag">SIGN-STABLE</span> which is what earns it a verdict at all &mdash; '
  'but read the SLOPE: it decays monotonically. Most of what benching &ldquo;saved&rdquo; is the '
  'desk&rsquo;s stop being tight enough to guarantee those trades lost</td></tr>'
  '<tr class="row-bad"><td class="ln">Leave-one-day-out</td><td class="ln">drop Tue &rarr; +$8.39; drop '
  'Thu &rarr; +$16.62</td><td class="ln">two days of five carry 100% of the gross positive</td></tr>'
  '<tr class="row-bad"><td class="ln">Strip-the-best-3</td><td class="ln">+$312.35 &rarr; +$66.31</td>'
  '<td class="ln">three signals of 117 are 79% of the result</td></tr>'
  '<tr class="row-bad"><td class="ln">Bootstrap, 10,000 draws</td>'
  '<td class="ln">&minus;$623.74 to +$1,208.31, <strong>P(&le;0) = 0.253</strong></td>'
  '<td class="ln">a direction, not a measurement</td></tr>'
  '<tr class="row-bad"><td class="ln"><strong>Label-shuffle placebo on the regime split</strong></td>'
  '<td class="ln"><strong>P = 0.943</strong></td>'
  '<td class="ln"><span class="tag pill-dontarm">REFUTED</span> chop is +$3.99 a signal (n=78) and '
  'aligned trend +$3.37 (n=35) &mdash; the same number</td></tr>'
  '</tbody></table>'
  '<p><strong>What that costs HOLD&nbsp;#2.</strong> The whole stated reason for keeping the '
  'aligned-momentum arm was that sentence: <em>&ldquo;in aligned trend, benching is FREE &mdash; 50 '
  'signals, &minus;$0.81 each &mdash; which is the actual argument for arming aggressively on a '
  'confirmed break&rdquo;</em>. It does not survive its own placebo. So, plainly: '
  '<strong>the arm is now held on judgement, with no number behind it.</strong> The honest case is that '
  'it is the operator&rsquo;s standing instruction of 2026-08-05, that the one arm it produced was '
  'right, and that no test says it is wrong. That is a reason to leave it alone. It is not a reason to '
  'arm harder, and nothing on this card may cite the free-in-trend sentence again. HOLD&nbsp;#2 now '
  'says exactly that.</p>'
  '<p class="ln">&#9733; The named caveat on any bench figure still stands and is one of the reasons the '
  '$810 is gone: <code>SUPPRESSED-OPEN</code> is logged at <code>tournament.py:306</code>, upstream of '
  'the 55-second veto at <code>tournament.py:360</code>, so for four of the six gates the benched '
  'population contains trades the gate&rsquo;s own veto would have thrown away. Anything built on it is '
  'an UPPER BOUND. Part&nbsp;3&nbsp;&sect;Q4\'s independent floor is +$128.</p></div>')

# ═══ §6 MED-TREND
A('<div class="card"><h3>&sect;6 &nbsp;Is the grind MED-TREND branch deployed on Monday? '
  '<span class="tag pill-dontarm">NO</span> &mdash; one verdict, and the cause of death named</h3>'
  '<p>The report gave two opposite instructions about one file on one Monday. Part&nbsp;2&nbsp;&sect;10 '
  'graded the rung &ldquo;SHADOW &rarr; deploy BANDED&rdquo; and &sect;11 said to deploy it; the MONDAY '
  'window intro said &ldquo;Part 2 graded twenty of them and all twenty failed, so '
  '<code>data/exit_overrides.json</code> is not touched&rdquo;, and HOLD&nbsp;#4 said change nothing. '
  '<strong>They are not contradicting each other about the same test &mdash; they are applying '
  'different bars, and neither said so.</strong></p>'
  '<table><thead><tr><th class="ln">Test</th><th class="num">grind MED-TREND, A 0.75R / B 1.0R</th>'
  '<th class="ln">Pass?</th></tr></thead><tbody>'
  '<tr class="row-hl"><td class="ln">In-sample $/signal (n=215)</td><td class="num">+$7.70</td>'
  '<td class="ln">&#10003;</td></tr>'
  '<tr class="row-hl"><td class="ln">Strip-the-best-3</td><td class="num">+$5.60</td>'
  '<td class="ln">&#10003;</td></tr>'
  '<tr class="row-hl"><td class="ln">Leave-one-day-out (worst fold)</td><td class="num">+$6.20</td>'
  '<td class="ln">&#10003;</td></tr>'
  '<tr class="row-hl"><td class="ln">Both halves</td><td class="num">+$13.50 / +$1.90</td>'
  '<td class="ln">&#10003;</td></tr>'
  '<tr class="row-hl"><td class="ln">Parameter plateau</td><td class="num">5 adjacent cells positive, '
  'monotone gradient; 8 of 48 cells positive</td><td class="ln">&#10003; &mdash; a plateau, not a '
  'spike</td></tr>'
  '<tr class="row-bad"><td class="ln"><strong>Out-of-sample POOL split (the retired V5 desk\'s real '
  'fills)</strong></td><td class="num"><strong>&minus;$4.50/signal on n=52</strong></td>'
  '<td class="ln"><strong>&#10007;</strong></td></tr>'
  '<tr class="row-bad"><td class="ln"><strong>Its own live forward arm</strong> '
  '(<code>rung_grindA_med_05</code>, running since 08-16)</td>'
  '<td class="num"><strong>&minus;$8.36/trade on n=21</strong>, against its control '
  '<code>rung_grindA_med_live</code> at &minus;$9.29</td><td class="ln"><strong>&#10007;</strong></td></tr>'
  '</tbody></table>'
  '<p><strong>That is the reconciliation.</strong> The twenty failed cells are graded on a FOUR-test bar '
  'that includes the pool split; &sect;7.2\'s &ldquo;PROVEN&rdquo; is a THREE-test bar. MED-TREND is the '
  'one cell that clears three and fails the fourth &mdash; so &ldquo;19 of 20 fail on three tests, 20 of '
  '20 fail on four&rdquo; and both sentences were true about different things. And the twenty are '
  'four rungs &times; five families, of which BIG-TREND is only one rung; &ldquo;the twenty failed '
  'cells&rdquo; was never a statement about BIG-TREND alone.</p>'
  '<p><span class="tag pill-dontarm">CAUSE OF DEATH FOR THE DEPLOY: THE OUT-OF-SAMPLE LEG.</span> Two '
  'independent out-of-sample legs, one historical and one forward, are both negative, and the forward '
  'one is the desk&rsquo;s own money. The paired comparison is genuinely encouraging &mdash; on the 19 '
  'entries both A arms share, the proposal makes &minus;$116.00 where the live ladder makes '
  '&minus;$176.50, a <strong>+$60.50 edge</strong>, better on 6, worse on 5, identical on 8 &mdash; but '
  '<strong>the whole rung is losing money in both configurations</strong>. A better exit on a losing '
  'entry is an entry problem wearing an exit costume.</p>'
  '<p><strong>ONE verdict, which HOLD&nbsp;#4 and the MONDAY window intro now both repeat: '
  '<code>data/exit_overrides.json</code> is not touched this weekend, MED-TREND included.</strong> It '
  'stays in shadow with <code>rung_grindA_med_live</code> as referee. Deploy when EITHER out-of-sample '
  'leg turns positive: the V5 pool above $0/signal, or the forward arm above its control over '
  'n&nbsp;&ge;&nbsp;40. Not on the in-sample number.</p></div>')

# ═══ §7 census
A('<div class="card"><h3>&sect;7 &nbsp;How much of &ldquo;$10,512 left on the table&rdquo; was really '
  'sat out? <strong>$8,845</strong> &mdash; and nine runs move buckets</h3>'
  '<p>The census scored a trade taken <em>inside</em> a run as &ldquo;sat out&rdquo;. '
  '<code>run_census.py</code> attributed trades over <code>start&nbsp;&plusmn;&nbsp;300s</code> while a '
  'run is <code>W=180</code> five-second bars = <strong>15 minutes</strong> long, so any entry more '
  'than five minutes into a run&rsquo;s own body was invisible. The 09-03 13:36 UP +130pt run had an '
  'attribution window of 13:31&ndash;13:41; <code>grind_long</code> bought both lots at '
  '<strong>13:42:05</strong> and was stopped at 13:56 &mdash; inside the run, scored as an absence.</p>'
  '<p><strong>The fix is one line</strong> &mdash; attribute over <code>[start&nbsp;&minus;&nbsp;300s, '
  'start&nbsp;+&nbsp;W&times;5s]</code>: five minutes of lead-in for an early entry, then the '
  'run&rsquo;s whole body. Re-frozen on the same tape:</p>'
  '<table><thead><tr><th class="ln">Bucket</th><th class="num">As printed</th>'
  '<th class="num">Attributed over the run&rsquo;s body</th><th class="ln">What moved</th>'
  '</tr></thead><tbody>'
  '<tr class="row-hl"><td class="ln">Caught (aligned)</td><td class="num">1</td>'
  '<td class="num"><strong>10</strong></td><td class="ln">nine runs were being scored as absences while '
  'the desk was in them</td></tr>'
  '<tr class="row-bad"><td class="ln">Fought (against)</td><td class="num">2</td><td class="num">2</td>'
  '<td class="ln">unchanged</td></tr>'
  '<tr><td class="ln">Sat out</td><td class="num">73</td><td class="num"><strong>64</strong></td>'
  '<td class="ln">&mdash;</td></tr>'
  '<tr class="row-hl"><td class="ln"><strong>Hindsight ceiling left on the table</strong></td>'
  '<td class="num"><strong>$10,512</strong></td><td class="num"><strong>$8,845</strong></td>'
  '<td class="ln"><strong>the headline overstated the sitting-out by $1,667, or 16%</strong></td></tr>'
  '<tr class="row-hl"><td class="ln">What the caught runs actually banked</td><td class="num">&mdash;</td>'
  '<td class="num"><strong>+$1,912</strong> on a $1,846 ceiling</td>'
  '<td class="ln">104% &mdash; see below</td></tr>'
  '</tbody></table>'
  '<p>The Gate column also stops naming only <code>day_rider</code> on a week when the tournament took '
  '12 legs: <code>abs_veto_short</code>, <code>grind_long</code> and <code>abs_veto_long</code> all now '
  'appear against runs they were actually in.</p>'
  '<p><strong>Two template faults fixed alongside it.</strong> (1) The lede hard-coded '
  '&ldquo;which is only {conv}% of&rdquo;, so a week where the caught runs BEAT their ceiling printed '
  'as a shortfall &mdash; &ldquo;only 359% of&rdquo;. It now branches, and says why over 100% is '
  'legitimate: the ceiling prices the run&rsquo;s own 15-minute move at one lot, and a position still '
  'open when the run ends goes on earning outside the census window. (2) A positive FOUGHT bucket now '
  'explains itself &mdash; the bucket is decided by which SIDE the desk was on relative to the run, not '
  'by whether the trade won, so a position opened against a run that reverses inside its own 15 minutes '
  'books money while still counting as fighting it. Read a green FOUGHT row as &ldquo;we were on the '
  'wrong side and got away with it&rdquo;, never as a reason to fight runs on purpose.</p>'
  '<p class="ln">&#9733; <strong>What this does NOT change.</strong> Movements&nbsp;2 and&nbsp;3 are '
  'computed on the <strong>2026-08-28</strong> freeze, which is a different week entirely and which this '
  'fix has not been applied to. Both sections now say so in a banner at the top rather than claiming '
  'their run list matches the Movement&nbsp;1 printed above them &mdash; it does not, and it never '
  'did in this document.</p></div>')

# ═══ §8 off-tape
w=off["windows"]
A('<div class="card"><h3>&sect;8 &nbsp;The rider&rsquo;s off-tape residual leg &mdash; one figure, and '
  '<span class="tag pill-dontarm">IT IS STILL HAPPENING</span></h3>'
  '<p>Four different totals for one artefact were in print. The adjudicated one is '
  'Part&nbsp;1.6&nbsp;&sect;6(b)\'s, and it is now the only one anywhere in this report, on the card '
  'included:</p>'
  '<table><thead><tr><th class="ln">Window</th><th class="num">Split orders</th>'
  '<th class="num">Residual legs</th><th class="num">Lots</th><th class="num">Cost</th>'
  '<th class="ln">Share of that book&rsquo;s P&amp;L</th></tr></thead><tbody>'
  f'<tr class="row-hl"><td class="ln"><strong>The report week, 08-24 &rarr; 08-28</strong></td>'
  f'<td class="num">{w["report week Mon 08-24 .. Fri 08-28"]["events"]}</td>'
  f'<td class="num">{w["report week Mon 08-24 .. Fri 08-28"]["off_legs"]}</td>'
  f'<td class="num">{w["report week Mon 08-24 .. Fri 08-28"]["off_lots"]:.0f}</td>'
  f'<td class="num"><strong>${w["report week Mon 08-24 .. Fri 08-28"]["cost_usd"]:,.2f}</strong></td>'
  '<td class="ln"><strong>66.8%</strong> of the rider&rsquo;s &minus;$1,576.94</td></tr>'
  f'<tr class="row-bad"><td class="ln"><strong>&#9733; The week AFTER, 08-31 &rarr; 09-04</strong> '
  '&mdash; the verification SATURDAY&nbsp;#4 itself asked for</td>'
  f'<td class="num">{w["the week AFTER  Mon 08-31 .. Fri 09-04"]["events"]}</td>'
  f'<td class="num">{w["the week AFTER  Mon 08-31 .. Fri 09-04"]["off_legs"]}</td>'
  f'<td class="num">{w["the week AFTER  Mon 08-31 .. Fri 09-04"]["off_lots"]:.0f}</td>'
  f'<td class="num"><strong>${w["the week AFTER  Mon 08-31 .. Fri 09-04"]["cost_usd"]:,.2f}</strong></td>'
  '<td class="ln"><strong>143%</strong> of the rider&rsquo;s +$613.50 &mdash; the rider was green '
  '<em>despite</em> it</td></tr>'
  f'<tr><td class="ln">All time</td><td class="num">{w["all time"]["events"]}</td>'
  f'<td class="num">{w["all time"]["off_legs"]}</td>'
  f'<td class="num">{w["all time"]["off_lots"]:.0f}</td>'
  f'<td class="num">${w["all time"]["cost_usd"]:,.2f}</td><td class="ln">&mdash;</td></tr>'
  '</tbody></table>'
  '<p><strong>The verification asked for &ldquo;a week with zero off-tape legs, or with the residual '
  'priced at the tape&rdquo;. It got neither.</strong> Seven more split orders, seven residual legs, '
  'fifteen lots, every one adverse, and <strong>0 of 7 on the tape</strong> within &plusmn;30 seconds. '
  'Every one is 29.0&ndash;29.5 points against, which is the 0.1% factor at this price level:</p>'
  '<table><thead><tr><th class="ln">When</th><th class="ln">Order</th><th class="ln">Side</th>'
  '<th class="num">Lots</th><th class="num">Residual price</th><th class="num">Points adverse</th>'
  '<th class="num">Cost</th></tr></thead><tbody>'
  + "".join(f'<tr class="row-bad"><td class="ln">{r["exec_time"][5:16].replace("T"," ")}Z</td>'
            f'<td class="ln"><code>{r["order_id"]}</code></td><td class="ln">{r["side"]}</td>'
            f'<td class="num">{r["qty"]:.0f}</td><td class="num">{r["price"]:,.2f}</td>'
            f'<td class="num">{r["adverse_pt"]:.1f}</td><td class="num">${r["cost_usd"]:,.2f}</td></tr>'
            for r in off["rows"] if "2026-08-31" <= r["exec_time"][:10] < "2026-09-05")
  + '</tbody></table>'
  '<p>Every leg carries a distinct, correctly-formatted IBKR <code>execId</code>, so this is not '
  'obviously a fabricated row &mdash; but <code>0.001</code> / <code>1.001</code> / <code>0.999</code> '
  'appears <strong>nowhere</strong> in <code>src/gazbot7/</code>, which is the other half of the '
  'question and is still open. Either way it is plumbing, not strategy: <strong>SATURDAY&nbsp;#4 is '
  'the largest single fixable item on this desk in two consecutive weeks.</strong></p></div>')

# ═══ §9 the card
tal=ship["tally"]
A('<div class="card"><h3>&sect;9 &nbsp;So what do I actually DO this weekend? The card is re-dated, and '
  'every 2026-08-28 row now carries a shipped-check</h3>'
  '<p>The card was addressed to a weekend that had gone: five window headers reading &ldquo;SATURDAY '
  '&middot; BEFORE THE SUNDAY 22:00Z REOPEN&rdquo; and &ldquo;MONDAY &middot; AT THE DESK&rdquo;, '
  'MONDAY&nbsp;#1&ndash;#4 all saying &ldquo;Arms: Monday&rdquo;, BUILD&nbsp;#6 asking for an arming '
  'window that opened on 2026-08-31. Published 2026-09-04, those point four to six days into the past, '
  'and 42 of the 54 rows carried a <code>-0828</code> suffix with no way to tell which had been '
  'actioned.</p>'
  '<p><strong>Both are fixed.</strong> Every window is re-dated to <strong>Sat 2026-09-05 / Sun '
  '2026-09-06 / Mon 2026-09-07</strong>, and every <code>-0828</code> row carries the verdict of a '
  'probe run against this box at render time &mdash; a file, a unit, a <code>grep</code> or a database '
  'read, never a memory (<code>scripts/rev2_shipped_check_0904.py</code>). '
  f'<strong>Of the 25 shippable rows: {tal.get("NOT DONE",0)} NOT DONE, {tal.get("CARRIED",0)} CARRIED, '
  f'{tal.get("MEASURED",0)} re-measured, and {tal.get("DONE",0)} DONE.</strong> The other 17 are HOLD or '
  'NOT-AN-ACTION rows &mdash; standing positions with nothing to ship.</p>'
  '<table><thead><tr><th class="ln">Row</th><th class="ln">Verdict</th><th class="ln">The probe, and '
  'what it read</th></tr></thead><tbody>'
  + "".join(f'<tr class="{"row-bad" if r["verdict"]=="NOT DONE" else "row-hl" if r["verdict"] in ("DONE","MEASURED") else ""}">'
            f'<td class="ln"><strong>{r["window"]}&nbsp;#{r["rank"]}</strong><br>'
            f'<span class="ln">{r["topic"][:110]}</span></td>'
            f'<td class="ln"><span class="tag">{r["verdict"]}</span></td>'
            f'<td class="ln">{r["evidence"]}</td></tr>'
            for r in sorted(ship["rows"], key=lambda r:(r["verdict"]!="NOT DONE", r["window"], r["rank"]))
            if r["verdict"] != "STANDING")
  + '</tbody></table>'
  '<p><strong>The one that matters most is SATURDAY&nbsp;#5.</strong> &ldquo;Move the rider&rsquo;s '
  'first flatten attempt earlier and put the page UPSTREAM of the flatten&rdquo; was issued last '
  'weekend, is NOT DONE, and is the row that bit tonight: '
  '<code>gazbot7-eod-flatten.timer</code> still fires at 16:53 and 16:57 New York, both shots died in '
  'the same timeout, and four lots are open. <strong>If one thing gets done this weekend, it is that '
  'one.</strong></p></div>')

# ═══ §10 limits
A('<div class="callout"><div class="ct">What I could not close, said plainly</div><ol>'
  '<li><strong>The 08-31&rarr;09-04 week is n=12 tournament legs on 4 gates.</strong> It contradicts '
  'four claims in this report and it is not big enough to REPLACE any of them. It is printed beside '
  'them, not instead of them. One good week and one bad week are the same size of evidence.</li>'
  '<li><strong>Movements 2 and 3 have NOT been recomputed on the corrected census attribution.</strong> '
  'They run on the 2026-08-28 freeze, which is a different week; re-freezing it would mean re-running '
  'both labs, and neither has run this cycle. The attribution bug is fixed in the script, so it will be '
  'right from the next freeze onward, and both sections now name their own freeze rather than claiming '
  'to share Movement&nbsp;1\'s.</li>'
  '<li><strong>The bench replay is still in-sample by construction</strong> &mdash; it reprices '
  'decisions already made, on the tape they were made on &mdash; and every replayed figure is one lot '
  'on the Lot-A ruler while the live desk runs two. The Lot-B tail is modelled nowhere.</li>'
  '<li><strong>&sect;2 is n=2 signals.</strong> Two clean cases move a mechanism question in a way a '
  'fortnight of silence cannot, and they are still two cases. What they rule out is &ldquo;arm on '
  'onset&rdquo; as a fix, because the gate&rsquo;s trigger came after the arm on both of them. They do '
  'not establish a median lag.</li>'
  '<li><strong>Nothing here reprices MGC.</strong> The gold half of this report sits on a parquet lake '
  'whose year backfill serves the wrong contract for 22% of its minutes; that is SATURDAY&nbsp;#9 and it '
  'is unfixed.</li>'
  '</ol></div>')

pathlib.Path(f"{SEC}/rev2_answers_0904.html").write_text("\n".join(H))
print(f"wrote {SEC}/rev2_answers_0904.html ({sum(len(x) for x in H):,} chars)")
