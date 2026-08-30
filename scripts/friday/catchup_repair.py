#!/usr/bin/env python3
"""Repair pass for the catch-up report. Runs on a timer through the night; finishes the job.

Operator, 2026-08-25: *"if it fails just fix it so its finished in the morning. make sure its
proofread and if any sections arent done, do them."*

WHY A SEPARATE PASS RATHER THAN A LONGER FIRST RUN. The 08-21 failure was not "the run died" — it
exited 0 having built 4 of 13 sections. A retry that only looks at the exit code would have done
nothing. This looks at the ARTIFACTS and rebuilds whatever is missing, which is the only signal
that has ever been trustworthy here.

SAFETY:
  · NEVER runs while the main build is active — two serial_runners would fight over the same
    artifacts and the same headless-Claude auth.
  · serial_runner is idempotent: a fresh artifact is HAVE and is skipped, so re-running is cheap
    and only the gaps cost time.
  · Late passes fall through to the TAIL automatically: once the remaining window is smaller than
    the 255m tail reserve, the body budget goes to zero and it spends what is left on
    assemble/proofread/rev2/final. That is deliberate — a proofread report with gaps beats a
    complete one nobody checked, and the operator asked specifically for the proofread.
"""
import datetime as dt
import os
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
PY_ = f"{GB}/.venv/bin/python"
SEC = f"{GB}/reports/friday_v7/sections"
WEB = f"{GB}/src/gazbot7/web_static"
CUT = dt.datetime(2026, 8, 25, 21, 0, tzinfo=dt.UTC).timestamp()

WANT = {
    "gf_MGC.md": "gold greenfield", "gf_full_RIDER_ALL.md": "RIDER_ALL",
    "gf_full_UNCLASS.md": "UNCLASS", "gf_full_OPEN-NEWS.md": "OPEN-NEWS",
    "gf_full_VACUUM.md": "VACUUM", "gf_full_FLOW-LED.md": "FLOW-LED",
    "gf_chopscalp.md": "chopscalp",
    "proofread.json": "PROOFREAD", "rev2_done.txt": "rev2", "final_check.txt": "final",
}


def log(m): print(f"{dt.datetime.now(dt.UTC):%H:%M:%SZ} [repair] {m}", flush=True)


# ★★★2026-08-25 THE GUARD THAT DID NOT GUARD. This was
#     subprocess.run(["systemctl","is-active","--quiet",unit]).returncode == 0
# and `is-active --quiet` exits NON-ZERO for the state "activating" — which is exactly the state a
# long-running `Type=oneshot` occupies for its ENTIRE run. So the guard reported "not running"
# about a build that was running, and launched a second serial_runner on top of it: two builds
# fighting over the same section artifacts and the same headless-Claude auth, unattended at 01:00.
# Found by running it, not by reading it.
# TWO INDEPENDENT CHECKS NOW, because the systemd state alone has already lied once:
#   1. the unit's ActiveState is anything other than inactive/failed;
#   2. a serial_runner process exists at all — true even if the unit was started by hand, outside
#      systemd entirely, which is how the 18:07 collision actually happened.
_BUSY_STATES = ("active", "activating", "reloading", "deactivating")


def unit_busy(unit: str) -> bool:
    r = subprocess.run(["systemctl", "show", "-p", "ActiveState", "--value", unit],
                       capture_output=True, text=True)
    return r.stdout.strip() in _BUSY_STATES


def build_running() -> bool:
    """Is ANY report build alive, however it was started?"""
    r = subprocess.run(["pgrep", "-f", "friday/serial_runner.py"], capture_output=True, text=True)
    return bool(r.stdout.strip())


def active(unit):
    return unit_busy(unit)


def missing():
    out = []
    for f, label in WANT.items():
        p = f"{SEC}/{f}"
        if not os.path.exists(p) or os.path.getmtime(p) < CUT:
            out.append(label)
    rep = f"{WEB}/weekly_2026-08-21.html"
    if not os.path.exists(rep) or os.path.getmtime(rep) < CUT:
        out.append("THE REPORT ITSELF")
    return out


def main() -> int:
    for unit in ("gazbot7-friday-catchup.service", "gazbot7-friday-report.service"):
        if unit_busy(unit):
            log(f"{unit} is {subprocess.run(['systemctl','show','-p','ActiveState','--value',unit], capture_output=True, text=True).stdout.strip()} "
                f"— standing down, nothing to repair yet")
            return 0
    if build_running():
        log("a serial_runner process is alive (started outside systemd?) — standing down")
        return 0
    gaps = missing()
    if not gaps:
        log("nothing missing — report and proofread are complete")
        subprocess.run(["systemctl", "disable", "--now", "gazbot7-friday-catchup-repair.timer"],
                       check=False)
        return 0
    log(f"{len(gaps)} still missing: {', '.join(gaps)} — running serial_runner to fill them")
    r = subprocess.run([PY_, "scripts/friday/serial_runner.py", "--deadline", "07:15",
                        "--per-week", "6"],
                       cwd=GB, env={**os.environ, "PYTHONPATH": "src", "HOME": "/root"})
    log(f"serial_runner rc={r.returncode}")
    subprocess.run([PY_, "scripts/friday/verify_catchup.py"], cwd=GB,
                   env={**os.environ, "PYTHONPATH": "src", "HOME": "/root"}, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
