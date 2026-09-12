#!/usr/bin/env python3
"""MOVEMENT 2 — THE IDLE-GATE LAB, week of 2026-08-17 .. 2026-08-21.

Renders the section from the two artefacts the lab itself produced this week:
  reports/friday_v7/sections/movement2_idle_gates.json  — all six gates fired MECHANICALLY at
      each of the 65 sat-out runs Movement 1 found, in the 10 min before ignition and the 5 min
      after, in their exact live config AND with every suppressor removed
  reports/friday_v7/sections/movement2_basefire.json    — the same six gates fired across the
      ENTIRE captured week, which is the honest denominator

Both are tick-honest off capture.db at $1.50/round-trip/lot and $2.00/point, and the census
window sits entirely inside capture.db's 5-trading-day rolling window (asserted at lab startup).

  PYTHONPATH=src .venv/bin/python scripts/fv7_m2_idle.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from fv7_common import (SEC, callout, correction, disposition, esc, m, pct, strip_best,  # noqa
                        table, write)

GATES = ("grind_long", "capitulation_long", "abs_veto_long", "rgv_short", "exhaustion_short",
         "abs_veto_short")
ARMS = (("pre_live", "10 min BEFORE ignition &middot; live config"),
        ("pre_ungated", "10 min BEFORE &middot; every suppressor removed"),
        ("post_live", "5 min AFTER ignition &middot; live config"),
        ("post_ungated", "5 min AFTER &middot; ungated"))


def fills(runs, arm, gate=None):
    return [f for r in runs for g in ([gate] if gate else GATES)
            for f in r["arms"][arm][g]["fills"]]


def main():
    d = json.load(open(f"{SEC}/movement2_idle_gates.json"))
    bf = json.load(open(f"{SEC}/movement2_basefire.json"))
    runs, meta = d["runs"], d["meta"]

    ceil = sum(r["ceil"] for r in runs)
    pts = sum(abs(r["move"]) for r in runs)
    clusters = {}
    for r in runs:
        clusters[r["cluster"]] = clusters.get(r["cluster"], 0) + 1

    # ── the four arms ────────────────────────────────────────────────────────────────────
    arm_rows = []
    for arm, lbl in ARMS:
        fl = fills(runs, arm)
        v = round(sum(f["usd"] for f in fl), 2)
        hit = sum(1 for r in runs if any(r["arms"][arm][g]["fills"] for g in GATES))
        wins = sum(1 for f in fl if f["usd"] > 0)
        arm_rows.append([("", "row-bad" if v < 0 else "row-hl")] + [
            lbl, f"{hit} / {len(runs)}", str(len(fl)), m(v),
            m(round(v / len(fl), 2)) if fl else "&mdash;",
            pct(100 * wins / len(fl)) if fl else "&mdash;",
            m(strip_best([f["usd"] for f in fl], 1)) if fl else "&mdash;"])
    arms_t = table(["Arm", "Runs it showed up for", "Fires", "Net", "$ / fire", "Win %",
                    "Best fire stripped"], arm_rows, numeric=set(range(1, 7)))

    # ── per gate, the two live arms ──────────────────────────────────────────────────────
    g_rows = []
    for g in GATES:
        pre = fills(runs, "pre_live", g)
        post = fills(runs, "post_live", g)
        base = bf[g]["fills"]
        pv, sv, bv = (round(sum(f["usd"] for f in x), 2) for x in (pre, post, base))
        g_rows.append([("", "row-bad" if pv + sv < 0 else "row-hl")] + [
            f"<code>{esc(g)}</code>",
            f"{len(pre)} &middot; {m(pv)}", f"{len(post)} &middot; {m(sv)}",
            f"{len(base)} &middot; {m(bv)}",
            m(round(bv / len(base), 2)) if base else "&mdash;",
            f"{bf[g]['raw']:,}",
            "; ".join(f"{esc(k)} &times;{n:,}" for k, n in bf[g]["blocked"].items()) or "&mdash;"])
    gates_t = table(["Gate", "Before ignition", "After ignition", "Whole week (base rate)",
                     "$ / fire, base rate", "Raw signals", "What its own filters blocked"],
                    g_rows)

    base_all = round(sum(f["usd"] for g in GATES for f in bf[g]["fills"]), 2)
    base_n = sum(len(bf[g]["fills"]) for g in GATES)
    pre_fl = fills(runs, "pre_live")
    pre_v = round(sum(f["usd"] for f in pre_fl), 2)

    # ── by cluster ───────────────────────────────────────────────────────────────────────
    cl_rows = []
    for c in sorted(clusters, key=lambda c: -clusters[c]):
        rs = [r for r in runs if r["cluster"] == c]
        fl = [f for r in rs for g in GATES for f in r["arms"]["pre_live"][g]["fills"]]
        v = round(sum(f["usd"] for f in fl), 2)
        cl_rows.append([("", "row-bad" if v < 0 else "row-hl")] + [
            esc(c), str(len(rs)), f"{sum(abs(r['move']) for r in rs):,} pt",
            m(sum(r["ceil"] for r in rs)), str(len(fl)), m(v)])
    cl_t = table(["Cause cluster", "Runs", "Points in them", "Ceiling if perfectly caught",
                  "Mechanical fires", "What those fires made"], cl_rows,
                 numeric=set(range(1, 6)))

    # ── direction alignment ──────────────────────────────────────────────────────────────
    al = {"with": [], "against": []}
    for r in runs:
        for g in GATES:
            for f in r["arms"]["pre_live"][g]["fills"]:
                same = (f["side"] == "LONG") == (r["dir"] == "UP")
                al["with" if same else "against"].append(f["usd"])
    align = table(["The mechanical fire was&hellip;", "Fires", "Net", "$ / fire", "Win %"],
                  [[("", "row-bad" if sum(v) < 0 else "row-hl")] + [
                      k, str(len(v)), m(round(sum(v), 2)),
                      m(round(sum(v) / len(v), 2)) if v else "&mdash;",
                      pct(100 * sum(1 for x in v if x > 0) / len(v)) if v else "&mdash;"]
                   for k, v in (("pointing the SAME way the run then went", al["with"]),
                                ("pointing the OPPOSITE way", al["against"]))],
                  numeric={1, 2, 3, 4})

    doc = f"""
