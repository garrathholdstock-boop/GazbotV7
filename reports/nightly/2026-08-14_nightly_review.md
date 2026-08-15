# Nightly review — 2026-08-14 (written in the CME halt, ~22:45Z)

Read-only on the desk. No config touched, `data/gate_switches.env` not edited.

## 1. The day's book, split by desk

| Desk | Trades (legs) | Net |
|---|---|---|
| TOURNAMENT | 37 | **+$170.50** |
| DAY-RIDER | 1 | **+$434.00** |
| **TOTAL** | 38 | **+$604.50** |

`data_quality IS NULL` applied. No quarantined rows today (the phantom rebook was 08-13 only).
No positions still open.

Tournament by gate (legs, not signals — A/B is a scale-out):

| Gate | Legs | Net |
|---|---|---|
| exhaustion_short_B | 15 | +$197.00 |
| exhaustion_short_A | 16 | +$113.00 |
| abs_veto_short_A | 3 | −$37.00 |
| abs_veto_short_B | 3 | −$102.50 |

exhaustion_short carried the whole tournament book (+$310 across both legs). abs_veto_short
lost $139.50 on ~3 signals. B lost more than A on the same signals → per the standing rule
that is a target/exit question on B, not a reason to drop either leg.

## 2. The day-rider's session — clean, no cross-desk interference

- **13:35:21 STOOD DOWN.** `"venue holds -2.0 but state says no entry — STANDING DOWN"`.
  That −2 was the *tournament's* abs_veto_short_A+B, which opened at 13:35:01 on the shared
  DUQ191770 account. The rider correctly refused to adopt another desk's position. This is the
  mirror image of CLOSED_ELSEWHERE and the guard worked.
- **13:38:22 ENTERED** 2 lots DOWN @ 30194.25 — drift confirmed, dir DOWN, eff 0.572, rt 0.51.
- Trail armed at +105pt (4×ATR 26.2). At 13:39 venue showed −4.0 = rider's 2 + tournament's 2;
  the rider tracked its own book separately throughout.
- **16:16:26 EXIT TRAIL** @ 30083.4, trigger `"reversed 32pt off the peak (>2xATR)"`, peak 30031.0.
- Fill 30085.0. **+$434.00** net of $3.00 fees (2 lots × $1.50/round-trip — correct).
- Then `"already traded this session — no re-entry"`, flat to the 21:00 hard flat and beyond.

**No CLOSED_ELSEWHERE.** Peak-to-exit giveback was 52.4pt (≈$216) — ordinary trail behaviour on a
2×ATR reversal trigger, not a fault.

## 3. The router's day — 4 real switches, all of them free

`grep -c APPLIED` for today = **4**. The tournament journal shows **5** "gate switches changed"
lines; the extra one (04:42:20) is a *new PID* re-reading the board after the daily ~04:35Z
gateway-outage restart, not a decision. Router log 4, journal 5, real count **4**:

| Time | Change | Why |
|---|---|---|
| 01:05:33 | capitulation_long → off | ASIA bench |
| 19:45:21 | exhaustion_short → off | stay-out meter 59/100 |
| 20:05:23 | abs_veto_short → off | 60min UP +61pt ER 0.263 |
| 20:30:28 | abs_veto_short → on | direction bench LAPSED, 60min FLAT |

A 5th write to `gate_switches.env` at 22:00:00 was **gazbot7-gate-reactivate.service**, not the
router — Paris-midnight re-arm of capitulation_long and exhaustion_short. That is what the file
mtime records, so mtime alone would have mis-attributed it.

**Churn priced, not assumed.** Neither exhaustion_short nor abs_veto_short carries an ATR floor
(only grind_long and capitulation_long do), so a bench on them cannot hide behind an ATR block —
a missed entry would appear as SUPPRESSED-OPEN. There were **zero** SUPPRESSED-OPEN after 16:02Z.
That zero is real, not a logging gap: hour 20 logged 1253 journal lines and 510 ATR-gate lines,
so the process was fully alive and evaluating through both bench windows.

→ **4 switches, $0 of foregone entries.** Churn was invisible at $0, literally.

The day's actual suppression was all on the long side and all in the morning — 240 abs_veto_long
legs + 228 grind_long legs (~234 signals) refused under the MONDAY #2 momentum start-bench.
Given the tape fell from 30194 to 30085, holding the longs off was the right call, not a cost.

## 4. Grind-exit shadow — both variants fail, one of them decisively

### two_ratchet (n=26) — worse than live, and the leak was in its favour

- live **+$29.50** vs shadow **−$265.00** → shadow loses by **$294.50**.
- The file's own `xcheck` is **−$406.00**. That reconciles exactly:
  `xcheck = sum(recon_pure) − live_net = −376.5 − 29.5`. So the honest, leak-free cost of the
  variant vs live is **−$406**, and the headline −265 is the flattered number.
