#!/bin/bash
# ★2026-10-03 Ping when the 17-18 Sept recreate attempt finishes — his two best days.
# ⚠ The queue's own ping fires only when the whole 2x2 completes (~15h away). This one covers the
#   short run he actually just asked about (~45min), so he is not waiting all night for it.
cd /home/alphabot/gazbot7
L=reports/sim_week_recursive/queue.log
while pgrep -f 'sim_week_recursive.py --arm v2_both --days 2026-09-17' >/dev/null; do sleep 30; done
echo "$(date -u +%FT%TZ) recreate 17-18 done — notifying" >> $L
PYTHONPATH=src .venv/bin/python -u scripts/ping_recreate.py >> $L 2>&1
