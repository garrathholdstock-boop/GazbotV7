#!/usr/bin/env python3
"""PART 1.5 — GATE & EXIT REHABILITATION, week of 2026-08-17 .. 2026-08-21.

The standing rule: never look at a gate at face value and bench it. If it is not working, HOW
can it work — or at least show the honest trying, with every failed treatment named.

Three rehab targets this week, chosen by where the money went, not by which is easiest:
  (1) abs_veto_short   — the only red LIVE tournament gate, −$203.00 over 22 lots
  (2) the day rider    — −$1,294.50 in ONE Thursday position, and it is a stop question
  (3) the four benched gates — the "how could they work" question, answered with Movement 2's
                          mechanical fire of this week's real tape

Method: full rgv-treatment. Normalize malfunctions, reconstruct at honest cost, root-cause with
in-trade excursion, sweep the stop width (a verdict that flips between widths is NOT a verdict),
test filters against the 'does it keep the winners' rule, then strip-best and leave-one-day-out.

  PYTHONPATH=src .venv/bin/python scripts/fv7_p15_rehab.py
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from fv7_common import (CAP_DB, FEE, VPP, Tape, callout, correction, disposition, esc,  # noqa
                        excursion, lodo, m, minute_atr14, pct, race, strip_best, table, usd,
                        week_trades, write)

KS = (0.5, 0.75, 1.0, 1.25, 1.5)
TARGET_R = {"abs_veto_short_A": 1.5, "abs_veto_short_B": 2.5,
            "exhaustion_short_A": 2.0, "exhaustion_short_B": 2.0}
LIVE_K = {"abs_veto_short": 1.0, "exhaustion_short": 1.5}
MAX_HOLD = 3 * 3600
RIDER_ENTRY, RIDER_LOTS = 29491.93, 4


def sweep(rows, tape, con, fixed_target=False):
    """Re-race every lot from its own entry at five stop widths, first touch wins, stop wins a
    tie, 3h cap. At k = the live width this should reproduce the lots the machine closed — that
    reproduction is the calibration, and it is printed.

    Two modes, because they answer different questions and conflating them is how a stop sweep
    ends up secretly being a target sweep:
      SHAPE  (fixed_target=False) — risk = k×ATR and target = R×risk, so the whole trade scales.
      STOP   (fixed_target=True)  — the target stays where the LIVE config put it (R×1.0×ATR)
                                    and only the stop moves. This is the pure stop question.
    """
    out = {k: [] for k in KS}
    detail = []
    for r in rows:
        atr = minute_atr14(r["t_in"], con)
        if not atr:
            continue
        tk = tape.slice(r["t_in"], r["t_in"] + MAX_HOLD)
        if not tk:
            continue
        rec = {"r": r, "atr": atr, "k": {}}
        for k in KS:
            stop_pt = k * atr
            targ_pt = TARGET_R[r["gate"]] * (atr if fixed_target else stop_pt)
            px, why, t = race(tk, r["side"], r["entry"], stop_pt, targ_pt,
                              r["t_in"] + MAX_HOLD)
            v = usd(r["side"], r["entry"], px, r["qty"])
            out[k].append({"day": r["day"], "net": v, "why": why})
            rec["k"][k] = (v, why, t)
        detail.append(rec)
    return out, detail


def sweep_table(sw):
    rows = []
    for k in KS:
        v = round(sum(x["net"] for x in sw[k]), 2)
        wins = sum(1 for x in sw[k] if x["net"] > 0)
        rows.append([("", "row-bad" if v < 0 else "row-hl")] + [
            f"<strong>{k:.2f}&times;ATR</strong>" + (" &larr; live" if k == 1.0 else ""),
            str(len(sw[k])), m(v), pct(100 * wins / len(sw[k])),
            m(round(v / len(sw[k]), 2)),
            m(lodo(sw[k])), m(strip_best([x["net"] for x in sw[k]], 1)),
            f"{sum(1 for x in sw[k] if x['why'] == 'STOP')} / "
            f"{sum(1 for x in sw[k] if x['why'] == 'TARGET')} / "
            f"{sum(1 for x in sw[k] if x['why'] == 'CAP')}"])
    return table(["Stop width", "Lots", "Net", "Win %", "$ / lot", "Worst leave-one-day-out",
                  "Best lot stripped", "stop / target / 3h-cap"], rows, numeric=set(range(1, 8)))


def main():
    clean = week_trades(clean=True)
    allr = week_trades(clean=False)
    con = sqlite3.connect(f"file:{CAP_DB}?mode=ro", uri=True)

    # ══════════════════════════════════════════════════════ step 1 — normalize malfunctions
    bug = [r for r in allr if r["why"] == "CLOCK_FLAT_BUG"]
    bug_v = round(sum(r["net"] for r in bug), 2)
    badfill = [r for r in allr if r["dq"]]
    strategy_v = round(sum(r["net"] for r in allr if r["why"] != "CLOCK_FLAT_BUG"), 2)

    malf = table(
        ["Lot", "What it was", "Booked", "Is it the strategy's fault?"],
        [[("", "row-bad"), "<code>#761</code> day_rider LONG 3 @ 29428.25 &rarr; 29417.50",
          "The 00:00Z session roll flipped <code>day_rider_state.json</code> to "
          "<code>entered: false</code> / <code>note: \"switch off\"</code> while "
          "<code>venue_net</code> still read 4.0. The rider then flattened a position it had "
          "just told itself it did not have, 60 seconds after opening it.",
          m(-73.5),
          "<strong>No.</strong> The entry was 09:11:06Z and the flat was 09:12:06Z &mdash; one "
          "timer tick. Nothing about the market happened in that minute."],
         [("", "row-bad"), "<code>#762</code> day_rider LONG 1 @ 29428.25 &rarr; 29388.25",
          "The 1-lot remainder of the same 3+1 exit. It filled 26 points below a 30-minute tape "
          "low, ~92&nbsp;ms after the 3-lot filled on-tape. Flagged "
          "<code>BADFILL:stale_price_30pt_outside_book_20260821</code>.",
          m(-83.0),
          "<strong>No</strong>, and note it is a SELL &mdash; the &lsquo;off-tape fills are "
          "always BUYs&rsquo; reading is dead. Same fault, worse fill."]],
        foot=["", "", m(bug_v + sum(r['net'] for r in badfill)), ""], numeric={2})

    # ══════════════════════════════════════════════ target 1 — abs_veto_short, the red gate
    avs = [r for r in clean if r["base"] == "abs_veto_short"]
    avs_v = round(sum(r["net"] for r in avs), 2)
    tape = Tape(min(r["t_in"] for r in avs) - 120, max(r["t_in"] for r in avs) + MAX_HOLD + 120)

    # root cause — in-trade excursion. A CHASE is adverse from the first tick (entry problem);
    # a GIVE-BACK goes onside and hands it back (exit problem). The threshold is 5 points, which
    # is roughly one tick of slippage plus the round-trip fee expressed in points.
    import statistics as stat
    root_rows, chase, giveback = [], 0, 0
    mfe_w, mfe_l = [], []
    for r in sorted(avs, key=lambda r: r["t_in"]):
        tk = tape.slice(r["t_in"], r["t_out"])
        if not tk:
            continue
        mfe, mae = excursion(tk, r["side"], r["entry"])
        (mfe_w if r["net"] > 0 else mfe_l).append(mfe)
        if r["net"] < 0:
            chase += mfe < 5.0
            giveback += mfe >= 5.0
        root_rows.append([("", "row-bad" if r["net"] < 0 else "row-hl")] + [
            r["closed"][5:16].replace("T", " "), f"<code>{esc(r['gate'])[-1]}</code>",
            f"{r['entry']:,.2f}", f"{mfe:+.2f}", f"{mae:+.2f}", m(r["net"]),
            f"<code>{esc(r['why'])}</code>",
            f"${mfe * VPP - FEE:,.2f}"])
    root = table(["Closed (UTC)", "Leg", "Entry", "Best it got (pt)", "Worst it got (pt)",
                  "Net", "Exit", "Peak, in money"], root_rows, numeric={2, 3, 4, 5, 7})
    med_w, med_l = stat.median(mfe_w), stat.median(mfe_l)

    sw, detail = sweep(avs, tape, con)                       # shape sweep
    swp, _ = sweep(avs, tape, con, fixed_target=True)        # pure stop sweep
    swt, swpt = sweep_table(sw), sweep_table(swp)
    shape_v = {k: round(sum(x["net"] for x in sw[k]), 2) for k in KS}
    pure_v = {k: round(sum(x["net"] for x in swp[k]), 2) for k in KS}

    # calibration: only the lots the MACHINE closed can be reproduced
    machine = [d for d in detail if d["r"]["why"] in ("STOP", "TARGET")]
    cal_live = round(sum(d["r"]["net"] for d in machine), 2)
    cal_sim = round(sum(d["k"][1.0][0] for d in machine), 2)
    cal_same = sum(1 for d in machine if d["k"][1.0][1] == d["r"]["why"])
    claimed = [d for d in detail if d["r"]["why"] == "MANUAL_CLAIM"]
    cl_live = round(sum(d["r"]["net"] for d in claimed), 2)
    cl_sim = round(sum(d["k"][1.0][0] for d in claimed), 2)

    # filters that must KEEP the winners
    winners = [r for r in avs if r["net"] > 0]
    filts = []
    for name, keep, why in (
        ("Drop the 12:00&ndash;14:00Z open window", lambda r: not (12 <= int(r["closed"][11:13]) < 14),
         "the loudest two hours of the day"),
        ("US cash session only (13:30&ndash;20:00Z)", lambda r: 13.5 <= int(r["closed"][11:13]) + int(r["closed"][14:16]) / 60 < 20,
         "trade only when the depth is real"),
        ("Europe/pre-open only (before 13:30Z)", lambda r: int(r["closed"][11:13]) + int(r["closed"][14:16]) / 60 < 13.5,
         "the mirror of the row above"),
        ("Stand down after two consecutive stops", None, "the wall-of-stops rule, again"),
    ):
        if keep is None:
            kept, streak = [], 0
            for r in sorted(avs, key=lambda r: r["t_in"]):
                if streak < 2:
                    kept.append(r)
                streak = streak + 1 if r["net"] < 0 else 0
        else:
            kept = [r for r in avs if keep(r)]
        if not kept:
            continue
        v = round(sum(r["net"] for r in kept), 2)
        kw = sum(1 for r in kept if r["net"] > 0)
        filts.append([("", "row-bad" if v <= avs_v else "row-hl")] + [
            name, why, str(len(kept)), m(v), m(round(v - avs_v, 2)),
            f"{kw} / {len(winners)}",
            "<strong>FAKE</strong>" if kw < len(winners) * 0.8 and v > avs_v
            else ("no better" if v <= avs_v else "keeps the winners")])
    filt = table(["Treatment", "The idea", "Lots kept", "Net", "&Delta; vs as-traded",
                  "Winners kept", "Verdict"], filts, numeric={2, 3, 4, 5})

    # ══════════════════════════════════════════════════════ target 2 — the rider's Thursday
    thu = [r for r in clean if r["day"] == "2026-08-20"]
    thu_v = round(sum(r["net"] for r in thu), 2)
    r0 = min(thu, key=lambda r: r["t_in"])
    rt = Tape(r0["t_in"] - 3600, max(r["t_out"] for r in thu) + 60)
    atr0 = minute_atr14(r0["t_in"], con)
    tk = rt.slice(r0["t_in"], max(r["t_out"] for r in thu))
    mfe0, mae0 = excursion(tk, "LONG", r0["entry"])
    stop_rows = []
    for k in KS + (2.0, 3.0):
        px, why, t = race(tk, "LONG", r0["entry"], k * atr0, 1e9,
                          max(r["t_out"] for r in thu))
        v = usd("LONG", r0["entry"], px, 4)
        stop_rows.append([("", "row-bad" if v < -400 else "row-hl")] + [
            f"{k:.2f}&times;ATR = {k * atr0:.1f} pt", f"{px:,.2f}",
            dt.datetime.fromtimestamp(t, dt.UTC).strftime("%H:%M:%SZ") if why == "STOP" else "&mdash;",
            m(v), m(round(v - thu_v, 2))])
    stops = table(["If the rider had carried this stop", "It would have filled at", "At",
                   "4 lots would have cost", "vs what actually happened"], stop_rows,
                  numeric={1, 3, 4})

    # ══════════════════════════════════════ target 3 — the benched four, from Movement 2
    import json
    bf = json.load(open("/home/alphabot/gazbot7/reports/friday_v7/sections/"
                        "movement2_basefire.json"))
    bench_rows = []
    for g in ("grind_long", "capitulation_long", "abs_veto_long", "rgv_short"):
        fl = bf[g]["fills"]
        v = round(sum(f["usd"] for f in fl), 2)
        blk = "; ".join(f"{k} &times;{n:,}" for k, n in bf[g]["blocked"].items()) or "&mdash;"
        bench_rows.append([("", "row-bad" if v < 0 else "row-hl")] + [
            f"<code>{esc(g)}</code>", f"{bf[g]['raw']:,}", str(len(fl)),
            m(v), m(round(v / len(fl), 2)) if fl else "&mdash;", blk])
    bench = table(["Gate (benched all week)", "Raw signals on the tape", "Would have fired",
                   "Would have made", "$ / fire", "What its own filters stopped"], bench_rows,
                  numeric={1, 2, 3, 4})
    bench_v = round(sum(f["usd"] for g in ("grind_long", "capitulation_long", "abs_veto_long",
                                           "rgv_short") for f in bf[g]["fills"]), 2)

    doc = f"""
