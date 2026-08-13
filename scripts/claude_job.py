#!/usr/bin/env python3
"""CLAUDE JOB — run one named, prompt-driven job headlessly, durably, and loudly.

★ WHY (2026-08-13). Six standing jobs — the bad-call ledger review, the hourly tape/gate watch, the
3-hourly maintenance sweep, the nightly grind-exit + router/selector review and the Sunday pre-open
ramp — existed ONLY as Claude-session crons. They died with the session, every time, and the manifest
(`data/router_crons_manifest.md`) exists solely so a human can remember to re-arm them by hand. That
is the fragility CLAUDE.md calls the #1 risk, and it is not theoretical: on this date the desk ran
for 10.5 hours with a dead router and none of these jobs existed to notice.

This is the one runner they all share. A job is a PROMPT FILE plus a tool allowlist plus a timer.
Adding a job is a file and a unit, not new code — which is the point, because six bespoke drivers
would be six things to drift.

★ THE INVOCATION IS DELIBERATELY THE SIMPLE ONE. `friday_report_durable.py` drives claude through
stream-json with an open stdin, because a 287-page report needs a long polled session. These jobs are
single-shot, so they use plain `claude -p <prompt> --allowedTools ...`, which is verified to work and
has far less to go wrong. Note the trap that killed the 08-07 report run: `--output-format
stream-json` REQUIRES `--verbose` or the CLI exits rc=1 in seconds. We avoid the whole class by not
using stream-json here.

★★ A RARE JOB MUST NOT SILENCE ITS OWN ERRORS. The Friday report died for a week because the CLI
started requiring a flag and the failure went to a log nobody read. So: every non-zero exit, timeout
and empty answer PAGES, stderr is captured to a file rather than discarded, and every run — success
or not — stamps `data/claude_jobs/<name>.json` so a job that silently stops running is visible to the
nightly supervisor rather than merely absent.

★ IT PAGES ON FAILURE, NOT ON SUCCESS. The operator's standing preference is final deliverables only,
no progress pings. A job that has nothing to say says nothing; the prompt files are written to report
only exceptions. The run record is on disk for anyone who wants to audit it.

  scripts/claude_job.py --name ledger-review [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"
CLAUDE = "/root/.local/bin/claude"
PROMPTS = f"{GB}/ops/job_prompts"
RUNDIR = f"{GB}/data/claude_jobs"

# Per-job tool allowlist. Deliberately explicit and per-job rather than one permissive default:
# the review jobs read and reason, only the ledger review needs to WRITE (it maintains the ledger
# markdown). None of them may move a switch — gate_switches.env belongs to the router tick alone,
# and a second writer is the "two routers" hazard.
TOOLS = {
    "ledger-review": "Bash,Read,Write,Edit",
    "hour-watch":    "Bash,Read",
    "sweep":         "Bash,Read",
    "nightly-review": "Bash,Read,Write,Edit",
    "sunday-ramp":   "Bash,Read",
}
TIMEOUT_S = {"ledger-review": 900, "hour-watch": 420, "sweep": 420,
             "nightly-review": 900, "sunday-ramp": 600}


def page(msg: str, critical: bool = True) -> None:
    try:
        subprocess.run([PY, "-c", "import sys; from gazbot7.notify import notify; "
                                  "notify(sys.argv[1], critical=sys.argv[2]=='1')",
                        msg[:900], "1" if critical else "0"],
                       cwd=GB, env={**os.environ, "PYTHONPATH": "src"}, timeout=30)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--dry-run", action="store_true", help="print the prompt, do not call claude")
    a = ap.parse_args()

    prompt_path = f"{PROMPTS}/{a.name}.md"
    try:
        with open(prompt_path) as fh:
            prompt = fh.read().strip()
    except Exception as e:
        page(f"⚠ GAZBOT JOB [{a.name}] has no prompt file ({e}) — the job cannot run at all.")
        return 2
    if not prompt:
        page(f"⚠ GAZBOT JOB [{a.name}] prompt file is EMPTY — refusing to invoke claude with it.")
        return 2

    if a.dry_run:
        print(f"--- {a.name} | tools={TOOLS.get(a.name, 'Bash,Read')} | "
              f"timeout={TIMEOUT_S.get(a.name, 600)}s ---")
        print(prompt)
        return 0

    os.makedirs(RUNDIR, exist_ok=True)
    err_path = f"{RUNDIR}/{a.name}.stderr.txt"
    t0 = time.time()
    rc, out, err = None, "", ""
    try:
        with open(err_path, "w") as errf:
            p = subprocess.run(
                [CLAUDE, "-p", prompt, "--allowedTools", TOOLS.get(a.name, "Bash,Read")],
                capture_output=False, stdout=subprocess.PIPE, stderr=errf, text=True,
                timeout=TIMEOUT_S.get(a.name, 600), cwd=GB,
                env={**os.environ, "PYTHONPATH": "src",
                     "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin"})
        rc, out = p.returncode, (p.stdout or "").strip()
    except subprocess.TimeoutExpired:
        rc, out = -1, ""
    except Exception as e:
        rc, out = -2, f"{type(e).__name__}: {e}"
    try:
        with open(err_path) as fh:
            err = fh.read().strip()[-600:]
    except Exception:
        pass

    took = time.time() - t0
    ok = (rc == 0 and bool(out))
    rec = {"name": a.name, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "rc": rc, "ok": ok, "took_s": round(took, 1), "chars": len(out),
           "output": out[:4000], "stderr_tail": err[-400:]}
    tmp = f"{RUNDIR}/{a.name}.json.tmp"
    with open(tmp, "w") as fh:
        json.dump(rec, fh, indent=1)
    os.replace(tmp, f"{RUNDIR}/{a.name}.json")

    print(f"[{a.name}] rc={rc} ok={ok} {took:.0f}s {len(out)}ch")
    if out:
        print(out[:4000])

    if not ok:
        # ★ The empty-output case is as much a failure as rc!=0 and is easier to miss: the CLI can
        # exit 0 having produced nothing (auth trouble, a refused prompt, a silent truncation).
        # Treat "ran fine, said nothing" as broken, because a review job that reviews nothing is
        # indistinguishable from a clean desk — the same trap as the router's "no change".
        why = ("TIMED OUT after %.0fs" % took if rc == -1 else
               f"rc={rc}" + (" but produced NO OUTPUT" if rc == 0 else ""))
        page(f"⚠ GAZBOT JOB [{a.name}] FAILED — {why}. stderr: {err[-300:] or '(empty)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
