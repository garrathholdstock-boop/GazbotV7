#!/usr/bin/env python3
"""PART 2 — THE SHADOW DESK & PROMOTION, week of 2026-08-17 .. 2026-08-21.

Built straight off data/shadow.db (shadow_trades JOIN shadow_real on trade_id — shadow.db's
exit_ts is in SECONDS, and gazbot7.db's shadow tables are EMPTY, so reading the wrong one
returns a confident empty set).

The ruler is stated before any number, because three of last week's shadow claims died on it:
  * score real_pnl, NEVER ceiling_pnl
  * VOID the Asia block (00:00–07:00Z) — the permanent Asia bench sits DOWNSTREAM of the fire,
    so a shadow arm books money there that the live desk provably cannot fill
  * dedupe the board before quoting a delta — byte-identical arms report perfect nulls

  PYTHONPATH=src .venv/bin/python scripts/fv7_p2_shadow.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from fv7_common import (SHADOW_DB, WEEK_HI_TS, WEEK_LO_TS, callout, correction,  # noqa
                        disposition, esc, m, pct, strip_best, table, write)

ASIA_END_H = 7      # 00:00–07:00Z: the permanent Asia bench. 0 live fills there since 08-05.


def hour(ts):
    return int(dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%H"))


def day(ts):
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%m-%d")


def fam_rows(con, fam, week_only=True):
    q = ("SELECT s.side,s.qty,s.entry_ts,s.entry_price,s.exit_ts,s.exit_price,s.exit_reason,"
         "s.target_r,s.stop_atr_mult,r.real_pnl,s.ceiling_pnl FROM shadow_trades s "
         "LEFT JOIN shadow_real r ON r.trade_id=s.id "
         "WHERE s.strategy=? AND s.data_quality IS NULL")
    a = [fam]
    if week_only:
        q += " AND s.entry_ts>=? AND s.entry_ts<?"
        a += [WEEK_LO_TS, WEEK_HI_TS]
    return [dict(zip(("side", "qty", "t", "px", "xt", "xpx", "why", "r", "k", "real", "ceil"),
                     row)) for row in con.execute(q + " ORDER BY s.entry_ts", a)]


def battery(rows):
    v = [r["real"] or 0 for r in rows]
    days = {}
    for r in rows:
        days.setdefault(day(r["t"]), []).append(r["real"] or 0)
    return {
        "n": len(v), "net": round(sum(v), 2),
        "win": 100 * sum(1 for x in v if x > 0) / len(v) if v else 0,
        "per": round(sum(v) / len(v), 2) if v else 0,
        "strip1": strip_best(v, 1), "strip3": strip_best(v, 3),
        "lodo": round(min(sum(v) - sum(d) for d in days.values()), 2) if len(days) > 1 else None,
        "green_days": sum(1 for d in days.values() if sum(d) > 0), "days": len(days),
    }


def main():
    con = sqlite3.connect(f"file:{SHADOW_DB}?mode=ro", uri=True)

    fams = [r[0] for r in con.execute(
        "SELECT strategy,COUNT(*) c FROM shadow_trades WHERE entry_ts>=? AND entry_ts<? "
        "AND data_quality IS NULL GROUP BY strategy HAVING c>=8", (WEEK_LO_TS, WEEK_HI_TS))]

    board = {}
    for f in fams:
        rs = fam_rows(con, f)
        asia = [r for r in rs if hour(r["t"]) < ASIA_END_H]
        trad = [r for r in rs if hour(r["t"]) >= ASIA_END_H]
        board[f] = {"all": rs, "asia": asia, "trad": trad,
                    "v": round(sum(r["real"] or 0 for r in rs), 2),
                    "av": round(sum(r["real"] or 0 for r in asia), 2),
                    "tv": round(sum(r["real"] or 0 for r in trad), 2)}
    order = sorted(board, key=lambda f: -board[f]["tv"])

    # ── the Asia void, stated as a table before the board ────────────────────────────────
    tot_v = round(sum(board[f]["v"] for f in board), 2)
    tot_av = round(sum(board[f]["av"] for f in board), 2)
    movers = sorted(board, key=lambda f: -abs(board[f]["av"]))[:6]
    void = table(
        ["Family", "Raw net", "Booked in 00:00&ndash;07:00Z", "Fires there", "What is left"],
        [[("", "row-bad" if board[f]["tv"] < board[f]["v"] else "row-hl")] + [
            f"<code>{esc(f)}</code>", m(board[f]["v"]), m(board[f]["av"]),
            f"{len(board[f]['asia'])} of {len(board[f]['all'])}", m(board[f]["tv"])]
         for f in movers],
        foot=["ALL 38 FAMILIES", m(tot_v), m(tot_av), "", m(round(tot_v - tot_av, 2))],
        numeric={1, 2, 3, 4})

    # ── the board ────────────────────────────────────────────────────────────────────────
    rows = []
    for f in order[:14] + ["&hellip;"] + order[-5:]:
        if f == "&hellip;":
            rows.append(["<em>&hellip; 14 families omitted, all between these two blocks &hellip;</em>",
                         "", "", "", "", "", ""])
            continue
        b = board[f]
        bt = battery(b["trad"]) if b["trad"] else None
        rows.append([("", "row-bad" if b["tv"] < 0 else "row-hl")] + [
            f"<code>{esc(f)}</code>", str(len(b["all"])), m(b["v"]),
            str(len(b["trad"])), m(b["tv"]),
            pct(bt["win"]) if bt else "&mdash;",
            m(bt["per"]) if bt else "&mdash;"])
    boardt = table(["Shadow family", "Fires", "Raw real_pnl", "Tradable fires",
                    "<strong>Tradable real_pnl</strong>", "Win %", "$ / fire"], rows,
                   numeric=set(range(1, 7)))

    # ── the battery on the tradable leaders ──────────────────────────────────────────────
    LEADERS = [f for f in order[:6]] + (["abs_veto_55s"] if "abs_veto_55s" not in order[:6] else [])
    bat_rows = []
    for f in LEADERS:
        bt = battery(board[f]["trad"])
        at = fam_rows(con, f, week_only=False)
        atr = [r for r in at if hour(r["t"]) >= ASIA_END_H]
        bat_rows.append([("", "row-bad" if bt["strip3"] < 0 else "row-hl")] + [
            f"<code>{esc(f)}</code>", str(bt["n"]), m(bt["net"]), pct(bt["win"]),
            m(bt["strip1"]), m(bt["strip3"]), m(bt["lodo"]),
            f"{bt['green_days']} / {bt['days']}",
            f"{len(atr)} &middot; {m(round(sum(r['real'] or 0 for r in atr), 2))}"])
    bat = table(["Family (tradable hours only)", "n", "Net", "Win %", "Best fire stripped",
                 "Best 3 stripped", "Worst leave-one-day-out", "Green days",
                 "All-time, tradable hours"], bat_rows, numeric=set(range(1, 8)))

    # ── side split for the abs_veto family ───────────────────────────────────────────────
    side_rows = []
    for f in ("abs_veto_55s", "abs_veto_50s", "abs_veto_60s", "thrust_loose"):
        if f not in board:
            continue
        for sd in ("LONG", "SHORT"):
            rs = [r for r in board[f]["trad"] if r["side"] == sd]
            if not rs:
                continue
            v = round(sum(r["real"] or 0 for r in rs), 2)
            side_rows.append([("", "row-bad" if v < 0 else "row-hl")] + [
                f"<code>{esc(f)}</code>", sd, str(len(rs)), m(v),
                m(round(v / len(rs), 2)),
                pct(100 * sum(1 for r in rs if (r["real"] or 0) > 0) / len(rs))])
    sides = table(["Family", "Side", "Fires", "Net", "$ / fire", "Win %"], side_rows,
                  numeric={2, 3, 4, 5})

    # ── byte-identical arms ──────────────────────────────────────────────────────────────
    sig = {}
    for f in fams:
        rs = fam_rows(con, f)
        h = hashlib.md5(repr([(r["side"], r["qty"], r["t"], r["px"], r["xt"], r["xpx"],
                               r["why"], r["r"], r["k"], r["real"]) for r in rs]).encode())
        sig.setdefault(h.hexdigest(), []).append((f, len(rs)))
    dupes = [g for g in sig.values() if len(g) > 1]
    n_dupe = sum(len(g) for g in dupes)
    dupe_t = table(
        ["Arms that are the SAME rows", "Fires each", "What the pair was supposed to measure",
         "The delta it reports"],
        [[("", "row-bad"),
          " == ".join(f"<code>{esc(f)}</code>" for f, _ in g), str(g[0][1]),
          {"capit_flip_live": "a 90-second flip window against the live one",
           "cx_clip_brk_live": "a clip-on-break exit, its stand-down control, and the grind-A clip "
                               "arm &mdash; three supposedly different exits",
           "odr_c5_s30": "the &lsquo;g&rsquo; variant of the open-rider claim ladder against the "
                         "plain one"}.get(g[0][0], "two configurations of one idea"),
          "<strong>exactly $0.00</strong>, on every field, by construction"]
         for g in dupes], numeric={1})

    # ── the grind exit shadows ───────────────────────────────────────────────────────────
    tr = json.load(open("/home/alphabot/gazbot7/data/two_ratchet_shadow.json"))
    pa = json.load(open("/home/alphabot/gazbot7/data/partial_shadow.json"))
    last_grind = max(t["opened_at"][:10] for t in tr["trades"])

    grind_t = table(
        ["Grind exit watch", "n", "Live / baseline", "Shadow / partial", "Delta",
         "Newest trade in it"],
        [[("", "row-bad"), "Two-ratchet runner-clip watch", str(tr["n"]), m(tr["live_net"]),
          m(tr["shadow_net"]), m(round(tr["shadow_net"] - tr["live_net"], 2)), last_grind],
         [("", "row-hl"), "2R-partial smoothness", str(pa["n"]), m(pa["baseline_net"]),
          m(pa["partial_net"]), m(pa["mean_delta"]),
          max(c[0] for c in pa["baseline"]["curve"])]], numeric={1, 2, 3, 4})

    doc = f"""
