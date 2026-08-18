#!/usr/bin/env python3
"""DATA INVENTORY — where every byte we own lives, and whether it is still being backed up.

★★ WHY (operator, 2026-08-13): *"this database and backup knowledge is absolutely critical for you
... he should even do a quick scan of backblaze at the start of every session. something durable
needs to be monitoring this is all working and our data is current and backed up at all times."*

Said after I surveyed the local disk, found V5's `alphabot.db` at ZERO BYTES, and concluded there was
no V5 history. There is: it is on Backblaze, it is 4,934 trades over 47 days including **574 MNQ
trades** we had never looked at, and I had not checked. The lesson is not "remember V5" — it is that
**the local disk is a CACHE, not the record.** The record is B2.

★ TWO MODES, and the split is the whole design:
    --scan    the SLOW truth. Lists B2 over the network (tens of seconds), writes data_status.json.
              Run by gazbot7-data-inventory.timer.
    (default) the FAST read. Prints the cached status instantly. Safe at session start, and it says
              how old the cache is rather than pretending it is live.

★ IT ALARMS ON STALENESS, NOT ON ABSENCE. Every backup job here already exists and has for weeks —
what was missing was anything checking they still RUN. A backup that silently stopped looks exactly
like a backup that is working, right up until you need it. Same shape as the router that logged "no
change" for 10.5 hours.

  PYTHONPATH=src scripts/data_inventory.py [--scan] [--json]
"""
from __future__ import annotations

import argparse
import json
import datetime as dt
import os
import re
import subprocess
import sys
import time

GB = "/home/alphabot/gazbot7"
STATUS = f"{GB}/data/data_status.json"
_ALARM_KEY = "data_inventory.faults"
# 12h, not the 4h scan cadence: a stale-source fault is not safety-critical (nothing is
# naked, no position is at risk) and sweep reports it independently. Loud enough to not be
# forgotten, quiet enough that a persistent fault does not train the operator to swipe past.
_ALARM_COOLDOWN_S = 12 * 3600

# (label, path, max_age_h or None if it never changes)
# (label, path, max_age_h, market_clock) — market_clock=True measures staleness against the last
# instant the MARKET WAS OPEN rather than wall-clock. See _last_market_ts().
LOCAL = [
    # ★★2026-08-17 gazbot7.db / shadow.db / shadow_mgc.db MOVED ONTO THE MARKET CLOCK. They were on
    # wall-clock on the stated theory that "nightly jobs write them, so a dead writer would hide all
    # weekend". THAT THEORY IS FALSE, and the desk proved it: gazbot7-backup is a WAL checkpoint +
    # `VACUUM INTO` a SEPARATE file — it READS gazbot7.db and only moves its mtime when there is WAL
    # to checkpoint, i.e. only when the desk actually TRADED. It ran and Finished on 08-15, 08-16 AND
    # 08-17 while the mtime sat unchanged at 08-15 03:30. So the mtime measures "did we trade",
    # not "is anything alive", and a flat desk is indistinguishable from a dead recorder.
    # ⚠ WHAT ACTUALLY VERIFIES RECORDING INTEGRITY IS `book_vs_fills` (sweep), which reconciles the
    # book against IBKR executions and REFUSES unverifiable days. This row is a liveness hint only.
    ("trade record   gazbot7.db", f"{GB}/data/gazbot7.db", 72, True),
    ("shadow book    shadow.db", f"{GB}/data/shadow.db", 30, True),
    # ★2026-08-15 the gold shadow book. Its own store by design (MGC_SHADOW_SCOPE §4), which is
    # exactly why it was in no backup, no inventory and no sweep — audit finding #6.
    ("gold shadow    shadow_mgc.db", f"{GB}/data/shadow_mgc.db", 30, True),
    ("live tape      capture.db", f"{GB}/data/capture.db", 2, True),
    ("L2 depth       depth.db", f"{GB}/data/depth.db", 2, True),
    # NOT on the market clock, and correctly so: tape-mirror writes this at 21:05 EVERY day including
    # weekends, so a missed write is a dead timer and wall-clock is exactly the right measure.
    ("tape manifest  _manifest.json", f"{GB}/data/tape/_manifest.json", 30, False),
]


