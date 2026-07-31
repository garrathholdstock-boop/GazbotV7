#!/usr/bin/env python3
"""DURABLE FRIDAY REPORT — builds the V7 weekly report HEADLESS, no live Claude session needed.

systemd: gazbot7-friday-report.timer (Fri 22:07 UTC) -> .service -> this script. Mirrors the
durable router tick: it pre-freezes the census (the multi-minute tick crunch that must NOT run
inside the workflow), then invokes headless `claude -p` WITH TOOLS to run the max-depth workflow
(Census->Desks->Rehab->BigRuns->Greenfield->Skeptic->Assemble->Proofread). Phase 7 (Proofread)
adversarially reads the report as the operator, gap-fills, does Revision 2, and pings on completion.

This removes the #1 fragility: the Friday report no longer depends on a live session surviving to
22:07. FAIL-SAFE: every step guarded; failures are logged AND Telegram-alerted so a bad build is
never silent. Root can't use --dangerously-skip-permissions, so we pass an explicit --allowedTools.
"""
import subprocess, os
from datetime import datetime, timezone

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"
CLAUDE = "/root/.local/bin/claude"
SEC = f"{GB}/reports/friday_v7/sections"
LOG = f"{GB}/data/friday_durable.log"
WF = f"{GB}/scripts/friday/friday_v7_maxdepth.workflow.js"
ENV = {**os.environ, "HOME": "/root", "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": "src"}


def log(m):
    try:
        with open(LOG, "a") as f:
            f.write(f"{datetime.now(timezone.utc).strftime('%FT%TZ')} {m}\n")
    except Exception:
        pass


def notify(msg, crit=True):
    try:
        subprocess.run([PY, "-c", "import sys;from gazbot7.notify import notify;notify(sys.argv[1],critical=" + ("True" if crit else "False") + ")", msg],
                       cwd=GB, env=ENV, timeout=30)
    except Exception:
        pass


def main():
    log("=== DURABLE FRIDAY REPORT — START ===")
    notify("📋 Durable Friday report starting (headless systemd) — freezing census, then max-depth build + self-proofread.", crit=False)

    # 1. PRE-FREEZE the census out-of-band (never inside the workflow — it times out there)
    try:
        os.makedirs(SEC, exist_ok=True)
        subprocess.run(f"{PY} scripts/run_census.py --days 7 --html {SEC}/movement1_census.html > {SEC}/census_stdout.txt 2>{SEC}/census_err.txt",
                       shell=True, cwd=GB, env=ENV, timeout=1200)
        subprocess.run(f"{PY} scripts/friday/parse_census_summary.py", shell=True, cwd=GB, env=ENV, timeout=180)
        if os.path.exists(f"{SEC}/census_summary.json"):
            log("census frozen OK")
        else:
            log("census_summary.json MISSING after freeze")
            notify("⚠ Durable Friday: census freeze produced no summary.json — build may be thin, CHECK.", crit=True)
    except Exception as e:
        log(f"census freeze error: {e}")
        notify(f"⚠ Durable Friday: census freeze errored ({e}) — CHECK.", crit=True)

    # 2. headless Claude runs the workflow (self-proofreads via Phase 7) + verifies + pings
    prompt = (
        f"You are building the GAZBOT V7 Friday weekly report, HEADLESS. The census is ALREADY frozen at "
        f"{SEC}/census_summary.json — do NOT run run_census.py. Launch the max-depth workflow via the Workflow "
        f"tool with scriptPath '{WF}' and let it run to completion (Census->Desks->Rehab->BigRuns->Greenfield->"
        f"Skeptic->Assemble->Proofread). Phase 7 (Proofread) adversarially reads the report as the operator would, "
        f"gap-fills every question he'd poke at, does Revision 2, and pings him. After it completes, verify the three "
        f"outputs exist in src/gazbot7/web_static/ (weekly_<date>.html + .pdf + monday_<date>.html) and the publish "
        f"gate passed; if the workflow died mid-run, read its journal and resume via Workflow scriptPath+resumeFromRunId. "
        f"Do NOT hand-write a summary — the pipeline IS the deliverable. It must be GOOD on wake-up (operator flies ~lunch)."
    )
    try:
        r = subprocess.run([CLAUDE, "-p", prompt, "--allowedTools", "Bash", "Workflow", "Read", "Write", "Edit", "Agent", "Task"],
                           cwd=GB, env=ENV, capture_output=True, text=True, timeout=18000)
        log(f"claude exit={r.returncode} | tail={(r.stdout or '')[-600:]!r}")
        if r.returncode != 0:
            notify(f"⚠ Durable Friday: headless build exited {r.returncode}. CHECK /v7/reports — may need manual recover.", crit=True)
    except subprocess.TimeoutExpired:
        log("claude build TIMEOUT (5h)")
        notify("⚠ Durable Friday: build hit the 5h timeout — CHECK report state / recover.", crit=True)
    except Exception as e:
        log(f"claude build error: {e}")
        notify(f"⚠ Durable Friday build error: {e} — CHECK.", crit=True)
    log("=== DURABLE FRIDAY REPORT — END ===")


if __name__ == "__main__":
    main()
