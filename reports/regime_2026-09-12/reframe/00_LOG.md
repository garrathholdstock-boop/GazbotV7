# REFRAME — index (2026-09-12)
READ `REFRAME.md`. Everything else here is its evidence.

| file | what it is |
|---|---|
| `REFRAME.md` | **the deliverable** — 6 framings, ranked, each with a verdict |
| `build_tape.py` / `tape_MNQ_1min.parquet` / `tape_MGC_1min.parquet` | cached front-month 1-min tapes (loader copied from `scripts/bt_regime_transition.py::tape`) |
| `a1_*` | horizon-vs-friction table + the FIRST (UTC-keyed) clock pass — **superseded, kept as the error record** |
| `a2_*` | first overnight-arm pass, UTC-keyed — **superseded by a3** |
| `a3_*` | clock decomposition + arms on the EXCHANGE clock (America/New_York) |
| `a4_*` | MGC replication + the paired MNQ/MGC overnight book (ρ=0.37) |
| `a5_*` | detectability arithmetic: 70,525 trades / 14.4 yr at the ceiling; friction as % of account |
| `a6_output.txt` | live-record forensics: rider "single-lot" rows are 20 positions, not 45 |
| `a7_spread.txt` | measured MNQ/MGC spread by session; liquidity-provision arithmetic |
| `a8_capture_ratio.txt` | break-even capture ratio by holding period, both contracts |
| `a9_data_ceiling.txt` | daily-history audit across all 29 daily parquets — the blocker |
| `a10_*` | ★ contract-roll contamination audit — caught a third of the overnight arm |
