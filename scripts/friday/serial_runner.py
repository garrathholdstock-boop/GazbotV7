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


# ★★★2026-08-16 GREENFIELD CLUSTER ROTATION — the list has to fit the night.
# Seven greenfield clusters declare 1,140m of the 1,755m body list, against a 228m budget. Running
# all seven every week is why 8 sections went unbuilt on 08-14: they cannot all fit, so which ones
# get built was decided by clock order rather than by value. Two run each week, chosen by ISO week
# so the cycle is deterministic and every cluster comes round in under a month.
# ⚠ ROTATED-OUT CLUSTERS ARE LOGGED, NEVER SILENT. CLAUDE.md: "if a workflow bounds coverage, log
# what was dropped — silent truncation reads as 'covered everything' when it didn't."
ROTATING = ["gf_RIDER_ALL", "gf_UNCLASS", "gf_OPEN-NEWS", "gf_VACUUM", "gf_FLOW-LED", "gf_chopscalp"]
PER_WEEK = 2


def rotate(phases, week_iso: int):
    """Keep every non-rotating phase; admit only PER_WEEK clusters, cycling by ISO week."""
    pool = [k for k in ROTATING if any(p["key"] == k for p in phases)]
    if not pool:
        return phases, []
    start = (week_iso * PER_WEEK) % len(pool)
    picked = {pool[(start + i) % len(pool)] for i in range(min(PER_WEEK, len(pool)))}
    dropped = set(k for k in pool if k not in picked)
    # ★2026-08-16 (audit) STRIP THE DANGLING DEPS TOO. movement3 and gf_report declare deps on all
    # seven clusters; rotation deletes four, so order()'s topological sort could NEVER resolve and
    # fell through to "UNRESOLVED deps, appending as-is" on EVERY run — which meant the entire tail
    # was ordered by declaration rather than dependency, and a log line meant to catch real cycles
    # fired every week. Removing a phase means removing the edges into it.
    out = []
    for p in phases:
        if p["key"] in dropped:
            continue
        if any(d in dropped for d in p.get("deps", ())):
            p = {**p, "deps": [d for d in p["deps"] if d not in dropped]}
        out.append(p)
    return out, sorted(dropped)


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


def deps_newer(p, phases, since: float) -> list:
    """Which of p's dependencies are NEWER than p's own artifact? (make-style staleness)

    ★★★2026-08-30 THE BUG THIS FIXES, and it cost a whole weekend. `fresh()` asks only "is this
    artifact from THIS report window", which both an artifact and its inputs can satisfy while the
    artifact is still OLDER than them. On 08-29 `assemble` ran at 02:34 and five body sections were
    then rebuilt at 07:27-09:08. All six were "fresh", so assemble was SKIPPED on both retries and
    the rebuilt sections — including the day_rider section that was the whole point — were never
    folded into the published report. Two runs completed "successfully" and changed nothing the
    operator could see.
    A checkpoint must be invalidated by its INPUTS, not just by the calendar.
    """
    try:
        mine = os.path.getmtime(p["artifact"])
    except OSError:
        return []
    by_key = {q["key"]: q for q in phases}
    out = []
    for d in p.get("deps", []):
        q = by_key.get(d)
        if not q:
            continue
        try:
            if os.path.getmtime(q["artifact"]) > mine + 1:
                out.append(d)
        except OSError:
            pass
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


# ★2026-08-16 Below this a headless section produces nothing at all — measured: gf_MGC was handed
# 13.2m on 08-14 and returned an empty artifact, which is worse than skipping because it also
# consumed the budget. Observed pace for a section that DOES finish is 15-28m.
MIN_SLICE_S = 20 * 60


