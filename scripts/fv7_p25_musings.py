#!/usr/bin/env python3
"""PART 2.5 — MID-WEEK MUSINGS, week of 2026-08-17 .. 2026-08-21.

The leads the desk chat and the mid-week labs threw up, each tested hard rather than inherited.
Source artefacts are this week's own: reports/friday_v7/p25/*.json, written 2026-08-21 22:57–23:13Z.

⚠ MGC IS $10.00 PER POINT. Every gold figure below comes out of the p25 lab already in dollars;
the sanity check is printed in §4 (a median gold trade of −$133 is −13.3 points, which is a
normal gold day-trade excursion; at the MNQ multiplier it would be −66 points, which is not).

  PYTHONPATH=src .venv/bin/python scripts/fv7_p25_musings.py
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import statistics as st
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from fv7_common import (CAP_DB, callout, correction, disposition, esc, m, m0, pct,  # noqa
                        table, write)

P25 = "/home/alphabot/gazbot7/reports/friday_v7/p25"


def load(n):
    return json.load(open(f"{P25}/{n}.json"))


def floor_reality():
    """Re-derive grind's 22-point floor reachability independently of the p25 lab, off
    capture.db's own 5s bars. Two windows disagreeing is worth printing; one window quoted as
    fact is not."""
    con = sqlite3.connect(f"file:{CAP_DB}?mode=ro", uri=True)
    rows = con.execute("SELECT bar_ts,high,low,close FROM bars WHERE symbol='MNQ' "
                       "ORDER BY bar_ts").fetchall()
    con.close()
    mins = {}
    for bt, h, l, c in rows:
        k = bt // 60 * 60
        if k in mins:
            mins[k][0] = max(mins[k][0], h)
            mins[k][1] = min(mins[k][1], l)
            mins[k][2] = c
        else:
            mins[k] = [h, l, c]
    prev, trs, atr = None, [], []
    for k in sorted(mins):
        h, l, c = mins[k]
        trs.append(max(h - l, abs(h - prev), abs(l - prev)) if prev is not None else h - l)
        prev = c
        if len(trs) >= 14:
            atr.append((k, sum(trs[-14:]) / 14))
    byday = {}
    for k, a in atr:
        byday.setdefault(dt.datetime.fromtimestamp(k, dt.UTC).strftime("%Y-%m-%d"), []).append(a)
    v = [a for _, a in atr]
    return {
        "mins": len(v), "days": len(byday),
        "lo": min(byday), "hi": max(byday),
        "med": st.median(v), "p90": sorted(v)[int(.9 * len(v))],
        "pct22": 100 * sum(1 for a in v if a >= 22) / len(v),
        "pct10": 100 * sum(1 for a in v if a >= 10) / len(v),
        "d_any": sum(1 for d in byday.values() if max(d) >= 22),
        "d_25": sum(1 for d in byday.values()
                    if 100 * sum(1 for a in d if a >= 22) / len(d) >= 25),
    }


def main():
    gm, dt_, afr = load("grind_mechanisms"), load("mnq_day_types"), load("atr_floor_reality")
    coil, revive = load("mgc_coil_anchor"), load("mgc_coil_revive")
    plateau, exitm = load("mgc_stop_plateau"), load("mgc_exit_fixed")
    oos, leads, stay = load("mgc_rider_oos"), load("rider_leads"), load("stayout")
    fr = floor_reality()

    # ── LEAD 1 — the grind trend-day mechanism ───────────────────────────────────────────
    base = gm["base"]
    mech_rows = [[("", "row-bad")] + [
        "<strong>Every live grind fire (the control)</strong>", str(base["n"]), m(base["net"]),
        m(base["per"]), pct(base["win"]), f"{base['keeps']} / {base['of']}",
        m(base["strip3"]), m(base["loo"])]]
    for grp, lbl in (("a", "day-type arming"), ("b", "directional-net requirement"),
                     ("c", "efficiency-ratio floor"), ("s", "the two stacked")):
        for x in gm[grp]:
            mech_rows.append([("", "row-bad" if x["strip3"] < 0 else "row-hl")] + [
                f"{esc(x['tag'])} <span class=\"tag\">{lbl}</span>", str(x["n"]), m(x["net"]),
                m(x["per"]), pct(x["win"]), f"{x['keeps']} / {x['of']}",
                m(x["strip3"]), m(x["loo"])])
    mech = table(["Mechanism", "Fires kept", "Net", "$ / fire", "Win %",
                  "Winners kept", "Best 3 stripped", "Leave-one-out"], mech_rows,
                 numeric=set(range(1, 8)))

    best_a = max(gm["a"], key=lambda x: x["net"])
    best_s = max(gm["s"], key=lambda x: x["net"])

    dtypes = table(["Day type", "Days", "Share of 240"],
                   [[esc(k), str(v), pct(100 * v / dt_["n"], 1)]
                    for k, v in sorted(dt_["counts"].items(), key=lambda kv: -kv[1])],
                   numeric={1, 2})

    # ── LEAD 3 — the gold programme ──────────────────────────────────────────────────────
    coil_rows = []
    for k in ("REVERSION (fade the coil edge → mid)", "CONTINUATION (break out) [mirror control]"):
        x = coil[k]
        coil_rows.append([("", "row-bad")] + [
            esc(k), str(x["n"]), str(x["days"]), m(x["net"]), m(x["exp"]), pct(x["win"], 1),
            m(x["strip3"]), m(x["strip_best_day"])])
    pl = coil["placebo"]
    coil_t = table(["Gold coil arm", "n", "Sessions", "Net", "$ / trade", "Win %",
                    "Best 3 stripped", "Best day stripped"], coil_rows, numeric=set(range(1, 8)))

    rev_rows = [[("", "row-hl" if x["net"] > 0 else "row-bad")] + [
        f"compression &le; {x['compress']}", f"{x['tgt']}&times;", str(x["n"]),
        m(x["net"]), m(x["net_per"]), pct(x["win"], 1)] for x in revive]
    rev_t = table(["Coil tightness", "Target", "n", "Net", "$ / trade", "Win %"], rev_rows,
                  numeric=set(range(2, 6)))
    best_rev = max(revive, key=lambda x: x["net"])

    pl_rows = [[("", "row-hl" if v["net"] > 0 else "row-bad")] + [
        f"<strong>{k}</strong>", str(v["stops"]), m(v["net"]), m(v["per"]), pct(v["win"], 1),
        m(v["strip3"]), m(v["loo"])] for k, v in plateau.items()]
    pl_t = table(["Gold stop width", "Stopped out", "Net", "$ / session", "Win %",
                  "Best 3 stripped", "Leave-one-out"], pl_rows, numeric=set(range(1, 7)))

    ex_rows = [[("", "row-hl" if v["net"] > 0 else "row-bad")] + [
        esc(k), m(v["net"]), m(v["per"]), pct(v["win"], 1), m(v["worst"]), m(v["strip3"]),
        m(v["loo_min"]), ", ".join(f"{a}&times;{b}" for a, b in v["why"].items())]
        for k, v in sorted(exitm.items(), key=lambda kv: -kv[1]["net"])]
    ex_t = table(["Gold exit", "Net", "$ / session", "Win %", "Worst session",
                  "Best 3 stripped", "Worst leave-one-out", "How they ended"], ex_rows,
                 numeric=set(range(1, 7)))

    oos_rows = []
    for k in ("is_loose", "oos_loose", "all_loose", "is_der", "oos_der", "all_der"):
        x = oos[k]
        oos_rows.append([("", "row-hl" if x["net"] > 0 else "row-bad")] + [
            ("loose trigger" if "loose" in k else "derived trigger") + " &mdash; " + esc(x["tag"]),
            str(x["n"]), str(x["days"]), pct(x["fire"], 1), m(x["net"]), m(x["per"]),
            f"{x['mfe_med']:,.0f} / {x['mae_med']:,.0f}"])
    oos_t = table(["Gold rider arm", "Fires", "Sessions", "Fire rate", "Net", "$ / fire",
                   "Median MFE / MAE ($)"], oos_rows, numeric=set(range(1, 6)))
    ctrl = oos["ctrl_OUT-OF-SAMPLE"]

    # ── LEAD 4 — the MNQ rider leads ─────────────────────────────────────────────────────
    pub = leads["published"]
    lead_rows = []
    for k, lbl in (("all", "every session it fired"), ("in", "inside the window"),
                   ("out", "outside it")):
        x = pub[k]
        lead_rows.append([("", "row-hl" if x["net2"] > 0 else "row-bad")] + [
            lbl, str(x["n"]), pct(x["held"], 1), m(x["net2"]), m(x["per2"]),
            m(x["med2"]), m(x["strip3"])])
    lead_t = table(["Open-rider population", "Sessions", "Held to the clock %", "Net at 2 lots",
                    "$ / session", "Median session", "Best 3 stripped"], lead_rows,
                   numeric=set(range(1, 7)))

    sp = stay["published"]
    sc = stay["corrected"]

    doc = f"""
