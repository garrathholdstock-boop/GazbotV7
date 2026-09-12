#!/usr/bin/env python3
"""PART 2.6 — ROUTER OPERATION REVIEW, week of 2026-08-17 .. 2026-08-21.

Rebuilt from raw logs, because the instruments that were supposed to answer this are dead:
data/router_nightly/ stops at 2026-08-14 and data/selector_nightly/ at 2026-08-18, and no timer
runs either. Sources actually used: data/router_trial_log.txt (the tick-by-tick record with
reasoning), data/gate_switches.env (the switch file AND its comment header), the systemd journal
for gazbot7-gate-reactivate, and Movement 2's mechanical counterfactual for the value question.

  PYTHONPATH=src .venv/bin/python scripts/fv7_p26_router.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from fv7_common import (DAYNAME, DAYS, callout, correction, disposition, esc, m, pct,  # noqa
                        table, write)

LOG = "/home/alphabot/gazbot7/data/router_trial_log.txt"
SWITCHES = "/home/alphabot/gazbot7/data/gate_switches.env"
NOW = dt.datetime(2026, 8, 22, 1, 0, tzinfo=dt.UTC)
RIDER_ENTRY_TS = "2026-08-21T13:13"

RX = re.compile(r"^(\S+Z) \| (\S+) \| (\S+) \| changed: (.*?) \| (.*)$")

# Every switch the router wrote this week, graded by hand against what the tape then did. The
# grade is the judgement; the timestamp, the gate and the direction are read off the log.
GRADES = {
    "2026-08-17T08:10:43Z": ("✅ GOOD", "Benched into the pre-open. The gate took two stops the "
                             "previous hour and the tape was going nowhere."),
    "2026-08-17T08:25:25Z": ("⚠ CHURN", "Re-armed 15 minutes later. Nothing changed in between; "
                             "this is the toggle pattern the ledger keeps flagging."),
    "2026-08-17T10:30:54Z": ("✅ GOOD", "Armed the long fader into a genuine bid."),
    "2026-08-17T12:40:43Z": ("✅ GOOD", "The fail-safe bench that avoided the 12:40 reversal. A "
                             "fail-safe bench is exempt from the confirmation rule, and this is "
                             "the example of why."),
    "2026-08-17T15:00:25Z": ("✅ GOOD", "Benched both faders into the afternoon drift. Neither "
                             "fired again that day."),
    "2026-08-18T01:55:36Z": ("&mdash; $0", "An Asia-hours bench. Worth exactly nothing in either "
                             "direction: entries are refused in that block anyway."),
    "2026-08-19T07:00:40Z": ("✅ GOOD", "Benched the short book at the European open before the "
                             "07:50 squeeze."),
    "2026-08-19T07:50:27Z": ("✅ GOOD", "Re-armed for the down-leg it then caught (+$179 in "
                             "claims at 13:50)."),
    "2026-08-19T12:40:58Z": ("❌ BAD", "Benched abs_veto_short and exhaustion_short ten minutes "
                             "before the 13:39 down-leg that made the rider $541, and armed the "
                             "LONG fader into it. Wrong side, wrong ten minutes."),
    "2026-08-19T12:51:24Z": ("❌ BAD", "Armed grind_long into the same down-leg. It could not "
                             "fire — the ATR floor saw to that — so the cost is $0 and the "
                             "process is still wrong."),
    "2026-08-19T13:40:31Z": ("✅ GOOD", "Corrected itself within the hour: grind off, short book "
                             "back on, one minute after the rider's entry."),
    "2026-08-19T13:41:01Z": ("⚠ CHURN", "A second write 30 seconds after the first, same "
                             "content plus abs_veto_long. Two writes, one decision."),
    "2026-08-19T13:50:52Z": ("&mdash; $0", "Housekeeping on a gate that had not fired."),
    "2026-08-19T15:05:33Z": ("✅ GOOD", "Benched the short book after the 14:51 stop."),
    "2026-08-19T15:35:52Z": ("❌ BAD", "Re-armed 30 minutes later with no positive case. It then "
                             "took three more stops for −$133."),
    "2026-08-19T18:16:31Z": ("✅ GOOD", "Applied the operator's 18:15Z bench instruction within "
                             "90 seconds."),
    "2026-08-19T22:00:35Z": ("&mdash; $0", "Re-asserted the bench at the reopen. No-op."),
    "2026-08-20T06:40:33Z": ("&mdash; $0", "Asia-hours bench."),
    "2026-08-20T08:05:37Z": ("&mdash; $0", "Housekeeping under the standdown."),
    "2026-08-21T14:05:18Z": ("✅ GOOD", "Re-benched abs_veto_short 2m15s after the OPEN-HOUR "
                             "WATCHER auto-armed it through a standing operator standdown. See "
                             "§4 — the router was the only thing that caught it."),
}


def main():
    rows = [m_.groups() for line in open(LOG, errors="replace").read().splitlines()
            if line.startswith("2026-") and (m_ := RX.match(line))]
    wk = [r for r in rows if "2026-08-17" <= r[0] < "2026-08-22"]
    ch = [r for r in wk if r[3] != "none"]

    # ── §1 duty cycle ────────────────────────────────────────────────────────────────────
    duty = table(
        ["Session", "Ticks", "Ticks that changed a switch", "Change rate"],
        [[DAYNAME[d], str(sum(1 for r in wk if r[0][:10] == d)),
          str(sum(1 for r in ch if r[0][:10] == d)),
          pct(100 * sum(1 for r in ch if r[0][:10] == d) /
              max(sum(1 for r in wk if r[0][:10] == d), 1), 1)] for d in DAYS],
        foot=["THE WEEK", str(len(wk)), str(len(ch)), pct(100 * len(ch) / len(wk), 1)],
        numeric={1, 2, 3})

    # ── §2 every switch, graded ──────────────────────────────────────────────────────────
    gr_rows = []
    for ts, _t, _d, changed, _why in ch:
        g, note = GRADES.get(ts, ("&mdash;", "Not graded."))
        bad = "❌" in g or "⚠" in g
        gr_rows.append([("", "row-bad" if bad else ("row-hl" if "✅" in g else ""))] + [
            ts[5:16].replace("T", " ") + "Z", f"<code>{esc(changed)}</code>", g, note])
    graded = table(["When (UTC)", "What it wrote", "Grade", "Why"], gr_rows)
    good = sum(1 for ts, *_ in ch if "✅" in GRADES.get(ts, ("",))[0])
    bad = sum(1 for ts, *_ in ch if "❌" in GRADES.get(ts, ("",))[0])
    churn = sum(1 for ts, *_ in ch if "⚠" in GRADES.get(ts, ("",))[0])
    zero = sum(1 for ts, *_ in ch if "$0" in GRADES.get(ts, ("",))[0])

    # ── §3 the value question ────────────────────────────────────────────────────────────
    bf = json.load(open("/home/alphabot/gazbot7/reports/friday_v7/sections/"
                        "movement2_basefire.json"))
    GAT = ("grind_long", "capitulation_long", "abs_veto_long", "rgv_short", "exhaustion_short",
           "abs_veto_short")
    mech = {g: round(sum(f["usd"] for f in bf[g]["fills"]), 2) for g in GAT}
    mech_all = round(sum(mech.values()), 2)
    benched4 = round(sum(mech[g] for g in GAT[:4]), 2)
    value = table(
        ["Gate", "Live this week", "If it had been armed all week, mechanically", "Difference"],
        [[("", "row-hl" if mech[g] < 0 else "row-bad")] + [
            f"<code>{esc(g)}</code>",
            {"abs_veto_short": m(-203.0), "exhaustion_short": m(144.5)}.get(g, "benched, $0"),
            f"{m(mech[g])} on {len(bf[g]['fills'])} fires",
            m(round({"abs_veto_short": -203.0, "exhaustion_short": 144.5}.get(g, 0.0) - mech[g], 2))]
         for g in GAT],
        foot=["ALL SIX", m(-58.5), f"{m(mech_all)} on {sum(len(bf[g]['fills']) for g in GAT)} fires",
              m(round(-58.5 - mech_all, 2))], numeric={1, 2, 3})

    # ── §4 who else can write the switch file ────────────────────────────────────────────
    seq = [line for line in open(LOG, errors="replace").read().splitlines()
           if line.startswith("2026-08-21T14:0")][:3]

    # ── §5 the comment header ────────────────────────────────────────────────────────────
    txt = open(SWITCHES, errors="replace").read().splitlines()
    top = [line for line in txt[:60] if line.startswith("#")][:45]
    carve = []
    for line in top:
        mm = re.search(r"(2026-\d\d-\d\d)T?(\d\d:\d\d)?Z?", line)
        if not mm or not re.search(r"★|OPERATOR|WATCHER", line):
            continue
        d = dt.datetime.fromisoformat(mm.group(1)).replace(tzinfo=dt.UTC)
        if mm.group(2):
            d = d.replace(hour=int(mm.group(2)[:2]), minute=int(mm.group(2)[3:]))
        age = NOW - d
        body = re.sub(r"^#\s*★*", "", line).strip()
        hits = sum(1 for r in wk if mm.group(2) and mm.group(2) + "Z" in r[4])
        carve.append([("", "row-bad" if age.days >= 2 else "")] + [
            esc(body[:96]), f"{age.days}d {age.seconds // 3600}h",
            "<strong>YES</strong> &mdash; spliced into every prompt as ACTIVE",
            f"{hits} of {len(wk)}"])
    carve_t = table(["Instruction sitting in the switch file's header", "Age at this report",
                     "Still being read to the router?", "Ticks that restated it"], carve,
                    numeric={3})

    lens = [len(r[4]) for r in wk]
    carve_hits = sum(int(c[4].split(' of ')[0]) for c in carve)
    at_cap = sum(1 for x in lens if x >= 1190)

    # ── §6 the attribution failure ───────────────────────────────────────────────────────
    post = [r for r in rows if r[0] >= RIDER_ENTRY_TS]
    flat = [r for r in post if re.search(r"\bflat\b", r[4], re.I)]

    # ── §7 the nightly rollups ───────────────────────────────────────────────────────────
    def newest(d):
        p = f"/home/alphabot/gazbot7/data/{d}"
        f = sorted(os.listdir(p)) if os.path.isdir(p) else []
        return f[-1].replace(".json", "") if f else "none"

    doc = f"""