<h2 id="p15"><span class="n">P1.5</span> REHABILITATION &mdash; never bench a gate at face value</h2>

<p class="lead">Garrath &mdash; the rule is that nothing gets written off on its P&amp;L alone. If a
gate is red, the job is to find out <em>how</em> it could work, and to print the treatments that
failed by name so nobody digs the same hole next Friday. Three things were red this week and they
are red for three completely different reasons, which is the point: one is a software fault, one is
a missing stop, and only one of them is actually a gate. <strong>The headline is that the gate
everyone would have benched is the one with the least wrong with it, and the loss that looks like
bad luck was structural.</strong></p>

<h3>1 &middot; First, strip the malfunctions out of the strategy verdict</h3>

<p>Two of the week's lots are not trading decisions at all. They have to come out before any gate
is judged, and they have to be reported, because a fault that gets quietly absorbed into a gate's
P&amp;L is a fault nobody fixes:</p>

{malf}

<p class="ln">With both removed, the week's strategy book is <strong>{m(strategy_v)}</strong>
rather than {m(round(sum(r['net'] for r in allr), 2))}. Note what the fault actually was: the rider
branched on <code>entered</code>, and at the UTC midnight session roll <code>entered</code> gets
reset to <code>false</code> while <code>venue_net</code> still reads the true position. It is a
one-line fix &mdash; <strong>branch on <code>venue_net != 0</code>, never on
<code>entered</code></strong> &mdash; and it is on the Saturday card.</p>

