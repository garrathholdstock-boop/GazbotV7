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
import urllib.parse
import urllib.request

GB = "/home/alphabot/gazbot7"


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
            ok = json.loads(r.read().decode()).get("ok") is True
        if not ok:
            print("telegram returned ok=false", file=sys.stderr)
        return 0 if ok else 1
    except Exception as ex:
        print(f"send failed: {type(ex).__name__}: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
