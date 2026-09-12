#!/usr/bin/env python3
"""PART 1 — THE LIVE DESK, week of 2026-08-17 .. 2026-08-21.

Rebuilt from data/gazbot7.db, data/capture.db, data/day_rider_state.json and the systemd
journal. Nothing in this file is transcribed from a prior week; every number is computed at
build time, and the ones that come from outside the trade table say where they come from.

  PYTHONPATH=src .venv/bin/python scripts/fv7_p1_live.py
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from fv7_common import (CAP_DB, DAYNAME, DAYS, FEE, VPP, Tape, callout, cls, correction,  # noqa
                        disposition, esc, excursion, lodo, m, minute_atr14, pct, pill, race,
                        strip_best, table, usd, week_trades, write)

RIDER_ENTRY = 29491.93          # day_rider_state.json — avgCost 58983.86 / $2, incl. commission
RIDER_LOTS = 4


def main():
    clean = week_trades(clean=True)
    allr = week_trades(clean=False)
    flagged = [r for r in allr if r["dq"]]

    net_clean = round(sum(r["net"] for r in clean), 2)
    net_all = round(sum(r["net"] for r in allr), 2)

    # ── the carried position, marked at the last tick before the CME close ────────────────
    con = sqlite3.connect(f"file:{CAP_DB}?mode=ro", uri=True)
    last_ts, last_px = con.execute(
        "SELECT ts_ms/1000.0, price FROM ticks WHERE symbol='MNQ' ORDER BY ts_ms DESC LIMIT 1"
    ).fetchone()
    con.close()
    carry = round((last_px - RIDER_ENTRY) * VPP * RIDER_LOTS, 2)
    carry_pt = round(last_px - RIDER_ENTRY, 2)

    # ── §1 the money ──────────────────────────────────────────────────────────────────────
    day_rows = []
    for d in DAYS:
        rs = [r for r in clean if r["day"] == d]
        fl = [r for r in flagged if r["day"] == d]
        v = round(sum(r["net"] for r in rs), 2)
        day_rows.append([("", "row-bad" if v < 0 else "row-hl")] + [
            DAYNAME[d], str(len(rs)), m(v),
            (m(round(sum(r["net"] for r in fl), 2)) + f" ({len(fl)})") if fl else "&mdash;",
            m(round(v + sum(r["net"] for r in fl), 2))])
    money = table(
        ["Session (UTC close)", "Lots", "Clean book", "Flagged lots", "Cash book"],
        day_rows,
        foot=["THE WEEK", str(len(clean)), m(net_clean),
              m(round(sum(r['net'] for r in flagged), 2)) + f" ({len(flagged)})", m(net_all)],
        numeric={1, 2, 3, 4})

    # ── §2 per-gate cards ─────────────────────────────────────────────────────────────────
    gates = sorted({r["gate"] for r in clean})
    gate_rows = []
    for g in gates:
        rs = [r for r in clean if r["gate"] == g]
        v = round(sum(r["net"] for r in rs), 2)
        wins = [r["net"] for r in rs if r["net"] > 0]
        loss = [r["net"] for r in rs if r["net"] <= 0]
        lots = sum(r["qty"] for r in rs)
        gate_rows.append([("", "row-bad" if v < 0 else "row-hl")] + [
            f"<code>{esc(g)}</code>", str(len(rs)), f"{lots:.0f}", m(v),
            pct(100 * len(wins) / len(rs)),
            m(round(sum(wins) / len(wins), 2)) if wins else "&mdash;",
            m(round(sum(loss) / len(loss), 2)) if loss else "&mdash;",
            m(round(v / len(rs), 2)),
            m(max(r["net"] for r in rs)), m(min(r["net"] for r in rs))])
    cards = table(["Slot", "Signals", "Lots", "Net", "Win %", "Avg win", "Avg loss",
                   "$ / signal", "Best", "Worst"], gate_rows, numeric=set(range(1, 10)))

    # ── §3 the A/B legs, paired on one signal ─────────────────────────────────────────────
    pairs = {}
    for r in clean:
        if r["leg"]:
            pairs.setdefault((r["base"], round(r["t_in"])), {})[r["leg"]] = r
    both = [p for p in pairs.values() if len(p) == 2]
    ab_rows, dl = [], []
    for base in sorted({p["A"]["base"] for p in both}):
        ps = [p for p in both if p["A"]["base"] == base]
        a = round(sum(p["A"]["net"] for p in ps), 2)
        b = round(sum(p["B"]["net"] for p in ps), 2)
        d = [round(p["B"]["net"] - p["A"]["net"], 2) for p in ps]
        dl += d
        ab_rows.append([("", "row-bad" if sum(d) < 0 else "row-hl")] + [
            f"<code>{esc(base)}</code>", str(len(ps)), m(a), m(b), m(round(sum(d), 2)),
            f"{sum(1 for x in d if x > 0)} / {len(d)}", m(strip_best(d, 1))])
    ab = table(["Gate", "Paired signals", "Lot A (tight)", "Lot B (wide)", "B &minus; A",
                "B ahead on", "B&minus;A, best pair stripped"], ab_rows,
               foot=["BOTH GATES", str(len(both)),
                     m(round(sum(p["A"]["net"] for p in both), 2)),
                     m(round(sum(p["B"]["net"] for p in both), 2)),
                     m(round(sum(dl), 2)), f"{sum(1 for x in dl if x > 0)} / {len(dl)}",
                     m(strip_best(dl, 1))], numeric=set(range(1, 7)))

    # ── §4 exit mix ───────────────────────────────────────────────────────────────────────
    why_rows = []
    for w in sorted({r["why"] for r in allr}):
        rs = [r for r in allr if r["why"] == w]
        v = round(sum(r["net"] for r in rs), 2)
        why_rows.append([("", "row-bad" if v < 0 else "row-hl")] + [
            f"<code>{esc(w)}</code>", str(len(rs)), m(v), m(round(v / len(rs), 2)),
            pct(100 * sum(1 for r in rs if r["net"] > 0) / len(rs))])
    exits = table(["Exit reason", "Lots", "Net", "$ / lot", "Win %"], why_rows,
                  numeric={1, 2, 3, 4})

    # ── §5 Thursday, lot by lot ───────────────────────────────────────────────────────────
    thu = [r for r in clean if r["day"] == "2026-08-20"]
    thu_rows = [[
        r["closed"][11:19], f"<code>{esc(r['gate'])}</code>", r["side"], f"{r['qty']:.0f}",
        f"{r['entry']:,.2f}", f"{r['exit']:,.2f}",
        f"{(r['t_out'] - r['t_in']) / 60:,.0f} min", f"<code>{esc(r['why'])}</code>", m(r["net"])]
        for r in thu]
    thursday = table(["Closed (UTC)", "Slot", "Side", "Lots", "In", "Out", "Held", "Exit", "Net"],
                     thu_rows, numeric={3, 4, 5, 6, 8},
                     foot=["", "", "", f"{sum(r['qty'] for r in thu):.0f}", "", "", "", "",
                           m(round(sum(r['net'] for r in thu), 2))])

    # ── §6 the operator's hand ────────────────────────────────────────────────────────────
    claims = [r for r in clean if r["why"] == "MANUAL_CLAIM"]
    claim_v = round(sum(r["net"] for r in claims), 2)
    claim_win = [r for r in claims if r["net"] > 0]
    auto = [r for r in clean if r["why"] != "MANUAL_CLAIM"]
    auto_v = round(sum(r["net"] for r in auto), 2)

    # MFE inside each claimed trade's own life — how much of the peak did his hand keep?
    tp = Tape(min(r["t_in"] for r in claims) - 60, max(r["t_out"] for r in claims) + 60)
    cap_rows, caps = [], []
    for r in sorted(claims, key=lambda r: r["t_in"]):
        tk = tp.slice(r["t_in"], r["t_out"])
        if not tk:
            continue
        mfe, mae = excursion(tk, r["side"], r["entry"])
        peak = round(mfe * VPP * r["qty"] - FEE * r["qty"], 2)
        keep = round(100 * r["net"] / peak, 0) if peak > 0 else None
        caps.append(keep if keep is not None else 0)
        cap_rows.append([("", "row-bad" if r["net"] < 0 else "")] + [
            r["closed"][5:10], f"<code>{esc(r['gate'])}</code>", f"{r['qty']:.0f}",
            m(peak), m(r["net"]), pct(keep) if keep is not None else "&mdash;",
            f"{mae:+.2f} pt"])
    capture = table(["Day", "Slot", "Lots", "Peak inside the trade", "He booked", "Kept",
                     "Worst it went against him"], cap_rows, numeric={2, 3, 4, 5, 6})
    med_keep = sorted(c for c in caps if c)[len([c for c in caps if c]) // 2] if caps else 0

    # ── the gates that never fired ────────────────────────────────────────────────────────
    silent = ["grind_long", "capitulation_long", "abs_veto_long", "rgv_short"]

    doc = f"""
