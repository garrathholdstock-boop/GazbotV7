#!/usr/bin/env python3
"""CAPTURE THE OPERATOR'S READ — a snapshot of the tape at the instant he presses.

★★★ WHY THIS IS THE MOST VALUABLE THING THIS DESK CAN COLLECT. Measured on the live record, single
lot: HIS MANUAL ENTRIES ARE +$78.27/trade over 28 trades at an 82% win rate — indistinguishable
from the rider's automatic entries and 37x the automated gates' +$2.10. Eleven months of studies
have failed to reproduce what he does, and 119 calibrations of his manual EXITS all lost. The
reason is simple and was never addressed: NOBODY EVER RECORDED WHAT HE WAS LOOKING AT. Every study
has tried to reverse-engineer his read from its outcome. This records the INPUT.

His own description of a winning press (2026-09-14, +$839 on the day): "i saw that usual persistent
downward grind on the first one, and then i saw it upward after it left the tunnel at the bottom,
and i thought from what ive seen historically they will continue for a while until they hit the next
tunnel." Both stated conditions were then MEASURED AND REFUTED (continuation 42-47% over 768 breaks;
transit 1.04x a duration-matched control). So what he is reading is NOT what he thinks he is
reading, which is exactly why it has to be captured rather than described.

★★ READ-ONLY, AND THE ONE THING IT MUST NEVER DO IS TOUCH THE REQUEST FILE. day_rider consumes
`day_rider_buy.txt` / `day_rider_claim.txt` and consumes them; a second reader that disposed of one
in any way would silently EAT THE OPERATOR'S PRESS. This opens them read-only and writes only its
own log. A test asserts that this file contains NO destructive filesystem call of any kind — which
is strict enough that it matches the words themselves, so this paragraph deliberately does not
name them.

⚠ IT MUST NOT DELAY THE ORDER. The rider reaches a completed tick 1.35s after the write via its own
path unit; this runs as a SEPARATE oneshot on the same inotify event, so the two do not queue.
⚠ COLLECT NOW, MODEL LATER. This makes no prediction and fits nothing. With 30-50 labelled presses
the question becomes answerable: what separates his winners from his losers? Answering it before
the data exists is how the 119 calibrations happened.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

GB = "/home/alphabot/gazbot7"
LOG = f"{GB}/data/operator_reads.jsonl"
WATCHED = {"buy": f"{GB}/data/day_rider_buy.txt", "claim": f"{GB}/data/day_rider_claim.txt",
           # ★★★2026-09-18 THE "LOOKED AND PASSED" PRESS — the NEGATIVE EXAMPLE, and the thing
           # eleven months of study never had. Every other record here is a "yes"; a decision
           # boundary cannot be learned from one side of it, which is why 119 calibrations failed.
           # ⚠⚠⚠ ITS FILE IS DELIBERATELY ONE NO ORDER PATH READS. day_rider consumes
           # day_rider_buy.txt and day_rider_claim.txt; it has never heard of operator_pass.txt, so
           # this button is INCAPABLE of placing an order however it is pressed or replayed. A
           # test asserts the rider's source never names it.
           "pass": f"{GB}/data/operator_pass.txt"}
# ★★2026-09-14 THE RACE THAT ATE THE LABEL. day_rider reaches a completed tick ~1.35s after the
# write and CONSUMES the request; this snapshot spends ~1.7s starting Python and building the
# day's context, so by the time it looked, the file was already empty and every captured row read
# `request: {}` — a dataset of presses with no record of WHAT WAS PRESSED. Measured, not guessed:
# the first live test captured an empty request. systemd copies the file in ExecStartPre, before
# the interpreter exists, and we read that snapshot instead. The original is never touched.
PRE = {"buy": "/run/gazbot7_press_buy.txt", "claim": "/run/gazbot7_press_claim.txt",
       # ⚠ A pass is not consumed by anything, so it cannot lose its own race — but it takes the
       # same ExecStartPre copy so all three kinds read through one code path.
       "pass": "/run/gazbot7_press_pass.txt"}


def peek(path: str) -> dict:
    """Read a request file WITHOUT consuming it. Never writes, never clears."""
    try:
        raw = open(path).read().strip()
    except OSError:
        return {}
    age = None
    try:
        age = dt.datetime.now(dt.UTC).timestamp() - os.path.getmtime(path)
    except OSError:
        pass
    return {"raw": raw[:400], "file_age_s": round(age, 2) if age is not None else None}


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    now = dt.datetime.now(dt.UTC)
    # the ExecStartPre copy first; fall back to the live file if the copy is missing
    req = peek(PRE.get(kind, ""))
    if not req.get("raw"):
        live = peek(WATCHED.get(kind, ""))
        if live.get("raw"):
            req = live
        else:
            req = {**req, "note": "request already consumed by day_rider before the snapshot ran"}
    rec = {"ts": now.isoformat(), "kind": kind, "request": req}
    # THE READ ITSELF: the same whole-day context the tape reader judges from, so a press and a
    # reader decision are directly comparable later.
    try:
        sys.path.insert(0, f"{GB}/scripts")
        from tape_reader import context
        ctx, facts = context("MNQ")
        rec["facts"] = facts
        rec["context"] = ctx
    except Exception as e:
        # LOUD, never silent: a snapshot that fails must still leave a row saying it failed, or the
        # dataset quietly becomes "the presses where nothing went wrong".
        rec["context_error"] = f"{type(e).__name__}: {e}"
    with open(LOG, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k != "context"})[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