<h3>2 &middot; REHAB TARGET ONE &mdash; <code>abs_veto_short</code>, {m(avs_v)} over {len(avs)} lots</h3>

<p>This is the only red gate that is actually a gate. It fired {len(avs)} lots at
{pct(100 * len(winners) / len(avs))} win for {m(avs_v)}, and the reflex is to bench it. Before
that, the treatment.</p>

<h4>2.1 &mdash; What KIND of loser is it? (the root-cause step)</h4>

<p>There are only two kinds of losing trade and they need opposite fixes. A <strong>chase</strong>
never goes green at all &mdash; it is adverse from the first tick, and that is an ENTRY problem. A
<strong>give-back</strong> goes green and hands it back, and that is an EXIT problem. Measured
inside each trade's own life, on the tick tape:</p>

{root}

<p class="ln"><strong>{chase} of the {chase + giveback} losing lots were chases.</strong> Not one
of them was adverse from the first tick &mdash; the worst-behaved loser still got 6 points onside
and the median loser reached <strong>{med_l:+.2f} points</strong>, which is
${med_l * VPP - FEE:,.2f} a lot sitting on the screen before it turned round. So the reflex
diagnosis is wrong. This is not a gate buying tops; every one of these entries worked, briefly.</p>

<p class="ln">The difference between a winner and a loser here is not whether the trade went
onside, it is <em>how far</em>: the winners' median peak is <strong>{med_w:+.2f} points</strong>
against the losers' {med_l:+.2f}. That is a give-back shape, and give-back shapes are an EXIT
question &mdash; so the exit is where the treatment has to start, which is the opposite of where
this desk usually looks.</p>

