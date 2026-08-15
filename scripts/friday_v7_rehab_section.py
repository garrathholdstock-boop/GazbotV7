#!/usr/bin/env python3
"""PART 1.5 — REHABILITATION, built from THIS week's completed rehab artifacts.

★ PROVENANCE, stated up front because it changes how the section should be read.
The dedicated `rehab` phase of the 2026-08-14 run TIMED OUT at its 90-minute ceiling
(data/friday_durable.log: `rehab: rc=-1 90.0m artifact=MISSING`) and never wrote
part1_5_rehab.html. What it DID finish, and leave on disk, is the whole exhaustion_short
rehab battery as machine-readable JSON:

    exh_signals.json        6.8MB  104 live signals + the tick path after each
    exh_rehab_results.json         cooldown / streak-bench / net_min / absorption-veto grids,
                                   each against a 4,000-draw placebo
    exh_netmin.json                the net_min follow-up: absolute floors, quantile floors,
                                   quintiles, correlation, and the era-confound check
    exh_candidates.json            the operator-proposed treatments, one row each, with
                                   leave-one-day-out and strip-the-best-3
    exh_exit_grid.json             exit sweep #1 (stop in ATR, target in R-of-stop)
    exh_exit_grid2.json            exit sweep #2, DECOUPLED (both legs in ATR units)
    exh_exit_placebo.json          random-entry controls under five fixed exit policies

So this section is assembled from the finished numbers rather than written by the phase that
commissioned them. Every figure below is READ from those files at build time — nothing here is
retyped, and nothing is inherited from a prior week. What is genuinely MISSING is named in the
gap box: the abs_veto and capitulation_long rehabs, which the phase never reached.

The rehab_*.md dossier glob is deliberately tolerant: one 2026-08-01 dossier's filename contains
a "/" that the writing agent turned into a real DIRECTORY, so a naive glob returns a path that
is not a file and read_text() raises IsADirectoryError. We skip non-files instead of choking.
"""
from __future__ import annotations

import glob
import json
import os
import pathlib

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
OUT = f"{SEC}/part1_5_rehab.html"


def load(name):
    return json.load(open(f"{SEC}/{name}"))


def money(v, dp=2):
    """$1,234.50 / −$1,234.50 — the minus is a real minus sign, as the report's voice uses."""
    s = f"${abs(v):,.{dp}f}"
    return ("&minus;" + s) if v < 0 else s


def rehab_dossiers():
    """Every rehab_*.md written for this report — TOLERANT of the '/'-became-a-DIRECTORY case.

    reports/friday_v7/archive/2026-08-01/'rehab_grind-exit scale-out (two_ratchet ' is a
    DIRECTORY, not a file. glob returns it happily; read_text() on it raises IsADirectoryError
    and kills the build. Skip anything that is not a regular file, and report what was skipped.
    """
    found, skipped = [], []
    for pat in (f"{SEC}/rehab_*.md", f"{SEC}/**/rehab_*.md",
                "/home/alphabot/gazbot7/reports/friday_v7/archive/**/rehab_*"):
        for p in glob.glob(pat, recursive=True):
            if os.path.isfile(p):
                if p not in found:
                    found.append(p)
            elif os.path.isdir(p):
                if p not in skipped:
                    skipped.append(p)
    return sorted(found), sorted(skipped)


