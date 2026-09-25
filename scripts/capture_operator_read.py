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
    # ⚠⚠ A SNAPSHOT COPY OLDER THAN THE PRESS IS NOT THIS PRESS. The ExecStartPre copy is taken
    # milliseconds before the interpreter starts, so a genuine one reads ~0.03s old. Anything
    # materially older is a leftover from a PREVIOUS press that a failed `cp` left in /run — belt
    # and braces behind the `rm -f` now in the units, because a MISLABELLED record is worse than a
    # missing one: it is indistinguishable from real data once it is in the file.
    if req.get("raw") and (req.get("file_age_s") or 0) > 5.0:
        print(f"discard: {kind} snapshot copy is {req['file_age_s']:.1f}s old — a stale /run file "
              f"from an earlier press, not this one")
        req = {}
    if not req.get("raw"):
        live = peek(WATCHED.get(kind, ""))
        if live.get("raw"):
            req = live
        else:
            # ⚠⚠2026-09-18 KIND-AWARE, because the old message was a FALSE EXPLANATION for a pass.
            # day_rider consumes day_rider_buy.txt and day_rider_claim.txt; it has never heard of
            # operator_pass.txt, so "consumed by day_rider" on a pass row would send a future
            # session hunting a race that cannot exist. A wrong cause is worse than no cause.
            if kind not in ("buy", "claim"):
                # ★★★2026-09-18 A STAMPLESS PASS IS A PHANTOM, AND IT MUST NOT BE RECORDED.
                # Nothing consumes operator_pass.txt, so a genuine pass ALWAYS finds its own file.
                # An empty one means inotify fired for some other reason — and DELETING the file
                # is itself a PathModified event, observed live: a cleanup `rm` at 10:24:26 fired
                # this unit 24 seconds after the real press and wrote a second, stampless row.
                # ⚠ That row is the worst possible kind of data: an unlabelled NEGATIVE EXAMPLE in
                # the very dataset built to learn his rejections — a pass he never made, at a
                # moment he was not even looking. A buy or claim in the same state is still
                # evidence (the press provably happened; the rider ate the label), which is why
                # only the non-order kinds are dropped.
                print(f"skip: {kind} fired with no request file — phantom (a delete is also a "
                      f"PathModified event). Nothing recorded.")
                return 0
            req = {**req, "note": "request already consumed by day_rider before the snapshot ran"}
    rec = {"ts": now.isoformat(), "kind": kind, "request": req}

    # ★★★2026-09-18 SUPPRESS THE DOUBLE FIRE AT THE SOURCE. `PathModified` triggers TWICE for one
    # write — measured over 2026-09-14..18, 52 of the consecutive same-kind gaps are UNDER TWO
    # SECONDS carrying an IDENTICAL request.raw, so 110 captured records were only ~57 real presses.
    # Downstream readers can dedupe a BUY or CLAIM on that stamp, but the second fire of a PASS
    # arrives with NO stamp at all (the ExecStartPre copy has already been overwritten), so it is
    # undedupable and would enter the dataset as a phantom press he never made — poisoning the very
    # negative-example sample this exists to build.
    # ⚠ Keyed on (kind, seconds since the last record of that kind), not on content: the phantom's
    # whole problem is that its content is empty.
    try:
        with open(LOG) as _fh:
            _last = None
            for _ln in _fh:
                _last = _ln
        if _last:
            _p = json.loads(_last)
            if _p.get("kind") == kind:
                _gap = (now - dt.datetime.fromisoformat(_p["ts"])).total_seconds()
                # 5s: the twin fires land ~1-2s apart; his own fastest genuine repeat press on
                # record is 83 seconds (2026-09-14 14:51:43 -> 14:53:06).
                if 0 <= _gap < 5.0:
                    print(f"skip: duplicate {kind} {_gap:.2f}s after the last one "
                          f"(PathModified fires twice per write)")
                    return 0
    except Exception:
        pass                      # a dedupe that cannot read must never LOSE a press
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

    # ★★★2026-09-25 CAPTURE THE GAUGE HE IS ACTUALLY LOOKING AT.
    # Operator: "if it slides powerfully to the right or left i buy or sell and it works."
    # ⚠⚠ THAT IS A CLAIM ABOUT THE SLOPE, AND NOTHING HERE HAS EVER MEASURED THE SLOPE. Every study
    # so far — the 80-cell grid, the gap rule — tested the LEVEL, i.e. where the marker SITS. He is
    # describing how fast it MOVES, which is a different quantity that happens to be the one I told
    # him to read ("read the slope, the level is just where you have been") and then never tested.
    # ⚠⚠⚠ AND UNTIL NOW HIS PRESSES WERE RECORDED WITHOUT IT. The operator-model dataset could not
    # see the method he was using, so no amount of collecting would ever have answered this. Adding
    # it here means the test builds itself out of what he already does — no new judgement, no new
    # button, nothing for him to remember.
    # ⚠ Rolling-3h window, matching the gauge he reads — not the session, which the gauge stopped
    # using this morning. A session-anchored capture would record a number he is not looking at.
    try:
        import sqlite3 as _sq
        _c = _sq.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
        _t = int(dt.datetime.now(dt.UTC).timestamp())

        def _cvd(a, b):
            return _c.execute(
                "SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size "
                "WHEN aggressor='sell' THEN -size ELSE 0 END),0) FROM ticks "
                "WHERE symbol='MNQ' AND ts_ms>=? AND ts_ms<?", (a * 1000, b * 1000)).fetchone()[0]

        g = {"window_min": 180}
        g["cvd_3h"] = _cvd(_t - 180 * 60, _t)
        # ★ THE SLIDE, at three speeds. Which one his eye is actually reading is unknown, so record
        #   all three and DECIDE LATER — but record them from the start, because ticks prune at 5
        #   days and a window not captured today can never be reconstructed.
        for _m in (1, 5, 15):
            g[f"slope_{_m}m"] = _cvd(_t - _m * 60, _t)
        _c.close()
        rec["gauge"] = g
    except Exception as e:
        # ⚠ LOUD, never silent — same rule as the context above. A dataset that drops its failures
        # quietly becomes "the presses where nothing went wrong".
        rec["gauge_error"] = f"{type(e).__name__}: {e}"
    with open(LOG, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k != "context"})[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