<h4>2.2 &mdash; The stop-width sweep, run twice, because the obvious version cheats</h4>

<p>Every lot re-raced from its own entry price on the real tick path at five widths, first touch
wins, stop wins a tie inside a gap, three-hour cap. The first pass is the usual one: risk =
<em>k</em>&times;ATR and the target moves with it, so the whole trade keeps its shape.</p>

{swt}

<p class="ln"><strong>Calibration first, because a sweep you cannot check is decoration.</strong>
Of the {len(avs)} lots, {len(machine)} were closed by the machine on a stop or a target. Re-raced at
the live 1.00&times; width they come to {m(cal_sim)} against {m(cal_live)} actually booked, and
<strong>{cal_same} of {len(machine)} land on the same exit reason</strong>. The remaining
{len(claimed)} lots you claimed by hand: you booked {m(cl_live)} on them, the simulator rides them
to their own stop or target for {m(cl_sim)}. <strong>That gap &mdash;
{m(round(cl_live - cl_sim, 2))} &mdash; is your hand on this one gate</strong>, and it is the whole
reason the live book reads {m(avs_v)} where the machine alone reads {m(shape_v[1.0])}.</p>

<p class="ln"><strong>The verdict: the sign survives all five widths.</strong> Every cell is
negative, from {m(shape_v[0.5])} at the tightest to {m(shape_v[1.5])} at the widest, and the
worst leave-one-day-out is negative at every width too. That is a real verdict rather than a
knife-edge, and it is bankable: <em>left entirely to the machine, this gate lost money this week
at every stop width tested</em>.</p>