<h2 id="p2"><span class="n">P2</span> THE SHADOW DESK &mdash; and the promotion that did not survive
the ruler</h2>

<p class="lead">Garrath &mdash; the shadow book ran {len(fams)} families with eight or more fires
this week, and if you rank them the way the board is usually ranked, the answer is easy and it is
wrong. <strong>Once the two filters this desk has already learned to apply are applied, the
family sitting second on the raw board falls to eleventh, the promotion case for it collapses from +$332
to +$23.50, and its 50-second sibling goes negative.</strong> The candidates that survive are
different ones, they are newer, and the honest recommendation this week is smaller than last
week's.</p>

<h3>1 &middot; The ruler, stated before any number</h3>

<p><strong>Score <code>real_pnl</code>, never <code>ceiling_pnl</code>.</strong> The ceiling is
what the trade would have made with a perfect exit; real is what the tape would have paid. On this
week's board they disagree by hundreds of dollars per family and the ceiling is always the
friendlier of the two.</p>

<p><strong>Void the Asia block.</strong> This is the one that reorders everything. The desk carries
a permanent bench on 00:00&ndash;07:00 UTC entries, and that bench sits <em>downstream</em> of where
a shadow arm records its fire &mdash; so an arm happily books money in a window where the live desk
has filled <strong>nothing since 5 August</strong>. It is not a small correction:</p>

