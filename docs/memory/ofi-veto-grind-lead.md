---
name: ofi-veto-grind-lead
description: "OFI delay-VETO on grind_long is the ONE book cell that survives retention — in-sample lead, not a result; confirm variants all fake wins"
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-04T11:37:28.871Z
---

2026-08-04, operator asked for the mechanical (codeable) test of the L2 book as a confirm/veto rather
than as a trigger: "do the mechanical one. fix the fee and run it."

`scripts/ofi_confirm_veto.py`, 20 days (2026-07-15→08-04), MNQ, $1.50 fee + $0 slip, tick-honest exits.
Output now SAVED to `reports/ofi/` — the previous version printed to stdout only, which is the direct
reason no conclusion from it could ever be cited.

**ONE cell survived the retention check:**
`grind_long` delay-VETO, d=15s, MLOFI(1-3), m=1.0 → RAW −$172/136tr (33.1%) becomes **+$772/115tr
(38.3%), keeping 14/14 catchable runs**. A $944 swing that does not drop the runs it should catch.

**Everything else failed.** Every *confirm* variant was flagged FAKE-WIN (beat baseline only by dropping
caught runs). `thrust_short` produced nothing — both its 55s proxies were NEGATIVE (−$203, −$213). So on
our own tape the book **vetoes, it does not select**, which is what the literature predicts: OFI has a
near-linear relation to short-horizon price change with slope inversely proportional to depth, but it
*tilts a distribution*; it does not forecast. Practitioner sources say the same — absorption and delta
divergence are entry FILTERS, and "rising price with negative cumulative delta is more often the
signature of absorption that has ALREADY played out."

**DO NOT ARM THIS YET. Five reasons, all live:**
1. In-sample, one regime, no OOS split.
2. `d=15` is the TOP of the delay grid — a parameter pinned at its boundary is suspect. Extend the grid.
3. ~100 cells swept per gate; one survivor is roughly what noise alone produces (multiple comparisons).
4. `SLIP_RT=0` is the optimistic bound, and a 15-SECOND delayed entry has real slippage.
5. $944 over only 21 vetoed trades = **$45/veto** — large enough to be one or two avoided disasters.
   Needs strip-best / LOO before it means anything. cf. [[friday-findings-need-adversarial-rederivation]]
   (4 of 5 recs died) and [[mfe-is-not-a-win-rate]].

**⚠ THE MECHANISM OBJECTION IT HAS NOT ANSWERED:** [[desk-l2-book-consumption-scope]] records a 07-13
study on all 57 live trades where aggregate L2 made things WORSE (−$194), because real absorption is
hidden iceberg refill invisible to a 10-level snapshot. OFI measures book *changes* over time rather
than static shape, so it is arguably a different statistic — arguably. A backtest number does not
discharge a mechanism objection.

Data now lives at `gazbot7/data/depth.db` (MNQ only, 10 levels) — see
[[desk-l2-book-consumption-scope]] for the V7 port.
