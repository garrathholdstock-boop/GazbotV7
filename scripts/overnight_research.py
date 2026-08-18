#!/usr/bin/env python3
"""OVERNIGHT RESEARCH — census, walk-forward and greenfield over the FULL history.

Operator, 2026-08-18: run the census for all runs over the whole data set, then the greenfield
report for both contracts, backtest any leads across different periods, and walk-forward every live
gate across all the data.

★ IT WAITS FOR THE BACKFILL. Running the census before the history lands would census the old,
smaller dataset and look complete — so phase 0 blocks until the pull reports done or its budget ends.

★ EVERY CENSUS USES --lake. run_census.py defaults to capture.db, which is PRUNED to a few trading
days: "--days 400" against it silently censuses whatever the hot tier happens to hold and reports as
though it covered 400. That is [[capture-retention-silently-halves-audits]] and it would have
invalidated the whole night. --lake spans V5 + Parquet + hot.

★ THE ARTIFACT ON DISK IS THE CHECKPOINT. A re-run skips completed phases, so this survives being
cut off — the Friday-report lesson.

★ JUDGE ON THE ARTIFACT, NEVER THE EXIT CODE. A phase that exits 0 having written nothing is a
FAILURE here, because that exact silent success has bitten this desk before.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/overnight"
VENV = f"{GB}/.venv/bin/python"
BACKFILL_LOG = f"{GB}/data/backfill/run.log"
STATE = f"{OUT}/_state.json"


def log(m: str) -> None:
    print(f"{dt.datetime.now(dt.UTC):%H:%M:%S} {m}", flush=True)


def run(cmd: list[str], out_path: str, timeout_s: int) -> tuple[bool, str]:
    """Run a phase, capture stdout to out_path, and JUDGE THE ARTIFACT not the return code."""
    env = dict(os.environ, PYTHONPATH=f"{GB}/src")
    try:
        r = subprocess.run(cmd, cwd=GB, env=env, capture_output=True, text=True, timeout=timeout_s)
        open(out_path, "w").write(r.stdout + ("\n--- stderr ---\n" + r.stderr if r.stderr else ""))
    except subprocess.TimeoutExpired:
        open(out_path, "w").write(f"TIMEOUT after {timeout_s}s")
        return (False, f"timeout {timeout_s}s")
    except Exception as e:
        open(out_path, "w").write(f"ERROR {e}")
        return (False, str(e)[:80])
    size = os.path.getsize(out_path)
    if size < 400:
        return (False, f"artifact only {size}B — exit code was {r.returncode}, but nothing was produced")
    return (True, f"{size:,}B")


def wait_for_backfill(deadline: float) -> str:
    """Block until the pull is done. It is the input to everything below."""
    log("phase 0: waiting for the history backfill")
    while time.time() < deadline:
        active = subprocess.run(["systemctl", "is-active", "gazbot7-backfill.service"],
                                capture_output=True, text=True).stdout.strip()
        try:
            tail = open(BACKFILL_LOG).read()[-600:]
        except Exception:
            tail = ""
        if "done:" in tail:
            n = len([f for f in os.listdir(f"{GB}/data/backfill") if f.endswith(".parquet")])
            log(f"  backfill COMPLETE — {n} parquet files")
            return "complete"
        if active not in ("active", "activating"):
            n = len([f for f in os.listdir(f"{GB}/data/backfill") if f.endswith(".parquet")])
            if n:
                log(f"  backfill not running, {n} files on disk — proceeding with what we have")
                return "partial"
            log("  backfill not running and produced NOTHING — proceeding on existing history only")
            return "empty"
        time.sleep(120)
    log("  deadline reached while waiting — proceeding with whatever landed")
    return "timeout"


# (key, description, argv, artifact, timeout_s) — coarse/cheap first so a truncated night still
# leaves the census on disk. The greenfield phases are LAST and reserved, per the Friday lesson.
def phases(deep: bool) -> list[tuple]:
    P = []
    for sym in ("MNQ", "MGC"):
        P.append((f"census_{sym}",
                  f"{sym} run census — EVERY run, full history",
                  [VENV, "scripts/run_census.py", "--symbol", sym, "--days", "400",
                   "--lake", "--html", f"{OUT}/census_{sym}.html"],
                  f"{OUT}/census_{sym}.txt", 3600))
        # a second pass at a lower bar: small runs are where participation questions actually live
        P.append((f"census_{sym}_small",
                  f"{sym} census at a LOWER run threshold (1.0xATR)",
                  [VENV, "scripts/run_census.py", "--symbol", sym, "--days", "400",
                   "--min-atr", "1.0", "--lake"],
                  f"{OUT}/census_{sym}_small.txt", 3600))
    # ★ WALK-FORWARD ACROSS PERIODS. Each window is re-tuned on PRIOR days only and applied to the
    # unseen day — no test day informs its own parameter. Several windows so a result that holds
    # only in one stretch is visible as such rather than averaging into a headline.
    for tag, since in (("all", "2026-06-01"), ("q3", "2026-07-01"),
                       ("recent", "2026-08-01"), ("preroll", "2026-06-15")):
        P.append((f"walkforward_{tag}",
                  f"walk-forward, live gates, window from {since}",
                  # ★ --lake, NOT --db capture.db. The hot tier is pruned: on the same window it
                  # yields 24 days against the lake's 43, and a walk-forward silently truncated to
                  # half its out-of-sample period looks like evidence while being worth much less.
                  [VENV, "scripts/forward_validate.py", "--lake", "--from", since],
                  f"{OUT}/walkforward_{tag}.txt", 2700))
    if deep:
        # Greenfield is Claude-driven and expensive; it runs LAST with whatever budget remains.
        P.append(("greenfield",
                  "greenfield research clusters, both contracts",
                  [VENV, "scripts/friday/serial_runner.py", "--since", "gf_MGC", "--force"],
                  f"{OUT}/greenfield.txt", 10800))
    return P


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=8.0, help="total budget")
    ap.add_argument("--wait-hours", type=float, default=5.0, help="max wait for the backfill")
    ap.add_argument("--no-deep", action="store_true", help="skip the greenfield phases")
    ap.add_argument("--force", action="store_true", help="re-run phases whose artifact exists")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    t_end = time.time() + a.hours * 3600

    status = wait_for_backfill(min(time.time() + a.wait_hours * 3600, t_end))

    todo = phases(not a.no_deep)
    results = {"backfill": status, "started": dt.datetime.now(dt.UTC).isoformat(), "phases": {}}
    for key, desc, cmd, art, tmo in todo:
        if os.path.exists(art) and os.path.getsize(art) > 400 and not a.force:
            log(f"skip  {key} — artifact already on disk")
            results["phases"][key] = "skipped (already done)"
            continue
        left = t_end - time.time()
        if left < 600:
            log(f"STOP  {key} — only {left/60:.0f}min left, not enough for a useful run")
            results["phases"][key] = "skipped (out of budget)"
            continue
        log(f"run   {key}: {desc}  (budget {min(tmo, int(left))//60}min)")
        ok, note = run(cmd, art, min(tmo, int(left)))
        results["phases"][key] = ("ok " if ok else "FAILED ") + note
        log(f"  {'ok' if ok else 'FAILED'}  {key}: {note}")

    results["finished"] = dt.datetime.now(dt.UTC).isoformat()
    json.dump(results, open(STATE, "w"), indent=1)
    log("=" * 64)
    for k, v in results["phases"].items():
        log(f"  {k:22s} {v}")
    log(f"artifacts in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