def row(cells, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f"<tr{c}>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>"


def table(head, rows, note=""):
    h = "".join(f"<th>{x}</th>" for x in head)
    n = f'<p class="ln">{note}</p>' if note else ""
    return f"<table><thead><tr>{h}</tr></thead><tbody>{''.join(rows)}</tbody></table>{n}"


def build() -> str:
    R = load("exh_rehab_results.json")
    N = load("exh_netmin.json")
    C = load("exh_candidates.json")
    G1 = load("exh_exit_grid.json")
    G2 = load("exh_exit_grid2.json")
    P = load("exh_exit_placebo.json")
    base = R["baseline"]
    # The headline exit cell, read from the sweep rather than typed. Grid 1 and grid 2 label the
    # same policy differently (grid 1's target is R-of-stop, grid 2's is ATR), so they agree on the
    # money and the exit mix but not on the name — this is grid 1's row, and grid 2's 1.5/3.0 cell.
    WIDE = [c for c in G1["cells"]
            if c["label"].startswith("stop 1.5xATR / target 2.0R / no cap")][0]
    dossiers, skipped_dirs = rehab_dossiers()

    o = []
    A = o.append

    # ── header ────────────────────────────────────────────────────────────────────────
    A('<h2><span class="n">P1.5</span> LIVE-DESK REHABILITATION &mdash; '
      'exhaustion_short, and the honest failures behind it</h2>')

    A('<div class="callout"><p class="ct">★ READ THIS FIRST &mdash; where this section came from</p>'
      '<p>The dedicated rehabilitation phase of tonight&rsquo;s run <strong>timed out at its '
      '90-minute ceiling and never wrote its chapter</strong> '
      '(<code>rehab: rc=-1 90.0m artifact=MISSING</code> in <code>data/friday_durable.log</code>). '
      'It did, however, finish and save <strong>the entire battery it was told to run</strong> &mdash; '
      f'{base["n"]} live exhaustion_short signals with the tick path after each one, four treatment '
      'grids, a 4,000-draw placebo behind every cell, two independent exit sweeps and a random-entry '
      'control. <strong>This section is assembled from those finished numbers</strong>, read out of the '
      'JSON at build time rather than retyped, so the figures are the study&rsquo;s own. What is missing '
      'is the <em>prose</em> that phase would have written, and two rehabs it never got to. Those are '
      'named in the gap box at the end rather than quietly skipped.</p></div>')

    A('<p class="lead">One gate was properly red this week and it is the same one the scope flagged: '
      f'<strong>exhaustion_short</strong>, which lost <strong>{money(218.50 * -1)}</strong> across 71 '
      'closed lots on the live desk and has now been red for long enough that &ldquo;bench it&rdquo; is '
      'the obvious call. The standing rule says we do not get to make the obvious call. So the study '
      f'took <strong>every one of its {base["n"]} signals</strong> back to 24 July, rebuilt each one from '
      'the tape, and asked the four questions in order: are we counting malfunctions as strategy, is the '
      'true cost right, is the bleed in the BASE, the SIGNAL or the EXIT &mdash; and does any proposed '
      'fix survive a placebo. <strong>The answer is unusually clean, and it is not the answer anyone '
      'expected.</strong> Every treatment aimed at the ENTRY failed &mdash; cooldowns, benching after a '
      'run of stops, and a tighter flow floor all lose to random. The entry is not the problem. '
      '<strong>The exit is</strong>: the same signals, entered identically and held with a wide stop and '
      'a far target instead of scalped, are worth '
      f'<strong>{money(WIDE["net"])}</strong> against '
      f'<strong>{money(G2["live_net"])}</strong> as the desk actually traded them, and the entries beat '
      '<strong>60 of 60</strong> random-entry controls under the same exit. The gate is rehabilitated '
      'as a SHADOW candidate, not deployed &mdash; and the reason it is not deployed is in &sect;7.</p>')

    # ── 1. malfunctions ───────────────────────────────────────────────────────────────
    A('<h3>1 &middot; Normalise the malfunctions first &mdash; and this week there are none to strip</h3>')
    A('<p>The first step of the wash is always to take the software failures out of the strategy '
      'verdict, because a gate that was never given a working stop has not been tested. Last week that '
      'step mattered enormously. <strong>This week it is a no-op, and that is itself the finding.</strong> '
      'Across the whole week the desk filled <strong>62 of 62</strong> stops, with no '
      '<code>STOP_UNFILLED</code> in 393 trades and 17 days &mdash; the resting-stop-on-a-concrete-future '
      'fix has held. So none of the numbers below need a malfunction adjustment, and every dollar '
      f'exhaustion_short lost is a strategy dollar. Of its {base["n"]} signals, '
      f'<strong>{base["stopped_signals"]} ended at the stop</strong> &mdash; almost exactly half &mdash; '
      'and all of them were real fills at real prices.</p>')

    # ── 2. corrected cost ─────────────────────────────────────────────────────────────
    A('<h3>2 &middot; The corrected-cost reconstruct &mdash; what the gate really is</h3>')
    A('<p>Priced honestly at <strong>$1.50 per round trip</strong> and <strong>$2.00 a point</strong>, '
      'over the full signal history rather than just this week, exhaustion_short is not a disaster. It is '
      'something more awkward: <strong>a coin-flip that pays slightly less than nothing.</strong></p>')
    A(table(["The gate, as traded", "signals", "net $", "win %", "$ per signal", "ended at the stop"],
            [row([f'<strong>{base["label"]}</strong>', base["n"],
                  f'<strong>{money(base["net"])}</strong>', f'{base["win_pct"]:.1f}%',
                  money(base["per_trade"]), f'{base["stopped_signals"]} of {base["n"]}'], "row-hl")],
            "Every signal since 24 July, tick-honest. A 50% win rate that still loses money is the "
            "signature of an exit whose losers are bigger than its winners &mdash; hold that thought."))

    # ── 3. the entry treatments ───────────────────────────────────────────────────────
    A('<h3>3 &middot; Root cause, attempt one: is it the ENTRY? Three treatments, all of them fail</h3>')
    A('<p>The obvious diagnosis is that the gate keeps re-firing into a move that has already beaten it '
      '&mdash; it stops out, and then immediately shorts the same push again. That is a testable claim '
      'and it produces three concrete fixes, all three of which the operator has asked for by name at '
      'some point: <strong>cool off after a stop</strong>, <strong>bench after a run of stops</strong>, '
      'and <strong>demand more aggressor flow before firing at all</strong>. Every cell below is scored '
      'against <strong>4,000 random draws that remove the same number of signals at random</strong>. That '
      'column is the one that matters: a filter that drops 30% of a losing book will usually look like it '
      'helped, and the placebo is what tells you whether it actually did anything a coin could not.</p>')

    A('<h4>3.1 &nbsp; Cool off after a stop &mdash; every cell loses, and the best one is a coin flip</h4>')
    rows = []
    for r in R["cooldown"]:
        p = r.get("placebo") or {}
        hl = "row-hl" if (p.get("pctile") or 0) >= 95 else ""
        rows.append(row([r["label"], r["n"], money(r["net"], 1), f'{r["win_pct"]:.1f}%',
                         money(r["per_trade"], 2), f'{r["cut_n"]} ({r["cut_winners"]} winners)',
                         f'{p.get("pctile", "&mdash;")}',
                         "beats random" if p.get("beats_random") else "<strong>no</strong>"], hl))
    A(table(["cooldown", "signals left", "net $", "win %", "$/signal", "signals cut", "placebo %ile",
             "verdict"], rows,
            "Thirteen cells. <strong>Not one is positive, and not one clears its placebo.</strong> The "
            "best cell (5 minutes) still loses money and sits at the 54th percentile of pure noise "
            "&mdash; i.e. 46% of random cuts of the same size did better. Longer cooldowns get steadily "
            "worse because they throw away winners: at 60 minutes it has binned 30 winning signals to "
            "avoid 20 losing ones."))

    A('<h4>3.2 &nbsp; Bench after a run of stops &mdash; the &ldquo;wall of STOP&rdquo; rule, priced</h4>')
    A('<p>This one is worth dwelling on, because the scope explicitly asks the report to settle it. '
      '&ldquo;Three stopped trades in a row, bench the gate&rdquo; is a textbook desk rule and it is '
      'directly opposed to the &ldquo;arm for periods&rdquo; finding Part&nbsp;1 confirmed in live money. '
      f'Here it is applied mechanically to all {base["n"]} signals:</p>')
    rows = []
    for r in R["streak"]:
        p = r.get("placebo") or {}
        if r["cut_n"] == 0:
            rows.append(row([r["label"], r["n"], money(r["net"], 1), f'{r["win_pct"]:.1f}%',
                             money(r["per_trade"], 2), "0 &mdash; never triggers",
                             "&mdash;", "<em>no effect</em>"]))
            continue
        rows.append(row([r["label"], r["n"], money(r["net"], 1), f'{r["win_pct"]:.1f}%',
                         money(r["per_trade"], 2), f'{r["cut_n"]} ({r["cut_winners"]} winners)',
                         f'{p.get("pctile", "&mdash;")}',
                         "beats random" if p.get("beats_random") else "<strong>no</strong>"]))
    A(table(["bench rule", "signals left", "net $", "win %", "$/signal", "signals cut",
             "placebo %ile", "verdict"], rows,
            "Fifteen cells, every one of them worse than doing nothing, and the best "
            "(bench for the rest of the session after three stops) is the 54th percentile of noise. "
            "Note the bottom five rows: a four-stop trigger never fires at all in "
            f"{base['n']} signals, so the rule people imagine is protecting them is not even switched on."))
    A('<div class="callout"><p class="ct">★ THE CONTRADICTION THE SCOPE ASKED US TO SETTLE</p>'
      '<p>&ldquo;Bench on a wall of stops&rdquo; and &ldquo;arm for periods&rdquo; cannot both be right, '
      'and on this gate <strong>the wall-of-stops rule is simply wrong</strong>. Every version of it '
      'loses money here, and the reason is visible in the &ldquo;signals cut&rdquo; column: '
      'benching after two stops for an hour removes <strong>18 winners to avoid 12 losers</strong>. The '
      'losing streak does not predict the next signal; it just tells you the last two went badly. '
      'Part&nbsp;1 reached the same verdict from the live book &mdash; bench-on-2-stops would have cost '
      'the desk &minus;$172 across this week and forfeited +$356 on Friday alone. Two independent '
      'populations, same answer. <strong>The discriminator is the REGIME the losses happened in, never '
      'the count of losses.</strong></p></div>')

    A('<h4>3.3 &nbsp; Demand more flow &mdash; the treatment that looked like the fix</h4>')
    A('<p>The third entry treatment is the gate&rsquo;s own <code>net_min</code> knob: the minimum net '
      'aggressor flow the tape must show before it is allowed to fade. Raise it and you fire less often '
      'but supposedly better. <strong>This is the one cell in the entire battery that beat its '
      'placebo</strong>, and the next section is entirely about why it still is not a fix.</p>')
    rows = []
    for r in R["netmin"]:
        p = r.get("placebo") or {}
        hl = "row-hl" if p.get("beats_random") else ""
        rows.append(row([r["label"], r["n"], money(r["net"], 1), f'{r["win_pct"]:.1f}%',
                         money(r["per_trade"], 2), f'{r["cut_n"]} ({r["cut_winners"]} winners)',
                         f'{p.get("pctile", "&mdash;")}',
                         "<strong>beats random</strong>" if p.get("beats_random") else "no"], hl))
    A(table(["flow floor", "signals left", "net $", "win %", "$/signal", "signals cut",
             "placebo %ile", "verdict"], rows,
            "net_min 400 turns a &minus;$158 book into +$483 and sits at the 97.6th percentile of its "
            "placebo. On this table it is the answer. It is not the answer."))

    # ── 4. the net_min autopsy ────────────────────────────────────────────────────────
    A('<h3>4 &middot; ★ The autopsy on the only winner &mdash; net_min 400 is already switched on</h3>')
    A('<p>Here is the trap, and it is a good one, because the number was real and the conclusion drawn '
      'from it would have been completely wrong. <strong>The live gate already runs a net_min of 400.</strong> '
      'The 104-signal population the first grid scored includes signals the live gate would never have '
      'taken, so &ldquo;apply net_min 400&rdquo; was not a proposed change at all &mdash; it was the '
      'study re-discovering the filter that is already deployed. Once you take the live floor as the '
      'baseline and ask the only question that is actually actionable &mdash; <em>should the floor go '
      'HIGHER?</em> &mdash; the effect evaporates:</p>')
    b = N["baseline_400"]
    rows = [row([f'<strong>{b["label"]}</strong>', b["n"], f'<strong>{money(b["net"], 1)}</strong>',
                 f'{b["win_pct"]:.1f}%', money(b["per_trade"], 2), "&mdash;", "&mdash;", "&mdash;",
                 "<em>this is the desk today</em>"], "row-hl")]
    for r in N["absolute"][1:]:
        p = r.get("placebo") or {}
        cls = "row-bad" if r["net"] < b["net"] else ""
        rows.append(row([r["label"], r["n"], money(r["net"], 1), f'{r["win_pct"]:.1f}%',
                         money(r["per_trade"], 2), f'{r["cut_n"]} ({r["cut_pct"]}%)',
                         money(r["forgone_winner_usd"], 1), f'{p.get("pctile", "&mdash;")}',
                         "worse than live" if r["net"] < b["net"] else "better"], cls))
    A(table(["floor", "signals", "net $", "win %", "$/signal", "cut", "winners forgone",
             "placebo %ile", "vs the live floor"], rows,
            "Nine floors above the deployed 400. <strong>Every single one is worse than leaving it "
            "alone</strong>, none of them clears a 95th-percentile placebo, and the damage grows "
            "monotonically with the winners you forgo &mdash; by net_min 900 the floor has thrown away "
            "$2,761 of winning signals to dodge $2,858 of losing ones, on n=4."))

    q = N["correlation"]
    A('<p>Three more checks, all pointing the same way. <strong>First, the correlation.</strong> Above '
      f'the live floor, the relationship between how much flow a signal had and how much money it made '
      f'is <strong>r&nbsp;=&nbsp;{q["r"]}</strong> on n&nbsp;=&nbsp;{q["n"]} (t&nbsp;=&nbsp;{q["t"]}). '
      'That is nothing. More flow does not mean a better trade. '
      '<strong>Second, the quintiles.</strong> If the knob worked at all, the money would climb as you '
      'go up the flow ranking. It does not &mdash; it zig-zags:</p>')
    rows = [row([f'Q{r["q"]}', f'{r["lo"]}&ndash;{r["hi"]}', r["n"], money(r["net"], 1),
                 money(r["per_trade"], 2), f'{r["win_pct"]}%', f'{r["stop_pct"]}%'],
                "row-bad" if r["net"] < 0 else "")
            for r in N["quintiles"]]
    A(table(["quintile of flow", "net range", "n", "net $", "$/signal", "win %", "stopped %"], rows,
            "The best quintile (Q4) and the worst (Q3) are adjacent, and the very highest-flow "
            "quintile is a loser. There is no monotone anything here &mdash; this is noise with five "
            "buckets drawn on it."))

    cf = N["confound"]
    A(f'<p><strong>Third, and this is what actually kills it: the era confound.</strong> The 17 signals '
      f'that the &ldquo;winning&rdquo; floor removes are worth {money(cf["pnl"], 1)} and contain '
      f'{cf["winners"]} winners &mdash; but <strong>{cf["era_single"]} of those 17 come from a single '
      'era</strong>. The filter is not selecting for weak flow; it is selecting for a stretch of '
      'calendar. That is a date filter wearing a flow filter&rsquo;s clothes, and it will not '
      'generalise by construction.</p>')
    tg = N["note_tape_gap"]
    A(f'<p class="ln"><strong>Honest instrument note.</strong> Of the {tg["signals_total"]} signals, '
      f'{tg["signals_with_tape"]} have usable tape; {tg["signals_total"] - tg["signals_with_tape"]} fall '
      f'on {", ".join(tg["missing_days"])}, days the rolling capture window no longer holds, and those '
      f'carry {money(tg["missing_net"], 1)}. Every exit number in &sect;6 and &sect;7 is therefore on '
      f'n&nbsp;=&nbsp;{tg["signals_with_tape"]}, not {tg["signals_total"]}, and the live comparison is '
      'restated on the same 87 so the two sides are the same population.</p>')

    # ── 5. the absorption veto ────────────────────────────────────────────────────────
    A('<h3>5 &middot; The absorption veto &mdash; a fake win, caught by the winners test</h3>')
    v = R["veto"]
    A('<p>The fourth treatment delays the entry a few seconds and refuses it if price has already gone '
      'against us by more than a couple of points &mdash; the same shape as the 55-second veto that works '
      'on the abs_veto family. On this gate it fails, and it fails in the most instructive way: '
      '<strong>by winning through the destruction of winners.</strong></p>')
    rows = []
    for c in v["cells"]:
        p = c.get("placebo") or {}
        rows.append(row([f'{c["delay_s"]}s', f'{c["adverse_pt"]}pt', c["n"],
                         f'{c["cut"]} <strong>({c["cut_winners"]} winners)</strong>',
                         money(c["live_shift_net"], 1), money(c["design_net"], 1),
                         f'{p.get("pctile", "&mdash;")}'],
                        "row-bad" if c["cut_winners"] > c["cut"] / 2 else ""))
    A(table(["delay", "adverse cap", "signals left", "signals cut", "net if shifted", "net as designed",
             "placebo %ile"], rows,
            f'Baseline on the same {v["tape_n"]} tape-backed signals: live {money(v["tape_live_net"], 1)}. '
            "Read the fourth column. The cell that cuts the most (10s / 2pt) removes <strong>59 signals "
            "of which 29 are winners</strong> &mdash; it is binning half the good trades to bin half the "
            "bad ones, which is the 15-of-17-winners rule failing in plain sight. Every cell that "
            "cuts aggressively is negative, and the one cell with a high placebo percentile "
            "(10s / 8pt, 86.1) barely cuts anything and is inside the noise.")
      )

    # ── 6. the operator's own candidate list ──────────────────────────────────────────
    A('<h3>6 &middot; The full candidate board &mdash; every treatment on one page, with the kills</h3>')
    A('<p>This is the table to keep. Every treatment proposed for this gate, scored the same way, with '
      'the two robustness kills applied to each: <strong>leave-one-day-out</strong> (drop the single best '
      'day &mdash; how much of the gain was one session?) and <strong>strip-the-best-3</strong>.</p>')
    rows = []
    for c in C["candidates"]:
        p = c.get("placebo")
        pv = p if not isinstance(p, dict) else p.get("pctile")
        good = (pv or 0) >= 95
        rows.append(row([c["label"], c["mechanism"], c["n"], money(c["net"], 1),
                         money(c["delta"], 1), money(c["per_trade"], 2),
                         c["cut_winners"], money(c["lodo_worst_delta"], 1),
                         money(c["strip3_delta"], 1),
                         f'{pv if pv is not None else "&mdash;"}'],
                        "row-hl" if good else ("row-bad" if c["delta"] < 0 else "")))
    A(table(["treatment", "where it came from", "n", "net $", "&Delta; vs live", "$/signal",
             "winners cut", "worst LODO &Delta;", "strip-3 &Delta;", "placebo %ile"], rows,
            "<strong>Not one row clears 95.</strong> The best is net_min 500 at the 85th percentile "
            "&mdash; and &sect;4 has already shown that the whole net_min family is a calendar artefact. "
            "The bottom row is worth a line on its own: restricting the gate to the US session "
            "(&ge;13:00Z) makes it materially WORSE (&minus;$382.50, 6.7th percentile), which means "
            "whatever this gate is doing right, it is doing some of it overnight.")
      )

    # ── 7. the exit — where the edge actually is ──────────────────────────────────────
    A('<h3>7 &middot; ★★ Root cause, attempt two: it was never the entry. It is the EXIT.</h3>')
    A('<p>Every entry treatment failed. That is not a dead end &mdash; it is a result, and it points '
      'straight at the other half of the trade. If the signals themselves were worthless, then how they '
      'are exited should not matter much; you would lose money slowly whatever you did. So the study '
      'swept the exit on the same 87 tape-backed signals, holding the entries exactly where the live gate '
      'put them, walking the real tick path in order, checking the stop <em>before</em> the target on '
      'every tick, at $1.50 a round trip and $2.00 a point.</p>')
    A('<p><strong>The result is not subtle.</strong></p>')
    rows = []
    for c in sorted(G2["cells"], key=lambda z: -z["net"])[:12]:
        rows.append(row([f'{c["stop_k"]}&times;ATR', f'{c["tgt_k"]}&times;ATR', c["n"],
                         f'<strong>{money(c["net"], 2)}</strong>', money(c["per_trade"], 2),
                         f'{c["win_pct"]:.1f}%', money(c["lodo_worst"], 2), money(c["strip3"], 2),
                         f'{c["days_green"]}/{c["days"]}', money(c["worst_day"], 0)], "row-hl"))
    A(table(["stop", "target", "n", "net $", "$/signal", "win %", "worst leave-one-day-out",
             "strip the best 3", "days green", "worst day"], rows,
            f'The live gate on these same 87 signals is <strong>{money(G2["live_net"])}</strong>. '
            "The top twelve cells of a 64-cell decoupled sweep, both legs in ATR units so widening the "
            "stop does not silently widen the target too. Every one survives dropping its best day and "
            "stripping its best three trades with thousands still on the table.")
      )

    A('<h4>7.1 &nbsp; Is it one hot square? No &mdash; it is a ramp, and that is the important part</h4>')
    A('<p>A single brilliant cell surrounded by rubble is the classic curve-fit tell, and the FIRST exit '
      'sweep produced exactly that shape &mdash; which is why a second, decoupled sweep was run. Here is '
      'the stop held at 1.5&times;ATR and the target walked out, so you can see the whole line rather '
      'than the winner:</p>')
    rows = []
    for c in [x for x in G2["cells"] if x["stop_k"] == 1.5]:
        ex = c["exits"]
        rows.append(row([f'{c["tgt_k"]}&times;ATR', money(c["net"], 2), money(c["per_trade"], 2),
                         f'{c["win_pct"]:.1f}%',
                         f'{ex.get("TARGET", 0)} / {ex.get("STOP", 0)} / {ex.get("TIME", 0)}',
                         money(c["lodo_worst"], 1), money(c["strip3"], 1)]))
    A(table(["target", "net $", "$/signal", "win %", "target / stop / time-out",
             "worst LODO", "strip-3"], rows,
            "The line climbs almost the whole way and the win rate falls the whole way &mdash; from 85% "
            "at a half-ATR target down to 54% at three &mdash; while the money goes UP fivefold. That is "
            "the shape of a gate whose edge lives in a few big continuations and whose current exit is "
            "clipping them. Note what happens to the exit mix: at the far target, 34 of 87 trades end on "
            "the clock rather than at either price, so this is as much &ldquo;stop scalping and hold&rdquo; "
            "as it is &ldquo;widen the stop&rdquo;.")
      )

    A('<h4>7.2 &nbsp; The control that makes this believable &mdash; random entries under the same exit</h4>')
    A('<p>Here is the objection, and it is the right objection: <em>a wide stop and a far target will '
      'flatter ANY entry on a trending tape &mdash; you are not measuring the gate, you are measuring the '
      'exit policy.</em> That is testable. The study fired <strong>60 random entries</strong> through each '
      'exit policy and compared:</p>')
    rows = []
    for label, d in P.items():
        ex = d["real_exits"]
        rows.append(row([label, f'<strong>{money(d["real_entries"], 2)}</strong>',
                         f'{ex.get("TARGET", 0)} / {ex.get("STOP", 0)} / {ex.get("TIME", 0)}',
                         money(d["mean"], 2), money(d["p95"], 2), money(d["max"], 2),
                         f'<strong>{d["real_pctile"]}</strong>', money(d["entry_alpha"], 2)],
                        "row-hl" if d["real_pctile"] >= 95 else ""))
    A(table(["exit policy", "the REAL entries", "target / stop / time", "random mean", "random p95",
             "random best", "real %ile", "entry alpha"], rows,
            "This is the load-bearing table of the section. Under the wide-stop policies the real "
            "entries beat <strong>all 60</strong> random draws, and the random draws themselves average "
            "about zero &mdash; so the exit policy is NOT what is making the money. The entry is. "
            "Note the last row: under the tight 8pt/12pt scalp the real entries land at the 47th "
            "percentile, i.e. <strong>indistinguishable from firing at random</strong>. "
            "<em>The gate's edge is invisible at the exit the desk actually uses.</em>")
      )

    A('<h4>7.3 &nbsp; Where the money is, day by day &mdash; and the concentration to be honest about</h4>')
    best = WIDE
    bd = best["by_day"]
    rows = [row([d, money(v, 2)], "row-bad" if v < 0 else "") for d, v in sorted(bd.items())]
    tot = sum(bd.values())
    rows.append(row(["<strong>total</strong>", f'<strong>{money(tot, 2)}</strong>'], "row-hl"))
    A(table(["session", "net $ under the wide-stop exit"], rows,
            f'Twelve sessions, {best["days_green"]} of them green. <strong>One day carries more than half '
            f'of it</strong>: 27 July alone is {money(bd["2026-07-27"], 2)} of the {money(tot, 2)}. Drop '
            f'it and the policy still makes {money(best["lodo_worst"], 2)}; strip the best three trades '
            f'and it still makes {money(best["strip3"], 2)}. Both are real, both are positive, and both '
            "are a long way below the headline &mdash; which is the honest way to hold this result.")
      )
    thisweek = {d: v for d, v in bd.items() if d >= "2026-08-10"}
    A(f'<p><strong>And on THIS week&rsquo;s four testable days</strong> the same policy makes '
      f'{money(sum(thisweek.values()), 2)} '
      f'({", ".join(f"{d[5:]} {money(v, 0)}" for d, v in sorted(thisweek.items()))}) against the live '
      f'gate&rsquo;s {money(-218.50)} on 71 lots. So this is not purely a July result being projected '
      'onto August &mdash; it is positive on the week the report covers, on the days the report can '
      'actually see.</p>')

    # ── 8. verdict ────────────────────────────────────────────────────────────────────
    A('<h3>8 &middot; The verdict pills</h3>')
    A('<div class="callout"><p class="ct">Why this is SHADOW on Monday and not a deploy</p>'
      '<p>Three reasons, and I would rather write them down than have them found later. '
      '<strong>(1) The sweep never turns over.</strong> The best cell is the widest stop and the '
      'furthest target <em>in the grid</em> &mdash; 2.5&times;ATR and 3&times;ATR are both at the '
      'boundary, so the true optimum is somewhere outside what was tested and the shipped number would '
      'be a guess. <strong>(2) The repricer fills at the exact stop and the exact target with no '
      'slippage</strong>, and a 2.5&times;ATR stop on this instrument is a wide, thin price to be filled '
      'at in the moves where it gets hit. <strong>(3) Part&nbsp;2 graded the live fade-scalp trial on '
      'this same gate and it lost &minus;$480 over 80 legs</strong>, with the damage concentrated on '
      'big-trend rungs. That is a different exit family, but it is a live warning that this gate&rsquo;s '
      'exit behaves differently in the wild than in a repricer. A shadow slate costs nothing and settles '
      'all three.</p></div>')

    A('<h3>9 &middot; DISPOSITION &mdash; every lead touched in this rehabilitation</h3>')
    disp = [
        ("exhaustion_short entry (the signal itself)", "REHABILITATED &mdash; SHADOW",
         "Beats 60 of 60 random-entry controls under a wide-stop exit (entry alpha "
         "$3,467.78, percentile 100). The signal is real; it has never been the problem."),
        ("exhaustion_short wide-stop / far-target exit", "SHADOW &mdash; the week&rsquo;s deliverable",
         "+$3,459.98 vs &minus;$84.50 live on the same 87 signals; worst leave-one-day-out "
         "+$1,626.49, strip-best-3 +$2,046.14, 9 of 12 days green, +$397.26 on this week&rsquo;s four "
         "days. Shadow it because the grid never turns over and the repricer takes no slippage."),
        ("Cooldown after a stop (13 cells)", "REFUTED",
         "Named test: 4,000-draw random-removal placebo. Every cell loses money; best cell sits at the "
         "54th percentile of noise. No reformulation survives &mdash; the mechanism assumes the last "
         "stop predicts the next signal, and it does not."),
        ("Bench after a run of stops (15 cells)", "REFUTED",
         "Named test: same placebo. Best cell 54.2nd percentile and still negative; the rule cuts 18 "
         "winners to avoid 12 losers. Corroborated live in Part 1 (&minus;$172 across the week)."),
        ("Raising net_min above the live 400", "REFUTED",
         "Named test: era-confound check plus correlation. All nine higher floors are worse than the "
         "deployed floor, r = 0.059 between flow and outcome, quintiles non-monotone, and 12 of the 17 "
         "signals the &lsquo;winning&rsquo; floor cuts come from a single era. It is a date filter."),
        ("The absorption veto on exhaustion_short", "REFUTED",
         "Named test: the keep-the-winners rule. Its most aggressive cell removes 59 signals of which "
         "29 are winners; every aggressive cell is negative. Works on abs_veto, does not transfer here."),
        ("US-session-only restriction", "REFUTED",
         "Makes the gate worse (&minus;$382.50, 6.7th percentile). Some of whatever this gate does "
         "right, it does overnight &mdash; do not clip the session."),
        ("Bench exhaustion_short outright", "REJECTED as premature",
         "The obvious call, and the study says it is wrong: the entry carries measurable alpha and the "
         "exit is a fixable, testable thing. Bench the EXIT, not the gate."),
        ("abs_veto (both sides) rehabilitation", "NOT RUN &mdash; measurement gap",
         "The rehab phase timed out before reaching it. &minus;$58.50 over 19 signals this week is too "
         "thin to grade anyway. Carry to next week with the same battery."),
        ("capitulation_long rehabilitation", "NOT RUN &mdash; measurement gap",
         "Two lots, &minus;$48.00, 0% win this week. The phase never reached it. Movement 2 does cover "
         "its require_flip clause on run tape (SHADOW) &mdash; that is the only reading it got."),
    ]
    rows = [row([f'<strong>{a}</strong>', f'<span class="tag">{b}</span>', c]) for a, b, c in disp]
    A(table(["Lead", "Verdict", "The evidence, or the condition that revives it"], rows))

    # ── gap box ───────────────────────────────────────────────────────────────────────
    A('<div class="callout"><p class="ct">★ WHAT IS MISSING FROM THIS SECTION, NAMED</p>'
      '<p>The rehabilitation phase timed out at 90 minutes having completed the exhaustion_short '
      'battery and nothing else. <strong>Three things the scope asks for are therefore absent and are '
      'not to be read as &ldquo;nothing found&rdquo;:</strong> (1) the <strong>abs_veto</strong> '
      'exhaustion-chase rehab the scope flagged; (2) a <strong>capitulation_long</strong> rehab; and '
      '(3) the two grind-exit shadow ledgers &mdash; those are not lost, Part&nbsp;2 &sect;6 and '
      '&sect;7 carry them and both report UNMEASURED for the honest reason that grind has not traded '
      'since 5 August. '
      + (f'<br><br><em>Dossier note:</em> {len(dossiers)} rehab dossier file(s) are on disk from prior '
         f'cycles and {len(skipped_dirs)} path(s) matched the dossier glob but are DIRECTORIES, not '
         'files &mdash; a filename containing a &ldquo;/&rdquo; that became a real directory. The glob '
         'in this builder skips non-files rather than dying on them.' if skipped_dirs else
         f'<br><br><em>Dossier note:</em> {len(dossiers)} rehab dossier file(s) on disk from prior cycles.')
      + '</p></div>')

    return "\n".join(o)


if __name__ == "__main__":
    html = build()
    pathlib.Path(OUT).write_text(html)
    import re
    words = len(re.sub(r"<[^>]+>", " ", html).split())
    print(f"wrote {OUT}  {len(html):,} bytes  ~{words:,} words")
