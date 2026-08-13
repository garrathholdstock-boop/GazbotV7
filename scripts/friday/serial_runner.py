#!/usr/bin/env python3
"""SERIAL PHASE RUNNER — one phase, one process, one at a time. Use the whole night.

★★ WHY (operator, 2026-08-13): *"we are not running anthropic. why is it such a big deal. run less
agents at a time and use the time you have."*

He is right and it is the whole fix. Every failure this report has had is a consequence of doing it
all inside ONE long-lived Claude session:

  · MEMORY. That session accumulates context for all 16 phases plus its sub-agents, so RSS only ever
    grows — 6.46GB, 6.76GB, 7.31GB on three consecutive attempts. A fresh process per phase returns
    to zero between phases and stays FLAT. This is what CLAUDE.md meant by "the real fix is
    checkpointing"; it was never built.
  · NO RESUME. When that one process died, everything in flight died with it and recovery was a
    human reading a journal. Here the ARTIFACT ON DISK IS THE CHECKPOINT: a phase whose artifact
    already exists is skipped, so a re-run continues instead of restarting.
  · THE TAIL WAS UNPROTECTED. assemble -> proofread -> rev2 -> final is serial and runs LAST, so it
    is always what gets lost — which is exactly why no REV2 report has ever been ready by Saturday
    morning. Here it gets a RESERVED time budget and optional sections are dropped to protect it.

★ NO Workflow, NO Agent in the tool allowlist. This script is the orchestrator now, so a phase has
no reason to fan out — and every sub-agent it cannot spawn is memory it cannot consume.

★ THE INVERSION THAT MATTERS. Before: run everything, hope the tail survives. Now: the tail is
guaranteed and the OPTIONAL sections are what gets cut. A report missing one greenfield lab but
carrying its proofread and revision is worth far more than a complete draft nobody checked.

  PYTHONPATH=src scripts/friday/serial_runner.py [--deadline "06:30"] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

from friday.friday_phases import PHASES  # noqa: E402

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"
CLAUDE = "/root/.local/bin/claude"
LOG = f"{GB}/data/friday_durable.log"
ENV = {**os.environ, "HOME": "/root", "PYTHONPATH": "src",
       "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin"}

# The chain that MUST finish. Everything before it is a section the report can survive without.
TAIL = ("assemble", "proofread", "rev2", "final")
TOOLS = "Bash,Read,Write,Edit"          # deliberately no Workflow/Agent — see docstring


def log(m: str) -> None:
    line = f"{dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%M:%SZ} [serial] {m}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def notify(m: str, crit: bool = False) -> None:
    try:
        subprocess.run([PY, "-c", "import sys;from gazbot7.notify import notify;"
                        f"notify(sys.argv[1],critical={crit})", m[:900]],
                       cwd=GB, env=ENV, timeout=30)
    except Exception:
        pass


def order(phases):
    """Dependency order, stable. Phases with no deps keep their declared order, which is roughly
    cheapest-and-most-valuable first."""
    done, out, pool = set(), [], list(phases)
    while pool:
        moved = False
        for p in list(pool):
            if all(d in done for d in p["deps"]):
                out.append(p); done.add(p["key"]); pool.remove(p); moved = True
        if not moved:                    # a dep cycle or a dep on something not in PHASES
            log(f"UNRESOLVED deps, appending as-is: {[p['key'] for p in pool]}")
            out.extend(pool); break
    return out


def fresh(path: str, since: float) -> bool:
    """Is this artifact from THIS report run, not last week's?

    ★★ THE DRY-RUN CAUGHT THIS BEFORE IT SHIPPED. "Artifact exists" as a checkpoint is only correct
    within one run — the sections directory still holds LAST week's files, so a naive existence
    check skipped 11 of 12 phases and would have stapled a stale report together and called it
    Friday's. A checkpoint that cannot tell old work from new is not a checkpoint, it is a way to
    publish last week twice.
    """
    try:
        return os.path.getmtime(path) >= since
    except OSError:
        return False


def run_phase(p, budget_s: float) -> bool:
    """One phase, one fresh `claude -p`. Returns True if its artifact exists afterwards."""
    cap = int(min(p["timeout_s"], budget_s))
    if cap < 120:
        log(f"SKIP {p['key']} — only {cap}s of budget left")
        return False
    t0 = time.time()
    err = f"{GB}/reports/friday_v7/sections/{p['key']}.stderr.txt"
    try:
        with open(err, "w") as ef:
            r = subprocess.run([CLAUDE, "-p", p["prompt"], "--allowedTools", TOOLS],
                               stdout=subprocess.PIPE, stderr=ef, text=True,
                               timeout=cap, cwd=GB, env=ENV)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        rc = -1
    except Exception as e:
        log(f"{p['key']} EXCEPTION {type(e).__name__}: {e}")
        rc = -2
    took = time.time() - t0
    ok = os.path.exists(p["artifact"]) and time.time() - os.path.getmtime(p["artifact"]) < took + 120
    # ★ The ARTIFACT is the verdict, not the exit code. On 2026-07-31 the session exited 0 having
    # only DESCRIBED what it would do; the report was never built and the driver called it success.
    log(f"{p['key']}: rc={rc} {took/60:.1f}m artifact={'OK' if ok else 'MISSING'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline", default="06:30",
                    help="UTC HH:MM to be finished by (next occurrence)")
    ap.add_argument("--reserve-min", type=int, default=200,
                    help="minutes held back for assemble+proofread+rev2+final")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-run phases whose artifact exists")
    ap.add_argument("--since", default="",
                    help="UTC ISO cutoff; artifacts older than this are STALE and get rebuilt. "
                         "Default: the most recent Friday 22:00Z, i.e. this report window.")
    a = ap.parse_args()

    now = dt.datetime.now(dt.UTC)
    hh, mm = (int(x) for x in a.deadline.split(":"))
    dl = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if dl <= now:
        dl += dt.timedelta(days=1)
    total = (dl - now).total_seconds()

    # Everything written BEFORE this instant belongs to a previous week and must be rebuilt.
    if a.since:
        since = dt.datetime.fromisoformat(a.since).timestamp()
    else:
        d = now - dt.timedelta(days=(now.weekday() - 4) % 7)      # most recent Friday
        cut = d.replace(hour=22, minute=0, second=0, microsecond=0)
        if cut > now:
            cut -= dt.timedelta(days=7)
        since = cut.timestamp()
    log(f"=== SERIAL RUN — deadline {dl:%Y-%m-%dT%H:%MZ} ({total/3600:.1f}h), "
        f"reserve {a.reserve_min}m for the tail, "
        f"artifacts older than {dt.datetime.fromtimestamp(since, dt.UTC):%Y-%m-%dT%H:%MZ} are STALE ===")

    phases = order(PHASES)
    body = [p for p in phases if p["key"] not in TAIL]
    tail = [p for p in phases if p["key"] in TAIL]

    if a.dry_run:
        for p in body + tail:
            state = "HAVE" if fresh(p["artifact"], since) else "todo"
            print(f"  {'TAIL ' if p['key'] in TAIL else '     '}{p['key']:<22} {state}  "
                  f"cap {p['timeout_s']//60}m")
        print(f"\n  window {total/3600:.1f}h | reserve {a.reserve_min}m | "
              f"body budget {(total - a.reserve_min*60)/3600:.1f}h")
        return 0

    built, skipped, failed = [], [], []
    for p in body:
        left = (dl - dt.datetime.now(dt.UTC)).total_seconds() - a.reserve_min * 60
        if fresh(p["artifact"], since) and not a.force:
            skipped.append(p["key"]); log(f"HAVE {p['key']} — skipping (artifact is the checkpoint)")
            continue
        if left <= 120:
            # ★ Stop building SECTIONS rather than eat the tail's budget. A report missing a
            # greenfield lab but carrying its proofread is worth more than a complete unchecked one.
            log(f"BUDGET: stopping section builds to protect the tail ({left/60:.0f}m left)")
            failed.extend(q["key"] for q in body[body.index(p):]
                          if not fresh(q["artifact"], since))
            break
        (built if run_phase(p, left) else failed).append(p["key"])

    log(f"sections: {len(built)} built, {len(skipped)} already had, {len(failed)} missing")
    if failed:
        notify(f"Friday report: {len(failed)} section(s) not built ({', '.join(failed[:6])}). "
               f"Proceeding to assemble + proofread + REV2 with what exists.", crit=False)

    tail_ok = True
    for p in tail:
        left = (dl - dt.datetime.now(dt.UTC)).total_seconds()
        if fresh(p["artifact"], since) and not a.force:
            log(f"HAVE {p['key']} — skipping"); continue
        if not run_phase(p, left):
            tail_ok = False
            log(f"TAIL PHASE FAILED: {p['key']} — stopping (downstream depends on it)")
            notify(f"⚠ Friday report: {p['key']} FAILED. The report is not complete; "
                   f"re-run `scripts/friday/serial_runner.py` and it will resume from here "
                   f"(finished artifacts are skipped).", crit=True)
            break

    log(f"=== SERIAL RUN END — tail {'OK' if tail_ok else 'INCOMPLETE'} ===")
    if tail_ok:
        notify(f"✅ Friday report complete through REV2 — {len(built)} sections built, "
               f"{len(skipped)} reused, {len(failed)} skipped.", crit=False)
    return 0 if tail_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
