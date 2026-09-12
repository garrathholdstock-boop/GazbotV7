#!/bin/bash
# S03 driver: one day at a time — download, extract per-minute features, DELETE the raw.
# Never holds two tapes on disk or in memory at once.
GB=/home/alphabot/gazbot7
W=/tmp/claude-0/-root/7d23ea02-1a64-45f1-9faa-faa8101cea4d/scratchpad
mkdir -p $W/bookpq $W/bookfeat $W/tickfeat $W/tickpq
cd $GB
for d in $(rclone lsf b2raw:gazbotv7/plain/tape/book/MNQ/ | sed 's/.parquet//' | sort); do
  [ -f "$W/bookfeat/$d.parquet" ] && continue
  rclone copy b2raw:gazbotv7/plain/tape/book/MNQ/$d.parquet $W/bookpq/ -q 2>/dev/null || continue
  sz=$(stat -c%s "$W/bookpq/$d.parquet" 2>/dev/null || echo 0)
  if [ "$sz" -lt 100000 ]; then echo "$d SKIP tiny ($sz b)"; rm -f $W/bookpq/$d.parquet; continue; fi
  systemd-run --scope -q -p MemoryMax=900M --setenv=HOME=/root \
    $GB/.venv/bin/python $GB/reports/regime_2026-09-12/book/s03_bookday.py \
    $d $W/bookpq/$d.parquet $W/bookfeat/$d.parquet 2>&1 | grep -E 'minutes=|Error'
  rm -f $W/bookpq/$d.parquet
done
echo "BOOK DONE: $(ls $W/bookfeat | wc -l) days"