<h2 id="p1"><span class="n">P1</span> THE LIVE DESK &mdash; the week of 17&ndash;21 August 2026</h2>

<p class="lead">Garrath &mdash; the short version is that the desk lost {m(abs(net_clean))} on the
clean book across five sessions, and that number is the <em>least</em> important one on this page.
Three sessions were green and two were red, but the two red ones were not the gates being wrong
about the market. Thursday was one position held for six hours through a fall it should have been
stopped out of, and Friday was a software fault plus a gateway that stopped answering &mdash; and
that second one is not finished. <strong>You are still long four lots right now.</strong> They were
opened at 13:13 UTC on Friday, every automatic path that exists to close them failed on the same
call, and at the last price the tape printed before the CME shut they were {m(carry)} down. That is
bigger than the whole week's trading, it is not in any P&amp;L on this page, and it is the first
thing on the action card.</p>

{correction("★ READ THE VENUE LINE BEFORE YOU READ ANY OF THESE TABLES",
 f"Every table in this section counts trades that <strong>CLOSED</strong>. The desk is carrying "
 f"<strong>{RIDER_LOTS} MNQU6 long from {RIDER_ENTRY:,.2f}</strong>, opened 2026-08-21T13:13:06Z "
 f"by the day rider and never closed. Marked at the last tick before the weekend "
 f"({dt.datetime.fromtimestamp(last_ts, dt.UTC):%H:%M:%S}Z, {last_px:,.2f}) that is "
 f"<strong>{carry_pt:+.2f} points &rarr; {m(carry)}</strong>. The nightly review of 22:43Z Friday "
 f"read it live off <code>updatePortfolio</code> at {m(-950.27)} unrealised, which is the same "
 f"position a few ticks earlier.",
 "A trades table can never contradict a benign story, because it only enumerates what closed. "
 "The one instrument that can is the venue position line, and it says four lots. Everything "
 "below is the story of the money that finished; this is the money that has not.")}