<h2 id="p26"><span class="n">P2.6</span> ROUTER OPERATION REVIEW &mdash; the desk's #1 lever, on
the stand</h2>

<p class="lead">Garrath &mdash; the router ran {len(wk):,} ticks this week and wrote a switch on
{len(ch)} of them. That is the headline and it is not a criticism: the tournament has been stood
down all week, so most of what the router had to decide was whether to keep doing nothing, and it
kept doing nothing correctly. <strong>What this section is actually about is the three things
that can write the switch file or claim to know the desk's state, and the fact that on the two
occasions this week where those disagreed, the router was right and the instruments around it were
wrong.</strong> It also has to say plainly that the two files built to answer &ldquo;was the router
optimal this week&rdquo; both stopped being written, so everything here is rebuilt from raw logs.</p>

<h3>1 &middot; The duty cycle</h3>

{duty}

<p class="ln">{pct(100 * len(ch) / len(wk), 1)} of ticks change anything. The audit's number for
the fortnight was 97.2% no-change; this week is
{pct(100 * (1 - len(ch) / len(wk)), 1)} no-change, so if anything the router has got quieter, which
under a standdown is the correct direction. There were no systemd failures and no aborted
decisions this week &mdash; both worth stating, because last cycle had a 10-hour block of aborts
that no scoreboard noticed.</p>

