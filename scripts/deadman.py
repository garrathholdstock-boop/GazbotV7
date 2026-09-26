#!/usr/bin/env python3
"""THE OFF-BOX DEAD-MAN'S SWITCH — the only instrument here that works when this box does not.

★★★2026-09-26 AUDIT, FINDING 08. Every alarm on this desk is OUTBOUND FROM THE MACHINE BEING
MONITORED. A hang, a full disk, a network drop, an expired credential or broken notify permissions
all present identically: NOTHING ARRIVES. And nothing arriving is indistinguishable from a quiet day.

This has already cost twelve hours: on 2026-08-21 `data/.notify_env` was written mode 600 root:root
while every desk service runs as `alphabot`, so all five went mute while the rider crashed mid-
flatten and the cross-desk kill fired. Sweep was green throughout. The file-mode check that came out
of it is good — and it runs on the same box.

Operator, 2026-09-26: "and so we never dont know something js happening in the backgrouns."

★ HOW IT WORKS, AND WHY IT IS THE CHEAPEST SAFETY SPEND AVAILABLE. This pings a hosted check on a
schedule. The hosted service alerts HIM when the pings STOP. The logic lives off-box, so it survives
everything on this list: the box powering off, the kernel OOM-killing python, the disk filling, the
network dropping, Telegram credentials expiring, or this very script being deleted.

★ IT REPORTS A VERDICT, NOT JUST A PULSE. A naive pinger says "the box has power", which is nearly
worthless — the 08-21 outage had a perfectly healthy box. So the ping carries the desk's own summary
and pings the check's /fail endpoint when the desk is unhealthy, so the off-box service escalates on
a SICK desk as well as on a SILENT one.
⚠ But the liveness half must never depend on the verdict half: if assembling the summary raises, it
still pings. A dead-man's switch that fails to ping because its own reporting broke would invert its
entire purpose.

⚠ CONFIGURATION IS DELIBERATELY ABSENT AND THE SCRIPT SAYS SO. `deadman_url` in
data/live_mode.json is empty until the operator creates a check (healthchecks.io, Better Stack,
Cronitor — any of them, the URL shape is the same) and pastes it in. Until then this exits 0 and
prints what is missing; it is installed and inert rather than pretending to protect.

⚠ NO SECRETS IN THE SERIES. The URL is a credential — anyone holding it can silence the alarm — so it
is never written to the log or the state file, only its host.

  PYTHONPATH=src .venv/bin/python scripts/deadman.py [--once] [--json] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "/home/alphabot/gazbot7/src")

GB = "/home/alphabot/gazbot7"
STATE = f"{GB}/data/deadman_state.json"
LOG = f"{GB}/data/deadman.log"
HEALTH = f"{GB}/data/core_health.json"
RECON = f"{GB}/data/desk_reconcile_state.json"
TIMEOUT_S = 10.0


def log(m: str) -> None:
    line = f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {m}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def url() -> str | None:
    try:
        from gazbot7 import livemode
        u = (livemode._conf().get("deadman_url") or "").strip()
        return u or None
    except Exception:
        return None


def verdict() -> tuple[bool, str]:
    """(healthy, one-line summary). NEVER RAISES — see the module docstring.

    ⚠ It reports `desk_flat`, not the tournament-scoped `flat` (audit finding 10), and an
    unreadable input makes the desk UNHEALTHY rather than silently fine: a summary that cannot see
    the desk is exactly the state this whole instrument exists to surface.
    """
    try:
        bits, healthy = [], True
        try:
            h = json.load(open(HEALTH))
            age = (dt.datetime.now(dt.UTC)
                   - dt.datetime.fromisoformat(h["ts"])).total_seconds()
            if age > 180:
                healthy = False
                bits.append(f"core_health {age:.0f}s STALE")
            else:
                bits.append(f"conn={h.get('conn')} desk_flat={h.get('desk_flat')}")
                if h.get("halted"):
                    healthy = False
                    bits.append("HALTED")
                if h.get("conn") != "HEALTHY":
                    healthy = False
        except Exception as e:
            healthy = False
            bits.append(f"core_health unreadable ({type(e).__name__})")
        try:
            r = (json.load(open(RECON)) or {}).get("read1") or {}
            age = dt.datetime.now(dt.UTC).timestamp() - os.path.getmtime(RECON)
            if age > 300:
                healthy = False
                bits.append(f"reconciler {age:.0f}s stale")
            elif r.get("breach"):
                healthy = False
                bits.append("RECONCILE BREACH")
            else:
                bits.append(f"venue={r.get('venue')}")
        except Exception as e:
            healthy = False
            bits.append(f"reconciler unreadable ({type(e).__name__})")
        return healthy, " · ".join(bits)
    except Exception as e:                       # belt-and-braces: the verdict may never break ping
        return False, f"verdict failed ({type(e).__name__})"


def ping(base: str, *, ok: bool, summary: str, timeout: float = TIMEOUT_S) -> tuple[bool, str]:
    """Ping the hosted check. `/fail` when the desk is sick, so the off-box service escalates.

    ⚠ The summary goes in the BODY, which every one of these services shows in its alert — so his
    phone tells him WHAT was wrong, not merely that the pings stopped.
    """
    target = base.rstrip("/") + ("" if ok else "/fail")
    # ⚠⚠ 2026-09-26 review: THE EXCEPTION TEXT LEAKED THE CREDENTIAL. A URL pasted without a scheme
    # ("hc-ping.com/SECRET-TOKEN") makes Request() raise ValueError whose message CONTAINS the URL,
    # and that string became rec["transport"] in the state file and a line in deadman.log — while
    # this module's own docstring promises the URL is "never written to the log or the state file".
    # A missing https:// is the likeliest possible operator error here. So validate the scheme first
    # and never let a raw URL reach an error string.
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False, ("malformed deadman_url: it must start with https:// — refusing to send "
                       "(the URL itself is withheld from this log deliberately)")
    try:
        req = urllib.request.Request(target, data=summary.encode()[:900],
                                     headers={"User-Agent": "gazbot7-deadman/1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (200 <= resp.status < 300), f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        # ⚠ Only the TYPE, never the message — urllib error text can embed the full URL.
        return False, f"{type(e).__name__} contacting {parsed.netloc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="assess and print; send nothing")
    a = ap.parse_args()

    u = url()
    healthy, summary = verdict()
    now = dt.datetime.now(dt.UTC)
    rec = {"ts": now.isoformat(), "healthy": healthy, "summary": summary,
           "configured": bool(u), "host": (urllib.parse.urlparse(u).netloc if u else None)}

    if not u:
        # ⚠ INSTALLED AND INERT, AND IT SAYS SO. Never pretend to protect.
        rec["note"] = ("deadman_url is not set in data/live_mode.json — NOTHING outside this box is "
                       "watching it. Create a check (healthchecks.io / Better Stack / Cronitor) and "
                       "paste its ping URL there. Audit finding 08.")
        log(rec["note"])
    elif a.dry_run:
        rec["note"] = f"would ping {rec['host']} ({'ok' if healthy else 'FAIL'}): {summary}"
        log(rec["note"])
    else:
        sent, how = ping(u, ok=healthy, summary=summary)
        rec.update(sent=sent, transport=how)
        log(f"ping {'ok' if healthy else 'FAIL'} → {rec['host']} : {how} · {summary}")
        st = {}
        try:
            st = json.load(open(STATE))
        except Exception:
            pass
        streak = 0 if sent else int(st.get("send_fail_streak") or 0) + 1
        rec["send_fail_streak"] = streak
        # ⚠ A FAILED PING IS NOT AN EMERGENCY HERE — it is the off-box service's job to notice
        # silence, and that is the whole point. But a persistent failure means we are relying on it
        # while it is not receiving anything, so say so ON THIS SIDE too, once.
        if streak == 15:
            try:
                from gazbot7.notify import notify
                notify(f"⚠ DEAD-MAN'S SWITCH has failed to reach {rec['host']} {streak} times in a "
                       f"row ({how}). Nothing off-box is watching this desk until it clears.",
                       critical=False)
            except Exception:
                pass

    try:
        with open(STATE + ".tmp", "w") as fh:
            json.dump(rec, fh, indent=1)
        os.replace(STATE + ".tmp", STATE)
    except Exception:
        pass
    if a.json:
        print(json.dumps(rec, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
