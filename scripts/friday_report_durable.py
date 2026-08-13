#!/usr/bin/env python3
"""DURABLE FRIDAY REPORT — builds the V7 weekly report HEADLESS, no live Claude session needed.

systemd: gazbot7-friday-report.timer (Fri 22:07 UTC) -> .service -> this script.

★★ FIX 2026-08-01 — the maiden run (2026-07-31) FAILED: the old driver used `claude -p "launch
the Workflow"`, but print-mode EXITS after the model's turn (right after launching), and the
Workflow is a BACKGROUND task that dies with the session → the build never completed. Root cause:
a headless session must stay ALIVE for the whole ~2h build; `-p` does not.

FIX: drive claude with stream-json I/O and HOLD STDIN OPEN so the session persists (the only mode
where background-task notifications arrive — per the CLI: "only works with --print and
--output-format=stream-json"). The driver keeps the session alive, POLLS for the finished report
file, then closes stdin to end the session. Root can't use --dangerously-skip-permissions, so we
pass an explicit --allowedTools.

⚠ NEEDS ONE LIVE END-TO-END VALIDATION before it's trusted for an unattended Friday (a real ~2h
run — the stream-json keep-alive was not fully validated at implementation time). Until validated,
the session personal-read/recover cron is the safety net (it recovered the 07-31 run by launching
the workflow in a live session, which is proven to work).

FAIL-SAFE: every step logged to data/friday_durable.log + Telegram-alerted; hard 5h timeout.
"""
import subprocess, os, sys, json, time, threading

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"
CLAUDE = "/root/.local/bin/claude"
SEC = f"{GB}/reports/friday_v7/sections"
LOG = f"{GB}/data/friday_durable.log"
WEB = f"{GB}/src/gazbot7/web_static"
WF = f"{GB}/scripts/friday/friday_v7_maxdepth.workflow.js"
ENV = {**os.environ, "HOME": "/root", "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": "src"}
POLL_S, MAX_S = 60, 18000  # poll every 60s, hard cap 5h


def log(m):
    try:
        with open(LOG, "a") as f:
            f.write(f"{time.strftime('%FT%TZ', time.gmtime())} {m}\n")
    except Exception:
        pass


def notify(msg, crit=True):
    try:
        subprocess.run([PY, "-c", "import sys;from gazbot7.notify import notify;notify(sys.argv[1],critical=" + ("True" if crit else "False") + ")", msg],
                       cwd=GB, env=ENV, timeout=30)
    except Exception:
        pass


def newest_weekly_mtime():
    try:
        fs = [os.path.join(WEB, f) for f in os.listdir(WEB) if f.startswith("weekly_") and f.endswith(".html")]
        return max((os.path.getmtime(f) for f in fs), default=0)
    except Exception:
        return 0