<h3>2 &middot; Every switch it wrote, graded</h3>

{graded}

<p class="ln"><strong>{good} good, {bad} bad, {churn} churn, {zero} worth exactly $0.</strong>
The $0 rows are Asia-hours writes: new entries are refused in that block regardless, so a bench
there is neither a save nor a cost, and it should not be counted as either. The two genuinely bad
calls are both on Wednesday and they are the same mistake made twice &mdash; benching the short
book at 12:40 ten minutes before the day's best down-leg, then re-arming at 15:35 with no positive
case, straight into three more stops. <strong>Re-arming without a positive live case is now this
gate's most expensive recurring pattern</strong>, and it has cost money on three separate occasions
that the ledger records.</p>

<h3>3 &middot; Is the router earning its keep? The mechanical counterfactual</h3>

<p>The honest way to ask is not &ldquo;did the benched gates lose money&rdquo;, because a benched
gate has no P&amp;L. Movement&nbsp;2 fires all six mechanically in their exact live config across
the whole of this week's captured tape &mdash; every fire counted, not just the ones near a big
move &mdash; which is the counterfactual this question needs:</p>

{value}

<p class="ln">The tournament's live book was {m(-58.5)} this week. Firing the same six gates
mechanically through the same tape is <strong>{m(mech_all)} on
{sum(len(bf[g]['fills']) for g in GAT)} fires</strong>. On that comparison the standdown plus the
router's benching is worth about <strong>{m(round(abs(mech_all + 58.5), 2))}</strong> this week,
and {m(abs(benched4))} of it is the four gates that never fired at all.</p>

