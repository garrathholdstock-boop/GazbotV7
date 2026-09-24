#!/usr/bin/env python3
"""Self-contained Telegram sender for GAZBOT V7. NO dependency on the retired alphabot2 tree.

★★★2026-08-20. This desk's entire alarm chain used to run alphabot2's python, its
notify_operator.py and its .env. CLAUDE.md calls that tree RETIRED, so deleting it would have
silenced every critical page — reconcile breaches, naked positions, the peak watch — while
notify() carried on returning True. The first replacement copied the old script verbatim and it
imported `alphabot.strategy.alerts.telegram`, i.e. it was still a dependency on the same tree.
This version talks to the Telegram HTTP API directly and imports nothing outside the stdlib.

Credentials come from data/.notify_env (mode 600, gitignored) or the environment.
Exit 0 on delivery, 1 on failure — so a caller CAN check, unlike the old chain.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

GB = "/home/alphabot/gazbot7"

#: ★★★2026-09-24 THE SENT LOG — so an erroneous alert can be RETRACTED.
#: Operator: "please delete any old erroneous messages." We could not: Telegram deletes a bot's own
#: message only by `message_id`, and this script threw the API response away, so nothing we had ever
#: sent was addressable. It now keeps the id.
#: ⚠ TELEGRAM ONLY ALLOWS A BOT 48 HOURS to delete its own message. The log keeps 7 days anyway —
#: the extra days are the AUDIT ("what did the desk actually say to him?"), which is useful long
#: after the retraction window shuts. `notify_delete.py --list` says which rows are still live.
SENT_LOG = f"{GB}/data/notify_sent.jsonl"
SENT_KEEP_S = 7 * 86400


def _record(message_id, message):
    """Append one sent message to the log. NEVER raises, NEVER changes the exit code.

    ⚠⚠ MODE 0666 DELIBERATELY. Alerts are sent by BOTH users on this box — rider_peak_watch runs as
    root and is the highest-volume sender, while day_rider, web, step_away and gate_reactivate run
    as `alphabot`. A log created 0644 by whichever happened to send first would be silently
    unwritable by the other, and we would keep exactly half the ids with nothing reporting the gap.
    That is the 2026-08-21 shape precisely: `.notify_env` written 600 root:root while every desk
    service ran as alphabot, and the PermissionError was swallowed for ~12 hours.
    It holds message ids and a text preview. No credentials. There is nothing here to protect.
    """
    try:
        rows = []
        cutoff = time.time() - SENT_KEEP_S
        try:
            with open(SENT_LOG) as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                        if float(r.get("ts") or 0) >= cutoff:
                            rows.append(r)
                    except Exception:
                        continue          # a torn line is dropped, never fatal
        except FileNotFoundError:
            pass
        rows.append({"ts": time.time(), "message_id": message_id,
                     "text": message[:200], "by": os.environ.get("SUDO_USER") or os.getuid()})
        tmp = SENT_LOG + f".tmp{os.getpid()}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        with os.fdopen(fd, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        os.chmod(tmp, 0o666)              # explicit: os.open is still masked by umask
        os.replace(tmp, SENT_LOG)         # atomic — a torn log would lose every id, not one
    except Exception:
        pass


def _env():
    env = dict(os.environ)
    try:
        with open(f"{GB}/data/.notify_env") as fh:
            for line in fh:
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass
    return env


def main() -> int:
    msg = " ".join(sys.argv[1:]).strip()
    if not msg:
        print("no message", file=sys.stderr)
        return 1
    e = _env()
    token = e.get("TELEGRAM_TOKEN") or e.get("TELEGRAM_BOT_TOKEN")
    chat = e.get("TELEGRAM_CHAT_ID") or e.get("TELEGRAM_CHAT")
    if not token or not chat:
        print("TELEGRAM_TOKEN/CHAT_ID not configured", file=sys.stderr)
        return 1
    data = urllib.parse.urlencode({"chat_id": chat, "text": msg[:4000],
                                   "disable_web_page_preview": "true"}).encode()
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read().decode())
        ok = resp.get("ok") is True
        if not ok:
            print("telegram returned ok=false", file=sys.stderr)
        else:
            # ⚠ AFTER the send, and unable to affect it. Recording is a convenience; delivery is
            # the job, and a bookkeeping fault must never be able to turn a delivered alert into a
            # reported failure.
            _record((resp.get("result") or {}).get("message_id"), msg)
        return 0 if ok else 1
    except Exception as ex:
        print(f"send failed: {type(ex).__name__}: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
