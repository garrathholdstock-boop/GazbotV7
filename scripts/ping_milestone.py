#!/usr/bin/env python3
"""Ping when the HOLDOUT daily average crosses a milestone. Operator: "ping me when its running at
500 a day."

⚠⚠ HOLDOUT ONLY. A training-week average is not progress and reporting one as progress is the first
step to believing it. docs/PROJECT_800_A_DAY.md: $500-600/day is the MILESTONE, $800 is the BAR, and
the word "complete" belongs only to $800.
⚠ Fires ONCE per milestone, tracked in a seen-file, so a loop that hovers at $520 does not ping
  every iteration.
⚠ weekend_ok=True or Saturday's filter drops it; never critical=True — a backtest milestone does not
  matter at 3am. Holds past quiet hours instead.
"""
import json, os, sys, time
import datetime as dt

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.notify import notify, in_quiet_hours      # noqa: E402

H = "/home/alphabot/gazbot7/reports/recursive_loop/history.json"
SEEN = "/home/alphabot/gazbot7/reports/recursive_loop/pinged.json"
STEPS = [300, 400, 500, 600, 700, 800]        # dollars per day, holdout
HOLD_DAYS = 10                                 # 2 weeks of 5


def seen():
    try:
        return set(json.load(open(SEEN)))
    except Exception:
        return set()


def main() -> int:
    if not os.path.exists(H):
        return 0
    h = json.load(open(H))
    if not h:
        return 0
    best, best_it = None, None
    for x in h:
        avg = x["holdout"]["net_usd"] / HOLD_DAYS
        if best is None or avg > best:
            best, best_it = avg, x
    done = seen()
    hit = [s for s in STEPS if best >= s and str(s) not in {str(x) for x in done}]

    # ★2026-10-03 PER-ITERATION PROGRESS. Operator: "can you ping me a quick 2 line progress each
    # time agents come back and your fine tuning? just so i dont get tempted to ask you all the
    # time how its going!"
    # ⚠⚠ THIS OVERRIDES HIS OWN STANDING RULE — CLAUDE.md says "FINAL DELIVERABLES ONLY: no progress
    #   pings; one message when done." He has explicitly lifted it FOR THIS PROJECT, because the
    #   alternative is him asking every twenty minutes. The old rule still governs everything else.
    iter_seen = f"iter{len(h)}"
    if not hit and iter_seen not in {str(x) for x in done}:
        ho = h[-1]["holdout"]; tr = h[-1]["train"]
        avg = ho["net_usd"] / HOLD_DAYS
        trend = ""
        if len(h) > 1:
            prev = h[-2]["holdout"]["net_usd"] / HOLD_DAYS
            trend = f" ({avg - prev:+,.0f}/day vs last)"
        msg = "\n".join([
            f"🔁 iteration {h[-1]['iter']} done — holdout ${avg:,.0f}/day{trend}",
            f"side {ho['side_accuracy']} · capture {ho['capture']} · {ho['trades_per_day']}/day "
            f"(bars: 0.75 / 0.15 / 3-6)",
            f"best so far ${best:,.0f}/day · train week was ${tr['net_usd']:+,.0f}",
            f"⚠ train figure is context only, never progress. bar is $800/day on the holdout."])
        held = False
        while in_quiet_hours(dt.datetime.now(dt.UTC)):
            held = True
            time.sleep(300)
        notify(msg + ("\n(held past quiet hours)" if held else ""),
               critical=False, mark=False, weekend_ok=True)
        json.dump(sorted({str(x) for x in done} | {iter_seen}, key=str), open(SEEN, "w"))
        print(msg)
        return 0
    if not hit:
        return 0
    s = max(hit)
    ho = best_it["holdout"]
    cleared = s >= 800 and best_it["met"]
    L = [("★★★ $800/DAY CLEARED ON THE HOLDOUT — this is the bar" if cleared
          else f"📈 RUNNING AT ${best:,.0f}/DAY on the holdout (crossed ${s})"),
         f"iteration {best_it['iter']} · holdout ${ho['net_usd']:+,.0f} over {HOLD_DAYS} days",
         f"side {ho['side_accuracy']} (bar 0.75) · capture {ho['capture']} (bar 0.15) · "
         f"{ho['trades_per_day']}/day (bar 3-6)",
         f"iterations so far: {len(h)}"]
    if not cleared:
        L += ["", "⚠ NOT complete — the bar is $800/day with all four metrics met. "
                  f"{'milestone' if s < 800 else 'P&L there but a metric short'}."]
    L.append("holdout = 14-18 Sep + 17-21 Aug, never trained on, never reviewed")
    msg = "\n".join(L)
    held = False
    while in_quiet_hours(dt.datetime.now(dt.UTC)):
        held = True
        time.sleep(300)
    if held:
        msg += "\n(held until after quiet hours)"
    ok = notify(msg, critical=False, mark=False, weekend_ok=True)
    json.dump(sorted({str(x) for x in done} | {str(s), iter_seen}, key=str), open(SEEN, "w"))
    print(f"sent={ok}\n{msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
