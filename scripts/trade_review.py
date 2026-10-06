#!/usr/bin/env python3
"""THE NIGHTLY PER-TRADE POST-MORTEM — in at what point and why, out at what point and why,
and which ONE of them to fix tomorrow.

★★★ Operator, 2026-10-06: *"what i want from each is some performance stats. not just a P&L.
i want to see what claude would do to analyse the days performance. each trade. at what point
did it jump in and why? at what point did it jump out and why? which one can be improved for
tomorrow... each night, that is what im going to want claude to do."*

THE REASONS WERE ALWAYS THERE AND NEVER ASSEMBLED. Every decision the harness makes stores a
free-text `reason`, and every trade carries its own `entry_reason` — ~5,600 of them across
three iterations, unread. What was missing is the other half of the question: *should* it have
got out there. That needs the tape AFTER the exit, which a review has and a live decision must
never have.

THE FOUR NUMBERS, per trade, all measured against the leg the trade actually sat on:
  1. **HOW LATE IN** — what share of the leg had already run before entry. This is the "get in
     earlier" number, and note what it is NOT: joining a confirmed leg at 20% instead of 60%
     is not a turn call. Turn entries are a measured coin at every setting
     ([[break-then-join-direction-is-a-coin]]); entering earlier WITHIN a confirmed leg is a
     different and unrefuted thing.
  2. **HOW EARLY OUT** — points still available in the trade's own direction, after the exit,
     before the leg genuinely ended. The "exit later" number, in points, per trade.
  3. **WAS THE EXIT ACTUALLY WRONG** — the sharpest test here. The rules exit on a structure
     break. After that exit, did price keep going AGAINST the trade (the exit was right) or
     immediately resume in its favour (premature)? This separates a bad exit RULE from an
     unlucky one, and nothing in the loop has ever distinguished them.
  4. **GIVEBACK** — peak open profit minus what was banked.

⚠⚠ ONE LESSON A NIGHT, NOT A LIST. A review that emits five improvements a night is how the
rule set reached ten mutually contradictory rules: iteration 2's set REVERSED iteration 1's
position on trade count (*"Target 8-15 entries"* → *"there is no quota"*) and that reversal is
what is currently losing — iteration 3 trades it at 4.2 trades/day and roughly $215-430/day
against the champion's $620. So this ranks by points forgone and names the single biggest one.

⚠⚠⚠ THE CAUSALITY BOUNDARY, WHICH IS THE WHOLE EXPERIMENT. A LESSON derived with hindsight and
carried into tomorrow's RULES is learning and is the point. Hindsight DATA reaching a live
decision is look-ahead and is how this project produced 866 winners from 866 trades. This
module is review-only: it is never imported by the live decision path, and
`sim_week_recursive._assert_causal` guards that path independently.

⚠ READ-ONLY: reads artefacts and tape, prints. Writes nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import textwrap

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")

WIN_START_MIN = 2 * 60
WIN_END_MIN = 13 * 60 + 30
RESUME_MIN = 30          # window after an exit used to judge whether it was premature
RESUME_PT = 15.0         # favourable move within that window that makes an exit premature


def _vis(bars, day: str):
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    return [b for b in bars if d0 + WIN_START_MIN * 60 <= b[0] <= d0 + WIN_END_MIN * 60]


def _idx(vis, epoch: int) -> int:
    lo, hi = 0, len(vis) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if vis[mid][0] < epoch:
            lo = mid + 1
        else:
            hi = mid
    return lo


def analyse(day: str, trades: list, calls: list) -> dict:
    import sim_week_recursive as SW
    import snake_page as SP
    bars, _ = SW.load_day(day)
    vis = _vis(bars, day)
    legs = SP._legs(vis) if len(vis) > 30 else []
    byts = {c["ts"]: c for c in calls}
    rows = []

    for i, t in enumerate(trades, 1):
        o_ep = int(dt.datetime.fromisoformat(t["opened"]).timestamp())
        c_ep = int(dt.datetime.fromisoformat(t["closed"]).timestamp())
        oi, ci = _idx(vis, o_ep), _idx(vis, c_ep)
        long_ = str(t.get("side")) == "LONG"
        sgn = 1 if long_ else -1

        leg = None
        for lg in legs:
            if lg["si"] <= oi <= lg["ei"]:
                leg = lg
                break

        r = {"n": i, "side": t.get("side"), "entry": t["entry"], "exit": t["exit"],
             "pnl": t["pnl_usd"], "held_min": t.get("held_min"),
             "points": t.get("points"), "peak_pt": t.get("peak_pt"),
             "entry_reason": t.get("entry_reason")
                             or (byts.get(t["opened"], {}) or {}).get("reason"),
             "exit_reason": (byts.get(t["closed"], {}) or {}).get("reason"),
             "with_leg": None, "late_pct": None, "forgone_entry_pt": None,
             "forgone_exit_pt": None, "capture_pct": None, "premature": None,
             "giveback_pt": None, "leg_pts": None, "leg_mins": None}

        # 4. giveback is independent of the leg
        if t.get("peak_pt") is not None and t.get("points") is not None:
            r["giveback_pt"] = round(t["peak_pt"] - t["points"], 2)

        if leg:
            r["with_leg"] = (leg["dir"] > 0) == long_
            r["leg_pts"] = round(leg["pts"], 1)
            r["leg_mins"] = leg["mins"]
            start_px = vis[leg["si"]][3]
            # 1. how much of the leg had already run when we entered
            already = sgn * (t["entry"] - start_px)
            if leg["pts"] > 0 and r["with_leg"]:
                r["late_pct"] = round(100.0 * max(0.0, already) / leg["pts"], 1)
                r["forgone_entry_pt"] = round(max(0.0, already), 1)
            # 2. what was still there after we left, in OUR direction, inside this leg
            seg = vis[min(ci, leg["ei"]):leg["ei"] + 1]
            if seg:
                best = max(b[1] for b in seg) if long_ else min(b[2] for b in seg)
                r["forgone_exit_pt"] = round(max(0.0, sgn * (best - t["exit"])), 1)
            if leg["pts"] > 0 and t.get("points") is not None:
                r["capture_pct"] = round(100.0 * t["points"] / leg["pts"], 1)

        # 3. premature? look forward a fixed window from the exit, regardless of leg
        fwd = vis[ci:_idx(vis, c_ep + RESUME_MIN * 60) + 1]
        if len(fwd) > 1:
            fav = max(sgn * (b[1] if long_ else b[2]) - sgn * t["exit"] for b in fwd)
            adv = max(sgn * t["exit"] - sgn * (b[2] if long_ else b[1]) for b in fwd)
            r["after_exit_fav_pt"] = round(fav, 1)
            r["after_exit_adv_pt"] = round(adv, 1)
            # premature only when the favourable move both clears the bar AND beats the
            # adverse one — price that went both ways by 20pt proves nothing either way
            r["premature"] = bool(fav >= RESUME_PT and fav > adv)
        rows.append(r)

    offered = sum(abs(l["pts"]) for l in legs) or 1.0
    took = sum(t.get("points") or 0 for t in trades)
    return {"day": day, "legs": legs, "rows": rows,
            "offered_pt": round(offered, 1), "took_pt": round(took, 1),
            "capture": round(took / offered, 4),
            "forgone_entry_pt": round(sum(r["forgone_entry_pt"] or 0 for r in rows), 1),
            "forgone_exit_pt": round(sum(r["forgone_exit_pt"] or 0 for r in rows), 1),
            "premature_exits": sum(1 for r in rows if r.get("premature")),
            "against_leg": sum(1 for r in rows if r.get("with_leg") is False)}


def render(a: dict, vpp: float = 8.0) -> str:
    L = [f"PER-TRADE POST-MORTEM — {a['day']}",
         f"  the day offered {a['offered_pt']:,.0f}pt across {len(a['legs'])} legs; "
         f"we took {a['took_pt']:+,.0f}pt = {100*a['capture']:.1f}%", ""]
    L.append(f"  {'#':>2} {'side':5} {'pnl':>8} {'held':>6} {'leg':>8} {'in at':>7} "
             f"{'cap':>7} {'left on table':>14} {'give':>7} {'exit'}")
    for r in a["rows"]:
        # ⚠ cells are precomputed, never nested f-strings — the first cut nested a quoted
        # f-string inside another and died on the quoting before it ever ran.
        leg = f"{r['leg_pts']:+.0f}pt" if r["leg_pts"] is not None else "—"
        late = f"{r['late_pct']:.0f}%" if r["late_pct"] is not None else "—"
        cap = f"{r['capture_pct']:.0f}%" if r["capture_pct"] is not None else "—"
        left = (f"{r['forgone_exit_pt']:.0f}pt=${r['forgone_exit_pt'] * vpp:,.0f}"
                if r["forgone_exit_pt"] is not None else "—")
        give = f"{r['giveback_pt']:.0f}pt" if r["giveback_pt"] is not None else "—"
        verdict = "PREMATURE" if r.get("premature") else "ok"
        if r.get("with_leg") is False:
            verdict = "AGAINST LEG"
        L.append(f"  {r['n']:>2} {str(r['side']):5} {r['pnl']:>+8,.0f} "
                 f"{(r['held_min'] or 0):>5.0f}m {leg:>8} {late:>7} {cap:>7} "
                 f"{left:>14} {give:>7} {verdict}")
    L += ["",
          f"  entries landed {a['forgone_entry_pt']:,.0f}pt into their legs "
          f"(${a['forgone_entry_pt']*vpp:,.0f} of leg already gone before we were on)",
          f"  exits left {a['forgone_exit_pt']:,.0f}pt on the table "
          f"(${a['forgone_exit_pt']*vpp:,.0f}) — {a['premature_exits']} of "
          f"{len(a['rows'])} exits were PREMATURE (price resumed our way within "
          f"{RESUME_MIN}min)",
          f"  {a['against_leg']} trade(s) were AGAINST the leg they sat on", ""]
    # the single dominant fault
    if a["forgone_exit_pt"] >= a["forgone_entry_pt"]:
        L.append(f"  → THE DOMINANT FAULT IS THE EXITS: "
                 f"${a['forgone_exit_pt']*vpp:,.0f} left vs "
                 f"${a['forgone_entry_pt']*vpp:,.0f} given away on late entries")
    else:
        L.append(f"  → THE DOMINANT FAULT IS LATE ENTRY: "
                 f"${a['forgone_entry_pt']*vpp:,.0f} of leg gone before entry vs "
                 f"${a['forgone_exit_pt']*vpp:,.0f} left after exit")
    worst = max(a["rows"], key=lambda r: (r.get("forgone_exit_pt") or 0), default=None)
    if worst:
        L += ["", f"  THE ONE TRADE TO FIX — #{worst['n']} {worst['side']}, left "
                  f"{worst['forgone_exit_pt']:.0f}pt "
                  f"(${(worst['forgone_exit_pt'] or 0)*vpp:,.0f}):"]
        if worst.get("entry_reason"):
            L.append(textwrap.fill(" ".join(str(worst["entry_reason"]).split()), 104,
                                   initial_indent="    IN:  ",
                                   subsequent_indent="         "))
        if worst.get("exit_reason"):
            L.append(textwrap.fill(" ".join(str(worst["exit_reason"]).split()), 104,
                                   initial_indent="    OUT: ",
                                   subsequent_indent="         "))
    return "\n".join(L)


def for_day(path: str) -> tuple[dict, str]:
    r = json.load(open(path))
    a = analyse(r["day"], r["trades"], r["calls"])
    return a, render(a)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artefact", help="a reports/sim_week_recursive/*.json or reports/shadow_runner/*.json")
    ap.add_argument("--json", action="store_true")
    k = ap.parse_args()
    if not os.path.exists(k.artefact):
        print(f"no such artefact: {k.artefact}")
        return 1
    a, txt = for_day(k.artefact)
    print(txt)
    if k.json:
        print(json.dumps({x: a[x] for x in a if x != "legs"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