def preflight_auth() -> tuple[bool, str]:
    """Can headless claude authenticate AT ALL? Checked BEFORE the 20-minute census freeze.

    ★★2026-08-13. On this date the durable ROUTER produced 125 consecutive no-op ticks over 10.5
    hours because its OAuth token had expired — and it looked healthy the whole time. This report
    runs the same way, once a week, unattended, at 22:07 on a Friday. An expired token here costs
    the entire report and is not discovered until Saturday: exactly the 2026-08-07 failure, where
    the session exited rc=1 eleven minutes in and the log said only "report not built".
    A 20-second check turns a silent weekend-long loss into a page the operator can act on in the
    minute it happens. The operator re-logs in by hand (he declined a long-lived API key), so the
    alarm IS the mitigation.
    """
    try:
        r = subprocess.run([CLAUDE, "-p", "reply with exactly: PREFLIGHT_OK", "--allowedTools", ""],
                           capture_output=True, text=True, timeout=120,
                           env={**ENV, "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin"})
        out = (r.stdout or "").strip()
        if r.returncode == 0 and "PREFLIGHT_OK" in out:
            return True, "ok"
        return False, f"rc={r.returncode} out={out[:160]!r} err={(r.stderr or '')[-160:]!r}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    log("=== DURABLE FRIDAY REPORT — START (stream-json keep-alive) ===")

    ok, why = preflight_auth()
    if not ok:
        log(f"PREFLIGHT FAILED — headless claude cannot run: {why}")
        notify(f"⚠⚠ FRIDAY REPORT ABORTED AT THE GATE — headless claude cannot authenticate "
               f"({why}). Nothing has been built and nothing will be. Run `claude` on the box and "
               f"/login, then: systemctl start gazbot7-friday-report.service", crit=True)
        log("=== DURABLE FRIDAY REPORT — END (ok=False, preflight) ===")
        return 1
    log("preflight auth OK")

    notify("📋 Durable Friday report starting (headless) — census freeze then keep-alive max-depth build + self-proofread.", crit=False)
    baseline_mtime = newest_weekly_mtime()

    # 1. PRE-FREEZE the census out-of-band
    try:
        os.makedirs(SEC, exist_ok=True)
        subprocess.run(f"{PY} scripts/run_census.py --days 7 --html {SEC}/movement1_census.html > {SEC}/census_stdout.txt 2>{SEC}/census_err.txt",
                       shell=True, cwd=GB, env=ENV, timeout=1200)
        subprocess.run(f"{PY} scripts/friday/parse_census_summary.py", shell=True, cwd=GB, env=ENV, timeout=180)
        log("census frozen OK" if os.path.exists(f"{SEC}/census_summary.json") else "census MISSING")
    except Exception as e:
        log(f"census freeze error: {e}"); notify(f"⚠ Durable Friday: census freeze errored ({e}).", crit=True)

    # 1b. ★2026-08-13 PART 0 — the progress page. Generated here, not by an agent phase, for the
    # same reason the census is: it is deterministic. It is a straight read of the trade record, so
    # a model writing it could only introduce error. Cheap (<1s) and it must never be stale — it is
    # the FIRST thing in the report and the one section a reader checks against their own memory.
    try:
        subprocess.run(f"{PY} scripts/friday/progress_page.py", shell=True, cwd=GB, env=ENV, timeout=120)
        ok = os.path.exists(f"{SEC}/part0_progress.html")
        log("progress page OK" if ok else "progress page MISSING")
        if not ok:
            notify("⚠ Durable Friday: Part 0 progress page did not generate — the report will open "
                   "on Part 1 instead.", crit=False)
    except Exception as e:
        log(f"progress page error: {e}")
        notify(f"⚠ Durable Friday: progress page errored ({e}).", crit=False)

    # 2. stream-json session, stdin HELD OPEN so the workflow (background task) survives to completion
    prompt = (
        f"Build the GAZBOT V7 Friday weekly report. The census is ALREADY frozen at {SEC}/census_summary.json "
        f"(do NOT run run_census.py). Launch the max-depth workflow via the Workflow tool with scriptPath '{WF}' "
        f"and let it run fully (Census->Desks->Rehab->BigRuns->Greenfield->Skeptic->Assemble->Proofread; Phase 7 "
        f"proof-reads as the operator, gap-fills, does Revision 2, and pings). Keep working until it completes; then "
        f"verify weekly_<date>.html + .pdf + monday_<date>.html exist in src/gazbot7/web_static/ and the publish gate "
        f"passed. If it dies mid-run, read its journal and resume via Workflow scriptPath+resumeFromRunId."
    )
    msg = json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}}) + "\n"
    done = False   # bound BEFORE the try: an exception in Popen must not NameError the exit-code path
    try:
        # ★★2026-08-07 --verbose IS MANDATORY and its absence killed the 08-07 run.
        # The CLI now errors "When using --print, --output-format=stream-json requires --verbose" and
        # exits rc=1 in seconds. This script worked on 07-31; the claude CLI was updated to 2.1.221
        # since, and nothing re-tested the invocation — a dependency changed under a script that only
        # runs once a week. ⚠ stderr was DEVNULL, so the error was INVISIBLE: the log said only
        # "claude session exited early (rc=1)" with no reason. stderr now goes to a file.
        err_path = f"{SEC}/claude_stderr.txt"
        _err = open(err_path, "w")
        p = subprocess.Popen([CLAUDE, "-p", "--verbose", "--input-format", "stream-json",
                              "--output-format", "stream-json",
                              "--allowedTools", "Bash", "Workflow", "Read", "Write", "Edit", "Agent", "Task"],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=_err, text=True, cwd=GB, env=ENV)
        p.stdin.write(msg); p.stdin.flush()          # send prompt, KEEP stdin open (session persists)
        t0 = time.time()
        while time.time() - t0 < MAX_S:
            time.sleep(POLL_S)
            if newest_weekly_mtime() > baseline_mtime + 60:   # a fresh report landed
                # give Phase-7 proofread time to finish its Rev2 rewrite, then finish
                time.sleep(600); done = True; break
            if p.poll() is not None:                          # session died early = the bug recurred
                try:
                    _err.flush()
                    tail = open(err_path).read()[-400:].replace("\n", " | ")
                except Exception:
                    tail = "(stderr unreadable)"
                log(f"claude session exited early (rc={p.returncode}) — report not built · stderr: {tail}")
                break
        try:
            p.stdin.close()
            p.wait(timeout=60)
        except Exception:
            p.kill()
        if done:
            log("report built OK (fresh weekly_*.html)"); notify("✅ Durable Friday report built (headless). Verify /v7/reports.", crit=False)
        else:
            log("NO fresh report after build window"); notify("⚠ Durable Friday: headless build did NOT produce a fresh report — session-backstop must recover. CHECK.", crit=True)
    except Exception as e:
        log(f"build error: {e}"); notify(f"⚠ Durable Friday build error: {e} — CHECK.", crit=True)
    log(f"=== DURABLE FRIDAY REPORT — END (ok={done}) ===")
    return done


if __name__ == "__main__":
    # ★ FIX 2026-08-01 (#2) — EXIT CODE must reflect the REPORT, not the driver.
    # The 07-31 run logged its own failure and still returned 0, so systemd recorded
    # "Finished ... SUCCESS" on a report that was never built and nobody was alerted by
    # the unit state. Now: no fresh weekly_*.html => exit 1 => the unit goes `failed`,
    # shows red in `systemctl status`, and OnFailure= can fire. Pairs with the
    # stream-json keep-alive fix (c4e7192), which fixed the driver exiting early.
    sys.exit(0 if main() else 1)