{correction("★ AND HERE IS WHY THAT NUMBER IS AN ESTIMATE AND NOT A RESULT",
 "The mechanical sim has no operator. Two of the live gates' best trades this week were closed by "
 "hand at a price the machine would not have taken, and the sim rides every one of those to its "
 "own stop. It also has no queue, no partial fills and no thin-tape veto. Every one of those "
 "biases makes the sim look WORSE than the live desk would have been, which means "
 f"{m(round(abs(mech_all + 58.5), 2))} is an upper bound on the value of benching, not a "
 "measurement of it.",
 "The audit ran the same question on the fortnight with a different instrument and got a range "
 "from +$2,062 to −$673 — it straddles zero. <strong>So the correct statement is: the standdown "
 "was probably worth something this week, it was certainly not worth thousands, and no instrument "
 "on this desk can currently put a confident number on it.</strong> That is a measurement problem "
 "and it is on the BUILD card.")}

<h3>4 &middot; ★ THE STANDDOWN IS A ROUTER-LOCAL VARIABLE, AND SOMETHING ELSE ARMED A GATE
THROUGH IT</h3>

<p>On Friday at 14:03Z, with the tournament stood down and all six gates reading <code>off</code>,
<code>abs_veto_short</code> was switched <strong>on</strong>. The router did not do it. Here is the
sequence, unedited, out of the trial log:</p>

<pre>{chr(10).join(esc(s[:180]) for s in seq)}</pre>

<p class="ln"><code>open_hour_watch.py</code> is a second writer to <code>gate_switches.env</code>
with off&rarr;on authority and <strong>no awareness of the standdown at all</strong>. It saw a
confirmed break (ER 0.36, ATR 22, a new extreme) and did exactly what it was built to do, which is
the standing &ldquo;if a huge trend develops, arm immediately&rdquo; instruction. The problem is
not the watcher's logic. The problem is that a standing operator standdown lives in a variable
inside one process, and the other five writers to that file cannot see it.</p>

<p class="ln"><strong>The gate was live for 2 minutes 15 seconds</strong> and fired nothing, so
this cost $0 &mdash; by luck, not by design. The exposure is bounded by the router's 5-minute tick,
not by any guard. If the watcher had armed at 14:06 instead of 14:03 the gate would have been live
for the whole 5-minute window into the US open. <strong>The standdown needs to be a file the
writers check, not a variable one of them holds.</strong> That is a Saturday item.</p>

<p class="ln">The one genuinely reassuring thing here: the router caught it on its very next tick
and re-benched it, calling it &ldquo;housekeeping, not thrash&rdquo;. That is the behaviour you
want from the slow deliberate loop.</p>

<h3>5 &middot; The switch file's comment header is still being read as live instruction</h3>