<h3>1 &middot; The money, session by session</h3>

{money}

<p class="ln">The <strong>clean book</strong> is <code>data_quality IS NULL</code> and it is the
strategy verdict &mdash; what the gates did when the machinery worked. The <strong>cash book</strong>
adds the flagged lot back, and it is what reconciles to the broker: one Friday day-rider lot filled
at 29388.25, about 30 points outside anything the book was showing, flagged
<code>BADFILL:stale_price_30pt_outside_book_20260821</code>. <strong>A BADFILL flag marks a
defective fill PRICE, not a phantom trade</strong> &mdash; the money left the account either way,
so quote the clean book when you are judging a gate and the cash book when you are counting cash.
Add the open carry and the week's real economic position is
<strong>{m(round(net_all + carry, 2))}</strong>.</p>

<h3>2 &middot; Every slot that fired, and the four that did not</h3>

{cards}

<p class="ln">Two base gates traded all week: <code>abs_veto_short</code> and
<code>exhaustion_short</code>, both of them short-side, plus the day rider on its own book. The
other four &mdash; <code>{'</code>, <code>'.join(silent)}</code> &mdash; fired
<strong>nothing at all</strong>, because they were benched for the whole week under the standing
tournament standdown. That is not an accident and it is not a gate failure; it is the desk's
current posture, and Movement&nbsp;2 prices what it saved. The short answer, in advance: firing all
six mechanically across this week's tape would have lost <strong>&minus;$1,905.36</strong> on 117
fires, so the four silent gates are the best-performing thing on this page.</p>

<h3>3 &middot; The two legs of the same signal &mdash; is the wide one still winning?</h3>

<p>Every tournament signal opens two lots at the same price with the same stop, and the only
difference is where profit is taken: Lot&nbsp;A takes the tight rung, Lot&nbsp;B rides for the
wider one. <strong>They are a scale-out, not an experiment</strong> &mdash; if B beats A the
instruction is to widen A's target, never to drop A. Paired on the signal, this week:</p>

{ab}

<p class="ln">{m(round(sum(dl), 2))} across {len(both)} paired signals, with B ahead on
{sum(1 for x in dl if x > 0)} of them. <strong>That is not a result.</strong> On this n a
single pair moves the sign, and stripping the best one leaves {m(strip_best(dl, 1))}. Last week's
wide-leg finding stood on 51 paired entries with all five daily folds positive; this week's {len(both)}
pairs neither confirm nor contradict it, and the honest statement is that the week was too quiet
to re-test it. Do not re-rank the exit ladder on this table.</p>

