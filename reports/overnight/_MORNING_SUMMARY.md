# Overnight run — 2026-08-18/19

## Banked and verified

| | |
|---|---|
| Backfill | **91 parquet files, 1,070,462 bars**, every file verified readable |
| Published to lake | **756,931 rows** — lake now spans **2023-11-30 → 2026-08-19** |
| MNQ 1-min | 376,904 bars, 2025-09-14 → 2026-08-18 |
| MGC 1-min | 468,055 bars, 2025-07-27 → 2026-08-18 |
| MGC 1-day | 6,030 bars, **2023-11-30** → 2026-08-19 (32 months) |

## Research artifacts (all on the corrected full-history basis)

| artifact | scope |
|---|---|
| `census_MNQ.txt` + `.html` | 347 runs ≥1.5×ATR, 1min, 2025-09-14..2026-08-18 |
| `census_MNQ_small.txt` | 598 runs ≥1.0×ATR, same span |
| `census_MGC.txt` + `.html` | 373 runs ≥1.5×ATR, 1min, 2025-07-27..2026-08-18 |
| `census_MGC_small.txt` | ≥1.0×ATR, same span |
| `walkforward_{all,preroll,q3,recent}.txt` | 240 / 205 / 163 / 78 days OOS |

## Read these caveats before acting on anything above

**1. The walk-forward is NOT your live slate.** `forward_validate.py` tests one frozen
2026-07-18 candidate (grind + LONG rgv, hardcoded at lines 124/140). Your desk runs six
gates with different params, dual-lot exits and router benching. A harness that walks the
LIVE roster forward does not exist yet.

**2. It ran on IBKR 1-minute backfill, not our 5s capture.** Different bar construction →
different path/ATR. A negative result here is partly a hypothesis about the bar source.
Result was stable and negative across all four windows: ~35-38% green days, combined
-14,279 over 232 OOS days, costs charged at $1.50/RT.

**3. THE CENSUS PARTICIPATION FIGURE IS NOT MEASURABLE OVER THIS WINDOW.**
The summary says "339 of 347 sat out". But:
  - before the desk existed (Sep 2025 - Jul 15): **234 runs, 0 participated**
  - after it went live (Jul 16 onward): **113 runs, 8 participated (7%)**
The headline is dominated by months with NO DESK. The $217,326 "money on the table" is
likewise ~2/3 counted against a period with no participant. Only the 113 post-live runs
carry information about participation.

## Not done

- **greenfield** — `--since gf_MGC` was invalid (serial_runner wants an ISO datetime); the
  artifact was 431 bytes of traceback, kept as `greenfield.FAILED_bad_arg.txt`.
  Deliberately NOT re-run: the gf_ phases read `reports/friday_v7/sections/census_summary.json`,
  and that summary needs the participation-window caveat above baked in first or the research
  will conclude the desk misses 98% of runs, which is an artifact of the window.
  Tonight's full-history censuses HAVE been published into that sections dir; the previous
  Friday set is backed up in `sections/_pre_backfill_2026-08-14/`.

## Faults found and fixed during the night

1. `run_census.py` read the PRUNED capture.db — "--days 400" censused ~30 days and printed
   "last 400d". Added `--lake`.
2. Then it hardcoded `timeframe='5s'`, which exists only for our own capture window. Now picks
   the WIDEST-SPAN timeframe fine enough to resolve the measurement (preferring the finest was
   also wrong — it would have kept 5s and discarded nine months).
3. The backfill wrote to `data/backfill/`, which the lake does not scan — every bar pulled was
   invisible to research. Added `backfill_to_lake.py`.
4. `forward_validate.py` had the SAME hardcoded 5s (written while fixing #2) — 42 days instead
   of 240.
5. Its header printed "alphabot.db 1m" even under `--lake` — it echoed the default, not the
   source used.
6. The backfill crashed on daily bars: IBKR returns `datetime.date` (no `.timestamp()`) for
   1-day and `datetime` for intraday.
7. It died on a gateway restart with no reconnect handling; an 8h job on a nightly-restarting
   gateway must reconnect.
8. The overnight chain's artifact check used SIZE only — 431 bytes of traceback passed a
   400-byte floor and was recorded "ok". It now inspects content.
9. `systemd-run` does not set HOME, and DuckDB requires it — five phases returned rc=0 in 20
   seconds with tracebacks in every artifact.
