#!/usr/bin/env bash
# Re-run the four walk-forward windows on the FULL history (tf now chosen by widest span).
# The first pass ran on 42 days because _load_days_lake hardcoded timeframe='5s'.
set -u
cd /home/alphabot/gazbot7
export PYTHONPATH=/home/alphabot/gazbot7/src
OUT=reports/overnight
run() {
  local tag="$1" since="$2"
  echo "$(date -u +%H:%M:%S)Z start walkforward_${tag} from ${since}"
  timeout 3600 .venv/bin/python scripts/forward_validate.py --lake --from "${since}" \
      > "${OUT}/walkforward_${tag}.txt" 2>&1
  echo "$(date -u +%H:%M:%S)Z   rc=$? size=$(stat -c %s "${OUT}/walkforward_${tag}.txt")B"
}
run all     2025-09-01
run q3      2026-01-01
run recent  2026-05-01
run preroll 2025-11-01
echo "$(date -u +%H:%M:%S)Z walkforwards done"
# census_MGC_small timed out at 60min on the first pass; give it three hours.
echo "$(date -u +%H:%M:%S)Z start census_MGC_small"
timeout 10800 .venv/bin/python scripts/run_census.py --symbol MGC --days 400 --min-atr 1.0 --lake \
    > "${OUT}/census_MGC_small.txt" 2>&1
echo "$(date -u +%H:%M:%S)Z   rc=$? size=$(stat -c %s ${OUT}/census_MGC_small.txt)B"
echo "$(date -u +%H:%M:%S)Z ALL DONE"
