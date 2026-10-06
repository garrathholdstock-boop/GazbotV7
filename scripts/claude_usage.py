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

GB = "/home/alphabot/gazbot7"
PROJ = pathlib.Path("/root/.claude/projects")
OUT = f"{GB}/data/claude_usage.json"
CURSOR = f"{GB}/data/claude_usage_cursor.json"
BUDGET = f"{GB}/data/claude_budget.json"

# A cheap substring gate before json.loads — most transcript lines are user/tool rows with
# no usage object, and parsing 5GB of JSON to find them would take minutes per run.
GATE = '"usage"'


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
    agg = {"days": {}, "by_model": {}, "by_project": {}} if full else _load(
        OUT, {"days": {}, "by_model": {}, "by_project": {}})
    agg.setdefault("days", {})
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
            inp = int(u.get("input_tokens") or 0)
            out = int(u.get("output_tokens") or 0)
            cc = int(u.get("cache_creation_input_tokens") or 0)
            cr = int(u.get("cache_read_input_tokens") or 0)
            model = m.get("model") or "unknown"
            for bucket, k in ((agg["days"], day), (agg["by_model"], model),
                              (agg["by_project"], proj)):
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

def week_window(now: dt.datetime, start_dow: int) -> tuple[str, str]:
    """[start, end) ISO dates for the budget week. start_dow: 0=Mon .. 6=Sun."""
    d = now.date()
    back = (d.weekday() - start_dow) % 7
    start = d - dt.timedelta(days=back)
    return start.isoformat(), (start + dt.timedelta(days=7)).isoformat()


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
    agg = _load(OUT, {"days": {}})
    cfg = _load(BUDGET, {})
    start_dow = int(cfg.get("week_start_dow", 0))
    budget = cfg.get("weekly_token_budget")
    s, e = week_window(now, start_dow)

    days = agg.get("days", {})
    wk = {k: v for k, v in days.items() if s <= k < e}
    used = sum(billable(v) for v in wk.values())
    raw = sum(billable(v) + int(v.get("cache_read", 0)) for v in wk.values())

    end_dt = dt.datetime.fromisoformat(e + "T00:00:00+00:00")
    hrs_left = max(0.0, (end_dt - now).total_seconds() / 3600)
    elapsed = max(1e-9, 168 - hrs_left)

    out = {
        "week_start": s, "week_end": e,
        "hours_left": round(hrs_left, 1),
        "used_tokens": used,
        "used_tokens_incl_cache_read": raw,
        "budget_tokens": budget,
        "per_day": {k: billable(v) for k, v in sorted(wk.items())},
        "updated": agg.get("updated"),
        "measures": "this box only — other devices are invisible, so this is a FLOOR",
        "excludes": "cache-read tokens (cheapest class) — see billable()",
    }
    if budget:
        out["pct_used"] = round(100.0 * used / budget, 1)
        out["remaining_tokens"] = max(0, budget - used)
        burn = used / elapsed                       # tokens per hour so far
        out["projected_week_tokens"] = int(burn * 168)
        out["on_pace"] = out["projected_week_tokens"] <= budget
        out["hours_to_exhaust"] = (round(out["remaining_tokens"] / burn, 1)
                                   if burn > 0 else None)
    else:
        out["note"] = "no budget set — put weekly_token_budget in data/claude_budget.json"
    return out


WEB = f"{GB}/src/gazbot7/web_static/claude_usage_web.json"


def publish() -> dict:
    """Write the compact summary the dashboard header reads.

    ★ IT GOES TO A STATIC FILE ON PURPOSE. web.py serves /static/* straight off disk on
    every request, so the dial needs NO new Python route and therefore NO web restart —
    and restarting `gazbot7-web` drops his browser tab, which is a standing warning on
    this desk. A new API endpoint would have been the obvious design and the wrong one.
    """
    s = summary()
    small = {k: s[k] for k in ("week_start", "week_end", "hours_left", "used_tokens",
                               "budget_tokens", "updated", "measures") if k in s}
    for k in ("pct_used", "remaining_tokens", "projected_week_tokens", "on_pace",
              "hours_to_exhaust", "note"):
        if k in s:
            small[k] = s[k]
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
    print(f"week {s['week_start']} → {s['week_end']}  ({s['hours_left']}h left)")
    print(f"  used {s['used_tokens']:,} tokens"
          + (f" of {s['budget_tokens']:,} = {s['pct_used']}%" if s.get("budget_tokens")
             else "  (no budget set)"))
    for d, v in s["per_day"].items():
        print(f"    {d}  {v:>12,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