<h2 id="m2"><span class="n">M2</span> THE IDLE-GATE LAB &mdash; could the gates we already own
have caught them?</h2>

<p class="lead">Garrath &mdash; Movement&nbsp;1 found {len(runs)} big runs this week that the desk
sat out completely: {pts:,} points of movement, worth {m(ceil)} if they had been caught perfectly.
The obvious question is whether the six gates we already own would have caught any of them if
they had simply been left armed. <strong>The answer is a clean and rather uncomfortable no.</strong>
Fired mechanically into those runs, in their exact live configuration, they lose
{m(abs(pre_v))}. Fired across the whole week rather than only near the runs, they lose
{m(abs(base_all))}. <strong>Not arming them was worth more than any entry idea in this
report.</strong></p>

<h3>1 &middot; The method, and the one thing that makes it honest</h3>

<p>Each of the {len(runs)} sat-out runs gets four independent simulations: the six gates fired
mechanically in the <strong>{meta['pre_s'] // 60} minutes before</strong> the run ignited (which is
the interesting one &mdash; catching a run means being in before it goes), and in the
<strong>{meta['post_s'] // 60} minutes after</strong>; each of those both in the exact live config
and <strong>ungated</strong>, meaning every ATR floor, veto and confirmation stripped out. Exits
are the live <code>scaleout</code> slate plus <code>exit_overrides.json</code>, raced on real
ticks at ${meta['fee']:.2f} per round trip and ${meta['vpp']:.2f} a point.</p>

<p>The thing that makes it honest is the <strong>base-rate control</strong>. Measuring a gate only
in windows we already know contained a big run is hindsight selection &mdash; it counts the fires
where the move existed and never counts the ones where it did not. So the same six gates are also
fired across the <em>entire</em> captured week, every fire counted. That control is the reason this
section can say something the last three idle-gate labs could not.</p>

<h3>2 &middot; The four arms</h3>

{arms_t}

<p class="ln">Every arm loses. Read the first two rows together: with their live filters on, the
gates show up for {sum(1 for r in runs if any(r['arms']['pre_live'][g]['fills'] for g in GATES))}
of the {len(runs)} runs and lose {m(abs(pre_v))}; strip every filter off and they show up for
{sum(1 for r in runs if any(r['arms']['pre_ungated'][g]['fills'] for g in GATES))} runs, take
{len(fills(runs, 'pre_ungated'))} fires, and lose
{m(abs(round(sum(f['usd'] for f in fills(runs, 'pre_ungated')), 2)))}. <strong>Removing the
suppressors triples the activity and makes the result worse</strong>, which is the strongest
defence of the gates' own filters this desk has produced.</p>

<p class="ln">The one nearly-flat row is the most interesting: fired <em>after</em> ignition with
live filters on, the gates lose only
{m(abs(round(sum(f['usd'] for f in fills(runs, 'post_live')), 2)))} across
{len(fills(runs, 'post_live'))} fires. Joining a run once it has already started is roughly free;
predicting one costs money. That is the same shape the greenfield lab reports from a completely
different direction in Movement&nbsp;3.</p>

<h3>3 &middot; Gate by gate, with the base rate beside it</h3>

{gates_t}

<p class="ln">Whole week, all six gates, every fire counted:
<strong>{m(base_all)} on {base_n} fires</strong>. That is the number to quote when anyone asks what
the standdown was worth. And look at the raw-signal column, because it explains the shape of this
entire report: <code>grind_long</code> generated {bf['grind_long']['raw']:,} raw signals this week
and its own 22-point ATR floor blocked {list(bf['grind_long']['blocked'].values())[0]:,} of them.
The gate is not benched by anybody's decision; it is benched by its own arithmetic.</p>

<h3>4 &middot; Which kinds of run, and did direction even matter?</h3>

{cl_t}

{align}

<p class="ln">This is the part that closes the &ldquo;just leave them armed&rdquo; argument for
good. The mechanical fires that happened to point the <em>same</em> way the run then went made
{m(round(sum(al['with']), 2))} across {len(al['with'])} fires. <strong>Being right about the
direction was not enough.</strong> The gates enter on their own triggers, which fire during the
chop before the move rather than at the ignition, so an aligned fire still gets stopped out in the
noise and is not there when the run happens.</p>

{correction("★ THE SURVIVORSHIP TRAP THIS LAB EXISTS TO AVOID — and it cuts BOTH ways",
 f"Last cycle's idle-gate lab reported a small positive and it was survivorship: the gates looked "
 "good because of which ones happened to be idle in the windows chosen. This week the base-rate "
 "control was built specifically to close that, and it does — but note that it closes the "
 "flattering reading AND the damning one.",
 f"In the run windows the gates make {m(round(pre_v / max(len(pre_fl), 1), 2))} a fire. Across the "
 f"whole week they make {m(round(base_all / base_n, 2))} a fire. Those are close, which is itself "
 "the finding: <strong>there is nothing special about the tape near a big run from these gates' "
 "point of view.</strong> They lose at about the same rate everywhere. If the run windows had "
 "looked much worse than the base rate, the story would be 'the gates are actively bad near "
 "runs'; if much better, 'they nearly work and need help'. Neither is true.",
 "So the honest conclusion is narrow and it should not be over-read: these six gates, at these "
 "settings, on THIS week's tape, do not contain a run-catcher. It is one week, the desk was stood "
 "down for most of it, and a genuine trend week could look different. What it does license is "
 "leaving them benched for now, which is what is already happening.")}

<h3>5 &middot; What this section does NOT say</h3>

<p>It does not say the {m(ceil)} in those {len(runs)} runs is unreachable &mdash; Movement&nbsp;3
takes a different route at it and finds a size threshold that pays. It does not say the gates are
worthless; two of them traded live this week and one of them was green. And it emphatically does
not say &ldquo;arm nothing forever&rdquo;: it says that <em>this particular six-gate roster, fired
mechanically, is not the tool for catching runs</em>, and that the tool will have to be built
rather than switched on.</p>

{disposition([
 ("Leave the six live gates armed to catch big runs", "REFUTED",
  f"Named test: {len(runs)} sat-out runs, four arms, plus a whole-week base-rate control. Every "
  f"arm negative; live config {m(pre_v)} in the run windows and {m(base_all)} across the week."),
 ("Strip the gates' filters so they show up more often", "REFUTED",
  "Ungated triples the fire count and makes the result worse in both windows. The ATR floors and "
  "vetoes are earning their keep."),
 ("Join a run AFTER ignition rather than predicting it", "SHADOW",
  f"The post-ignition live arm is nearly flat at "
  f"{m(round(sum(f['usd'] for f in fills(runs, 'post_live')), 2))} on "
  f"{len(fills(runs, 'post_live'))} fires, against a clearly negative pre-ignition arm. That is "
  "the only asymmetry in the whole lab. Shadow an ignition-confirmed entry and let it accumulate n."),
 ("Direction alignment as a permission rule", "REFUTED",
  f"Aligned mechanical fires made {m(round(sum(al['with']), 2))} on {len(al['with'])} fires. "
  "Knowing which way the run would go was not enough, because the gates fire before the ignition "
  "and get stopped in the chop."),
 ("The 22-point ATR floor on grind_long", "PARKED",
  f"It blocked {list(bf['grind_long']['blocked'].values())[0]:,} of "
  f"{bf['grind_long']['raw']:,} raw signals this week. Revive with the floor ladder proposed in "
  "Part 2.5 — this lab cannot say whether 22 is right, only that it binds almost everything."),
])}
"""
    write("movement2_idle_gates.html", doc.strip())
    print(f"\nruns {len(runs)} ceiling {ceil} pts {pts}")
    for arm, _ in ARMS:
        fl = fills(runs, arm)
        print(f"  {arm:14} n={len(fl):3d} {sum(f['usd'] for f in fl):+9.2f}")
    print(f"base rate {base_all} on {base_n}")
    print(f"aligned {sum(al['with']):+.2f} n={len(al['with'])}  against {sum(al['against']):+.2f} n={len(al['against'])}")


if __name__ == "__main__":
    main()
