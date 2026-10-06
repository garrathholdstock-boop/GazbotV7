#!/usr/bin/env python3
"""THE OVERNIGHT GUARD FOR THE RECURSIVE LOOP — because a dead CLI and a flat
result look identical in the artefacts.

★★★ WHY THIS EXISTS. On 2026-10-03 iteration 1's training week scored -$2,106 and I
reported it as "the loss is entirely in the exits, side 0.857 / capture 0.008". Two of
those five days were NOT trading decisions at all: 2026-07-29 errored on 125 of 138
calls and 2026-07-30 on 138 of 138 — my session's token outage. 07-30 made ZERO trades
and booked exactly $0.00, which reads in every summary as a flat day rather than a blind
one. The nightly review then wrote iteration 2's rule set from that week.

This is [[an-instrument-that-reports-healthy-about-something-it-does-not-check]] and
[[durable-router-dies-on-oauth-expiry]] in one: the loop exits 0, the artefact parses,
the day is scored, and nothing anywhere says the model never answered.

WHAT IT DOES
  · probes the claude CLI every PROBE_EVERY_S. DEAD_STREAK consecutive failures means
    every remaining day would be blind, so it SIGTERMs the loop rather than letting it
    burn iterations 4-12 on empty tape. A single blip poisons one day and is left alone
    — the post-hoc filter below catches that; killing the night over 7 minutes is worse.
  · stamps every new day artefact with its own error rate into a side file. It never
    rewrites the artefact: the loop owns that file and a second writer would race it.
  · holds any Telegram until quiet hours end. He is asleep and this is a BACKTEST —
    nothing is at risk and nothing can be acted on at 3am. critical=False, always.

⚠⚠ READ-ONLY ON THE DESK. It touches no switch file, no request file, no order path, no
database. The ONLY thing it can signal is a SIGTERM to a backtest process it identifies
by interpreter path and script name.
⚠ `pgrep -f` self-match: the pattern lives INSIDE this file, never on its command line,
and is anchored on the interpreter. That self-match cost a Telegram four times already.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.notify import notify, in_quiet_hours      # noqa: E402

GB = "/home/alphabot/gazbot7"
ART = f"{GB}/reports/sim_week_recursive"
OUT = f"{GB}/reports/recursive_loop/poison.json"
# ★★2026-10-06 WATCH EVERY RESEARCH RUNNER, NOT JUST THE LOOP. The guard was built for
# recursive_loop and a 127M-token A/B was launched beside it unguarded — the usage limit hit
# mid-run and 16 of 20 arms errored 138/138, producing nothing. The loop survived with
# 1-error days because the guard was watching IT. Guarding one runner and not the next is
# [[an-instrument-that-reports-healthy-about-something-it-does-not-check]].
WATCHED = ("recursive_loop.py", "ab_rule_toggle.py", "paired_arm.py")
LOOP_PAT = r"[.]venv/bin/python .*(recursive_loop|ab_rule_toggle|paired_arm)\.py"

PROBE_EVERY_S = 300
DEAD_STREAK = 3            # ~15 min of a dead CLI before the night is written off
POISON_RATE = 0.10         # >10% errored calls and the day is not a trading decision


def log(m: str) -> None:
    print(f"{dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%M:%SZ} night_guard: {m}", flush=True)


def loop_pids() -> list[int]:
    """Only the PYTHON process actually executing recursive_loop.py.

    ⚠⚠ `pgrep -f` matches ANY command line containing the pattern, and on 2026-10-03 the
    first version of this function returned the milestone watcher's parent shell — a
    `bash -c` whose heredoc text merely CONTAINED "recursive_loop.py". That shell is not
    the loop, it never exits while the session lives (so `if not pids` could never become
    true and the guard would never stand down), and SIGTERMing it would have killed the
    milestone watcher instead. This desk has now paid for that same self-match five
    times. So pgrep only NOMINATES; /proc/<pid>/cmdline DECIDES.
    """
    p = subprocess.run(["pgrep", "-f", LOOP_PAT], capture_output=True, text=True)
    out = []
    for x in p.stdout.split():
        try:
            argv = open(f"/proc/{int(x)}/cmdline", "rb").read().split(b"\0")
            argv = [a.decode(errors="replace") for a in argv if a]
        except Exception:
            continue
        if not argv or os.path.basename(argv[0]) not in ("python", "python3"):
            continue                      # a shell whose text mentions the script is not the script
        if not any(a.endswith(w) for a in argv[1:] for w in WATCHED):
            continue
        out.append(int(x))
    return out


def cli_ok() -> bool:
    try:
        p = subprocess.run(["claude", "-p", "Reply with the single word OK."],
                           capture_output=True, text=True, timeout=90)
        return p.returncode == 0 and "OK" in p.stdout
    except Exception:
        return False


def scan() -> dict:
    """Error rate per day artefact. Never writes the artefact itself."""
    out = {}
    for f in sorted(glob.glob(f"{ART}/loop*_*.json")):
        try:
            r = json.load(open(f))
        except Exception:
            continue                      # a half-written file is not a verdict
        c = r.get("calls") or []
        if not c:
            continue
        err = sum(1 for x in c if x.get("error"))
        out[os.path.basename(f)] = {
            "day": r.get("day"), "calls": len(c), "errors": err,
            "rate": round(err / len(c), 4), "trades": len(r.get("trades") or []),
            "net_usd": r.get("net_usd"),
            "poisoned": err / len(c) > POISON_RATE,
        }
    return out


def hold_then_send(msg: str) -> None:
    held = False
    while in_quiet_hours(dt.datetime.now(dt.UTC)):
        held = True
        time.sleep(300)
    notify(msg + ("\n(held until after quiet hours)" if held else ""),
           critical=False, mark=False, weekend_ok=True)


def main() -> int:
    dead = 0
    seen_poison: set[str] = set()
    log(f"armed · probing every {PROBE_EVERY_S}s · kill after {DEAD_STREAK} dead probes")
    while True:
        pids = loop_pids()
        if not pids:
            log("loop is gone — standing down")
            json.dump(scan(), open(OUT, "w"), indent=1)
            return 0

        ok = cli_ok()
        dead = 0 if ok else dead + 1
        if not ok:
            log(f"claude CLI probe FAILED ({dead}/{DEAD_STREAK})")

        if dead >= DEAD_STREAK:
            for p in pids:
                try:
                    os.kill(p, signal.SIGTERM)
                except Exception:
                    pass
            log(f"STOPPED the loop (pids {pids}) — CLI dead {dead} probes running")
            json.dump(scan(), open(OUT, "w"), indent=1)
            hold_then_send(
                "⛔ RECURSIVE LOOP STOPPED OVERNIGHT — the claude CLI stopped answering\n"
                f"{dead} consecutive probes failed, so every further day would have been "
                "blind.\nStopped deliberately rather than burning iterations on empty tape.\n"
                "Fix: run `claude` then /login, then relaunch the loop.\n"
                "Nothing was at risk — this is a backtest, no order path.")
            return 0

        snap = scan()
        json.dump(snap, open(OUT, "w"), indent=1)
        fresh = [k for k, v in snap.items() if v["poisoned"] and k not in seen_poison]
        for k in fresh:
            seen_poison.add(k)
            log(f"POISONED DAY {k}: {snap[k]['errors']}/{snap[k]['calls']} calls errored "
                f"— not a trading decision, must not be scored or reviewed")

        time.sleep(PROBE_EVERY_S)


if __name__ == "__main__":
    raise SystemExit(main())
