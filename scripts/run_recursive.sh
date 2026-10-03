#!/bin/bash
# ⚠ anchored on the interpreter path — a bash script must never match its own pgrep pattern
cd /home/alphabot/gazbot7
while pgrep -f '[.]venv/bin/python .*sim_week_recursive.py --arm both' >/dev/null; do sleep 60; done
PYTHONPATH=src .venv/bin/python -u scripts/recursive_loop.py --iters 12 \
  >> reports/recursive_loop/loop.log 2>&1
PYTHONPATH=src .venv/bin/python -u scripts/ping_loop.py >> reports/recursive_loop/loop.log 2>&1