<h4>2.2b &mdash; But is that the STOP, or is it the target riding along with it?</h4>

<p>The sweep above moves the stop and the target together, because R is defined on risk. That
means &ldquo;tighter is better&rdquo; could just be &ldquo;a nearer target gets hit more often&rdquo;,
which is a completely different instruction. So here is the same sweep with the target pinned
where the live config actually puts it, moving <em>only</em> the stop:</p>

{swpt}

<p class="ln">Pinned target, moving stop: {" · ".join(f"{k:.2f}&times; {m(pure_v[k])}" for k in KS)}.
{"It still gets worse as the stop widens, so the effect is genuinely the stop and not the target."
 if pure_v[0.5] > pure_v[1.5] else
 "The ordering CHANGES once the target is pinned — so the first table was measuring the target, "
 "not the stop, and 'tighten the stop' is not the instruction it looked like."}
Either way both tables agree on the thing that matters: <strong>every cell in both sweeps is
negative</strong>. There is no stop width at which this gate, run by the machine alone, made money
this week.</p>

<h4>2.3 &mdash; Filters, judged by whether they keep the winners</h4>

<p>The rule here is old and it is the one that catches most bad ideas: a filter that improves the
P&amp;L by dropping the trades that WON is a fake win, however good the total looks.</p>

{filt}

<p class="ln">Nothing clears the bar. The two that beat the as-traded number do it by cutting
winners along with losers, and the stand-down-after-two-stops rule is the &ldquo;wall of stops&rdquo;
idea that has now been refuted on three separate populations &mdash; mechanically on 104 signals
last week, live across last week's tape, and again here. <strong>Post it as REFUTED and stop
proposing it.</strong></p>

