# L2 BOOK CAPTURE — PORTED INTO V7 (2026-08-04)

Operator: *"move the book capture into v7 so we can use it"*, then *"we dont need anything but mnq"*.

## What was wrong

The 10-level order book had been captured continuously since 2026-07-15 — 4.2M MNQ snapshots — by
`alphabot-depth-capture.service`, living in the **retired alphabot2 V5 tree**, on IBKR clientId 97,
tagged "observe-only R&D". Two concrete failures came from that placement:

1. **I told the operator we did not persist the L2 book at all.** It was invisible to me because it
   lived in the tree `CLAUDE.md` says never to probe — I read "alphabot2 is retired" as "alphabot2 has
   nothing". Compounding it, `cl_sims.build_ctx` carried a *deliberate* exclusion whose stated reason
   was arithmetically wrong: "~86 contracts visible vs ~2,664 contracts/min of flow, 6x below where
   absorption is measurable". Measured: **162 contracts vs ~170/min** — the visible book is roughly
   **57 seconds of flow**, not a rounding error. The claim also compared a *stock* of resting liquidity
   against a *flow rate*, which is a units mismatch independent of the values. Conclusion inverted.
2. **Nothing swept it.** A capture no health check watches can die silently. The 20-day history that
   every L2 study depends on would have stopped growing with no alarm — and did, for M2K, on 07-29.

## What changed

| | before | after |
|---|---|---|
| unit | `alphabot-depth-capture` (V5 tree) | `gazbot7-depth-capture`, `gazbot7.slice` |
| script | `alphabot2/scripts/depth_capture.py` | `gazbot7/scripts/depth_capture.py` |
| database | `alphabot2/data/depth.db` | `gazbot7/data/depth.db` |
| symbols | MNQ, MES, MGC, M2K | **MNQ only** |
| write batching | `FLUSH_S = 5.0` | `FLUSH_S = 1.0` |
| swept | no | yes — service + **data freshness** |

**History preserved:** the 2.4GB database was **moved**, not copied (same filesystem — instant, no
extra disk on a volume at 80%). 9.46M rows intact and continuous from 2026-07-15.

**MNQ only.** The V5 unit requested four symbols and IBKR refused the fourth with
`Error 309: Max number (3) of market depth requests has been reached` — which is why M2K silently
stopped on 07-29 and nobody noticed. This desk is MNQ-only, so the other three bought nothing while
consuming 2 of 3 scarce depth slots and ~55% of the table's rows. Note the cap for future reference:
**only three depth subscriptions may be live at once.** Non-MNQ history is not deleted; the 20-day
retention prune ages it out on its own.

**`FLUSH_S` 5.0 → 1.0.** The capturer samples at 250ms but wrote in 5-second batches, so a *live* read
was up to 5s behind reality by design. Harmless while the book was only read offline for backtests;
not harmless now that `cl_sims.book_snapshot()` reads it at signal time to attach a book to a verdict.
Measured read age after the change: **~0.9s** (was ~5s). Costs ~4 extra commits/sec on a table doing
~15 rows/sec.

**Swept two ways.** `gazbot7-depth-capture` is in `sweep.py::_SOFT_SERVICES`, *and* `check_capture()`
now asserts **L2 data freshness** — because an active unit is not proof of capture, the same trap as
the router's full-roster pin that logged "no change" for 411 ticks while doing nothing. WARN, never
CRIT: no gate reads depth, so a gap costs research, not trades. Pinned by
`test_depth_capture_down_is_WARN_never_CRIT`.

## Readers repointed

`cl_sims.py`, `ofi_confirm_veto.py`, `ofi_seconds_sweep.py`, `footprint_backtest.py`,
`footprint_backtest_duck.py`, `exhaustion_long_test.py`, `cost_waterfall.py`, `run_census_full.py`.
The old path no longer exists, so nothing can silently fall back to a stale copy. `gazbot7-shadow` was
restarted to pick up the new constant.

## ⚠ The standing objection this port does NOT discharge

A 2026-07-13 study on **all 57 live trades** found aggregate L2 made things *worse*: tape-only
absorption cut +$176, book-gated −$18. Root cause: the absorption that matters is **hidden iceberg
refill** (~175 contracts absorbed in 60s into a visible bid of ~4) which a 10-level snapshot cannot
see. That killed both the pre-entry veto and the book-confirmed exit cut.

Better plumbing does not answer a mechanism objection. The one cell that currently survives — an OFI
delay-VETO on `grind_long` — is measured on book *changes over time* rather than static shape, which is
arguably a different statistic. Arguably. See `reports/ofi/` and the caveats recorded with it.
