#!/usr/bin/env python3
"""MOVEMENT 3 — the greenfield lab, built from what this week's hunt actually finished.

★ PROVENANCE. Five greenfield phases were scheduled tonight. ONE of them produced anything:

    gf_MGC        rc=-1  13.2m  artifact=MISSING  — died before its write-up, but AFTER it had
                                                    saved gf_mgc_breaks.json: 397 MGC book
                                                    breaks over 21 sessions with their L2
                                                    features and forward outcomes.
    gf_VACUUM     never ran — budget exhausted (serial_runner: "0m left")
    gf_FLOW-LED   never ran
    gf_OPEN-NEWS  never ran
    gf_chopscalp  never ran
    movement3     never ran (it depends on all five above)

So the MNQ cause-cluster hunt did not happen this week and this section says so in the box at
the top rather than implying a null was reached. What DID happen is scored here in full, to the
escalation discipline the scope mandates: full population -> top 25 by size -> top 15, every
level reported including the ones that fail.

Numbers come from scripts/gf_mgc_analyse.py -> gf_mgc_scored.json. MGC is $10.00 A POINT and
the fee is $1.50 PER ROUND TRIP; both are applied there, not here.
"""
from __future__ import annotations

import json
import pathlib

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
OUT = f"{SEC}/movement3_greenfield.html"


def money(v, dp=2):
    s = f"${abs(v):,.{dp}f}"
    return ("&minus;" + s) if v < 0 else s