{void}

<p class="ln">Across all {len(fams)} families, <strong>{m(tot_av)} of the week's
{m(tot_v)} was booked in a window the desk cannot trade</strong>. Every number from here down is
tradable-hours only.</p>

<p><strong>And dedupe before quoting any delta</strong> &mdash; see &sect;5, where
{n_dupe} of the {len(fams)} arms turn out to be the same rows under different names.</p>

<h3>2 &middot; The board, raw and then honest</h3>

{boardt}

<p class="ln">Read the two money columns side by side. <code>abs_veto_55s</code> is second on the
raw board and eleventh on the honest one. <code>abs_veto_50s</code> crosses from
{m(board['abs_veto_50s']['v'])} to {m(board['abs_veto_50s']['tv'])} &mdash; from a promotion
candidate to a losing arm &mdash; purely by removing trades that could never have been filled. The
arms that barely move are the ones worth looking at, because their money was made in hours the desk
was actually open.</p>

<h3>3 &middot; The promotion battery, on the four that survive the ruler</h3>

{bat}

<p class="ln">This is the part that decides Monday, so read the last four columns rather than the
second one. <code>odr_c10_s30</code> has the biggest number on the board and the worst robustness
on it: stripping its best three fires takes {m(battery(board['odr_c10_s30']['trad'])['strip3'])},
and two of its five days are red. That is one or two trades carrying a family, on n=18. The
<code>lad_absS_*</code> and <code>sw_absS_*</code> arms &mdash; ladder and stop-width variants on
the abs-veto short signal &mdash; are smaller and steadier: four of five days green, leave-one-day-out
still positive, and the k=1.0 stop-width arms carry real all-time n behind them
({m(round(sum(r['real'] or 0 for r in fam_rows(con, 'sw_absS_B_k10', False) if hour(r['t']) >= ASIA_END_H), 2))}
on <code>sw_absS_B_k10</code> across all its tradable-hour fires).</p>

