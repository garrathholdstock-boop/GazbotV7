#!/usr/bin/env python3
"""Telegram the simulation result — respecting his own quiet-hours rule rather than bypassing it.

★ He asked: "ping me on telegram when theyre done."

⚠⚠ TWO OF HIS OWN FILTERS WOULD HAVE EATEN THIS SILENTLY, and both for good reasons:
  1. WEEKEND QUIET (notify.py:242) drops anything without `weekend_ok=True` while the venue is
     shut and the desk is flat — which is now, Saturday. It OUTRANKS `critical` on purpose,
     because it was the red alerts that woke him on a Saturday.
  2. QUIET HOURS (notify.py:244) drop anything non-critical between 22:00 and 06:00 Paris. The
     queue is ~15h from a 10:07Z start, so it lands about 03:07 Paris — inside the window.

⚠⚠⚠ SO THE WRONG FIX IS `critical=True`. That bypasses quiet hours by CLAIMING this matters at 3am,
and a finished backtest does not. The file's own rule: "A routine alert can never be marked: if it
is not worth waking him for, the circle would be claiming an urgency the quiet-hours rule itself
denies." Marking a simulation result would be exactly that.

→ `weekend_ok=True` so the weekend filter lets it through, and if it lands in quiet hours we HOLD
  until 06:05 Paris and say in the text when the run actually finished. Same pattern as
  overnight_allclear, which exists because of this precise problem.
"""
import json, glob, os, sys, time
import datetime as dt
from zoneinfo import ZoneInfo

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.notify import notify, in_quiet_hours      # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/sim_week_recursive"
PARIS = ZoneInfo("Europe/Paris")


def rows():
    out = {}
    for f in sorted(glob.glob(f"{OUT}/*_2026-*.json")):
        base = os.path.basename(f)[:-5]
        arm, day = base.rsplit("_", 1)
        try:
            r = json.load(open(f))
        except Exception:
            continue
        out.setdefault(arm, []).append(r)
    return out


def body(finished_at: dt.datetime) -> str:
    by = rows()
    L = [f"🧪 SIM QUEUE DONE — {len(by)} arm(s)",
         f"finished {finished_at.astimezone(PARIS):%a %H:%M} Paris"]
    for arm, rs in sorted(by.items()):
        t = [x for r in rs for x in r["trades"]]
        if not t:
            continue
        net = sum(r["net_usd"] for r in rs)
        w = sum(1 for x in t if x["pnl_usd"] > 0)
        L.append(f"{arm}: ${net:+,.0f} · {len(t)} trades ({len(t)/len(rs):.1f}/day) · "
                 f"{100*w/len(t):.0f}% win · {len(rs)} day(s)")
    L += ["", "⚠ read the replication not the winner — an effect in one week and not the other is "
              "noise. ~15 trades per arm-week is thin.",
          "full detail: reports/sim_week_recursive/"]
    return "\n".join(L)


def main() -> int:
    finished = dt.datetime.now(dt.UTC)
    # ⚠ HOLD rather than bypass. A backtest is not worth waking him for.
    held = False
    while in_quiet_hours(dt.datetime.now(dt.UTC)):
        held = True
        time.sleep(300)
    msg = body(finished)
    if held:
        msg += "\n(held until after quiet hours — it finished overnight)"
    ok = notify(msg, critical=False, mark=False, weekend_ok=True)
    print(f"sent={ok} held={held}\n{msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