# ★★★2026-08-29 THE BODY RUNS IN PARALLEL NOW, and this is the fix that was needed all along.
# Operator: "i still dont understand why we are hitting limits… it can basically start straight away
# and churn away all night. you know the server and ram we have. just design it to churn within
# those limits and make sure it works."
#
# He was right and the file name was the tell. Every section ran ONE AT A TIME because the design
# assumed a `claude -p` costs ~2.3GB on a 7.5GB box. MEASURED 2026-08-29 while a real run was going:
#     one section agent      465MB steady (sampled over 30s, no spikes)
#     the WHOLE job, cgroup  1,435MB peak — runner + agent + every subprocess
#     unit ceiling           MemoryHigh 4,608MB
# So four concurrent agents is ~2.8GB against a 4.6GB ceiling. We were never memory-bound; we were
# bound by a serial loop protecting against a cost that is five times smaller than believed.
#
# WHAT THIS BUYS. 13 sections x ~23m serial = 299m, which did not fit the 166m body budget — that is
# why four were SKIPPED on 08-28 and eight went unbuilt. In waves of 4 the same 13 sections take
# 4 waves, so each one can be given ~80 MINUTES instead of 23 inside the same night.
#
# ⚠ THE TAIL STAYS SERIAL. assemble -> proofread -> rev2 -> final is a real dependency chain and
#   parallelising it would be nonsense. Only the body fans out.
# ⚠ DEPENDENCIES ARE HONOURED: movement3 and gf_report consume every greenfield cluster, so they
#   run in a later wave, never alongside their inputs.
# ⚠ MEMORY IS CHECKED BEFORE EACH LAUNCH, not assumed. If available RAM falls below MIN_FREE_MB the
#   scheduler waits rather than starting another agent — the box has had three global_oom kills and
#   the desk must always win contention.
MIN_FREE_MB = 1200


def _free_mb() -> int:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 10 ** 6            # unreadable -> do not let a missing gauge stall the run


def run_wave(phases, cap_s: float, workers: int):
    """Run `phases` concurrently, at most `workers` at once. Returns {key: ok}."""
    import threading
    results, lock = {}, threading.Lock()
    sem = threading.Semaphore(workers)

    def one(p):
        with sem:
            waited = 0
            while _free_mb() < MIN_FREE_MB and waited < 600:
                time.sleep(15); waited += 15
            if waited:
                log(f"MEM: waited {waited}s for headroom before {p['key']} "
                    f"({_free_mb()}MB free)")
            ok = run_phase(p, cap_s)
        with lock:
            results[p["key"]] = ok

    ts = [threading.Thread(target=one, args=(p,), daemon=True) for p in phases]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return results


def plan_waves(body, workers: int):
    """Split body into dependency-respecting waves of at most `workers`."""
    done, waves, remaining = set(), [], list(body)
    while remaining:
        ready = [p for p in remaining if all(d in done or d not in {q["key"] for q in body}
                                             for d in p.get("deps", []))]
        if not ready:                      # a cycle or an unbuildable dep — run the rest serially
            ready = remaining[:1]
        for i in range(0, len(ready), workers):
            waves.append(ready[i:i + workers])
        for p in ready:
            done.add(p["key"]); remaining.remove(p)
    return waves


