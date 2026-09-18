#!/usr/bin/env python3
"""THE EVENT CALENDAR — when the tape is going to move for a reason that is not the tape.

★★★ WHY (2026-09-16). The operator held LONG 4 into the FOMC decision, bought again at T+52 while
the post-decision slide was still running, and lost $1,272 on that one trade — more than the whole
day's -$833. His words: *"if i knew the fed was making a decision i probably wouldve held off."*

★★ THE MEASUREMENT THAT JUSTIFIES THIS FILE (2026-09-18, our own 5s tape, 30-min release window):

    MNQ   FOMC 29-Jul 171.3pt (100th pct, 3.5x median) · 16-Sep 132.3pt (98th, 2.7x)
          CPI  12-Aug 205.0pt (95th) · 11-Sep 271.8pt (100th)
          NFP  07-Aug 219.8pt (100th) · 04-Sep 218.0pt (100th)      ordinary median 49-69pt
    MGC   FOMC 16-Sep $66.10 — 6.6x the median and 2.8x gold's previous MAXIMUM over 32 sessions
          CPI/NFP $51-110 vs an ordinary median of $17

    6 event windows tested, 6 in the top 5%. A day I MISLABELLED as an event (2026-07-16, when the
    June CPI actually landed on the 14th) came back at 68.8pt — the exact ordinary median. That
    accidental control is the reason to believe the other six.

⚠⚠ IT SAYS *WHEN*, NEVER *WHICH WAY*. Every direction study on this desk has come back a coin
([[break-then-join-direction-is-a-coin]]), and his FOMC loss was a DIRECTION error, not a timing
one. This calendar exists so he can STAND ASIDE, and it must never be read as a trade signal.

⚠⚠⚠ AND IT IS NOT A SWITCH. His event-day record is -$1,518 over 12 entries against +$1,076 over
67 on ordinary sessions — but that is 5 days, and the split was chosen after seeing it. PROMISING,
NOT PROVEN. This informs him; it does not bench a gate.

★ TIMES ARE STORED IN EASTERN AND CONVERTED AT READ TIME. Storing UTC would bake in a DST offset
that is wrong for half the year — US clocks change 1 Nov 2026 and the EU changed 25 Oct, so the
same 08:30 release is 12:30Z today and 13:30Z in November.

★★ WHAT IT CAN AND CANNOT FETCH, measured from this box:
      federalreserve.gov  200  -> scraped
      api.nasdaq.com      200  -> scraped (earnings, as they are published)
      bls.gov             403  -> BLOCKED to this box under any User-Agent
    So CPI/NFP dates are SEEDED from a human-verified fetch and CANNOT self-renew. That is not a
    hidden limitation: `--check` pages when any series is running out of future dates, because a
    calendar that quietly empties is exactly the instrument-reports-healthy failure this desk keeps
    meeting. The seed's provenance travels with every row.

  PYTHONPATH=src .venv/bin/python scripts/event_calendar.py --refresh | --show [--days N] | --check
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, "/home/alphabot/gazbot7/src")

ET = ZoneInfo("America/New_York")
PARIS = ZoneInfo("Europe/Paris")
PATH = "/home/alphabot/gazbot7/data/event_calendar.json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")

# ── the measured impact, carried into every alert so the number he sees is OURS, not folklore ──
IMPACT = {
    "FOMC": "MNQ ran 2.7-3.5x a normal 30-min window on both FOMC days in our tape (98th/100th "
            "pct); MGC ran 6.6x its median and 2.8x its previous MAXIMUM",
    "CPI": "MNQ 205-272pt in the 30-min window (95th-100th pct vs a 69pt median); MGC 3-6x",
    "NFP": "MNQ 218-220pt in the 30-min window (100th pct both times); MGC 3-6x",
    "EARNINGS": "NOT MEASURED on our tape yet — included because it moves the index, not because "
                "we have tested it. Treat as unquantified.",
}

# ⚠ SEEDED, NOT SCRAPED — bls.gov returns 403 to this box. Verified by hand on 2026-09-18 from
# https://www.bls.gov/schedule/news_release/cpi.htm and .../empsit.htm. All 08:30 ET.
# ⚠ WHEN THESE RUN OUT A HUMAN MUST REFRESH THEM. `--check` says so before that happens.
SEED_BLS = [
    ("2026-10-02", "NFP", "Employment Situation (Sep)"),
    ("2026-10-14", "CPI", "CPI (Sep)"),
    ("2026-11-06", "NFP", "Employment Situation (Oct)"),
    ("2026-11-10", "CPI", "CPI (Oct)"),
    ("2026-12-04", "NFP", "Employment Situation (Nov)"),
    ("2026-12-10", "CPI", "CPI (Nov)"),
]
BLS_SOURCE = "bls.gov (human-verified 2026-09-18; this box cannot fetch it — HTTP 403)"

# The Nasdaq-100 names big enough to move MNQ on their own.
EARNINGS_TICKERS = {"NVDA", "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "NFLX"}
MONTHS = ("January February March April May June July August September October November December"
          .split())


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_fomc() -> list[dict]:
    """FOMC decision days from the Fed's own calendar page.

    ⚠ THE DECISION IS THE *LAST* DAY of a two-day meeting — "September 15-16" moves the tape on the
    16th, which is exactly the day that cost him $1,272. A parser that took the first day would put
    every alert 24 hours early. A trailing `*` marks projections + a press conference; both FOMC
    days in our tape were that type and they are the ones that ran 3.5x.

    ⚠⚠ TWO BUGS THE FIRST VERSION SHIPPED WITH, caught before it ever paged (2026-09-18):
      1. It scraped the parenthetical "(Minutes: February 18, 2026)" lines as if they were
         MEETINGS, inventing a February FOMC that does not exist.
      2. It read a fixed 4,000 characters per year, which cut 2026 off after April — so it MISSED
         27-28 October and 8-9 December, the next two meetings and the entire reason for the file.
    Parenthetical text is now stripped and each year runs to the next year heading.

    ★★★ AND THE INVARIANT THAT MAKES THIS SAFE: THE FOMC HOLDS EXACTLY EIGHT MEETINGS A YEAR. A
    year that does not parse to 8 is a broken parse, and a broken parse is DISCARDED with a warning
    rather than written to a calendar he will stand aside on. A scraper that silently half-works is
    worse than one that refuses — this desk has met that failure too many times.
    """
    html = _get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    heads = [(int(m.group(1)), m.start(), m.end())
             for m in re.finditer(r">(20\d\d) FOMC Meetings", html)]
    out, problems = [], []
    for idx, (year, hstart, hend) in enumerate(heads):
        stop = min([h[1] for h in heads if h[1] > hend] or [len(html)])
        seg = re.sub(r"<[^>]+>", " ", html[hend:stop])
        seg = re.sub(r"\([^)]*\)", " ", seg)        # ★ kill "(Minutes: ...)" — not meetings
        seg = re.sub(r"\s+", " ", seg)
        # ★★ THE MEETING TABLE ENDS WHERE THE FOOTNOTES BEGIN, and everything after it is a date
        # trap: the 2027 block is followed by "a two-day meeting is scheduled for January 25-26,
        # 2028" and "Last Update: September 16, 2026" — which parsed as a 2027 January and a 2027
        # September, giving 10 meetings for a year that has 8. Cut at the first footnote marker.
        for _stop in ("Meeting associated", "Note:", "Back to Top", "Last Update"):
            _i = seg.find(_stop)
            if _i > 0:
                seg = seg[:_i]
        found = []
        for mm in re.finditer(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:\s*-\s*(\d{1,2}))?(\*?)",
                              seg):
            month = MONTHS.index(mm.group(1)) + 1
            day = int(mm.group(3) or mm.group(2))        # ★ the LAST day decides
            try:
                d = dt.date(year, month, day)
            except ValueError:
                continue
            found.append((d, mm.group(4) == "*"))
        # dedupe, keep order
        seen, uniq = set(), []
        for d, sep in found:
            if d not in seen:
                seen.add(d); uniq.append((d, sep))
        if len(uniq) != 8:
            problems.append(f"{year}: parsed {len(uniq)} meetings, expected 8 — DISCARDED")
            continue
        for d, sep in uniq:
            out.append({
                "date": d.isoformat(), "et_time": "14:00", "kind": "FOMC",
                "name": "FOMC decision" + (" + projections & press conference" if sep else ""),
                "symbols": ["MNQ", "MGC"], "confirmed": True,
                "source": "federalreserve.gov/monetarypolicy/fomccalendars.htm",
            })
    if problems:
        print("⚠ FOMC parse problems: " + " · ".join(problems), file=sys.stderr)
    if not out:
        raise RuntimeError("FOMC parse yielded nothing usable: " + "; ".join(problems))
    return out


def fetch_earnings(days_ahead: int = 120) -> list[dict]:
    """Megacap earnings dates from Nasdaq, as they are published.

    ⚠ Exact dates are only confirmed ~3-4 weeks ahead, so this is a ROLLING fetch, not an annual
    table. Anything further out than the confirmation horizon simply is not knowable and this
    returns nothing for it rather than inventing a window.
    ⚠ It asks per DATE, so it is bounded by days_ahead — never an unbounded crawl.
    """
    out, today = [], dt.date.today()
    for i in range(days_ahead):
        d = today + dt.timedelta(days=i)
        if d.weekday() > 4:
            continue
        try:
            js = json.loads(_get(f"https://api.nasdaq.com/api/calendar/earnings?date={d}", 15))
        except Exception:
            continue
        for row in ((js.get("data") or {}).get("rows") or []):
            t = (row.get("symbol") or "").strip().upper()
            if t not in EARNINGS_TICKERS:
                continue
            when = (row.get("time") or "").strip()
            # ⚠ "time-not-supplied" is COMMON. Say UNKNOWN rather than guess after-close: a
            # before-open report lands in a completely different session.
            et = {"time-after-hours": "16:05", "time-pre-market": "07:00"}.get(when)
            out.append({
                "date": d.isoformat(), "et_time": et or "16:05", "kind": "EARNINGS",
                "name": f"{t} earnings" + ("" if et else " (time UNCONFIRMED — assumed after close)"),
                "symbols": ["MNQ"], "confirmed": bool(et),
                "source": "api.nasdaq.com/api/calendar/earnings",
            })
    return out


def seeded_bls() -> list[dict]:
    return [{"date": d, "et_time": "08:30", "kind": k, "name": n,
             "symbols": ["MNQ", "MGC"], "confirmed": True, "source": BLS_SOURCE}
            for d, k, n in SEED_BLS]


def utc_of(ev: dict) -> dt.datetime:
    """Eastern -> UTC at READ time, so a DST change can never leave a stale offset in the file."""
    d = dt.date.fromisoformat(ev["date"])
    hh, mm = (int(x) for x in ev["et_time"].split(":"))
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).astimezone(dt.timezone.utc)


def load() -> dict:
    try:
        with open(PATH) as fh:
            return json.load(fh)
    except Exception:
        return {"events": [], "generated_at": None}


def save(events: list[dict], notes: list[str]) -> None:
    ev = {}
    for e in events:                                  # dedupe on (date, kind, name)
        ev[(e["date"], e["kind"], e["name"])] = e
    doc = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "notes": notes,
        "impact_measured_2026_09_18": IMPACT,
        "events": sorted(ev.values(), key=lambda e: (e["date"], e["et_time"])),
    }
    tmp = PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1)
    os.replace(tmp, PATH)                             # atomic: a half-written calendar is worse


def upcoming(days: int = 14) -> list[dict]:
    now = dt.datetime.now(dt.UTC)
    out = []
    for e in load().get("events", []):
        t = utc_of(e)
        if now <= t <= now + dt.timedelta(days=days):
            out.append({**e, "utc": t.isoformat(), "in_hours": (t - now).total_seconds() / 3600})
    return sorted(out, key=lambda e: e["utc"])


def coverage_warnings() -> list[str]:
    """★ A CALENDAR THAT QUIETLY RUNS DRY IS THE FAILURE THIS DESK KEEPS MEETING. CPI and NFP
    cannot self-renew from this box, so their exhaustion must be LOUD and EARLY."""
    now = dt.datetime.now(dt.UTC)
    warn = []
    for kind, floor_days in (("CPI", 45), ("NFP", 45), ("FOMC", 120)):
        fut = [e for e in load().get("events", []) if e["kind"] == kind and utc_of(e) > now]
        if not fut:
            warn.append(f"{kind}: NO FUTURE DATES AT ALL — the calendar is blind to it.")
            continue
        last = max(utc_of(e) for e in fut)
        left = (last - now).days
        if left < floor_days:
            warn.append(f"{kind}: only {len(fut)} date(s) left, last is {last.date()} "
                        f"({left}d away, floor {floor_days}d)"
                        + (" — bls.gov is UNFETCHABLE from this box, so a HUMAN must refresh it."
                           if kind in ("CPI", "NFP") else ""))
    return warn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--days", type=int, default=14)
    a = ap.parse_args()

    if a.refresh:
        events, notes = list(seeded_bls()), []
        for label, fn in (("FOMC", fetch_fomc), ("EARNINGS", fetch_earnings)):
            try:
                got = fn()
                events += got
                notes.append(f"{label}: fetched {len(got)}")
            except Exception as e:
                # ⚠ KEEP WHAT WE HAD. A failed fetch must never empty the calendar.
                kept = [x for x in load().get("events", []) if x["kind"] == label
                        or (label == "EARNINGS" and x["kind"] == "EARNINGS")]
                events += kept
                notes.append(f"{label}: FETCH FAILED ({type(e).__name__}: {str(e)[:80]}) — "
                             f"kept {len(kept)} previously known")
        notes.append(BLS_SOURCE)
        save(events, notes)
        print("\n".join(notes))
        for w in coverage_warnings():
            print("⚠ " + w)
        return 0

    if a.check:
        warn = coverage_warnings()
        if warn:
            msg = "⚠ EVENT CALENDAR COVERAGE: " + " · ".join(warn)
            print(msg)
            try:
                from gazbot7.notify import dedupe_ok, notify
                if dedupe_ok("event_calendar.coverage", msg, cooldown_s=86400):
                    notify(msg, critical=False)
            except Exception:
                pass
        else:
            print("ok — every series has future dates")
        return 0

    up = upcoming(a.days)
    if not up:
        print(f"no events in the next {a.days} days")
        return 0
    print(f"{'when (UTC)':<18} {'Paris':<7} {'kind':<9} {'in':>7}  event")
    for e in up:
        t = dt.datetime.fromisoformat(e["utc"])
        print(f"{t.strftime('%a %d %b %H:%M'):<18} "
              f"{t.astimezone(PARIS).strftime('%H:%M'):<7} {e['kind']:<9} "
              f"{e['in_hours']:>6.1f}h  {e['name']}"
              + ("" if e["confirmed"] else "  ⚠UNCONFIRMED"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
