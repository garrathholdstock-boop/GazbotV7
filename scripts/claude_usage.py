#!/usr/bin/env python3
"""HOW MUCH CLAUDE HAS THIS DESK ACTUALLY USED — measured, not guessed.

★★★ Operator, 2026-10-06, after the weekend's recursive runs exhausted his weekly credit
budget mid-experiment: *"as we are going to use claude to monitor and execute all the
time, i need a little dial on the dashboard showing how much weekly credits we have used
and how much we have to go."*

WHERE THE NUMBER COMES FROM. Every Claude Code session on this box writes a JSONL
transcript under ~/.claude/projects/, and every assistant message carries the API's own
`usage` object — input, output, cache-creation and cache-read tokens, plus the model. That
is the real meter, written by the thing doing the spending. 34,280 files, ~5GB.

⚠⚠⚠ WHAT THIS CANNOT KNOW, AND THE DIAL MUST SAY SO.
  1. **It measures THIS BOX.** Usage from his phone, the desktop app or any other machine
     is invisible here, so the figure is a FLOOR on account-wide consumption, never a
     ceiling.
  2. **It does not know his allowance.** No local file states the plan's weekly limit and
     no CLI flag reports it, so the budget is a number HE sets in
     `data/claude_budget.json`. With no budget configured the dial shows raw usage and
     says "no budget set" — it does NOT invent a percentage.
  3. **A token is not a credit.** Anthropic weights cache reads far below fresh input, and
     weights differ per model, so "% of credits" computed from a raw token sum would be
     fiction. The dial therefore reports TOKENS, and the budget is in tokens.
This is the [[an-instrument-that-reports-healthy-about-something-it-does-not-check]] rule
applied to my own new instrument: it reports exactly what it measured and labels the rest.

★ INCREMENTAL. A full rescan of 5GB every ten minutes would be absurd, so a cursor file
records bytes-read per transcript and each run reads only what is new. Daily totals are
persisted, so history is never recomputed — and a transcript that is rotated or truncated
is detected by a SHRINKING size and re-read from zero rather than silently skipped.

⚠ READ-ONLY on the desk: it reads transcripts and writes two files, both its own.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
from zoneinfo import ZoneInfo

GB = "/home/alphabot/gazbot7"
PROJ = pathlib.Path("/root/.claude/projects")
OUT = f"{GB}/data/claude_usage.json"
CURSOR = f"{GB}/data/claude_usage_cursor.json"
BUDGET = f"{GB}/data/claude_budget.json"

# A cheap substring gate before json.loads — most transcript lines are user/tool rows with
# no usage object, and parsing 5GB of JSON to find them would take minutes per run.
GATE = '"usage"'
MIN_PACE_H = 2.0          # a burn rate under 2h of window is noise, not a trend


def _load(p, default):
    try:
        return json.load(open(p))
    except Exception:
        return default


def _atomic(p, obj):
    tmp = p + ".tmp"
    json.dump(obj, open(tmp, "w"), indent=1)
    os.replace(tmp, p)


def scan(full: bool = False) -> dict:
    cur = {} if full else _load(CURSOR, {})
    agg = {"days": {}, "hours": {}, "by_model": {}, "by_project": {}} if full else _load(
        OUT, {"days": {}, "hours": {}, "by_model": {}, "by_project": {}})
    agg.setdefault("days", {})
    agg.setdefault("hours", {})
    agg.setdefault("by_model", {})
    agg.setdefault("by_project", {})

    new_msgs = 0
    for f in PROJ.rglob("*.jsonl"):
        key = str(f)
        try:
            size = f.stat().st_size
        except OSError:
            continue
        seen = cur.get(key, 0)
        if size == seen:
            continue
        if size < seen:                     # rotated or truncated — start over on this file
            seen = 0
        try:
            fh = open(f, "rb")
        except OSError:
            continue
        with fh:
            fh.seek(seen)
            raw = fh.read()
        cur[key] = seen + len(raw)
        proj = f.parent.name
        for line in raw.split(b"\n"):
            if GATE.encode() not in line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            m = r.get("message")
            if not isinstance(m, dict):
                continue
            u = m.get("usage")
            if not isinstance(u, dict):
                continue
            ts = r.get("timestamp")
            if not ts:
                continue
            day = ts[:10]
            # ★2026-10-06 HOURLY buckets as well as daily. His budget resets Wed 07:00 Paris,
            # which is 05:00Z in summer and 06:00Z in winter — a reset MID-DAY, so day buckets
            # cannot place a Wednesday message in the right week. The reset is on an hour
            # boundary, so hourly resolution is exact rather than approximate.
            hour = ts[:13]
            inp = int(u.get("input_tokens") or 0)
            out = int(u.get("output_tokens") or 0)
            cc = int(u.get("cache_creation_input_tokens") or 0)
            cr = int(u.get("cache_read_input_tokens") or 0)
            model = m.get("model") or "unknown"
            for bucket, k in ((agg["days"], day), (agg["hours"], hour),
                              (agg["by_model"], model), (agg["by_project"], proj)):
                b = bucket.setdefault(k, {"in": 0, "out": 0, "cache_create": 0,
                                          "cache_read": 0, "msgs": 0})
                b["in"] += inp
                b["out"] += out
                b["cache_create"] += cc
                b["cache_read"] += cr
                b["msgs"] += 1
            new_msgs += 1

    agg["updated"] = dt.datetime.now(dt.UTC).isoformat()
    agg["new_messages_this_run"] = new_msgs
    _atomic(CURSOR, cur)
    _atomic(OUT, agg)
    return agg


# ── the window the dial reports ─────────────────────────────────────────────────────────

def week_window(now: dt.datetime, cfg: dict) -> tuple[dt.datetime, dt.datetime]:
    """The budget week as INSTANTS, not dates.

    ★ Operator, 2026-10-06: *"i go back to zero at 7am every wednesday."* So the week is
    [last Wed 07:00 local, next Wed 07:00 local) — a boundary in the middle of a day, which
    is why the aggregator keeps hourly buckets.

    ⚠⚠ COMPUTED IN THE LOCAL ZONE, NEVER AS A FIXED UTC HOUR. 07:00 Europe/Paris is 05:00Z
    under CEST and 06:00Z under CET, and Paris changes over on 2026-10-25 — so a hardcoded
    UTC reset would silently be an hour wrong for half the year. Same rule the event
    calendar and overnight-allclear already follow.
    """
    # ⚠⚠ ANCHORED IN UTC, AND THAT IS NOT WHAT HE SAID. He reported "7am every wednesday"
    # from his own wall clock; the CLI's refusal message is the authority and reads
    # "You've hit your weekly limit · resets Oct 7, 5am (UTC)". Both describe the same
    # instant TODAY (CEST = UTC+2) and they SEPARATE on 2026-10-25, when 07:00 Paris becomes
    # 06:00Z while the reset stays 05:00Z. The first cut of this function used Europe/Paris
    # and would have been an hour wrong for the whole winter — note this is the INVERSE of
    # the event-calendar lesson: there the schedule was local and storing UTC baked in a bad
    # offset; here the schedule is genuinely UTC and the local reading is what drifts.
    tz = ZoneInfo(cfg.get("reset_tz", "UTC"))
    dow = int(cfg.get("reset_dow", 2))          # 0=Mon .. 2=Wed
    hr = int(cfg.get("reset_hour_utc", cfg.get("reset_hour_local", 5)))
    loc = now.astimezone(tz)
    anchor = loc.replace(hour=hr, minute=0, second=0, microsecond=0)
    back = (anchor.weekday() - dow) % 7
    start = anchor - dt.timedelta(days=back)
    if start > loc:                              # today IS the reset day but before the hour
        start -= dt.timedelta(days=7)
    # rebuild from the wall clock so the NEXT boundary is also 07:00 local, not start+168h —
    # across a DST change those differ by an hour and the window would drift.
    nxt = (start + dt.timedelta(days=7)).replace(hour=hr, minute=0, second=0, microsecond=0)
    s_utc, e_utc = start.astimezone(dt.UTC), nxt.astimezone(dt.UTC)

    # ★★2026-10-06 AN EARLY RESET IS INVISIBLE FROM HERE AND ONLY HE KNOWS IT HAPPENED.
    # Operator, the same day the dial first read 100%: "im not 100% used claude let me reset
    # early, im fine." The schedule says the week runs to Wed 05:00Z; a support-granted reset
    # moves the floor and no local signal reports it. So `last_reset_at` in the budget config
    # overrides the computed start whenever it is LATER — the measurement is untouched, only
    # the window moves, and the stale half of the week stops being counted.
    # ⚠ It is never allowed to move the window FORWARD past now or BACKWARD before the
    # schedule: a typo in this field must not invent head-room or resurrect a spent week.
    override = cfg.get("last_reset_at")
    if override:
        try:
            o = dt.datetime.fromisoformat(str(override))
            o = o.replace(tzinfo=dt.UTC) if o.tzinfo is None else o.astimezone(dt.UTC)
            if s_utc < o <= now:
                s_utc = o
        except Exception:
            pass                        # a malformed override is ignored, never fatal
    return s_utc, e_utc


def billable(b: dict) -> int:
    """⚠ A DELIBERATE CHOICE, AND IT IS NOT ANTHROPIC'S FORMULA.

    Cache READS are excluded because they are the cheapest class by an order of magnitude
    and including them would make a long cached session look catastrophic. Input, output
    and cache CREATION are counted at face value. This is a consistent yardstick for
    "are we spending more than last week", NOT a billing figure, and the dial labels it.
    """
    return int(b.get("in", 0)) + int(b.get("out", 0)) + int(b.get("cache_create", 0))


def summary(now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.UTC)
    agg = _load(OUT, {})
    cfg = _load(BUDGET, {})
    budget = cfg.get("weekly_token_budget")
    s_dt, e_dt = week_window(now, cfg)

    hours = agg.get("hours") or {}
    s_key, e_key = s_dt.strftime("%Y-%m-%dT%H"), e_dt.strftime("%Y-%m-%dT%H")
    wk = {k: v for k, v in hours.items() if s_key <= k < e_key}
    used = sum(billable(v) for v in wk.values())

    # per-day inside the window, for the sparkline under the dial
    per_day: dict[str, int] = {}
    for k, v in sorted(wk.items()):
        per_day[k[:10]] = per_day.get(k[:10], 0) + billable(v)

    hrs_left = max(0.0, (e_dt - now).total_seconds() / 3600)
    elapsed = max(1e-9, (now - s_dt).total_seconds() / 3600)
    span = (e_dt - s_dt).total_seconds() / 3600

    out = {
        "week_start": s_dt.isoformat(), "week_end": e_dt.isoformat(),
        "resets": f"{int(cfg.get('reset_hour_utc', cfg.get('reset_hour_local', 5))):02d}:00 "
                  f"{cfg.get('reset_tz', 'UTC')} every "
                  f"{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][int(cfg.get('reset_dow', 2))]}",
        "hours_left": round(hrs_left, 1),
        "used_tokens": used,
        "budget_tokens": budget,
        "per_day": per_day,
        "updated": agg.get("updated"),
        "measures": "this box only — phone and desktop app are invisible, so this is a FLOOR",
        "excludes": "cache-read tokens (cheapest class) — see billable()",
    }
    if budget:
        out["pct_used"] = round(100.0 * used / budget, 1)
        out["remaining_tokens"] = max(0, budget - used)
        # ⚠⚠ A BURN RATE NEEDS TIME TO MEAN ANYTHING. Measured over the first minutes of a
        # week, tokens/hour is enormous and the projection says "over budget" no matter how
        # little was spent — so the chip went RED the instant an early reset was recorded on
        # 2026-10-06, at 2.1% used. Below MIN_PACE_H the pace verdict is UNKNOWN (None), not
        # False: the dial's red state keys on `on_pace === false`, and a defaulted flag that
        # means "no data" would be read as "alarm"
        # ([[a-defaulted-flag-is-not-a-separated-flag]]).
        if elapsed >= MIN_PACE_H:
            burn = used / elapsed
            out["projected_week_tokens"] = int(burn * span)
            out["on_pace"] = out["projected_week_tokens"] <= budget
            out["hours_to_exhaust"] = (round(out["remaining_tokens"] / burn, 1)
                                       if burn > 0 else None)
        else:
            out["on_pace"] = None
            out["pace_note"] = (f"only {elapsed:.1f}h into the window — too early to project "
                                f"(needs {MIN_PACE_H}h)")
    else:
        out["note"] = "no budget set — put weekly_token_budget in data/claude_budget.json"
    return out


WEB = f"{GB}/src/gazbot7/web_static/claude_usage_web.json"


def publish() -> dict:
    """Write the compact summary the dashboard header reads.

    ★ IT GOES TO A STATIC FILE ON PURPOSE. web.py serves /static/* straight off disk on
    every request, so the dial needs NO new Python route and therefore NO web restart —
    and restarting `gazbot7-web` drops his browser tab, a standing warning on this desk.
    A new API endpoint was the obvious design and the wrong one.
    """
    s = summary()
    keep = ("week_start", "week_end", "resets", "hours_left", "used_tokens", "pace_note",
            "budget_tokens", "updated", "measures", "pct_used", "remaining_tokens",
            "projected_week_tokens", "on_pace", "hours_to_exhaust", "note")
    small = {k: s[k] for k in keep if k in s}
    small["per_day"] = s.get("per_day", {})
    _atomic(WEB, small)
    return small


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true", help="ingest new transcript bytes")
    ap.add_argument("--full", action="store_true", help="rescan everything from zero")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.scan or a.full:
        agg = scan(full=a.full)
        print(f"ingested {agg['new_messages_this_run']:,} new assistant messages; "
              f"{len(agg['days'])} days on record")
    s = publish()
    if a.json:
        print(json.dumps(s, indent=1))
        return 0
    print(f"week {s['week_start'][:16]}Z → {s['week_end'][:16]}Z   "
          f"({s['hours_left']}h left · resets {s['resets']})")
    print(f"  used {s['used_tokens']:,} tokens"
          + (f" of {s['budget_tokens']:,} = {s['pct_used']}%" if s.get("budget_tokens")
             else "  (no budget set)"))
    for d, v in s["per_day"].items():
        print(f"    {d}  {v:>12,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
