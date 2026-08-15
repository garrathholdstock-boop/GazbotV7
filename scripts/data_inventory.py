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
import glob
import json
import datetime as dt
import os
import subprocess
import sys
import time

GB = "/home/alphabot/gazbot7"
STATUS = f"{GB}/data/data_status.json"

# (label, path, max_age_h or None if it never changes)
# (label, path, max_age_h, market_clock) — market_clock=True measures staleness against the last
# instant the MARKET WAS OPEN rather than wall-clock. See _last_market_ts().
LOCAL = [
    ("trade record   gazbot7.db", f"{GB}/data/gazbot7.db", 30, False),
    ("shadow book    shadow.db", f"{GB}/data/shadow.db", 30, False),
    # ★2026-08-15 the gold shadow book. Its own store by design (MGC_SHADOW_SCOPE §4), which is
    # exactly why it was in no backup, no inventory and no sweep — audit finding #6.
    ("gold shadow    shadow_mgc.db", f"{GB}/data/shadow_mgc.db", 30, False),
    ("live tape      capture.db", f"{GB}/data/capture.db", 2, True),
    ("L2 depth       depth.db", f"{GB}/data/depth.db", 2, True),
    ("tape manifest  _manifest.json", f"{GB}/data/tape/_manifest.json", 30, False),
]


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
        open_now = not (
            (wd == 5)                                        # all Saturday
            or (wd == 6 and hh < 22)                         # Sunday before the 22:00 reopen
            or (wd == 4 and hh >= 21)                        # Friday after the 21:00 close
            or (wd <= 3 and hh == 21)                        # the Mon-Thu daily halt
        )
        if open_now:
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
            # ★ tape files age on MARKET time — the hours the venue was shut are not staleness.
            ref = _last_market_ts(now) if market_clock else now
            age_h = max(0.0, (ref - st.st_mtime) / 3600)
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
        if s["faults"]:
            try:
                sys.path.insert(0, f"{GB}/src")
                from gazbot7.notify import notify
                notify("⚠ GAZBOT DATA/BACKUP — " + " | ".join(s["faults"])[:800], critical=True)
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