def _market_open_at(t: dt.datetime) -> bool:
    """Is the CME trading MNQ/MGC at this instant? Closed Fri 21:00Z → Sun 22:00Z, plus the
    21:00-22:00Z daily halt Mon-Thu. The single definition of the venue clock in this file."""
    wd, hh = t.weekday(), t.hour             # Mon=0 .. Sun=6
    return not (
        (wd == 5)                                        # all Saturday
        or (wd == 6 and hh < 22)                         # Sunday before the 22:00 reopen
        or (wd == 4 and hh >= 21)                        # Friday after the 21:00 close
        or (wd <= 3 and hh == 21)                        # the Mon-Thu daily halt
    )


def _market_hours_between(t0: float, t1: float, *, cap_days: int = 30) -> float:
    """Hours the market was OPEN between t0 and t1 — the honest measure of staleness.

    ★★2026-08-17 WHY THIS EXISTS ALONGSIDE `_last_market_ts`. That one re-bases the clock to the
    last open instant, which forgives the shut hours ONLY WHILE YOU ARE STILL INSIDE the closed
    window. The moment Monday opens, `_last_market_ts(now) == now`, and the whole weekend lands back
    in the age: on Monday 08:48 a file last written Saturday read as **53h stale** and paged the
    operator, with every backup job having run and Finished. Forgiving a weekend only until the
    weekend ends is not forgiving it.

    This counts ACTUAL open time, so the weekend stays forgiven on Monday — while a death during
    trading hours still accumulates at full rate, which is the property that must not be lost.

    ★ EXACT, not sampled. A first cut walked fixed 15-minute steps and lost up to one step at every
    open/close boundary — and with the Mon-Thu daily halt that is TWO boundaries per trading day, so
    the error compounded ~30min/day and would have eaten hours off a 30h threshold. Because
    `_market_open_at` depends only on weekday and HOUR, the venue status is constant within any clock
    hour, so clipping each segment to the hour boundary is exact rather than approximate.
    """
    if t1 <= t0:
        return 0.0
    t0 = max(t0, t1 - cap_days * 86400)      # bound the walk; older than this is stale either way
    open_s, t = 0.0, t0
    while t < t1:
        cur = dt.datetime.fromtimestamp(t, dt.UTC)
        nxt = (cur.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)).timestamp()
        end = min(nxt, t1)
        if _market_open_at(cur):
            open_s += end - t
        t = end
    return open_s / 3600


def _last_market_ts(now: float) -> float:
    """The most recent instant the CME was trading, at or before `now`.

    ★★2026-08-15 WHY THIS EXISTS. capture.db and depth.db are written by the TAPE. When the market is
    shut there is no tape, so a flat "expect < 2h" is guaranteed to fire — every weekend, for two
    days, on the same Telegram channel that carries naked-position alarms. It did exactly that this
    Saturday: "capture.db not written for 9h | depth.db not written for 15h", with all four capture
    services ACTIVE and depth.db's last write 12 minutes after the Friday close. Nothing was wrong.

    An alarm that fires on schedule when nothing is wrong is not a safety net, it is training to
    ignore the channel — the same fault as the day-rider's every-tick "standing down" message.

    ⚠ THE FIX IS NOT TO SUPPRESS IT. It re-bases the clock onto MARKET time, so a genuine death is
    still caught: if capture stopped at Friday 10:00, this still reports 11h stale on Saturday,
    because it measures to the Friday 21:00 close, not to Saturday lunchtime. Only the hours the
    market was SHUT are forgiven.

    CME (MNQ/MGC): closed Fri 21:00Z -> Sun 22:00Z, and daily 21:00-22:00Z Mon-Thu.
    """
    t = dt.datetime.fromtimestamp(now, dt.UTC)
    for _ in range(8):                       # walk back at most a week; loop is bounded by design
        wd, hh = t.weekday(), t.hour         # Mon=0 .. Sun=6
        if _market_open_at(t):
            return t.timestamp()
        # step back to the last second before this closed window began
        if wd == 6 and hh < 22:
            t = t.replace(hour=0, minute=0, second=0) - dt.timedelta(seconds=1)   # -> Sat, still shut
        elif wd == 5:
            t = t.replace(hour=0, minute=0, second=0) - dt.timedelta(seconds=1)   # -> Fri 23:59:59
        elif wd == 4 and hh >= 21:
            t = t.replace(hour=21, minute=0, second=0) - dt.timedelta(seconds=1)  # -> Fri 20:59:59
        else:
            t = t.replace(hour=21, minute=0, second=0) - dt.timedelta(seconds=1)  # -> daily halt start
    return t.timestamp()

