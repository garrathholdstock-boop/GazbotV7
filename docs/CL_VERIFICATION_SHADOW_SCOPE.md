# CL-VERIFICATION SHADOW — spec

> **What this is.** Every live gate signal gets a Claude yes/no recorded against it. **Nothing is
> gated.** The live trade proceeds exactly as it does today. After a week we score the calls against
> what actually happened: did the ones I'd have vetoed lose, did the ones I'd have passed win?
>
> **Why shadow first.** The bar is not "better than nothing" — it is **beat +$2,538**, which is what
> abs_veto's mechanical 55s veto is already worth over un-vetoed thrust. And four of five headline
> findings fell over this week under re-derivation. Grade the judgement before routing capital
> through it.

---

## 1. Naming

Sims are prefixed **`CL-`** so they sort together and are unmistakable:

| sim | shadows |
|---|---|
| `CL-grind_long` | grind_long |
| `CL-capitulation_long` | capitulation_long |
| `CL-abs_veto_long` | abs_veto_long |
| `CL-abs_veto_short` | abs_veto_short |
| `CL-exhaustion_short` | exhaustion_short |
| `CL-rgv_short` | rgv_short |
| `CL-nipc_long` | nipc_long *(benched for diagnosis — spec'd, not started)* |
| `CL-nipc_short` | nipc_short *(same)* |

One deviation from your `CL - ` : I dropped the space. These strings become `shadow_trades.strategy`
keys, appear in SQL, JSON and CSV, and get split on whitespace in a couple of report scripts. `CL-`
gives the same instant recognisability without the parsing hazard. Say if you want the space back.

## 2. Trigger — when I get woken

**Persistence pre-filter: the gate's entry condition must hold for 15 consecutive decision cycles
(= 15s at the desk's 1s cadence) before a verification is requested.**

This is your "15 cycles in a row" and it does three jobs: it filters flicker (the resolution study
measured 56–61% of fast abs_veto episodes never confirming), it throttles the call rate, and it is
itself a mechanical noise filter of the kind we already know works.

⚠ **Log the signals that die before 15 cycles too.** Their outcomes are the control group for
whether the persistence filter is doing anything, and without them we cannot tell the filter's
contribution from mine.

## 3. What I get shown

Assembled by a trusted wrapper — I never run commands, same architecture as the durable router.

- The signal: gate, side, price, the gate's own trigger values
- Regime: ATR-14, ER30, day-bias, the 0–10 tradeability read, the untradeable meter
- Tape: aggressor flow imbalance over 30s/60s/5m, RVOL
- Position of the run: extension vs VWAP, distance into any current move, minutes since session open
- Recent behaviour: last 5 closed trades on this gate, and whether the desk is in a stop-wall

**❌ NOT the L2 book.** The greenfield study found MNQ's whole visible 10-deep book is **86 contracts
against 2,664 contracts a minute of flow** — roughly 6× below the depth where absorption means
anything, a fact credited with explaining four separate dead ends. Asking me to read buyer absorption
off that book would be me reporting noise with confidence. **Tape flow is real and measurable; the
book is not, on this instrument.** If we want book-based absorption it needs a different contract.

## 4. What I return

Strict JSON, same fail-safe contract as the router: **any error, timeout or parse failure records
`no_verdict` and NEVER blocks anything.**

```json
{"verdict": "PASS" | "VETO", "confidence": 0-100, "reason": "<one line>",
 "primary_factor": "<the single thing that decided it>"}
```

`primary_factor` is deliberately required — it makes the calls **auditable in aggregate**. If every
veto cites the same factor, that factor is a mechanical rule and should be coded, not asked.

## 5. Latency — measured, not assumed

The durable router runs this exact loop today: timer fires on `:00`, service finishes at **`:04`–`:17`,
typically `:05`–`:07`** — and that includes three subprocess calls each attaching DuckDB to a 5.7GB
capture. A single-signal call with a pre-assembled context will be faster.

**Budget: under 10s typical, 15s hard timeout.** For scale, the desk already waits **55 seconds** on
abs_veto's veto and that wait is worth +$2,538. Latency is not the constraint here.

Record actual latency on every call. If p95 exceeds 15s the design changes, and I want that visible
rather than discovered later.

## 6. Scoring — decided before we start

The experiment is clean *because* nothing is gated: every signal proceeds, so we observe the outcome
of both arms with no selection bias.

Primary: **$/signal of PASS vs VETO.** The claim is only real if VETO signals lose money and PASS
signals make it, by a margin that beats the mechanical veto already in place.

Also reported: agreement rate with the existing 55s veto (if I only reproduce it, code it and skip
the call); accuracy split by gate and by regime (day-level judgement demonstrably works — today it
saved ~$2,586 — signal-level is untested and may simply not be the same skill); confidence
calibration; and the persistence filter's own contribution from the <15-cycle control group.

**Success:** VETO-set $/signal materially below PASS-set, holding on strip-best-3 and leave-one-day-out,
across ≥100 verified signals or two weeks.
**Failure, stated up front so it cannot be argued around:** no separation, or separation that
disappears once the 55s veto's own calls are removed — i.e. I am just re-deriving the mechanical rule.

## 7. Cost and safety

~30–90 signals/day across the roster, cut by the persistence filter. Read-only: the layer writes to
`shadow.db` only, touches no switch, no order, no live config. Fail-safe by construction — a dead
verification layer is invisible to the desk.

## 8. Honest risks

- **I may just reproduce the mechanical veto.** Then it is a slower, costlier 55s rule. The agreement
  metric is there to catch exactly that.
- **Signal-level ≠ regime-level.** My demonstrated wins are day-scale reads (stay out / bench). A
  single signal in isolation is a much thinner information set and may not be a skill I have.
- **Hindsight leakage.** The context builder must use ONLY data available at signal time. Any
  forward-looking field silently invalidates the whole experiment; assert it in tests.
- **Small n per gate.** Six gates × a week is thin per cell. Report pooled first, per-gate as a
  direction.