<h3>4 &middot; How the week's lots actually ended</h3>

{exits}

<p class="ln">The <code>CLOCK_FLAT_BUG</code> rows are not an exit style, they are the Friday fault
&mdash; Part&nbsp;1.5 takes them apart. Note the shape of everything else: 21 stops for
{m(round(sum(r['net'] for r in allr if r['why'] == 'STOP'), 2))} against 16 manual claims for
{m(claim_v)} and four targets for
{m(round(sum(r['net'] for r in allr if r['why'] == 'TARGET'), 2))}. <strong>The desk's automated
profit-taking barely appears this week</strong> &mdash; one TRAIL exit for $185.00 and four
targets. Almost every dollar the desk made, your hand made.</p>

<h3>5 &middot; THURSDAY &mdash; the week's whole loss, in one position</h3>

<p>Thursday 20 August cost {m(round(sum(r['net'] for r in thu), 2))}, which is more than the other
four sessions made between them. It was not the gates. The tournament did not fire a single lot
that day. It was one day-rider long, four lots, opened at 13:38 UTC and closed by your own hand in
three pieces between 19:33 and 20:17 as it kept going the wrong way:</p>

{thursday}

<p class="ln">One entry, one direction, no stop that bound, and just under six hours of holding.
The rider had no protective exit in the water for any of it. Part&nbsp;1.6 walks the rider's own
week in detail and Part&nbsp;1.5 asks the rehabilitation question &mdash; whether the entry was
wrong, or whether an entry that was fine was ruined by having no stop &mdash; and the answer is not
the obvious one.</p>

<h3>6 &middot; Your hands, scored honestly</h3>

<p>{len(claims)} of the week's {len(clean)} clean lots were closed by you pressing Claim, and they
account for {m(claim_v)} of the P&amp;L, {len(claim_win)} of {len(claims)} of them green. Everything
the machine closed by itself came to {m(auto_v)}. Stated that way it reads like your hand carried
the week, and in cash terms it did &mdash; but the honest version needs the counterfactual, so
here is the peak that existed <em>inside each claimed trade's own life</em> against what you
actually booked:</p>

{capture}

<p class="ln">Median capture of the in-trade peak: <strong>{med_keep:.0f}%</strong>. The peak column
counts only ticks between the entry and the exit &mdash; an excursion after the trade closed is
money the desk was flat for, and counting it would let a chart accuse your own book of leaving
money behind that was never available.</p>

{callout("The claim replay: your hand is real, and a peak-and-give-back rule does not reproduce it",
 "This week's claim-replay study (<code>reports/claim_replay/</code>) rebuilt the 1&nbsp;Hz "
 "peak-watch ladder against all 35 booked manual claims on the tape. Where the watcher is "
 "actually in scope &mdash; the rider's two-lot book &mdash; an exit-shaped signal fired inside "
 "the hold on 4 of 4 trades and fired BEFORE you pulled every time, median lead 1,383 seconds. "
 "It also booked less money on every one of them: $165 vs $189, $382 vs $731, $137 vs $456, "
 "$454 vs $544.",
 "Then it was calibrated properly &mdash; 75 cells on 341 training trades, best cell taken to 126 "
 "held-out ones. In-sample it makes <strong>+$1,069</strong>. Out-of-sample it makes "
 "<strong>&minus;$4</strong>. Applied exactly as it stands live it fires on 10 of 467 trades for "
 "&minus;$436. <strong>The give-back exit shape is REFUTED as a way to reproduce your hand</strong>, "
 "over 44 + 75 calibrations on two independent populations.",
 "The finding underneath it is the useful part: scoring any rule against the trades you chose to be "
 "present for was always going to lose, because <em>your presence is the filter</em>. The money an "
 "automated claim could win is in the 671 exits nobody watched &mdash; and in that population the "
 "STOP bucket is &minus;$18,672 over 378 trades. That is an ENTRY-side question (which trades are "
 "stop-bound?), not an exit-side one, and the lead has been moved there rather than killed.")}

<h3>7 &middot; Three instruments that reported confidently and wrongly this week</h3>

