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
        # ★ FALSE, not 1. The wrapper is `sys.exit(0 if main() else 1)`, so a truthy return means
        # SUCCESS — returning 1 here would have reported a green unit on an auth failure, which is
        # the exact "logged its own failure and still returned 0" bug this file already carries a
        # comment about. Caught before it shipped.
        return False
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

    # 2. THE BUILD
    # ★★2026-08-13 THE BUILD IS NOW SERIAL, one phase per process. Operator: "run less agents at a
    # time and use the time you have." He was right and it is the whole fix.
    # The stream-json keep-alive driver this replaces ran all 16 phases inside ONE Claude session,
    # so RSS only ever grew (6.46 / 6.76 / 7.31 GB on three consecutive attempts) and any death lost
    # everything in flight. serial_runner.py starts a FRESH PROCESS PER PHASE — memory returns to
    # zero between phases, and the artifact on disk is the checkpoint so a re-run resumes rather
    # than restarts.
    # It also RESERVES time for assemble -> proofread -> rev2 -> final and drops optional sections to
    # protect it. That inverts the failure this exists to fix: REV2 has never survived to Saturday
    # morning precisely because it is built LAST.
    rc = 1
    try:
        r = subprocess.run(f"{PY} scripts/friday/serial_runner.py --deadline 06:30",
                           shell=True, cwd=GB, env=ENV, timeout=int(7.5 * 3600))
        rc = r.returncode
    except subprocess.TimeoutExpired:
        log("serial runner hit its own 7.5h wall")
    except Exception as e:
        log(f"serial runner error: {e}")
    done = (rc == 0)
    log(f"serial runner rc={rc} -> done={done}")

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
