#!/usr/bin/env python3
"""DURABLE ROUTER TICK — one router decision via HEADLESS Claude, no live session needed.

Invoked by systemd (gazbot7-router-tick.timer) every 5 min. This is the ROBUSTNESS layer:
the router keeps managing the desk even after a Claude *session* ends.

SAFE ARCHITECTURE: this trusted wrapper gathers the desk state as TEXT, asks headless
`claude -p` (NO tools — pure reasoning) for a JSON decision, then THIS script applies it.
Claude never runs commands. FAIL-SAFE: any error / non-parse / invalid decision => NO
switch change (gate_switches.env left untouched). Benching-only, PAPER; stops/safety untouched.
"""
import subprocess, json, os, re, time
from datetime import datetime, timezone

GB = "/home/alphabot/gazbot7"
SW = f"{GB}/data/gate_switches.env"
LOG = f"{GB}/data/router_trial_log.txt"
HLOG = f"{GB}/data/router_headless.log"
PY = f"{GB}/.venv/bin/python"
GATES = ["grind_long", "capitulation_long", "abs_veto_long", "exhaustion_short", "abs_veto_short", "rgv_short"]
# ★LIVE TRIAL 2026-07-31 (operator): exhaustion_short is PINNED ON for a fade-scalp (0.5R/1.5R) live trial —
# the durable tick must NOT bench it while the trial runs. Revert: PINNED = frozenset().
PINNED = frozenset({"exhaustion_short"})
MAINT_HOUR_UTC = 21  # CME index-futures daily maintenance halt 21:00-22:00 UTC


def hlog(msg):
    try:
        with open(HLOG, "a") as f:
            f.write(f"{datetime.now(timezone.utc).strftime('%FT%TZ')} {msg}\n")
    except Exception:
        pass


def sh(cmd, timeout=60):
    env = os.environ.copy(); env["PYTHONPATH"] = "src"
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout, cwd=GB, env=env).stdout
    except Exception as e:
        return f"(error: {e})"


def read_switches():
    cur = {}
    try:
        for line in open(SW):
            s = line.strip()
            if "=" in s and not s.startswith("#"):
                k, v = s.split("=", 1)
                cur[k.strip()] = v.strip()
    except Exception:
        pass
    return cur


def apply_switches(valid):
    lines = open(SW).read().splitlines()
    out = []
    for line in lines:
        hit = False
        for g, v in valid.items():
            if line.strip().startswith(g + "="):
                out.append(f"{g}={v}"); hit = True; break
        if not hit:
            out.append(line)
    with open(SW, "w") as f:
        f.write("\n".join(out) + "\n")


def append_log(msg):
    ts = datetime.now(timezone.utc).strftime('%FT%TZ')
    try:
        with open(LOG, "a") as f:
            f.write(f"{ts} | tune | DURABLE | {msg}\n")
    except Exception:
        pass


def main():
    # skip during the maintenance halt (desk frozen; nothing to decide)
    if time.gmtime().tm_hour == MAINT_HOUR_UTC:
        hlog("skip: CME maintenance halt"); return

    desk = sh(f"{PY} scripts/desk_view.py")
    if "DAY BIAS" not in desk:
        hlog("ABORT: desk_view unreadable -> no change"); return
    recent = sh(f"{PY} scripts/recent_trades.py 6")
    logtail = sh(f"tail -6 {LOG}")
    cur = read_switches()

    prompt = (
        "You are the GAZBOT V7 intelligent router making ONE 5-min bench/enable decision (PAPER, "
        "benching-only). Decide which of the 6 gates should be on/off on a HOLISTIC regime read "
        "(trend vs chop), not mechanical thresholds.\n\n"
        "RULES: chop (low ER, range-bound) -> bench ALL momentum (grind_long, abs_veto_long), keep "
        "reversion (capitulation_long). day-bias UP>=+40 -> bench shorts; DOWN<=-40 -> bench longs. "
        "Re-arm momentum only on a real range-break WITH ER climbing + vol expanding (not a delta-blip). "
        "abs_veto_long is veto-protected (≈0-cost armed in chop unless it's firing+stopping); grind_long "
        "is a churner (keep OFF unless ER>=0.35 strong trend). exhaustion_short is PINNED ON for an operator "
        "live-trial today — do NOT include it in changes, leave it on regardless of regime. "
        "Reversion stays through chop. DON'T THRASH — change a switch ONLY when evidence genuinely changed; "
        "most ticks are no-change.\n\n"
        f"CURRENT SWITCHES: {json.dumps(cur)}\n\n"
        f"=== DESK VIEW ===\n{desk}\n=== RECENT TRADES ===\n{recent}\n=== RECENT ROUTER LOG ===\n{logtail}\n\n"
        "Output ONLY a JSON object, nothing else:\n"
        '{"changes": {"<gate>": "on"|"off"}, "reason": "<one tight line>", "notify": "<telegram text, or empty string if no change>"}\n'
        "changes = ONLY gates whose state should FLIP from CURRENT (empty {} if no change). Be conservative."
    )

    try:
        r = subprocess.run(["/root/.local/bin/claude", "-p", prompt, "--allowedTools", ""],
                           capture_output=True, text=True, timeout=200,
                           env={**os.environ, "HOME": "/root"})
        out = (r.stdout or "").strip()
    except Exception as e:
        hlog(f"ABORT: claude invocation failed {e} -> no change"); return

    m = re.search(r'\{.*\}', out, re.DOTALL)
    if not m:
        hlog(f"ABORT: no JSON in output -> no change | raw={out[:200]!r}"); return
    try:
        dec = json.loads(m.group(0))
    except Exception as e:
        hlog(f"ABORT: JSON parse fail {e} -> no change | raw={out[:200]!r}"); return

    changes = dec.get("changes") or {}
    reason = str(dec.get("reason", ""))[:300]
    notify = str(dec.get("notify", "")).strip()

    valid = {g: v for g, v in changes.items()
             if g in GATES and g not in PINNED and v in ("on", "off") and cur.get(g) != v}

    if not valid:
        append_log(f"changed: none | {reason}")
        hlog(f"no change | {reason}")
        return

    apply_switches(valid)
    append_log(f"changed: {valid} | {reason}")
    hlog(f"APPLIED {valid} | {reason}")
    if notify:
        try:
            subprocess.run([PY, "-c", "import sys; from gazbot7.notify import notify; notify(sys.argv[1], critical=False)", notify],
                           cwd=GB, env={**os.environ, "PYTHONPATH": "src"}, timeout=30)
        except Exception:
            pass


if __name__ == "__main__":
    main()
