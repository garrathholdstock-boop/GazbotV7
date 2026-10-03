#!/bin/bash
# ★★★2026-10-03 THE WEEKEND QUEUE. Operator: "lets go crazy and do this properly."
# Waits for the two v1 runs to finish, then walks the 2x2 matrix over BOTH weeks.
# ⚠ STRICTLY SEQUENTIAL. The box is 7.5GB and the Friday report has OOM-killed it three times;
#   two concurrent runs is the most it should ever carry, and the matrix adds no concurrency.
# ⚠ Resumable by construction — every day caches to its own JSON, so a kill costs one day at most.
cd /home/alphabot/gazbot7
L=reports/sim_week_recursive/queue.log
echo "$(date -u +%FT%TZ) queue start — waiting for the v1 runs" >> $L
while pgrep -f 'sim_week_recursive.py --arm both' >/dev/null \
   || pgrep -f 'sim_week_recursive.py --arm selfaware' >/dev/null; do sleep 60; done
echo "$(date -u +%FT%TZ) v1 runs done — starting the 2x2 on w1" >> $L
PYTHONPATH=src .venv/bin/python -u scripts/sim_week_recursive.py --arm matrix --week w1 >> $L 2>&1
echo "$(date -u +%FT%TZ) w1 done — starting w0 (the replication week)" >> $L
PYTHONPATH=src .venv/bin/python -u scripts/sim_week_recursive.py --arm matrix --week w0 >> $L 2>&1
echo "$(date -u +%FT%TZ) QUEUE COMPLETE — notifying (holds if inside quiet hours)" >> $L
PYTHONPATH=src .venv/bin/python -u scripts/sim_queue_notify.py >> $L 2>&1