<p><code>switch_notes()</code> splices the top 45 comment lines of <code>gate_switches.env</code>
into every router prompt, labelled ACTIVE. Nothing prunes them. Here is what is currently in
there:</p>

{carve_t}

<p class="ln">Five instructions, the oldest <strong>thirteen days old</strong>. The 19 August
operator bench says &ldquo;PINNED until 21:55Z&rdquo; &mdash; that deadline passed on Wednesday and
the line is still labelled ACTIVE. The 11 August one carries its own expiry (&ldquo;expires
16:00Z&rdquo;) and outlived it by eleven days. And the 9 August one is the dangerous one: it states
that <strong><code>abs_veto_short</code> IS ARMED BY DEFAULT</strong>, which directly contradicts
the standing operator standdown the router is currently enforcing. A carve-out comment never
expires, and revoking one in the ledger does not revoke it in the file.</p>

{correction("★ THE THREE DEAD ONES GOT ZERO MENTIONS — AND THAT IS NOT A FIX",
 f"Of the {len(wk):,} tick reasons this week, {carve_hits} restated one of these five lines. But "
 "the split is the whole point: the two LIVE-ish ones (Friday's watcher note and Wednesday's "
 f"operator bench) account for every single mention, and the three genuinely dead ones — 8, 11 "
 "and 13 days old — were restated <strong>zero times</strong>.",
 f"A zero-mention streak reads like the problem has gone away. It has not, and no streak ever can "
 f"show that it has. <strong>{at_cap:,} of the {len(wk):,} reasons this week are pinned at exactly "
 f"the 1,200-character cap</strong> — median length {sorted(lens)[len(lens) // 2]}, maximum "
 f"{max(lens)}. The mention rate is measuring how much room was left in the reason field after the "
 "live situation was described, and this week the live situation was a standdown, an Asia block "
 "and a four-lot carry, all of which are more urgent to narrate than a nine-day-old carve-out.",
 "Read the desk\'s six previous samples (42/54 → 49/49 → 9/40 → 0/48 → 3/48 → 9/48) and this "
 "one the same way: as readings of spare capacity, not as a trend. <strong>The only thing that "
 "closes this is deleting the lines.</strong> Any week the reason field is less crowded, a "
 "thirteen-day-old &lsquo;armed by default&rsquo; instruction is one tick away from being read "
 "as policy again.")}

<h3>6 &middot; ★ The router has spent {len(post)} consecutive ticks calling a four-lot position flat</h3>

<p>The day rider opened four lots long at 13:13Z on Friday and never closed them. Since that
moment the router has ticked {len(post)} times, and <strong>{len(flat)} of those ticks contain the
word &ldquo;flat&rdquo;</strong>. It is not lying and it is not broken: it reads
<code>core_health.json</code>, whose <code>flat</code> field is tournament-scoped, and the
tournament genuinely is flat. But the sentence a human reads is &ldquo;Flat, healthy=True,
halted=False&rdquo;, and it is being printed while the desk carries roughly $235,000 of notional
into a weekend gap.</p>

<p class="ln">The ticks are not silent about the rider &mdash; most of them name its closed rows,
&minus;$727, &minus;$268, &minus;$293.50 &mdash; and the last one describes it as
&ldquo;clientId 4, a desk I neither route nor bench&rdquo;. <strong>That is the failure in one
sentence.</strong> Citing what CLOSED and declining responsibility for what is OPEN is an
attribution that terminates in the wrong place. The trades table can only ever enumerate closed
rows, so it can never contradict a benign story; the venue position line can, and it says four.
&ldquo;Not mine to close&rdquo; obliges escalation, not dismissal.</p>

<h3>7 &middot; The two instruments that should have written this section</h3>

{table(["Rollup", "Newest file", "Days stale at this report", "What runs it"],
 [[("", "row-bad"), "<code>data/router_nightly/</code>", f"<code>{newest('router_nightly')}</code>",
   str((NOW.date() - dt.date(2026, 8, 14)).days), "<strong>Nothing. No timer.</strong>"],
  [("", "row-bad"), "<code>data/selector_nightly/</code>",
   f"<code>{newest('selector_nightly')}</code>",
   str((NOW.date() - dt.date(2026, 8, 18)).days), "<strong>Nothing. No timer.</strong>"]],
 numeric={2})}