<h2 id="p25"><span class="n">P2.5</span> MID-WEEK MUSINGS &mdash; every lead from the week, tested
until it broke</h2>

<p class="lead">Garrath &mdash; four leads came out of the week's chats and mid-week labs, and this
section exists to test them hard rather than repeat them. <strong>One of them dies in a way that
is genuinely useful:</strong> the &ldquo;only run grind on a clean trend day&rdquo; idea works on
paper, makes +$580 where the control loses $958, and then turns out to be un-runnable, because the
gate's own ATR floor and the clean-trend condition almost never happen on the same day. That is a
better answer than either a yes or a no, and it changes what the Saturday question is.</p>

<h3>1 &middot; LEAD ONE &mdash; should grind only run on a confirmed trend?</h3>

<p>The mechanism lab took every live grind fire in the record &mdash; {base['n']} of them, losing
{m(abs(base['net']))} between them &mdash; and asked which permission rule would have kept the
winners while dropping the churn. Four families of rule, each scored on the same fires, with the
winner-retention column carried all the way through because a rule that improves the total by
throwing away winners is a fake:</p>

{mech}

<p class="ln">Read the last three columns, not the third. The best day-type rule
(<em>{esc(best_a['tag'])}</em>) turns {m(base['net'])} into <strong>{m(best_a['net'])}</strong>
&mdash; and then strip its best three fires and it is {m(best_a['strip3'])}, leave one day out and
the worst fold is {m(best_a['loo'])}. It keeps {best_a['keeps']} of the {best_a['of']} winners,
so it is not a fake win; it is a real effect with no robustness underneath it. The stacked version
(<em>{esc(best_s['tag'])}</em>) is nominally the best cell in the whole table at
{m(best_s['net'])} on n={best_s['n']}, and it keeps only {best_s['keeps']} of {best_s['of']}
winners. Neither is deployable.</p>