def run_phase(p, budget_s: float) -> bool:
    """One phase, one fresh `claude -p`. Returns True if its artifact exists afterwards."""
    cap = int(min(p["timeout_s"], budget_s))
    if cap < 120:
        log(f"SKIP {p['key']} — only {cap}s of budget left")
        return False
    t0 = time.time()
    err = f"{GB}/reports/friday_v7/sections/{p['key']}.stderr.txt"
    # ★★★2026-08-29 KEEP STDOUT ON FAILURE. It was captured to a PIPE and thrown away, so when
    # eight phases died with rc=1 in 0.0s on 08-29 the reason went into a discarded variable and
    # left EMPTY stderr files — an unexplainable failure by construction. `claude -p` reports quota
    # and auth problems on STDOUT, which is exactly the class of failure that kills a whole night.
    # The tail of stdout is now appended to the phase's error file whenever rc is non-zero.
    out_txt = ""
    try:
        with open(err, "w") as ef:
            r = subprocess.run([CLAUDE, "-p", p["prompt"], "--allowedTools", TOOLS],
                               stdout=subprocess.PIPE, stderr=ef, text=True,
                               timeout=cap, cwd=GB, env=ENV)
        rc = r.returncode
        out_txt = r.stdout or ""
    except subprocess.TimeoutExpired as e:
        rc = -1
        out_txt = (e.stdout or "") if isinstance(getattr(e, "stdout", None), str) else ""
    except Exception as e:
        log(f"{p['key']} EXCEPTION {type(e).__name__}: {e}")
        rc = -2
    took = time.time() - t0
    if rc != 0 and out_txt:
        try:
            with open(err, "a") as ef:
                ef.write(f"\n--- STDOUT TAIL (rc={rc}) ---\n{out_txt[-4000:]}\n")
        except Exception:
            pass
    # ★2026-08-30 rc=-1 IS A TIMEOUT, NOT A CRASH — and yesterday's version of this line called
    # every one of them "the CLI died on invocation", which was flatly wrong and sent me looking at
    # auth for phases that had run their full 90-180 minute cap. Distinguish them:
    #   rc == -1  -> ran to the cap and was killed. Nothing to diagnose; it needed more time or the
    #                box was too slow (on 08-29 three of them overlapped a 93%-memory-pressure
    #                thrash caused by an orphaned 4.4GB grandchild).
    #   rc  >  0  -> the process exited by itself. With no output at all that is the CLI failing on
    #                invocation — quota, auth or binary.
    if rc == -1:
        log(f"{p['key']}: TIMED OUT at its {cap//60}m cap — not a crash. More time, or a faster box.")
    elif rc != 0 and not out_txt:
        log(f"{p['key']}: rc={rc} with NO output at all — the CLI died on invocation "
            f"(quota, auth or binary). Check `claude -p` by hand.")
    ok = os.path.exists(p["artifact"]) and time.time() - os.path.getmtime(p["artifact"]) < took + 120
    # ★ The ARTIFACT is the verdict, not the exit code. On 2026-07-31 the session exited 0 having
    # only DESCRIBED what it would do; the report was never built and the driver called it success.
    log(f"{p['key']}: rc={rc} {took/60:.1f}m artifact={'OK' if ok else 'MISSING'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    # ★★★2026-08-29 WINDOW WIDENED. The 08-28 run built 5 of 13 sections and its tail died: 13 body
    # phases against a 166m budget, with four SKIPPED for fair shares of 19-20m against the 20m floor.
    # The reserve was not the fault — run_phase() caps every phase at its declared timeout, so the
    # tail cannot exceed 255m and the reserve is correctly sized for the worst case. The fault was
    # that the WINDOW was 420m for 975m of declared work.
    # 05:15 -> 05:55: the operator needs it by 08:00 Paris = 06:00Z, so 05:15 was leaving 45m unused
    # against a hard requirement, every week.
    ap.add_argument("--deadline", default="05:55",
                    help="UTC HH:MM to be finished by (next occurrence). 05:55Z = 07:55 Paris, "
                         "just inside the operator's 08:00 Paris requirement.")
    # ★2026-08-16 (audit) 200 was UNDER-DECLARED: assemble 60 + proofread 60 + rev2 90 + final 45
    # = 255m. The tail loop hands each phase the whole remainder with no fair share, so a slow
    # assemble ate the reserve and `final` was skipped for lack of budget — the same "declared
    # timeouts never compared to the budget" defect this file was rewritten to fix, left unfixed on
    # the ONE chain that must finish. 255 = the tail's own declared sum.
    # ★2026-08-29 255 -> 225. Still ABOVE every measured tail (08-21: 122m, 08-28: 147m) and above
    # the sum of what the tail actually needs, but 30m is returned to the body. Not cut further:
    # 255 is the tail's declared worst case and `final` has already been starved once by a slow
    # assemble (08-16). Insurance, deliberately over-provisioned — just less so.
    ap.add_argument("--reserve-min", type=int, default=225,
                    help="minutes held back for assemble+proofread+rev2+final")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tail-only", action="store_true",
                    help="skip every body section and run assemble->proofread->rev2->final only. "
                         "For a RESUME: the sections already on disk are the checkpoint, and the "
                         "operator is waiting for the proofread, not for one more greenfield lab. "
                         "(--reserve-min is the wrong lever for this: it starves the body budget "
                         "but the loop still enters the first phase before it checks.)")
    ap.add_argument("--force", action="store_true", help="re-run phases whose artifact exists")
    ap.add_argument("--per-week", type=int, default=None,
                    help="how many greenfield clusters to admit (default PER_WEEK=2, sized for the "
                         "228m Friday window). A CATCH-UP RUN with a long deadline can afford all "
                         "of them: at the observed ~23m/section, six clusters is ~140m. Overriding "
                         "this on a FRIDAY re-creates the 08-14 failure where the list could not "
                         "fit and clock order decided what got built.")
    ap.add_argument("--workers", type=int, default=4,
                    help="sections to build CONCURRENTLY. Measured 2026-08-29: one agent is 465MB "
                         "and the whole job peaks at 1,435MB against a 4,608MB ceiling, so 4 is "
                         "~2.8GB and safe. The scheduler also refuses to launch below "
                         "MIN_FREE_MB of free RAM. The TAIL is always serial.")
    ap.add_argument("--since", default="",
                    help="UTC ISO cutoff; artifacts older than this are STALE and get rebuilt. "
                         "Default: the most recent Friday 22:00Z, i.e. this report window.")
    a = ap.parse_args()

    now = dt.datetime.now(dt.UTC)
    # ★2026-08-15 accept a FULL ISO datetime as well as HH:MM. HH:MM silently caps the window at 24h
    # (it rolls to tomorrow and stops), which is fine for the Friday-night run but cannot express a
    # weekend-long hunt — the desk is flat from Fri 21:00Z to Sun 22:00Z and that is ~49 usable hours.
    if "T" in a.deadline or "-" in a.deadline:
        dl = dt.datetime.fromisoformat(a.deadline)
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=dt.UTC)
    else:
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

    week_iso = dl.isocalendar().week
    if a.per_week is not None:
        globals()["PER_WEEK"] = max(0, min(a.per_week, len(ROTATING)))
        log(f"ROTATION OVERRIDE: admitting {PER_WEEK} of {len(ROTATING)} greenfield clusters "
            f"(default {2}) — only safe because this run's body budget is not the Friday 228m.")
    rotated, dropped = rotate(PHASES, week_iso)
    if dropped:
        log(f"ROTATION (ISO week {week_iso}): running {PER_WEEK} of {len(ROTATING)} greenfield "
            f"clusters. NOT run this week: {', '.join(dropped)}")
    phases = order(rotated)
    body = [p for p in phases if p["key"] not in TAIL]
    tail = [p for p in phases if p["key"] in TAIL]

    # ★★★2026-08-16 THE SCHEDULE WAS NEVER SATISFIABLE, AND NOTHING SAID SO.
    # 2026-08-14's run: 17 body phases declaring 1,755m of timeouts against a 228m body budget —
    # 7.7x over. `rehab` then took its full declared 90m cap (40% of the ENTIRE budget), produced
    # nothing, and starved everything downstream: gf_MGC got 13.2m of an intended 90 and also died,
    # then the budget hit zero with 8 sections unbuilt. That is not a phase misbehaving, it is a
    # wish-list being run as a plan. This block makes the arithmetic VISIBLE before the run commits
    # to it — the classic "instrument that reports healthy about something it never checks".
    body_cap = sum(q["timeout_s"] for q in body) / 60.0
    body_budget = (total - a.reserve_min * 60) / 60.0
    log(f"PREFLIGHT: {len(body)} body phases declare {body_cap:.0f}m of timeouts against a "
        f"{body_budget:.0f}m budget ({body_cap / max(body_budget, 1):.1f}x)")
    _w = max(1, a.workers)
    _waves = (len(body) + _w - 1) // _w
    log(f"PREFLIGHT: {len(body)} sections in ~{_waves} wave(s) of {_w} -> "
        f"{body_budget/max(_waves,1):.0f}m per section (serial would be "
        f"{body_budget/max(len(body),1):.0f}m)")
    if body_budget / max(_waves, 1) < MIN_SLICE_S / 60:
        log(f"PREFLIGHT ⚠ even in waves the per-section share is below the "
            f"{MIN_SLICE_S//60}m floor — sections WILL be skipped.")

    if a.dry_run:
        for p in body + tail:
            _sd = deps_newer(p, phases, since)
            state = ("todo" if _sd else "HAVE") if fresh(p["artifact"], since) else "todo"
            if _sd:
                state = "REBUILD"
            print(f"  {'TAIL ' if p['key'] in TAIL else '     '}{p['key']:<22} {state}  "
                  f"cap {p['timeout_s']//60}m")
        print(f"\n  window {total/3600:.1f}h | reserve {a.reserve_min}m | "
              f"body budget {(total - a.reserve_min*60)/3600:.1f}h")
        return 0

    if a.tail_only:
        log(f"TAIL-ONLY: skipping {len(body)} body section(s); "
            f"what is on disk is the report")
        body = []
    built, skipped, failed = [], [], []
    todo_body = [q for q in body
                 if a.force or not fresh(q["artifact"], since) or deps_newer(q, phases, since)]
    skipped = [q["key"] for q in body if q not in todo_body]
    for k in skipped:
        log(f"HAVE {k} — skipping (artifact is the checkpoint)")

    # ★★★2026-08-29 WAVES, NOT A QUEUE. The old loop ran one section at a time and gave each
    # 1.6x the even split of what remained — with 13 sections in a 166m budget that is ~20m each,
    # under the 20m floor, which is why four were SKIPPED and eight went unbuilt on 08-28.
    # Measured on 08-29: an agent is 465MB and the whole job peaks at 1,435MB against a 4,608MB
    # ceiling, so 4 at once is safe. 13 sections in waves of 4 is 4 waves — each section can have
    # ~80m instead of 20m, inside the SAME night.
    waves = plan_waves(todo_body, a.workers)
    if waves:
        log(f"SCHEDULE: {len(todo_body)} section(s) in {len(waves)} wave(s) of up to {a.workers} "
            f"(memory floor {MIN_FREE_MB}MB, {_free_mb()}MB free now)")
    for wi, wave in enumerate(waves, 1):
        left = (dl - dt.datetime.now(dt.UTC)).total_seconds() - a.reserve_min * 60
        waves_left = len(waves) - wi + 1
        if left <= 120:
            # ★ Stop building SECTIONS rather than eat the tail's budget. A report missing a
            # greenfield lab but carrying its proofread is worth more than a complete unchecked one.
            log(f"BUDGET: stopping section builds to protect the tail ({left/60:.0f}m left)")
            failed.extend(q["key"] for w in waves[wi-1:] for q in w)
            break
        # each WAVE gets an even share of what is left; inside a wave the phases run together, so
        # the wave costs the SLOWEST member, not the sum.
        cap = min(left / waves_left, max(q["timeout_s"] for q in wave))
        if cap < MIN_SLICE_S:
            log(f"SKIP wave {wi} ({', '.join(q['key'] for q in wave)}) — {cap/60:.0f}m share is "
                f"below the {MIN_SLICE_S//60}m minimum a section needs to produce anything")
            failed.extend(q["key"] for q in wave)
            continue
        log(f"WAVE {wi}/{len(waves)}: {', '.join(q['key'] for q in wave)} — {cap/60:.0f}m each")
        for k, ok in run_wave(wave, cap, a.workers).items():
            (built if ok else failed).append(k)

    log(f"sections: {len(built)} built, {len(skipped)} already had, {len(failed)} missing")
    if failed:
        notify(f"Friday report: {len(failed)} section(s) not built ({', '.join(failed[:6])}). "
               f"Proceeding to assemble + proofread + REV2 with what exists.", crit=False)

    tail_ok = True
    for p in tail:
        left = (dl - dt.datetime.now(dt.UTC)).total_seconds()
        stale_deps = deps_newer(p, phases, since)
        if fresh(p["artifact"], since) and not a.force and not stale_deps:
            log(f"HAVE {p['key']} — skipping"); continue
        if stale_deps:
            log(f"REBUILD {p['key']} — its inputs are newer: {', '.join(stale_deps)}")
        if not run_phase(p, left):
            tail_ok = False
            log(f"TAIL PHASE FAILED: {p['key']} — stopping (downstream depends on it)")
            notify(f"⚠ Friday report: {p['key']} FAILED. The report is not complete; "
                   f"re-run `scripts/friday/serial_runner.py` and it will resume from here "
                   f"(finished artifacts are skipped).", crit=True)
            break

    # ★★★2026-08-30 THE OPERATOR IS TOLD BY THE DRIVER, NOT BY AN AGENT. The "your report is ready"
    # Telegram used to be the last instruction inside `final`'s prompt — a phase that has never once
    # run to completion — so it has never fired. A notification that depends on an LLM finishing a
    # long narrative task is a lottery ticket, not a notification. This is deterministic: it reads
    # what is on disk and says so, and it fires whether the tail finished or not, because "it did not
    # finish" is exactly the message worth sending.
    try:
        import glob as _glob
        _reps = sorted(_glob.glob(f"{GB}/src/gazbot7/web_static/weekly_*.html"),
                       key=os.path.getmtime)
        if _reps:
            _r = _reps[-1]
            _html = open(_r, encoding="utf-8", errors="replace").read()
            _h2 = _html.count("<h2"); _tb = _html.count("<table")
            _kb = os.path.getsize(_r) // 1024
            _missing = [q["key"] for q in body + tail
                        if not fresh(q["artifact"], since) and not a.tail_only]
            notify(("✅ Friday report READY — " if tail_ok else "⚠ Friday report INCOMPLETE — ")
                   + f"{os.path.basename(_r)} · {_h2} sections · {_tb} tables · {_kb}KB"
                   + (f" · {len(_missing)} section(s) unbuilt: {', '.join(_missing[:5])}"
                      if _missing else " · all sections present")
                   + "\n/v7/reports", crit=not tail_ok)
        else:
            notify("⚠⚠ Friday report: NO weekly_*.html on disk at all after the run.", crit=True)
    except Exception as _e:
        log(f"final ping failed ({type(_e).__name__}: {_e}) — the report itself is unaffected")

    log(f"=== SERIAL RUN END — tail {'OK' if tail_ok else 'INCOMPLETE'} ===")
    if tail_ok:
        notify(f"✅ Friday report complete through REV2 — {len(built)} sections built, "
               f"{len(skipped)} reused, {len(failed)} skipped.", crit=False)
    return 0 if tail_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
