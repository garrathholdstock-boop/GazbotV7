---
name: run-state-is-the-primary-discriminator
description: "★★★2026-08-06 — ONE variable explains essentially all desk P&L: is a directional RUN in progress AND is the gate aligned. In-run aligned +$10.34/tr taken (+$35 on missed, raced); chop −$28.43/tr. A $39/trade spread. gazbot7/runstate.py ships it into the tick. THE BENCH/ARM ASYMMETRY INVERTS INSIDE A RUN."
metadata: 
  node_type: memory
  type: project
  originSessionId: 20d20fe8-b00d-478a-9a38-35782c5c05e3
  modified: 2026-08-06T22:27:05.522Z
---

**Built 2026-08-06 (`2cd59e2`) after the operator challenged the desk being "basically benched the whole
time".** Reviewed Mon 08-03 → Thu 08-06: found 26 runs from RAW bars (30m window, |net|>=80pt, ER>=0.35,
extended while ER>=0.30), then classified every trade — **taken AND missed** — by whether it sat inside an
*aligned* run. The 31,502 `SUPPRESSED-OPEN` lines collapse to **260 distinct missed opportunities**
(same gate, >120s gap = new episode), each **RACED target-vs-stop first-touch**, stop = 1×ATR at entry.

|                | TAKEN                     | MISSED (raced @2R, 1 lot)     |
|----------------|---------------------------|-------------------------------|
| in-run aligned | n=34 · 50% · **+$10.34/tr** | n=61 · **67%** · **+$2,141**  |
| in-run counter | n=4 · 0% · −$20.38/tr     | n=16 · 6% · −$643             |
| chop / no run  | n=51 · 16% · **−$28.43/tr** | n=183 · 27% · **−$1,517**     |

**A ~$39/trade spread that dwarfs gate, side and time-of-day.** The desk sat flat through **18 of 26
runs**, blocking $2,141 (1 lot) / $4,283 (2 lot) of aligned signal — while *correctly* saving ~$2,160 of
chop damage. **Benching was never too aggressive in aggregate; it was INDISCRIMINATE** about the one
variable that matters. Tuesday is the proof: the only green day (+$330.50) is the only day armed through
two big runs.

**★★ THE ASYMMETRY INVERTS.** "Wrongly benched is cheap, wrongly armed is expensive — sit benched one more
tick" is correct in CHOP and expensive in a RUN. Applying it blind to which regime we are in is the whole
defect. **Inside a detected aligned run, BENCHED is the expensive error.**

**Shipped:** `gazbot7/runstate.py` + `scripts/run_detect.py`, injected into `router_tick_durable.py`
**above** the untradeable meter, with the rule that **when the two disagree the RUN STATE wins** — the
meter is a DAY aggregate and read 87/100 STAY-OUT through a +297pt run on 08-06. It **reports STATE ONLY
and never flips a switch**; the arm/bench call stays with Claude (operator: "claude, not python scripts,
needs to arm or de-arm").

**Replayed live over the same week** (recomputed each minute, trailing bars only, no look-ahead):
ARM n=20 65% +$729 (+$36.5/tr) · FLAT n=240 33% −$747.

⚠ **IN-SAMPLE and LATE.** Thresholds came from the week they score on; a trailing 30m window confirms a
run only once most of it has happened (captured 20 of 61, ~34%). Status is **promising, not validated** —
needs forward days. Full attack list for the Friday report:
`docs/MIDWEEK_LEAD_2026-08-06_RUN_STATE.md`.

⚠ **The exits eat most of it:** actual in-run trades made $10.34/tr against the raced $35/tr, so the
$4,283 headline is NOT achievable — realistic recovery ~$1,200–1,500. That gap is an EXIT problem.
⚠ **Not every miss is a router error:** 4 runs (345pt of movement) produced ZERO signals from any gate —
arming would have changed nothing. Gate mechanics, Friday rehab. See
[[read-the-tape-first-shadow-is-confirmation]], [[go-find-the-price-yourself]],
[[vol-expansion-is-the-binding-leg]], [[intelligent-routing-not-blanket-benching]].