<p class="ln">Note also what the b- and c-family rows say, because they close a recurring
proposal: <strong>no directional-net requirement and no ER floor rescues grind</strong>. Every
single one of them stays negative. The ER-0.35 floor that is already live keeps 35 fires and still
loses {m(gm['c'][1]['net'])}. This desk has now refuted &ldquo;fix grind with an efficiency
filter&rdquo; on three separate occasions and it should stop being proposed.</p>

{correction("★ AND THEN THE FINDING THAT ACTUALLY MATTERS — THE RULE CANNOT BE RUN",
 f"The day-type lab classified {dt_['n']} sessions. <strong>{dt_['trend_days']} of them are "
 f"clean-trend days.</strong> The number that are clean-trend AND clear grind's 22-point ATR "
 f"floor is <strong>{dt_['trend_and_atr22']}</strong>.",
 "So &ldquo;arm grind on clean-trend days&rdquo; and &ldquo;grind's ATR floor lets it fire&rdquo; "
 "are very nearly mutually exclusive conditions. A clean trend is a day that goes somewhere "
 "smoothly; the 22-point floor wants a day that is violent. The rule that scores +$580 in the "
 "table above would, in production, have armed the gate on about one day in two hundred and "
 "forty — and on the other 239 the arming decision would have been irrelevant because the floor "
 "would have refused every signal anyway.",
 "<strong>This is why the mid-week lead is neither adopted nor refuted, but reframed.</strong> "
 "The question is not &lsquo;when should grind be armed?&rsquo;. Nothing about arming is binding. "
 "The question is whether 22 is the right floor, and that has never been tested — it is a number "
 "the gate was born with.")}