- **The leak, isolated.** `shadow_usd` differs from `recon_pure_usd` on exactly **one** trade —
  2026-07-27T18:54, shadow +$144.50 vs pure +$33.00. That single leaked runner is the *entire*
  $111.50 gap between the shadow and its own pure reconstruction.
- This variant holds *longer*, so the leak bias helps it — and it still loses by $294.50–$406.
  **That makes the "two_ratchet is worse" conclusion robust.** It is safe to reject.
- Material divergence from live: 11/26 = **42%**, corroborating the standing 44% figure.

### THE RACE (not MFE): reaching R is not surviving to R

| Threshold | Reached | …and STOPPED OUT anyway |
|---|---|---|
| ≥1.0R | 11/26 | **6** (55%) |
| ≥2.0R | 6/26 | 1 |
| ≥3.0R | 6/26 | 1 |

Exit reasons: STOP 19, CHANDELIER 4, MANUAL_CLAIM 3. One trade reached **3.06R** and still closed
−$46.50. Any read of these 26 trades from rMFE alone would have booked 11 winners at 1R where 6
were losses.

### partial (n=40, scalp_r 2.0) — not deployable, and the headline is mislabelled

- `mean_delta: 307.5` is **not a mean, it is the total**. True mean is **$7.69/trade**
  (307.5/40). It equals `partial_net − baseline_net` exactly. Reading that field as written
  overstates the per-trade effect by 40×.
- Only **10 of 40** trades differ at all (8 up, 2 down; median non-zero +$53, range +$130/−$158.5).
- **Both variants are 0.0% green days and 0.0% green weeks.** Baseline −$1382.40, partial
  −$1074.90. The "improvement" is a choice between two things that lost money in every day and
  every week of the window. Neither is deployable; +$307.50 is a less-bad loser, not an edge.
- Regime split at the live `atr_split=22.0`: **LO ATR<22 n=21, delta +$369.50** (5 trades differ);
  **HI ATR≥22 n=19, delta −$62.00** (5 trades differ). The entire "edge" is 5 low-vol trades.
- ⚠ **This variant exits EARLIER and has no leak control.** two_ratchet ships a `recon_pure_usd`
  column, so its leak was measurable and turned out to be one trade. partial_shadow ships only
  `baseline_usd`/`partial_usd`/`delta` — there is no pure column, so the 44% stop-leak cannot be
  measured or subtracted. Its +$307.50 is exactly the class of result this desk has been burned by.
- Fees: 10 partials add legs; at $1.50/round-trip that is ~$15, immaterial next to the above.

### Exit selector — the nightly regret metric is contaminated

`data/selector_nightly/` has no file for today (last is 2026-08-13). There is **no systemd timer
or unit for it anywhere**, and the file set is gappy (07-29..07-31, 08-03..08-07, 08-13) — it is
run ad hoc, not nightly, despite the name. Its only consumer is the Friday report:
`scripts/friday/friday_phases.py:192` rolls `data/selector_nightly/*.json` into the **ROUTER VALUE**
figure — so the contamination below propagates into the Friday headline.

The 08-13 file counts **5 identical day_rider LONG rows**, all chosen_pnl −31.5, regret 72.5. The
DB has exactly one legitimate day_rider row for 08-13 (id 668) plus **four** marked
`EXCLUDE:day_rider_phantom_rebook_20260813`. The selector counted all five.

`scripts/selector_nightly.py:84-87` filters `exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE')`
but **never filters `data_quality`** — the very filter this desk's own P&L query mandates.

Effect on the 08-13 headline:

| | As published | Deduped |
|---|---|---|
| n | 14 | 10 |
| regret | 748 | 458 |
| selector_pnl | −228 | −102 |

**48% of that day's total regret is one trade counted five times.** Any selector tuning done off
these files is chasing a quarantined phantom.

## Needs a decision

1. **`scripts/selector_nightly.py` must filter `data_quality IS NULL`** (line 87). Until it does,
   every regret/selector_pnl number it has produced on a day with quarantined rows is inflated.
   Historic files should be regenerated after the fix.
2. **Reject two_ratchet.** −$406 vs live leak-free over 26 trades, and the leak was helping it.
3. **Do not act on partial_shadow.** 0% green days/weeks on both arms, no leak control, and the
   whole delta is 5 low-vol trades. If it is worth pursuing, it needs a `recon_pure` column first.
4. Fix the `mean_delta` label in the partial shadow writer — it emits a total under a mean's name.
5. exhaustion_short was benched 19:45 (two minutes after its last fill) and was the day's only
   profitable gate; the 22:00 reactivate has already re-armed it. No action, noted for continuity.

## Durable rule

**A shadow variant is only as trustworthy as its pure-reconstruction column: two_ratchet ships
`recon_pure_usd` and its leak proved to be one trade, partial_shadow ships none — so an
"exit-earlier" delta with no pure column is unfalsifiable and must not be acted on.**