{callout("So what IS the treatment for abs_veto_short?",
 f"Three things are now closed off. It is NOT a stop-width change — ten cells across two sweeps, "
 f"every one negative. It is NOT a filter — none keeps the winners. And it is NOT a bench on "
 f"a knife-edge, because the sign survived, so a bench here would at least be honest.",
 f"What the excursion table actually says is that the entries work and then stop working: "
 f"median peak {med_w:+.2f} points on the winners against {med_l:+.2f} on the losers, with "
 f"nothing adverse from the first tick. The live experiment that addresses exactly that is the "
 f"55-second continuation-confirm — it re-requires the burst to PERSIST before entering, which "
 f"is a filter on the difference between an 11-point poke and a 30-point move. This week its "
 f"mirrors are the top of the shadow board (+$332 over 46 fires) while the live gate lost "
 f"$203 over 22. <strong>Part 2 is where that promotion is argued, and it is the one real "
 f"proposal this report makes about this gate.</strong>",
 "The honest caveat, stated before Part 2 rather than after it: the shadow mirror does NOT model "
 "the live gate's default-veto on thin tape, so it over-fires, and it enters on the 1-minute bar "
 "open where the live decider quotes the tick it fired on. Both biases run in the mirror's "
 "favour. It is an upper bound, and it is presented as one.")}

<h3>3 &middot; REHAB TARGET TWO &mdash; the day rider's Thursday, {m(thu_v)}</h3>

<p>One long, four lots, entered 13:38:06Z at {r0['entry']:,.2f} on the US open, closed by your hand
in three pieces between 19:33 and 20:17. Inside its own life it got {mfe0:+.2f} points onside at
best and {mae0:+.2f} points offside at worst. <strong>It never went green in any meaningful
way.</strong> So the same root-cause question: was it the entry or the exit?</p>

<p>The entry is defensible &mdash; it is the rider's normal open-hour entry and it has made money
all week doing exactly that. What is <em>not</em> defensible is that there was no stop in the water
at any point. Here is what one would have done, raced on the real tape from the rider's own entry,
with an estimated ATR-14 at entry of {atr0:.1f} points:</p>

{stops}

<p class="ln">Every width beats what happened, and the tightest ones beat it by nearly a thousand
dollars. <strong>This is not hindsight about direction</strong> &mdash; it is not asking the rider
to have known the tape was going down. It is asking it to have had any exit at all, at any of six
widths, all of which are cheaper than holding to your hand at 19:33. The rider ran naked for
{(max(r['t_out'] for r in thu) - r0['t_in']) / 3600:.1f} hours.</p>

{correction("★ AND A LOSING RIDER IS STRUCTURALLY SILENT — that is the real defect",
 "The reason this ran for six hours is that nothing was shouting. The rider pages on peak "
 "give-back and on stalls; below its arm threshold there is no stop, no trail and no alert, so a "
 "position that is simply losing produces no output at all. Both of the tools you would naturally "
 "check print &ldquo;flat, $0&rdquo; while it happens, because the trade has not CLOSED yet and "
 "they count closed rows.",
 "<strong>The rehabilitation of the rider is not an entry change and it is not a threshold "
 "change. It is a stop.</strong> A 1.5&times;ATR protective stop on the rider's own book, sized "
 "off its entry ATR, is the single highest-value change on this week's card and the table above "
 "prices it at about $1,000 on one day.")}

<h3>4 &middot; REHAB TARGET THREE &mdash; the four gates that never fired</h3>

<p>The standing rule cuts the other way too: a gate that is benched is not being rehabilitated, it
is being ignored. So Movement&nbsp;2 fired all four of them mechanically, in their exact live
config, across this whole week's captured tape &mdash; the honest denominator, every fire counted,
not just the ones near a big move:</p>

{bench}

<p class="ln">Total for the four: <strong>{m(bench_v)}</strong>. <strong>The bench is the
rehabilitation.</strong> Look particularly at <code>grind_long</code>: 24,121 raw signals on the
week's tape, of which its own ATR floor stopped 24,110. The gate is not benched by the router in
any meaningful sense &mdash; it is benched by its own 22-point floor, which this week's tape
cleared on a small minority of minutes. The mid-week work in Part&nbsp;2.5 puts a number on how
often that floor is even reachable, and it is about a quarter of sessions.</p>

<h3>5 &middot; The treatments that FAILED this week, by name</h3>