<h3>2 &middot; So how reachable IS a 22-point ATR? Two independent measurements</h3>

{table(["Measurement", "Window", "Median 1-min ATR-14", "p90", "% of minutes &ge; 22pt",
        "Days with any such minute"],
 [["The p25 lab (via the parquet lake)", f"{afr['days']} sessions",
   f"{afr['med']:.2f}", f"{afr['p90']:.2f}", pct(afr['pct_min'], 1),
   f"{afr['days_ever']} of {afr['days']}"],
  ["This report, recomputed off <code>capture.db</code>'s own 5s bars",
   f"{fr['days']} sessions, {fr['lo']} &rarr; {fr['hi']}",
   f"{fr['med']:.2f}", f"{fr['p90']:.2f}", pct(fr['pct22'], 1),
   f"{fr['d_any']} of {fr['days']}"]], numeric={2, 3, 4, 5})}

<p class="ln">The two disagree &mdash; 25% of minutes against 11% &mdash; and they are measuring
different windows, so both are printed rather than one being picked. What they agree on is the
shape, and the shape is the point: <strong>the 22-point floor sits at roughly the ninetieth
percentile of one-minute ATR</strong>. On the recent window it is almost exactly p90
({fr['p90']:.2f}). A floor at p90 is not a filter, it is an off-switch that opens during
violence, and it explains every grind number in this report: 24,110 signals blocked out of 24,121
this week, no live fire since 5 August, and two grind-exit shadow watches with nothing in them.</p>

<p class="ln">One more number worth having: <strong>{fr['d_any']} of {fr['days']} days contain at
least one minute above the floor, but only {fr['d_25']} of {fr['days']} spend a quarter of the
session there.</strong> So &ldquo;the floor was reachable today&rdquo; is true almost every day and
means nothing; the floor is reachable for a few minutes of spike and then gone.</p>

<h3>3 &middot; What the week's days actually looked like</h3>

{dtypes}

<p class="ln">Two-fifths of sessions classify as clean trend, which is a lot more than the desk's
folklore assumes, and only {dt_['counts'].get('violent-whipsaw', 0)} of 240 are the violent-whipsaw
type the desk spends most of its worry on. The terciles behind the classification are a session
round-trip ratio of {dt_['terciles'][0]:.2f} and {dt_['terciles'][1]:.2f}.</p>

<h3>4 &middot; THE GOLD PROGRAMME &mdash; four arms, and gold is $10 a point</h3>

<p>Before any number: the multiplier check. The gold tables below show a median session of about
{m(plateau['5.0x']['med'])}. At $10 a point that is roughly
{abs(plateau['5.0x']['med']) / 10:.0f} points, which is an ordinary MGC day-trade excursion. At the
MNQ multiplier it would be {abs(plateau['5.0x']['med']) / 2:.0f} points, which gold does not do
intraday. <strong>The lab is priced correctly.</strong></p>

<h4>4a &mdash; The coil, and its mirror control</h4>

{coil_t}

<p class="ln">Both directions lose. Fading the coil edge loses {m(abs(coil['REVERSION (fade the coil edge → mid)']['net']))}
over {coil['REVERSION (fade the coil edge → mid)']['n']:,} trades and breaking out of it loses
{m(abs(coil['CONTINUATION (break out) [mirror control]']['net']))} &mdash; and the placebo is the
sentence that closes it: <strong>{pl['beaten']} of the random sets did worse</strong>, against a
placebo median of {m(pl['median'])}. A coil edge on gold carries no directional information in
either direction at this fidelity.</p>

