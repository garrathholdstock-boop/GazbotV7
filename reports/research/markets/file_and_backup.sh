#!/bin/bash
# 2026-10-26 market research: when the IBKR pull ends, file the new markets into the lake, write a manifest, back everything up to B2, verify.
cd /home/alphabot/gazbot7
LOG=reports/research/markets/file_and_backup.log
until grep -q "done:\|deadline reached" reports/research/markets/backfill_pull.log && ! ps -eo pid,args | awk '$2 ~ /python$/ && $3 ~ /backfill_history\.py$/' | grep -q .; do sleep 60; done
echo "[$(date -u +%H:%M:%SZ)] pull finished; filing" >> $LOG
SYMS=MES,M2K,MYM,MBT
PYTHONPATH=src .venv/bin/python scripts/backfill_to_lake.py --symbols $SYMS >> $LOG 2>&1
PYTHONPATH=src .venv/bin/python reports/research/markets/manifest.py >> $LOG 2>&1
for s in MES M2K MYM MBT; do
  rclone copy data/tape/bars/$s b2raw:gazbotv7/plain/tape/bars/$s --retries 3 --stats 0 >> $LOG 2>&1
  rclone copy data/backfill b2raw:gazbotv7/plain/backfill --include "${s}_*.parquet" --retries 3 --stats 0 >> $LOG 2>&1
done
rclone copy reports/research/markets/MANIFEST_2026-10-26.json b2raw:gazbotv7/plain/backfill/ >> $LOG 2>&1
rclone copy reports/research/markets/MANIFEST_2026-10-26.md b2raw:gazbotv7/plain/backfill/ >> $LOG 2>&1
for s in MES M2K MYM MBT; do
  echo "verify $s lake: $(rclone check data/tape/bars/$s b2raw:gazbotv7/plain/tape/bars/$s --one-way 2>&1 | tail -1)" >> $LOG
  echo "verify $s raw:  $(rclone check data/backfill b2raw:gazbotv7/plain/backfill --include "${s}_*.parquet" --one-way 2>&1 | tail -1)" >> $LOG
done
echo "[$(date -u +%H:%M:%SZ)] FILE_AND_BACKUP_DONE" >> $LOG