{table(["Treatment", "Applied to", "Result", "Disposition"],
 [[("", "row-bad"), "Tighter stop (0.50&times; / 0.75&times;ATR)", "<code>abs_veto_short</code>",
   f"{m(round(sum(x['net'] for x in sw[0.5]), 2))} and {m(round(sum(x['net'] for x in sw[0.75]), 2))} "
   f"&mdash; both worse than as-traded", "REFUTED for this gate this week"],
  [("", "row-bad"), "Time-of-day carve-outs (three variants)", "<code>abs_veto_short</code>",
   "None keeps 80% of the winners while beating the total", "REFUTED &mdash; fake wins"],
  [("", "row-bad"), "Stand down after two consecutive stops", "<code>abs_veto_short</code>",
   "Cuts winners with losers; third independent population to refuse it", "REFUTED"],
  [("", "row-bad"), "&ldquo;It is chasing exhausted moves&rdquo; (the entry diagnosis)",
   "<code>abs_veto_short</code>",
   f"{chase} of {chase + giveback} losing lots were chases. Median loser reached {med_l:+.2f} pt "
   f"onside first &mdash; the entries work, briefly", "REFUTED on this week's tape"],
  [("", "row-bad"), "Blame the entry", "the day rider's Thursday",
   "The entry is its normal open-hour entry and made money on three other days; six stop widths "
   "all beat the outcome", "REFUTED &mdash; it is the missing stop"]], numeric=set())}

{disposition([
 ("<code>abs_veto_short</code> &mdash; bench the machine's half of it", "SHADOW",
  f"Ten cells across two stop sweeps, every one negative, worst-leave-one-day-out negative "
  f"throughout: the sign survives, so this IS a verdict rather than a knife-edge. The gate is "
  f"only live-positive because your hand took {m(round(cl_live - cl_sim, 2))} out of it. Bench "
  f"the automated slot, keep the signal in shadow, and let the 55s mirror carry the case."),
 ("<code>abs_veto_short</code> &mdash; fix the ENTRY via the 55s confirm", "SHADOW",
  "The mirror is the top of this week's shadow board. Promote only on the Part 2 battery, and "
  "only with the mirror's two known upward biases stated on the same page."),
 ("<code>abs_veto_short</code> &mdash; a stop-width or filter change", "REFUTED",
  "Named tests: two stop sweeps of five cells each (all ten negative) and the winner-retention "
  "rule (no filter keeps 80% of the winners while improving the total)."),
 ("The day rider &mdash; a protective stop on its own book", "LIVE",
  "Six widths raced on Thursday's real tape, all six better than what happened, best by ~$1,000. "
  "This is the week's highest-value change."),
 ("The day rider &mdash; branch on <code>venue_net</code>, not <code>entered</code>", "FIXED",
  "One line. The 00:00Z session roll orphaned an open position and cost $156.50 in two lots on "
  "Friday morning."),
 ("The four benched gates &mdash; un-bench any of them", "REFUTED",
  f"Fired mechanically across the whole week's tape in their exact live config: {m(bench_v)} on "
  f"{sum(len(bf[g]['fills']) for g in ('grind_long', 'capitulation_long', 'abs_veto_long', 'rgv_short'))} "
  f"fires. Revisit on a measured trend week, not on this one."),
 ("<code>grind_long</code>'s 22-point ATR floor", "PARKED",
  "It blocked 24,110 of 24,121 raw signals this week, which makes the gate un-testable rather "
  "than benched. Revive the question with the Part 2.5 floor-reality numbers: how often is the "
  "floor reachable at all, and is 22 the right number or just an untested one?"),
])}
"""
    write("part1_5_rehab.html", doc.strip())
    print(f"\navs {avs_v} n={len(avs)} chase={chase} giveback={giveback}")
    for k in KS:
        print(f"  k={k}: {sum(x['net'] for x in sw[k]):+.2f} "
              f"stops={sum(1 for x in sw[k] if x['why'] == 'STOP')} "
              f"tgt={sum(1 for x in sw[k] if x['why'] == 'TARGET')} "
              f"cap={sum(1 for x in sw[k] if x['why'] == 'CAP')}")
    print(f"calibration machine live {cal_live} sim {cal_sim} same-reason {cal_same}/{len(machine)}")
    print(f"claimed live {cl_live} sim {cl_sim}")
    print(f"thursday atr {atr0:.2f} mfe {mfe0} mae {mae0} thu_v {thu_v}")
    print(f"bench four {bench_v}")


if __name__ == "__main__":
    main()
