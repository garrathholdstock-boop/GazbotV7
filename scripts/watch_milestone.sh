#!/bin/bash
# ⚠ anchored on the interpreter path — a bash script must never match its own pgrep pattern.
#   That self-match cost a Telegram earlier today: the watcher waited on itself forever.
cd /home/alphabot/gazbot7
while true; do
  PYTHONPATH=src .venv/bin/python -u scripts/ping_milestone.py >> reports/recursive_loop/loop.log 2>&1
  pgrep -f '[.]venv/bin/python .*recursive_loop.py' >/dev/null || { sleep 600; \
    pgrep -f '[.]venv/bin/python .*recursive_loop.py' >/dev/null || break; }
  sleep 300
done