# (label, remote, max_age_h) — freshness comes from the newest object's timestamp
REMOTE = [
    ("B2 state   (encrypted: gazbot7.db, shadow.db, configs)", "gaz:state", 30),
    ("B2 tape    (plaintext parquet, DuckDB-readable in place)", "b2raw:gazbotv7/plain", 96),
    ("B2 V5 arch (21 tables incl. 574 MNQ trades)", "gaz:v5archive", None),
    ("B2 V5 full (alphabot_20260501.db.zst, 183MB)", "b2raw:AlphabotV2", None),
]


def sh(cmd, timeout=180):
    """Returns (stdout, err). ★ The error is RETURNED, never swallowed: the first cut piped stderr
    to /dev/null and returned only stdout, so an invalid rclone flag produced an empty listing that
    was indistinguishable from an empty bucket — and the monitor reported all four remotes as
    missing. A check that cannot tell "nothing there" from "I failed to look" is not a check."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), (r.stderr or "").strip()
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def scan() -> dict:
    """The slow, authoritative pass. Network listings included."""
    out = {"ts": time.time(), "local": [], "remote": [], "faults": []}
    now = time.time()

    for label, path, max_h, market_clock in LOCAL:
        try:
            st = os.stat(path)
            # ★ market_clock files age on OPEN-MARKET time — hours the venue was shut are not
            # staleness, and they stay forgiven after the venue reopens (see _market_hours_between).
            age_h = (_market_hours_between(st.st_mtime, now) if market_clock
                     else max(0.0, (now - st.st_mtime) / 3600))
            row = {"label": label, "path": path, "mb": round(st.st_size / 1e6, 1),
                   "age_h": round(age_h, 1), "ok": True}
            if st.st_size == 0:
                row["ok"] = False
                out["faults"].append(f"{label} is ZERO BYTES — this is how V5 looked when I wrongly "
                                     f"concluded its history did not exist")
            elif max_h and age_h > max_h:
                row["ok"] = False
                out["faults"].append(f"{label} not written for {age_h:.0f}h (expect <{max_h}h)")
        except FileNotFoundError:
            row = {"label": label, "path": path, "mb": 0, "age_h": None, "ok": False}
            out["faults"].append(f"{label} MISSING at {path}")
        out["local"].append(row)

    for label, remote, max_h in REMOTE:
        # ★ RECURSIVE, AND NEVER TRUNCATED BEFORE TAKING THE MAX. The first cut used
        # `--max-depth 3 | head -400`, which reported b2raw:gazbotv7/plain as 104h stale on its very
        # first run — a FALSE ALARM. The real paths are plain/tape/<kind>/<symbol>/<date>.parquet
        # (deeper than 3), and `head` samples alphabetically, so the newest object was never in the
        # sample. A monitor that cries wolf is worse than no monitor: it trains you to ignore the
        # one that matters. Take the max over ALL objects, then truncate for display only.
        # `rclone lsl` is ALREADY recursive — passing --recursive is an unknown flag and it exits
        # having listed nothing.
        raw, err = sh(f"rclone lsl {remote}", timeout=300)
        lines = [x for x in raw.splitlines() if x.strip()]
        n = len(lines)
        newest = None
        for line in lines:
            parts = line.split(None, 3)
            if len(parts) >= 3:
                stamp = f"{parts[1]} {parts[2][:8]}"
                newest = max(newest, stamp) if newest else stamp
        row = {"label": label, "remote": remote, "objects": n, "newest": newest, "ok": n > 0}
        if n == 0:
            out["faults"].append(f"{label}: rclone listed NOTHING at {remote}"
                                 + (f" — {err[:120]}" if err else
                                    " — credentials or connectivity; the offsite copy is UNVERIFIED"))
        elif max_h and newest:
            try:
                age_h = (now - time.mktime(time.strptime(newest, "%Y-%m-%d %H:%M:%S"))) / 3600
                row["age_h"] = round(age_h, 1)
                if age_h > max_h:
                    row["ok"] = False
                    out["faults"].append(f"{label}: newest object is {age_h:.0f}h old "
                                         f"(expect <{max_h}h) — is the backup timer still firing?")
            except Exception:
                pass
        out["remote"].append(row)

    # ★ THE INTERLOCK. prune_capture.py may not delete a day tape_mirror.py has not verified. If the
    # mirror stalls the prune correctly stops too — so capture.db GROWS. Growth you notice; a silent
    # hole in the tape you do not. Watch the symptom.
    try:
        gb = os.path.getsize(f"{GB}/data/capture.db") / 1e9
        out["capture_gb"] = round(gb, 2)
        if gb > 12:
            out["faults"].append(f"capture.db is {gb:.1f}GB — the prune is probably blocked by a "
                                 f"stalled tape-mirror (the interlock working as designed)")
    except Exception:
        pass
    try:
        man = json.load(open(f"{GB}/data/tape/_manifest.json"))
        out["mirror_days"] = len({k.split("|")[-1] for k in man.get("verified", {})})
    except Exception:
        out["mirror_days"] = None

    return out


def render(s: dict, quick: bool) -> None:
    age = (time.time() - s.get("ts", 0)) / 3600
    print(f"DATA INVENTORY  ({'cached, ' if quick else ''}{age:.1f}h old)")
    for r in s.get("local", []):
        flag = "  " if r["ok"] else "!!"
        print(f" {flag} {r['label']:<34} {r['mb']:>9,.1f} MB  "
              f"{('%.1fh' % r['age_h']) if r.get('age_h') is not None else '—':>7} old")
    for r in s.get("remote", []):
        flag = "  " if r["ok"] else "!!"
        extra = f"  newest {r['newest']}" if r.get("newest") else ""
        print(f" {flag} {r['label']:<34} {r['objects']:>6} objects{extra}")
    if s.get("mirror_days") is not None:
        print(f"    tape mirror: {s['mirror_days']} verified day-partitions | "
              f"capture.db {s.get('capture_gb', '?')}GB")
    for f in s.get("faults", []):
        print(f"  ! {f}")
    if not s.get("faults"):
        print("    all sources present and current")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true", help="hit the network; refresh the cache")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.scan:
        s = scan()
        tmp = STATUS + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(s, fh, indent=1)
        os.replace(tmp, STATUS)
        # ★★2026-08-18 DEDUPE ON THE SITUATION, NEVER ON THE MESSAGE TEXT.
        # This job runs 4-hourly and the message carries a live age ("not written for 42h"), which
        # INCREMENTS on every scan. notify.dedupe_ok() re-sends whenever the text changes — by
        # design, so a position going -2 -> -4 alarms at once — so deduping on the raw message would
        # suppress nothing at all: every scan is a "new" message describing an identical, unchanged
        # fault. The operator got the same finding every four hours and asked why it was not fixed.
        # Digits are therefore masked to build a STABLE signature of WHICH sources are faulting.
        # A genuinely NEW fault (another file, or a file recovering and re-failing) changes the
        # signature and pages immediately. [[a-correct-decision-repeated-every-tick-is-an-alarm-outage]]
        try:
            sys.path.insert(0, f"{GB}/src")
            from gazbot7.notify import dedupe_clear, dedupe_ok, notify
            if s["faults"]:
                sig = " | ".join(sorted(re.sub(r"[\d,.]+", "#", f) for f in s["faults"]))
                if dedupe_ok(_ALARM_KEY, sig, cooldown_s=_ALARM_COOLDOWN_S):
                    notify("⚠ GAZBOT DATA/BACKUP — " + " | ".join(s["faults"])[:800], critical=True)
            else:
                # ⚠ CLEAR ON RESOLVE, or a fault that heals and returns inside the cooldown is
                # swallowed. The cooldown suppresses a CONTINUING state, never a new occurrence.
                dedupe_clear(_ALARM_KEY)
        except Exception:
            pass
    else:
        try:
            s = json.load(open(STATUS))
        except Exception:
            print("no cached inventory yet — run: scripts/data_inventory.py --scan")
            return 0

    if a.json:
        print(json.dumps(s, indent=1))
    else:
        render(s, quick=not a.scan)
    return 1 if s.get("faults") else 0


if __name__ == "__main__":
    raise SystemExit(main())