<h4>4b &mdash; Except in the tightest coils, which is a PARKED lead, not a finding</h4>

{rev_t}

<p class="ln">Restrict to the tightest compression and the sign flips: {m(best_rev['net'])} at
{best_rev['tgt']}&times; on n={best_rev['n']:,}. That is a real number on real n and it is
<strong>still not a result</strong>, because it is the best cell of nine on the same data that
produced the null above, with no placebo run against it and no out-of-sample. It is PARKED with a
named revival condition: run the same placebo the full-sample arm got, and hold out a year.</p>

<h4>4c &mdash; The gold exit and stop lab</h4>

{pl_t}

{ex_t}

<p class="ln">This is the most interesting gold result and also the one most likely to be a mirage.
There is a genuine <em>plateau</em> &mdash; the stop has to be enormous before gold pays, and the
progression from 2.0&times; to 5.0&times; is monotone rather than jumpy, which is what a real
effect looks like rather than a grid artefact. But look at the two robustness columns on the best
cell: strip its best three sessions and {m(plateau['5.0x']['net'])} becomes
{m(plateau['5.0x']['strip3'])}, and the worst leave-one-out fold is {m(plateau['5.0x']['loo'])}.
<strong>Nearly the whole result is three sessions.</strong> And a 5&times;ATR stop on gold is not
really a stop; it is a disaster brake on a naked hold, which the top row of the exit table already
shows losing money.</p>

<h4>4d &mdash; The gold rider, in and out of sample &mdash; and a control that undoes it</h4>

{oos_t}

<p class="ln">The loose trigger is negative in and out of sample, which is clean. The derived
trigger is the interesting one: {m(oos['is_der']['net'])} in-sample and
<strong>{m(oos['oos_der']['net'])} out-of-sample on {oos['oos_der']['n']} fires over
{oos['oos_der']['days']} sessions</strong>. An arm that does better out of sample than in is
usually a good sign.</p>

{correction("★ BUT THE DIRECTIONAL CONTROL KILLS IT, AND IT HAS TO BE SAID ON THE SAME PAGE",
 f"The same out-of-sample window carries a plain directional control: hold gold LONG every "
 f"session and you lose <strong>{m(ctrl['long'])}</strong>; hold it SHORT every session and you "
 f"make <strong>{m(ctrl['short'])}</strong>, over {ctrl['n']} sessions.",
 f"The gold rider's out-of-sample {m(oos['oos_der']['net'])} is a rounding error against a "
 f"{m0(ctrl['short'])} short drift sitting underneath it. Any gold arm that is even slightly "
 "short-biased will look profitable on this window without carrying one gram of edge. "
 "<strong>Every gold result in this report needs its long/short mix reported next to it, and "
 "none of them currently do.</strong> That is a method fix, it is on the BUILD card, and until "
 "it lands no gold arm should be promoted to anything.")}

<h3>5 &middot; The MNQ open-rider leads, and the stay-out meter</h3>

{lead_t}

<p class="ln">The open rider, replayed across {pub['sessions']} sessions at two lots, loses
{m(abs(pub['all']['net2']))}. Split it by the window lead and the &ldquo;inside&rdquo; population
makes {m(pub['in']['net2'])} on {pub['in']['n']} sessions while &ldquo;outside&rdquo; loses
{m(abs(pub['out']['net2']))} on {pub['out']['n']}. That looks like the window is the whole story
until the strip-best-3 column: the inside population goes to {m(pub['in']['strip3'])}.
<strong>Three sessions are the entire lead.</strong> REFUTED as a session filter on this evidence.</p>