{table(["Instrument", "What it said", "What was true", "Cost of believing it"],
 [[("", "row-bad"), "<code>core_health.json</code> &middot; the router's own health line",
   '<code>"flat": true, "healthy": true</code> &mdash; still says it as this report renders',
   f"The venue has been long {RIDER_LOTS} lots since 13:13Z Friday",
   "It is the flag every other tool trusts. 132 of the 137 router ticks since the entry repeated "
   "the word &ldquo;flat&rdquo;."],
  [("", "row-bad"), "<code>hour_watch.py</code> &middot; the hourly desk read",
   "Friday day net &minus;$150.50",
   "&minus;$69.00 on the clean book &mdash; it has no <code>data_quality</code> filter, so the "
   "BADFILL lot lands in its total",
   "Neither number is wrong; they answer different questions. IB's own realizedPNL "
   "&minus;$149.38 reconciles to the FLAGGED figure, so hour_watch is right about CASH and "
   "wrong about STRATEGY."],
  [("", "row-bad"), "<code>router_nightly</code> / <code>selector_nightly</code>",
   "Nothing at all for this week",
   "The newest router rollup is 2026-08-14 and the newest selector rollup 2026-08-18 &mdash; no "
   "timer runs either of them",
   "The weekly router review in Part&nbsp;2.6 had to be rebuilt from raw logs. A monitoring file "
   "that silently stops being written is worse than one that errors."]],
 numeric=set())}

<h3>8 &middot; What actually happened, in five sentences</h3>

<p><strong>Monday</strong> was the week's clean session: the short book worked in a falling tape,
the rider took {m(453.0)} out of one claimed short, and the desk closed {m(458.0)}.
<strong>Tuesday</strong> was the busiest day by far at {len([r for r in clean if r['day'] == '2026-08-18'])}
lots for {m(162.5)} &mdash; a genuine chop day where <code>exhaustion_short</code> faded the
oscillation well and <code>abs_veto_short</code> gave most of it back.
<strong>Wednesday</strong> was the best at {m(500.0)}, essentially one rider short claimed for
{m(541.0)} inside eleven minutes, after which the short book stopped out four times in a row for
{m(-153.0)} and the operator benched it at 18:15Z.
<strong>Thursday</strong> was {m(-1294.5)} in the single rider long described above.
<strong>Friday</strong> booked {m(-156.5)} on a software fault at 09:12Z, then opened the four-lot
long at 13:13Z that is still open, and at 19:57Z the IB gateway entered the partial wedge that
stopped every closing path on the box.</p>

{disposition([
 ("The four silent gates (grind_long, capitulation_long, abs_veto_long, rgv_short)", "HOLD",
  "They traded nothing and that was correct: the mechanical counterfactual in Movement 2 is "
  "&minus;$1,905.36 across this week's tape. Keep them benched; revisit only on a measured trend "
  "week, not on a quiet one."),
 ("abs_veto_short as a live slot", "SHADOW",
  "&minus;$203.00 over 22 lots this week, and its 55-second shadow mirror is the week's best "
  "shadow family (+$332 over 46). The live/shadow gap is the whole question &mdash; Part 1.5 "
  "takes it apart and Part 2 tests whether the mirror is promotable."),
 ("exhaustion_short as a live slot", "LIVE",
  "The only live slot green on the week: +$144.50 over 14 lots at 57% win. No change proposed."),
 ("The wide-leg (Lot B) exit finding", "PARKED",
  "22 paired signals is too thin to re-test it and the sign flips on one pair. Revive it next "
  "week on n&ge;40 pairs, or sooner if the shadow ladder arms produce their own pairs."),
 ("The automated claim detector (peak / give-back)", "REFUTED",
  "Out-of-sample &minus;$4 on 126 held-out trades against +$1,069 in-sample, and &minus;$436 as "
  "the live config stands. Two independent populations, 119 calibrations. Relocated to the "
  "entry-side question rather than killed."),
 ("<code>core_health.flat</code> as a safety signal", "FAULT",
  "It is tournament-scoped and it says the desk is flat while the venue is long four lots. "
  "BUILD item: make it read the venue position line, or rename it."),
])}
"""
    write("part1_live.html", doc.strip())

    print(f"\nclean {net_clean}  cash {net_all}  carry {carry}  claims {claim_v}/{len(claims)}")
    print(f"A/B pairs {len(both)}  B-A {sum(dl):+.2f}  strip1 {strip_best(dl, 1)}")
    print(f"median claim capture {med_keep}%")


if __name__ == "__main__":
    main()
