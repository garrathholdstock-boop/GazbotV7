#!/usr/bin/env python3
"""WAS HE ACTUALLY LOOKING? — presence sessions from the nginx access log.

Operator, 2026-09-18: *"im looking at it periodically during the work day when i have time. not all
day and reading every telegram."*

★★★ WHY THIS IS THE UNLOCK. Scoring the alerts (scripts/score_alerts.py) found the machine led only
3 of 24 entries. But 8 of 19 alerts fired in hours he has NEVER traded in, and for the question
"WHICH LEG IS WORTH ALERTING ON" we have 141 legs and 24 he acted on — a labelled set already,
CONTAMINATED BY ABSENCE. A leg he ignored at 03:00 is not a rejection; it is a leg nobody saw. This
separates the two.

★★ NO CODE CHANGE WAS NEEDED. The build queue proposed patching web.py's no-op `log_message`. nginx
is the front door (443 -> 127.0.0.1:8087) and has logged every request all along, including the
static reports and the phone. Instrumenting the app would have recorded LESS and required a restart
that drops his tab.

⚠⚠⚠ THE TRAP THIS FILE EXISTS TO AVOID: "the dashboard was open" IS NOT "he was looking", and the
two devices differ enormously. Measured 2026-09-18:
    DESKTOP  14,571 requests in 109 minutes = 134/MINUTE, zero gaps over 30 min, ONE session.
             The page polls hard, so a tab left open manufactures presence indefinitely.
    PHONE    3,550 requests, 3 gaps over 30 min, TEN distinct sessions across 02:25-08:19.
             A phone screen does not stay open passively — this is the honest signal, and it is
             exactly the "periodically during the work day" he describes.
So a desktop session is reported as DASHBOARD-OPEN (weak) and a phone session as LOOKED (strong),
and no caller may collapse them. A presence number that counts an idle tab is the
instrument-reports-healthy failure this desk keeps meeting.

⚠ Bots are excluded by user-agent, not by IP — the scanners rotate addresses (Palo Alto Networks,
etc. hit /v7/ several times a day).

  PYTHONPATH=src .venv/bin/python scripts/presence.py [--day 2026-09-18] [--sessions] [--at ISO]
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import gzip
import re
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

LOGS = "/var/log/nginx/access.log*"
LINE = re.compile(r'^(\S+) \S+ \S+ \[(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) [^\]]*\] '
                  r'"(\w+) ([^" ]*)[^"]*" (\d{3})')
MON = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}

# ★ Device, by USER-AGENT. His two clients, measured on the live log.
PHONE_UA = re.compile(r"iPhone.*(OS 18_|Version/26)")
DESK_UA = re.compile(r"Windows NT 10\.0.*Chrome/15[0-9]")
# ⚠ Anything that announces itself as a crawler is not him, whatever its address.
BOT_UA = re.compile(r"bot|crawl|scan|spider|Palo Alto|curl|wget|python-requests", re.I)

# A burst with gaps under this is ONE look. 10 min is longer than any page's own polling interval
# and shorter than the gap between his real visits (his phone showed 10 sessions in 6 hours).
SESSION_GAP_S = 600


def events(day: str | None = None):
    for fn in sorted(glob.glob(LOGS)):
        op = gzip.open if fn.endswith(".gz") else open
        try:
            fh = op(fn, "rt", errors="replace")
        except Exception:
            continue
        with fh:
            for ln in fh:
                if "/v7" not in ln:
                    continue
                m = LINE.match(ln)
                if not m:
                    continue
                ua = ln[ln.rfind('"', 0, len(ln) - 2):] if '"' in ln else ""
                if BOT_UA.search(ln):
                    continue
                who = "phone" if PHONE_UA.search(ln) else ("desk" if DESK_UA.search(ln) else None)
                if not who:
                    continue
                t = dt.datetime(int(m.group(4)), MON[m.group(3)], int(m.group(2)),
                                int(m.group(5)), int(m.group(6)), int(m.group(7)),
                                tzinfo=dt.timezone.utc)
                if day and t.strftime("%Y-%m-%d") != day:
                    continue
                yield t, who


def sessions(day: str | None = None) -> list[dict]:
    """Bursts, per device. ⚠ NEVER merge the devices before sessionising: the desktop's 134
    requests/minute would swallow every phone gap and report one unbroken presence."""
    out = []
    for who in ("phone", "desk"):
        ts = sorted(t for t, w in events(day) if w == who)
        if not ts:
            continue
        s = ts[0]; prev = ts[0]; n = 1
        for t in ts[1:]:
            if (t - prev).total_seconds() > SESSION_GAP_S:
                out.append({"device": who, "start": s, "end": prev, "reqs": n,
                            "mins": (prev - s).total_seconds() / 60})
                s, n = t, 0
            prev = t; n += 1
        out.append({"device": who, "start": s, "end": prev, "reqs": n,
                    "mins": (prev - s).total_seconds() / 60})
    return sorted(out, key=lambda x: x["start"])


def looked_around(t: dt.datetime, window_min: int = 15, strong_only: bool = True) -> str | None:
    """Was he looking within `window_min` of `t`? Returns 'LOOKED' (phone), 'DASHBOARD-OPEN'
    (desktop, weak — may be an idle tab), or None.

    ⚠ `strong_only` defaults TRUE. A desktop session is not evidence of attention and the default
    must not quietly upgrade it — the caller has to ask for the weak signal explicitly.
    """
    best = None
    for s in sessions(t.strftime("%Y-%m-%d")):
        if s["start"] - dt.timedelta(minutes=window_min) <= t <= s["end"] + dt.timedelta(minutes=window_min):
            if s["device"] == "phone":
                return "LOOKED"
            best = "DASHBOARD-OPEN"
    return None if (strong_only and best) else best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"))
    ap.add_argument("--sessions", action="store_true")
    ap.add_argument("--at")
    a = ap.parse_args()
    if a.at:
        t = dt.datetime.fromisoformat(a.at)
        print(f"{a.at}: {looked_around(t, strong_only=False) or 'NOT PRESENT'}")
        return 0
    ss = sessions(a.day)
    if not ss:
        print(f"no presence on {a.day}")
        return 0
    print(f"=== {a.day} ===")
    print(f"{'device':<7} {'from':<6} {'to':<6} {'mins':>6} {'reqs':>6}   signal")
    for s in ss:
        print(f"{s['device']:<7} {s['start'].strftime('%H:%M'):<6} {s['end'].strftime('%H:%M'):<6} "
              f"{s['mins']:>6.0f} {s['reqs']:>6}   "
              f"{'LOOKED' if s['device']=='phone' else 'dashboard-open (weak — may be an idle tab)'}")
    ph = [s for s in ss if s["device"] == "phone"]
    print(f"\n  {len(ph)} phone look(s) — the honest presence signal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