<p class="ln">These are the files the standing weekly review is supposed to roll up: net router
value, leakage by regime, selector optimal-pick rate and regret. Neither has a timer, so both
simply stopped. <strong>There is no week-in-review to present</strong>, and rather than dress that
up, the honest version is the raw-log rebuild above. Two known defects also make the selector
rollup wrong when it does run: it has no <code>data_quality</code> filter, so quarantined rows
inflate its regret, and all four of its modes reprice at a hard-coded 1.0 stop multiple, which is
not what two of the live gates use.</p>

<h3>8 &middot; Verdict, and the Saturday actions</h3>

<p><strong>Is the router earning its keep? On this week, yes, and for a reason that is not about
its thresholds.</strong> It made {good} good calls and {bad} bad ones, it applied your 18:15Z bench
inside 90 seconds, and it was the only component on the box that noticed a gate had been armed
through your standdown. Its thresholds were not the lever this week and nothing here argues for
touching them. Its <em>clock</em> was not the lever either &mdash; there were only
{len(ch)} writes to be timed. <strong>The router's problem this week is not its judgement, it is
that it is surrounded by instruments that give it wrong inputs</strong>: a health flag that says
flat when the desk is long, a comment header full of expired instructions, a second writer that
can undo a standdown, and two rollups that quietly stopped.</p>

{disposition([
 ("Make the standdown a FILE that every writer checks", "LIVE",
  "It is currently a variable inside router_tick_durable.py. open_hour_watch.py armed a gate "
  "through it on Friday and the only reason it cost $0 is that the tape did not produce a signal "
  "in the 2m15s window. Saturday item."),
 ("Delete the expired carve-outs from gate_switches.env's header", "LIVE",
  "Three instructions are spliced into every prompt as ACTIVE; two of them expired days ago and "
  "one is eight days old. Nothing prunes them and no mention-rate streak closes it."),
 ("Point <code>core_health.flat</code> at the venue position", "LIVE",
  f"{len(flat)} of the last {len(post)} router ticks said 'flat' while the venue was long four "
  "lots. Either make the field desk-wide or rename it tournament_flat."),
 ("Change the router's thresholds or timing this week", "REFUTED",
  f"There were {len(ch)} switch writes all week, {zero} of them worth $0 by construction. There "
  "is no sample here to tune a threshold on, and tuning on this week would be fitting to a "
  "standdown."),
 ("Re-arm a gate on a lapse rather than a positive case", "REFUTED",
  "Named instance: 2026-08-19 15:35Z re-armed abs_veto_short 30 minutes after benching it, with "
  "no new evidence, straight into three stops for −$133. Third occasion on this gate."),
 ("Give router_watch narrow fast-BENCH authority", "PARKED",
  "The asymmetry argument still holds — a wrong bench is cheap, a wrong arm is expensive — but "
  "this week produced no measurable actuation-lag cost to justify the build, because the desk was "
  "stood down. Revive it with a lag number from a week the tournament actually trades."),
 ("Put a timer on router_nightly and selector_nightly", "LIVE",
  "Both stopped silently. A monitoring file that stops being written is worse than one that "
  "errors, because its absence looks like a quiet week."),
 ("Fix selector_nightly's two known defects before believing it again", "PARKED",
  "No data_quality filter (quarantined rows inflate regret) and a hard-coded 1.0 stop multiple "
  "for all four modes. Revive when both are fixed; until then do not quote its regret."),
])}
"""
    write("part2_6_router_review.html", doc.strip())
    print(f"\nticks {len(wk)} changes {len(ch)} good {good} bad {bad} churn {churn} zero {zero}")
    print(f"mech all {mech_all} benched4 {benched4}")
    print(f"post-entry ticks {len(post)} flat {len(flat)}  at-cap {at_cap}/{len(wk)}")
    print(f"carve-outs {len(carve)}")


if __name__ == "__main__":
    main()