<p class="ln">The stay-out meter's direction call, on the same population: when its two reads
agree it is right {pct(sp['agree_hit'], 1)} of the time over {sp['agree_n']} sessions, which is a
coin. Split by call, its UP calls hit {pct(sp['up_rate'], 1)} and its DOWN calls
{pct(sp['dn_rate'], 1)} &mdash; and that gap is the same short drift the gold control just
exposed, not skill. The {sp['mixed_n']} mixed-signal sessions average
{m(sp['mixed_mean'])}. The corrected series ({sc['n']} sessions) says the same thing to within a
point. <strong>The meter is a stay-out instrument and it should not be read as a direction
instrument</strong>, which is exactly what it says on its own label and exactly what keeps getting
forgotten.</p>

{disposition([
 ("Arm grind only on clean-trend days", "PARKED",
  f"It is not refuted &mdash; it makes {m(best_a['net'])} against a {m(base['net'])} control and "
  f"keeps {best_a['keeps']} of {best_a['of']} winners. It is un-runnable: only "
  f"{dt_['trend_and_atr22']} of {dt_['n']} sessions are both clean-trend and above the 22-point "
  f"floor. Revive it the moment the floor question below is answered."),
 ("grind's 22-point ATR floor as a number", "SHADOW",
  f"It sits at the ninetieth percentile of one-minute ATR ({fr['p90']:.2f} on the recent window) "
  "and has never been swept. Shadow a floor ladder (14 / 16 / 18 / 22) and let it accumulate n. "
  "This is the real grind question and nobody has asked it."),
 ("Fix grind with an ER floor or a directional-net requirement", "REFUTED",
  "Named test: nine cells across two families on 128 live fires, every one negative, including "
  "the ER-0.35 floor that is already deployed."),
 ("MGC coil &mdash; fade the edge (or break it)", "REFUTED",
  f"Named test: a mirror control that also loses, and a placebo that {pl['beaten']} random sets "
  f"failed to beat from below on {coil['REVERSION (fade the coil edge → mid)']['n']:,} trades."),
 ("MGC coil, tightest-compression cell only", "PARKED",
  f"{m(best_rev['net'])} on n={best_rev['n']:,}. Revive by running the SAME placebo the "
  "full-sample arm got and holding out a year of tape. Until then it is the best of nine cells "
  "on data that produced a null."),
 ("MGC 5&times;ATR stop / hold-to-clock", "PARKED",
  f"Monotone plateau, which is the shape of a real effect, but strip-best-3 takes "
  f"{m(plateau['5.0x']['net'])} to {m(plateau['5.0x']['strip3'])}. Revive at n&ge;200 sessions "
  "or on a second instrument."),
 ("The MGC derived-trigger rider", "PARKED",
  f"Out-of-sample {m(oos['oos_der']['net'])}, which is real, against a {m0(ctrl['short'])} "
  "always-short drift on the same window. Revive only with the long/short mix reported beside it."),
 ("Report the long/short mix on every gold arm", "LIVE",
  "A method fix, not a strategy. Without it every gold number on this desk is confounded with a "
  "large short drift, and this section found two arms already reading it as edge."),
 ("The open-rider &lsquo;inside the window&rsquo; session filter", "REFUTED",
  f"Named test: strip-best-3 takes {m(pub['in']['net2'])} to {m(pub['in']['strip3'])} on "
  f"{pub['in']['n']} sessions. Three sessions are the whole lead."),
 ("The stay-out meter as a DIRECTION signal", "REFUTED",
  f"{pct(sp['agree_hit'], 1)} hit rate over {sp['agree_n']} sessions when both reads agree. Its "
  "up/down asymmetry is the market's short drift, not the meter's skill. It stays in service as "
  "a stay-out instrument, which is what it was built to be."),
])}
"""
    write("part25_musings.html", doc.strip())
    print(f"\nfloor: {fr['pct22']:.2f}% of {fr['mins']:,} minutes over {fr['days']} days "
          f"(p90 {fr['p90']:.2f}); p25 lab says {afr['pct_min']:.2f}%")
    print(f"grind base {base['net']:.2f} -> best day-type {best_a['net']:.2f} "
          f"(strip3 {best_a['strip3']:.2f}); trend&atr22 = {dt_['trend_and_atr22']}/{dt_['n']}")


if __name__ == "__main__":
    main()