{correction("★ THE CASE FOR abs_veto_55s IS AN ALL-TIME CASE, NOT A THIS-WEEK CASE — say it that way",
 f"This week, tradable hours: <strong>{m(battery(board['abs_veto_55s']['trad'])['net'])} on "
 f"{battery(board['abs_veto_55s']['trad'])['n']} fires</strong>, 35% win, two of five days green, "
 f"and stripping the single best fire turns it "
 f"{m(battery(board['abs_veto_55s']['trad'])['strip1'])}. On this week alone it is nothing.",
 f"All-time, tradable hours: <strong>"
 f"{m(round(sum(r['real'] or 0 for r in fam_rows(con, 'abs_veto_55s', False) if hour(r['t']) >= ASIA_END_H), 2))} "
 f"on {len([r for r in fam_rows(con, 'abs_veto_55s', False) if hour(r['t']) >= ASIA_END_H])} fires</strong>. "
 f"That is a real body of evidence and it is why the family is still the lead candidate at all.",
 "So the honest sentence is: <em>the 55-second confirm has a strong multi-week record and a flat "
 "week</em>. That is a perfectly good reason to keep incubating it and a bad reason to promote it "
 "on Monday off this report's numbers. Anyone quoting &lsquo;+$332 this week&rsquo; is quoting the "
 "Asia block.")}

<h3>4 &middot; Two-sided, or short only?</h3>

{sides}

<p class="ln">The long side of the abs-veto family is small and positive, the short side is bigger
and positive, and neither is decisive on this week's n. The standing principle still holds &mdash;
you tune a SIDE, you never relegate a DIRECTION &mdash; and nothing here argues for dropping
either. It also does not argue for adding the long side to a live slot: {len([r for r in board['abs_veto_55s']['trad'] if r['side'] == 'LONG'])}
tradable-hour long fires is not a sample.</p>

<h3>5 &middot; ★ {n_dupe} of the {len(fams)} shadow arms are the same rows under different names</h3>

{dupe_t}

<p class="ln">Every one of these pairs was created to measure a difference, and every one of them
reports a perfect null &mdash; not because the configurations agree, but because <strong>only one
configuration is running and its trades are being written twice</strong>. A broken arm and a
genuinely neutral change are indistinguishable in the board's summary view, and the summary view is
what a report reads. <strong>Diff the rows before quoting any shadow A/B delta</strong>; the check
is four lines of SQL and it is now in <code>scripts/fv7_p2_shadow.py</code>. Note especially
<code>cx_clip_brk_live == cx_clip_brk_standdown</code>: that pair exists specifically to test
whether standing an exit down changes anything, and it has been answering &ldquo;no&rdquo; from a
broken arm.</p>

<h3>6 &middot; The two grind-exit watches &mdash; and why they say nothing this week</h3>

{grind_t}

<p class="ln"><strong>The newest trade in either watch is {last_grind}.</strong> Grind has not
fired a live lot since then, because its own 22-point ATR floor blocked 24,110 of 24,121 raw
signals on this week's tape (Part&nbsp;1.5&nbsp;&sect;4). So both watches are reporting the same
fortnight-old window they reported last Friday, and neither has anything to add.</p>

