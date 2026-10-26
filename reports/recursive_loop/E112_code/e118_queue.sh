#!/bin/bash
# E118 A2: wait for the Nov 24-28 week to finish (or stop), then the 7 disaster sessions, then resume the unseen-week chain.
cd /home/alphabot/gazbot7
while ps -eo pid,args | awk '$2 ~ /python$/ && $3 ~ /e118_chain/' | grep -q . ; do
  grep -q "WEEK 2025-11-24" reports/e112/e118_chain.log && break
  sleep 60
done
for p in $(ps -eo pid,args | awk '$2 ~ /python$/ && $3 ~ /e118_chain/ {print $1}'); do kill $p; done
sleep 5
echo "[$(date -u +%H:%M:%SZ)] disaster sessions start" >> reports/e112/e118_chain.log
E118_ALLOW_LIVE_HOURS=1 E112_MAX_CALLS=2500 PYTHONPATH=src .venv/bin/python reports/recursive_loop/E112_code/replay.py \
  --arm v103 --arm v103T30 --arm v103D --days 2025-10-01,2025-10-03,2025-10-22,2025-10-31,2025-11-12,2025-11-13,2025-11-17 --workers 2 >> reports/e112/e118_disaster.log 2>&1
echo "[$(date -u +%H:%M:%SZ)] disaster sessions done; resuming the unseen-week chain" >> reports/e112/e118_chain.log
E118_ALLOW_LIVE_HOURS=1 E112_MAX_CALLS=1500 E118_WORKERS=2 PYTHONPATH=src .venv/bin/python reports/recursive_loop/E112_code/e118_chain.py --start 00:00 >> reports/e112/e118_chain.log 2>&1
