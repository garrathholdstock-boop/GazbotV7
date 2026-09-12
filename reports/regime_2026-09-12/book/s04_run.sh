#!/bin/bash
GB=/home/alphabot/gazbot7
W=/tmp/claude-0/-root/7d23ea02-1a64-45f1-9faa-faa8101cea4d/scratchpad
mkdir -p $W/tickfeat $W/tickpq
for d in $(rclone lsf b2raw:gazbotv7/plain/tape/ticks/MNQ/ | sed 's/.parquet//' | sort); do
  [ -f "$W/tickfeat/$d.parquet" ] && continue
  rclone copy b2raw:gazbotv7/plain/tape/ticks/MNQ/$d.parquet $W/tickpq/ -q 2>/dev/null || continue
  sz=$(stat -c%s "$W/tickpq/$d.parquet" 2>/dev/null || echo 0)
  if [ "$sz" -lt 20000 ]; then echo "$d SKIP tiny"; rm -f $W/tickpq/$d.parquet; continue; fi
  systemd-run --scope -q -p MemoryMax=900M --setenv=HOME=/root \
    $GB/.venv/bin/python $GB/reports/regime_2026-09-12/book/s04_tickday.py \
    $d $W/tickpq/$d.parquet $W/tickfeat/$d.parquet 2>&1 | grep -E 'minutes=|Error'
  rm -f $W/tickpq/$d.parquet
done
echo "TICK DONE: $(ls $W/tickfeat | wc -l) days"