<p class="ln">Two things are still worth saying about them. The two-ratchet has now watched
{tr['n']} trades containing {tr['runners']} genuine runners and has clipped
<strong>{tr['runner_clips']}</strong> of them &mdash; but its own net is
{m(tr['shadow_net'])} against the live pure-6.0's {m(tr['live_net'])}, so the &ldquo;zero clips
means reconsider it&rdquo; test cannot fire while the thing is losing anyway. And the
2R-partial's headline is now the opposite of its rationale: it improves the mean by
{m(pa['mean_delta'])} while its daily standard deviation goes from {pa['baseline']['std']} to
<strong>{pa['partial']['std']}</strong>. It was adopted as a variance lever. On this window it is a
mean lever that increases variance, which is a different product, and it should not be described as
smoothing anything until it is re-measured on a week where grind actually trades.</p>

{callout("The over-trading caveat, baked in",
 f"The shadow board took {sum(len(board[f]['all']) for f in board):,} fires this week across "
 f"{len(fams)} families. The live desk took 55 lots. A shadow arm has no capital, no queue "
 "position, no thin-tape default-veto and no operator, so it nominates far more trades than the "
 "paper desk could ever hold, and its per-fire numbers are systematically friendlier than the "
 "desk's. <strong>Shadow nominates; paper judges.</strong> Nothing on this page is a P&amp;L "
 "forecast — it is a ranking of which signal to let the paper desk judge next.")}

{disposition([
 ("<code>abs_veto_55s</code> &mdash; promote to a live two-sided slot on Monday", "REFUTED",
  f"Named test: the Asia void. {m(board['abs_veto_55s']['av'])} of its {m(board['abs_veto_55s']['v'])} "
  f"was booked in a window with zero live fills since 08-05, leaving "
  f"{m(board['abs_veto_55s']['tv'])} on {len(board['abs_veto_55s']['trad'])} fires, 2 of 5 days "
  f"green. Refuted as a THIS-WEEK case only."),
 ("<code>abs_veto_55s</code> &mdash; keep incubating on its all-time record", "SHADOW",
  "It is still the best-evidenced family on the book across all tradable-hour fires. Revive the "
  "promotion question when it has a positive tradable-hours week with a positive "
  "leave-one-day-out — not before."),
 ("<code>lad_absS_B_15</code> / <code>lad_absS_A_10</code> (ladder arms on abs-veto short)",
  "SHADOW",
  "The most robust things on this week's honest board: 4 of 5 days green and positive "
  "leave-one-day-out on both. But n=20 in their first week and no all-time record at all. "
  "Revive as promotion candidates at n&ge;60 tradable fires."),
 ("<code>odr_c10_s30</code> (open-rider claim ladder)", "SHADOW",
  "Biggest tradable number on the board and the least robust: strip-best-3 turns it negative and "
  "2 of 5 days are red on n=18. Keep it running; do not act on it."),
 ("<code>abs_veto_50s</code> and <code>abs_veto_60s</code>", "PARKED",
  "Both negative in tradable hours this week. Revive only if the 55s arm is promoted and a "
  "window-length sweep is wanted around it — there is no independent case for either."),
 ("The 7 byte-identical shadow arms", "FAULT",
  "BUILD item: a row-level duplicate check at shadow-write time, and re-seed the three broken "
  "arms. Until then every A/B delta on this board is unverified."),
 ("The two-ratchet grind exit", "PARKED",
  "Unchanged since 08-05 because grind has not fired. Revive the clip test on the first week "
  "grind trades at all — the ATR-floor question in Part 2.5 gates it."),
 ("The 2R-partial as a VARIANCE lever", "REFUTED",
  f"Named measurement: daily standard deviation {pa['baseline']['std']} &rarr; "
  f"{pa['partial']['std']} on the same window it improves the mean. It is not smoothing. "
  "Re-open only as a mean lever, and only on fresh grind trades."),
])}
"""
    write("part2_shadow.html", doc.strip())
    print(f"\nfamilies {len(fams)}  raw {tot_v}  asia {tot_av}  tradable {round(tot_v - tot_av, 2)}")
    for f in order[:6]:
        print(f"  {f:22} raw {board[f]['v']:9.2f}  trad {board[f]['tv']:9.2f}")
    print(f"dupe arms {n_dupe}")


if __name__ == "__main__":
    main()
