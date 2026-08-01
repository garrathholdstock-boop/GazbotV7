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


def main():
    log("=== DURABLE FRIDAY REPORT — START (stream-json keep-alive) ===")
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
        p = subprocess.Popen([CLAUDE, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
                              "--allowedTools", "Bash", "Workflow", "Read", "Write", "Edit", "Agent", "Task"],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, cwd=GB, env=ENV)
        p.stdin.write(msg); p.stdin.flush()          # send prompt, KEEP stdin open (session persists)
        t0 = time.time()
        while time.time() - t0 < MAX_S:
            time.sleep(POLL_S)
            if newest_weekly_mtime() > baseline_mtime + 60:   # a fresh report landed
                # give Phase-7 proofread time to finish its Rev2 rewrite, then finish
                time.sleep(600); done = True; break
            if p.poll() is not None:                          # session died early = the bug recurred
                log(f"claude session exited early (rc={p.returncode}) — report not built"); break
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