def row(cells, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f"<tr{c}>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>"


def table(head, rows, note=""):
    h = "".join(f"<th>{x}</th>" for x in head)
    n = f'<p class="ln">{note}</p>' if note else ""
    return f"<table><thead><tr>{h}</tr></thead><tbody>{''.join(rows)}</tbody></table>{n}"


def build() -> str:
    D = json.load(open(f"{SEC}/gf_mgc_scored.json"))
    C = json.load(open(f"{SEC}/census_summary.json"))
    b = D["baseline"]
    o = []
    A = o.append

    A('<h2><span class="n">M3</span> The greenfield lab &mdash; the gold book-break hunt, '
      'and the four hunts that never ran</h2>')

    A('<div class="callout"><p class="ct">★ READ THIS FIRST &mdash; what is here and what is not</p>'
      '<p>This movement was scheduled as <strong>five separate hunts</strong>: one per MNQ '
      'cause-cluster (VACUUM, FLOW-LED, OPEN-NEWS), a chop-day scalp lab, and a dedicated gold hunt. '
      '<strong>Four of the five never started.</strong> The serial runner ran out of budget after the '
      'rehabilitation phase overran &mdash; <code>BUDGET: stopping section builds to protect the tail '
      '(0m left)</code> &mdash; and the synthesis phase that reads all five never ran either. '
      'So <strong>there is no MNQ greenfield hunt in this report</strong>. That is a gap, not a null: '
      'nobody looked, so nobody found nothing. It is named in the disposition table and it is the '
      'first thing to reschedule.<br><br>'
      'The gold hunt <em>did</em> get far enough to save its signal file before it died, and that file '
      'is a real dataset: <strong>397 MGC book breaks across 21 sessions</strong> from 16 July, each '
      'with the order-book features it was built to test and the forward outcome. It is scored below '
      'to the full discipline &mdash; placebo, strip-the-best-three, leave-one-day-out, the size '
      'escalation, the excursion statistic and the book-separation table. '
      '<strong>Additional gold work that DID complete is in Part&nbsp;2.5 Part&nbsp;A</strong> '
      '(the MGC day rider, the coil bouncer, the London-open break fade) &mdash; that is where the two '
      'gold SHADOW candidates of the week live. This section is the fourth gold idea, and it is the '
      'one that failed.</p></div>')

    A(f'<p class="lead">The idea was a good one and it is the natural thing to try with L2 on a new '
      f'instrument. Gold breaks a level; look at the order book at the moment it breaks; if the far '
      f'side is <em>empty</em> &mdash; nothing resting in the way &mdash; the move should run, and if '
      f'the far side is stacked it should stall. That is the <strong>far-side-depletion</strong> '
      f'hypothesis, it is exactly what Movement&nbsp;1 asks of the book on MNQ, and on '
      f'{b["n"]} gold breaks <strong>it is not just absent, it is backwards.</strong> '
      f'The raw signal makes {money(b["net"])} at {money(b["per"])} a go. The book features it was '
      f'built on select the LOSERS. And the one feature that does separate &mdash; resting book '
      f'imbalance &mdash; only works in a middle band and evaporates the moment you narrow to the '
      f'biggest moves, which is the opposite of what the escalation was supposed to reveal.</p>')

    # ── 1. baseline ───────────────────────────────────────────────────────────────────
    A('<h3>1 &middot; The raw gate, before anything is filtered</h3>')
    A(table(["the population", "signals", "sessions", "net $", "$/signal", "win %",
             "strip the best 3", "worst leave-one-day-out"],
            [row([f'<strong>{b["label"]}</strong>', b["n"], f'{b["days"]} ({b["green_days"]} green)',
                  f'<strong>{money(b["net"])}</strong>', money(b["per"]), f'{b["win"]}%',
                  money(b["strip3"]), money(b["lodo"])], "row-bad")],
            "Every break the detector found on MGC from 16 July to 14 August, priced at $10.00 a "
            "point with $1.50 off each round trip. It is a coin flip that pays the fee &mdash; and "
            "strip its best three trades and it is "
            f'{money(b["strip3"])}, so even the coin flip is carried by a handful of prints.'))

    # ── 2. candidates ─────────────────────────────────────────────────────────────────
    A('<h3>2 &middot; Twenty candidate filters, and the two that are worth reading</h3>')
    A('<p>Each row is a single mechanical rule applied to the same 397 breaks. The <strong>placebo '
      'percentile</strong> is against 2,000 random subsets of the same size: below 95 means a coin '
      'could have picked as well, and <strong>below about 5 means the filter is actively selecting '
      'the wrong signals</strong>, which turns out to be the interesting column here.</p>')
    rows = []
    for c in sorted(D["candidates"], key=lambda z: -z["net"]):
        p = c["placebo"]
        cls = "row-hl" if (p or 0) >= 95 else ("row-bad" if (p or 100) <= 10 else "")
        rows.append(row([c["label"], c["n"], money(c["net"]), money(c["per"]), f'{c["win"]}%',
                         money(c["strip3"]), money(c["lodo"]),
                         f'<strong>{p}</strong>' if p is not None else "&mdash;"], cls))
    A(table(["candidate filter", "n", "net $", "$/signal", "win %", "strip-3", "worst LODO",
             "placebo %ile"], rows,
            "One row clears 95 and five rows are below 10. The rows below 10 are the hypothesis "
            "itself."))

    A('<div class="callout"><p class="ct">★ THE FINDING &mdash; an empty book ahead of a gold break is '
      'a WARNING, not a green light</p>'
      '<p>Read the bottom of that table, not the top. <strong>&ldquo;Far side is empty&rdquo; loses '
      '&minus;$2,059.50 over 192 signals and sits at the 4.8th percentile of its placebo.</strong> '
      '&ldquo;Far side thin&rdquo; is the 3.7th. &ldquo;Empty far side AND a clean trend&rdquo; is the '
      '3.6th and loses &minus;$27.91 a go. Being in the 4th percentile is not noise &mdash; it means '
      'that of 2,000 random ways to pick 192 of these breaks, 1,904 of them did BETTER. The feature '
      'carries real information and <strong>the sign is the other way round</strong>: on gold, a level '
      'that breaks into a vacuum is a level nobody is defending because nobody is there, and price '
      'comes straight back. That is a refutation of the gate as specified, and simultaneously the most '
      'promising thing in this section &mdash; it is a <em>fade</em> lead, not a break lead, and it is '
      'PARKED as one.</p></div>')

    # ── 3. the one that works ─────────────────────────────────────────────────────────
    A('<h3>3 &middot; The one filter that separates &mdash; and why it is still not a gate</h3>')
    A('<p>Resting book imbalance is the exception. Skew the book our way at the moment of the break '
      'and the population turns from &minus;$291 to +$1,795 over 134 signals, at the 96th percentile '
      'of its placebo, still +$590 after stripping its best three and still +$970 after dropping its '
      'best day. That is the only row in the study that survives all four checks. Then you cut it '
      'finer and it falls over:</p>')
    rows = [row([s["label"], s["n"], money(s["net"]), f'<strong>{money(s["per"])}</strong>',
                 f'{s["win"]}%', money(s["strip3"]), money(s["lodo"])],
                "row-hl" if s["net"] > 500 else ("row-bad" if s["net"] < 0 else ""))
            for s in D["book_sep"]]
    A(table(["book imbalance at the break", "n", "net $", "$/signal", "win %", "strip-3",
             "worst LODO"], rows,
            "<strong>This is the killer column and it is the fourth row.</strong> If book imbalance "
            "were a real mechanism, more of it would be better. It is not: the +0.10 to +0.25 band "
            "makes $19.32 a signal and the band ABOVE it &mdash; the book most strongly on our side "
            "&mdash; loses money. An edge that lives in one middle bucket and dies on either side of "
            "it is a bucket, not a mechanism.")
      )

    # ── 4. the escalation ─────────────────────────────────────────────────────────────
    A('<h3>4 &middot; The escalation &mdash; full census, then the top 25, then the top 15</h3>')
    A('<p>The scope&rsquo;s instruction is explicit and it exists because marginal moves wash out the '
      'footprint the monsters might carry: if nothing works on everything, narrow to the biggest moves '
      'and hunt again. <strong>Here the escalation runs the wrong way</strong>, which is a result in '
      'itself.</p>')
    for lvl in D["escalation"]:
        bb = lvl["base"]
        rows = [row([f'<strong>no filter &mdash; {lvl["level"]}</strong>', bb["n"],
                     f'<strong>{money(bb["net"])}</strong>', money(bb["per"]), f'{bb["win"]}%',
                     money(bb["strip3"]), "&mdash;"], "row-bad" if bb["net"] < 0 else "row-hl")]
        for s in lvl["best"]:
            p = s["placebo"]
            rows.append(row([s["label"], s["n"], money(s["net"]), money(s["per"]), f'{s["win"]}%',
                             money(s["strip3"]), f'{p}' if p is not None else "&mdash;"],
                            "row-hl" if (p or 0) >= 95 else ""))
        A(f'<h4>{lvl["level"]}</h4>')
        A(table(["rule", "n", "net $", "$/signal", "win %", "strip-3", "placebo %ile"], rows))
    A('<p><strong>Read the three tables together.</strong> On the full population the imbalance rule '
      'makes +$1,795 and survives strip-3 at +$590. Narrow to the 25 biggest moves and it still shows '
      '+$992.50 &mdash; but strip its best three and it is <strong>&minus;$212.50</strong>, i.e. the '
      'whole thing is three prints. Narrow again to the top 15 and <strong>every single rule is '
      'negative</strong>; the best of them loses &minus;$54.00. The footprint does not get cleaner as '
      'the moves get bigger. It gets worse. Whatever separates gold breaks, it is not something that '
      'concentrates in the monsters &mdash; and that is a genuinely useful thing to know before anyone '
      'spends another night on it.</p>')

    # ── 5. excursion ──────────────────────────────────────────────────────────────────
    A('<h3>5 &middot; The excursion statistic &mdash; why no stop can save this</h3>')
    e = D["excursion"]
    A(table(["what was measured", "value", "what it means"],
            [row(["median favourable excursion", f'<strong>{e["median_mfe_atr"]}&times;ATR</strong>',
                  "the typical break does eventually go our way by about three ATR"]),
             row(["median adverse excursion", f'<strong>{e["median_mae_atr"]}&times;ATR</strong>',
                  "&hellip; and goes against us by almost exactly the same amount first"], "row-bad"),
             row(["signals reaching 2&times;ATR our way", f'{e["mfe_ge_2atr_pct"]}%',
                  "two-thirds do offer a real move at some point"]),
             row(["signals going 1&times;ATR against us first", f'<strong>{e["mae_ge_1atr_pct"]}%</strong>',
                  "four-fifths hurt before they help &mdash; this is the number that kills it"],
                 "row-bad"),
             row(["signals that &lsquo;ran&rsquo;", f'{e["ran_pct"]}%',
                  "a coin flip, by the detector's own definition"])],
            "<strong>Median MFE 3.28 ATR against median MAE &minus;3.04 ATR is a symmetric "
            "distribution.</strong> There is no asymmetry to build a stop around: any stop tight "
            "enough to make the losers small takes out 80% of the population before it works, and any "
            "stop wide enough to survive costs more than the winners pay. This single table is why "
            "the exit rehabilitation that rescued exhaustion_short in Part 1.5 cannot rescue this "
            "&mdash; there, the entry beat 60 of 60 random controls; here, the entry is the coin flip."))

    # ── 6. day by day ─────────────────────────────────────────────────────────────────
    A('<h3>6 &middot; Day by day &mdash; the whole sample, nothing hidden</h3>')
    rows = [row([d["day"], d["n"], money(d["net"])], "row-bad" if d["net"] < 0 else "")
            for d in D["by_day"]]
    A(table(["session", "breaks", "net $"], rows,
            f'{sum(1 for d in D["by_day"] if d["net"] > 0)} green sessions of {len(D["by_day"])}. '
            "No week, no session and no regime rescues it."))

    A('<h3>7 &middot; Regime and session splits</h3>')
    rows = [row([s["label"], s["n"], money(s["net"]), money(s["per"]), f'{s["win"]}%',
                 money(s["strip3"])], "row-bad" if s["net"] < 0 else "")
            for s in sorted(D["regime"] + D["session"], key=lambda z: -z["net"])]
    A(table(["cut", "n", "net $", "$/signal", "win %", "strip-3"], rows,
            "CLEAN_TREND &mdash; the regime the whole idea assumed &mdash; is the worst cut in the "
            "study at &minus;$21.99 a signal. Asia is the least-bad, which is a liquidity story "
            "rather than a mechanism, and it does not survive strip-3."))

    # ── 8. reconciliation with the census ─────────────────────────────────────────────
    A('<h3>8 &middot; Against the census &mdash; the big-moves-caught column</h3>')
    A(f'<p>Movement&nbsp;1 froze <strong>{C["runs"]} big runs on MNQ</strong> this week of which we '
      f'<strong>sat out {C["sat_out"]}</strong>, carrying a hindsight ceiling of '
      f'<strong>{money(C["ceiling"], 0)}</strong> on a single lot. <strong>This section catches none '
      'of them, and it was never going to</strong> &mdash; it is a gold gate and that ceiling is a '
      'Nasdaq number. The honest big-moves-caught line for Movement&nbsp;3 this week is '
      '<strong>0 of 60, because the four hunts aimed at those 60 runs did not run.</strong> '
      'Movement&nbsp;2 is the only part of the report that engaged with them, and its verdict was an '
      'honest null: six mechanical fires for +$15.50, &minus;$94.50 once the best is stripped.</p>')
    rows = [row([k, v, money(round(C["ceiling"] * v / C["runs"]), 0) + " (pro-rata)"])
            for k, v in sorted(C["clusters"].items(), key=lambda z: -z[1])]
    A(table(["cause cluster", "runs this week", "share of the ceiling"], rows,
            "The cluster-by-cluster hunt these were frozen for is the work that did not happen. "
            "OPEN/NEWS at 22 runs is the largest addressable block and has never had a dedicated "
            "hunt on this week's tape."))

    # ── 9. disposition ────────────────────────────────────────────────────────────────
    A('<h3>9 &middot; DISPOSITION &mdash; every lead touched in this movement</h3>')
    disp = [
        ("MGC far-side depletion as a BREAK-CONTINUATION gate", "REFUTED",
         "Named test: 2,000-draw random-subset placebo on n=192. &minus;$2,059.50 at the "
         "<strong>4.8th percentile</strong> &mdash; 1,904 of 2,000 random picks did better, so the "
         "feature carries information and the sign is inverted. No reformulation saves it AS A BREAK "
         "SIGNAL; the reformulation is the next row."),
        ("Fade the gold break when the far side is empty", "PARKED &mdash; the reformulation",
         "The inverse of the refuted rule is +$2,059.50 gross on 192 signals before it is a strategy. "
         "Revive by: building it as a FADE with its own entry timing and stop, and re-testing on a "
         "held-out window &mdash; an inverted backtest is a hypothesis, not a result."),
        ("MGC book imbalance (+0.10 to +0.25) at the break", "PARKED",
         "The only cut that clears its placebo (96.2nd percentile, +$1,795, strip-3 +$590, LODO "
         "+$970). Parked not shadowed because the band above it LOSES money &mdash; a non-monotone "
         "response is a bucket, not a mechanism. Revive if: it stays positive on 4+ untouched weeks "
         "AND the &gt;0.25 band stops being negative."),
        ("The size escalation (top 25 / top 15)", "REFUTED as a route to this edge",
         "Named test: re-running all 20 filters at each narrowing. Top-25 best cell is three prints "
         "(strip-3 &minus;$212.50); at top-15 every rule is negative. The footprint does not "
         "concentrate in the monsters, so narrowing further is not the answer here."),
        ("An exit fix for the MGC break gate", "REFUTED",
         "Named test: the excursion table. Median MFE +3.28 ATR against median MAE &minus;3.04 ATR "
         "with 80.4% going a full ATR against us first. The distribution is symmetric &mdash; there "
         "is no stop that makes it work, unlike exhaustion_short in Part 1.5."),
        ("MNQ VACUUM-cluster greenfield hunt", "NOT RUN &mdash; measurement gap",
         "Phase never started (budget exhausted). 8 runs this week. First thing to reschedule."),
        ("MNQ FLOW-LED-cluster greenfield hunt", "NOT RUN &mdash; measurement gap",
         "Phase never started. Only 2 runs this week, so it is also the lowest-value of the four."),
        ("MNQ OPEN/NEWS-cluster greenfield hunt", "NOT RUN &mdash; measurement gap",
         "Phase never started. <strong>22 runs &mdash; the largest addressable cluster of the "
         "week</strong> and the highest-value hunt not done."),
        ("The chop-day scalp lab", "NOT RUN &mdash; measurement gap",
         "Phase never started. Relevant: Movement 2 found this week's runs ignited out of unusually "
         "quiet tape, which is exactly the population this lab was for."),
        ("MGC day rider / coil bouncer / London break fade", "SEE PART 2.5",
         "Not missing &mdash; relocated. Both SHADOW gold candidates of the week are dispositioned "
         "in Part 2.5 Part A, which completed."),
    ]
    A(table(["Lead", "Verdict", "The named test, or what would revive it"],
            [row([f'<strong>{a}</strong>', f'<span class="tag">{v}</span>', w])
             for a, v, w in disp]))

    A('<div class="callout"><p class="ct">★ THE ONE STONE STILL UNTURNED</p>'
      '<p>Both of this movement&rsquo;s honest verdicts point at the same missing piece and it is not '
      'another feature. <strong>It is the OPEN/NEWS cluster on MNQ &mdash; 22 of this week&rsquo;s 68 '
      'runs, roughly a third of an $8,024 ceiling, and no gate on this desk has ever been built for '
      'it.</strong> That hunt was scheduled tonight, was fifth in the queue, and the queue ran out. It '
      'costs one phase to find out and it should be first next week, ahead of any further gold '
      'work.</p></div>')

    return "\n".join(o)


if __name__ == "__main__":
    html = build()
    pathlib.Path(OUT).write_text(html)
    import re
    print(f"wrote {OUT}  {len(html):,} bytes  "
          f"~{len(re.sub(r'<[^>]+>', ' ', html).split()):,} words")
