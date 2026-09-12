# Interim 2 — causal MGC<->MNQ directional grid  [2026-09-12]

160 train cells (5 signal windows k x 4 horizons h x 2 thresholds x 2 directions x 2 hour-scopes).
Entry = OPEN of bar t+1, exit = OPEN of bar t+1+h, signal uses only closes <= t. Friction 1.25pt MNQ
/ 0.45pt MGC per round turn. Day-block bootstrap (whole sessions resampled) for every CI.

## The train winner does not survive

`MGC->MNQ, k=30, h=60, top-20% |gold move|, US hours` — the single best of 160 train cells:

| split | n | hit rate | net pt/trade | day-block 95% CI | always-long, same minutes |
|---|---|---|---|---|---|
| train    | 6096 | 0.546 | **+13.17** | [+2.81, +23.37] | -13.93 |
| validate | 6969 | 0.509 | +3.60 | [-7.24, +13.68] | +6.86 |
| **test** | 3590 | **0.489** | **-3.65** | [-22.51, +16.57] | -16.65 |

Hit rate 0.546 -> 0.509 -> 0.489. That is the shape of an in-sample artefact, not an edge.

## Across all 8 headline cells x 3 splits (24 rows, `05_decompose.csv`)

* **22 of 24 day-block CIs include zero.** The two that do not are both TRAIN.
* Out-of-sample hit rates cluster on the coin: validate 0.443-0.528, test 0.464-0.519.
* The `always-long` benchmark on the identical minutes swings -16.6 / +6.9 / -13.9 points. The
  MNQ 60-minute drift on these minutes is far larger and far noisier than any claimed signal, which
  is exactly why a raw P&L sort produced +13 pt/trade.
* **The naive shuffled twin was itself positive (+2.40 pt).** A control that makes money net of
  friction is a broken control — it changed the entry population (a within-session signal shuffle
  re-selects which minutes clear the top-20% threshold). Replaced with same-minutes controls.

## Caveat carried forward
The per-trade sign-flip control's sd (~1.3 pt) is too tight: with 60-minute holds entered every
minute, trades inside the same hour are near-duplicates, so flipping signs independently understates
the spread. Superseded in step 06 by a block-level sign flip. The day-block bootstrap above was
already correct and is the number that decides.

**Interim verdict, Line 1 directional: NULL (heading to REFUTED).**
