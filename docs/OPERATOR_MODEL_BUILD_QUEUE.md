# THE OPERATOR-MODEL BUILD QUEUE

> **The goal, in the operator's words (2026-09-15):** *"we can potentially still automate these one
> day but the desk needs to understand and replicate my decision making."*
>
> **Tick these off here.** Each item carries the evidence that justifies it, its size, and a
> DEFINITION OF DONE — so "done" is a fact, not an opinion. Add the date and the commit when you
> tick one.

---

## THE EVIDENCE THIS QUEUE IS BUILT ON (2026-09-15, 61 entries over the rider's life)

| held for | n | total | wins |
|---|---:|---:|---:|
| under 15 min | 15 | −$1,327 | 6/15 |
| **15–60 min** | **17** | **+$4,570** | **14/17** |
| **1–3 hours** | **12** | **+$2,019** | **10/12** |
| 3–8 hours | 13 | +$1,207 | 10/13 |
| **over 8 HOURS** | **4** | **−$6,612** | **0/4** |

**Under 3 hours: +$5,262 over 44 entries. Over 3 hours: −$5,406 over 17.** The whole book is −$143,
so **four abandoned positions are −$6,612 and everything else he has ever done is +$6,469.**
⚠ Hold time is partly an OUTCOME, not only a choice — a trade going against you gets held in hope,
so some of the gap is the disposition effect. The >8h bucket is not that shape: 0 winners from 4,
and the 09-10 case ran 13.6 hours to −331pt. That is ABANDONMENT, and it is what this queue targets.

---

## ✅ DONE

- [x] **`trades.entry_source`** — record WHO opened a position (`manual` / `auto` / NULL=unknown).
      *2026-09-15, `b9fc2c3`.* 28 rows backfilled from journald; 83 left NULL deliberately.
      **Why:** attributing two days of P&L required parsing 461,738 journal lines.

---

## THE QUEUE — best first

### [x] 1. THE "LOOKED AND PASSED" BUTTON — **DONE 2026-09-18**
`PASS` sits under BUY/SELL with an optional "why not?" note. **No PIN and no confirm**, deliberately
— the PIN guards an ORDER and this places none, and friction that makes him skip recording a pass
defeats the point: the sample IS the product.
★★★ **THE SAFETY PROPERTY IS STRUCTURAL.** It writes `data/operator_pass.txt`, a filename
`day_rider` has never heard of — there is no code path from it to the broker, and a test asserts
the rider's source never names it. ⚠ `PathModified`, never `PathExists`: nothing consumes a pass
file, so `PathExists` would re-fire forever and fabricate presses he never made.
⚠ **Needs a `gazbot7-web` restart to go live** (it drops his tab — ask first).

<details><summary>original entry</summary>

### [ ] 1. THE "LOOKED AND PASSED" BUTTON  ·  size: S  ·  **the blocker**
One tap, places no order, writes the identical snapshot with `kind: "pass"`.

**Why it is first:** all 28 captured presses are a "yes". **You cannot learn a decision boundary
from one side of it.** With positives only, the best any model can do is describe what his entries
look like — which is exactly what 119 failed calibrations already did
([[claiming-cannot-be-backtested]]). This is the difference between UNDERSTANDING his reads and
REPLICATING them.

**Definition of done:** a `pass` record lands in `data/operator_reads.jsonl` with the same `facts`
schema as a buy, it places no order (asserted against the SOURCE, like the capture path), and
`operator_reads_join.py` counts passes separately from presses.
✅ Verified end-to-end 2026-09-18: `kind: pass`, note captured, full 3,162-char tape snapshot,
request grabbed in 0.02s, rider untouched. The synthetic test row was removed from the dataset.

</details>

### [x] 2. PRESENCE HEARTBEAT — **DONE 2026-09-18**, `scripts/presence.py`
★ **It needed NO code change.** nginx is the front door and had logged every request all along —
patching `web.py`'s no-op `log_message` would have recorded LESS (no static reports, no phone) and
needed a restart that drops his tab.
⚠⚠ **The devices are not interchangeable:** desktop **134 requests/MINUTE** (an open tab fakes
presence forever) vs phone **10 distinct sessions** in six hours. Phone = `LOOKED`, desktop =
`DASHBOARD-OPEN` (weak). They are sessionised separately and `strong_only` defaults to True.
★★ **THE RESULT:** of 16 alerts he ignored in the week to 09-18, **11 fired while he was
demonstrably looking** — so the alert's problem is **SELECTION, not absence**, and those 11 are the
first genuine NEGATIVE EXAMPLES this desk has had.

<details><summary>original entry</summary>

### [ ] 2. PRESENCE HEARTBEAT  ·  size: S
`web.py:2026` `log_message` is a deliberate no-op, so **not one dashboard request is logged
anywhere.** Make it write a timestamp.

**Why:** absence is the most expensive state this desk has — the −$6,612 above — and it is
currently invisible to it. This is the first instrument that would see it.

**Definition of done:** a rolling `data/operator_presence.jsonl` (or equivalent) with a bounded
size, from which "was he at the screen in the 10 min before/after this entry" is answerable. ⚠ It
must not log anything identifying beyond a timestamp and a coarse path.

</details>

### [ ] 3. HIS WORDS AT THE MOMENT  ·  size: S–M
A free-text field on the press — three words is enough. *"choppy grind up"*, *"left the tunnel"*,
*"second push"*.

**Why:** the 3,175-char `context` in each record is what the DESK saw. Nothing records what HE saw,
and his categories are the labels a model would have to learn. ⚠ The desk has repeatedly mistaken
its own axis (volatility) for his (displacement) — three times before it was caught.

### [ ] 4. PIN THE MICROSTRUCTURE BEHIND EACH PRESS  ·  size: M
Copy the `ticks`/`quotes`/`book` window around every press out of the 5-day hot tier.

**Why:** `book` retains 5 days; presses began 09-14 and the book starts 09-09, so the
microstructure behind the earliest presses is **already at the edge of deletion**. Order-book
thinning is in a live pre-registered test, so this may well be load-bearing.
⚠ **NOT fixed by renewing the data subscription** — the subscription is what flows data IN;
`gazbot7-capture-prune.timer` is what deletes it. Two different fixes.

### [ ] 5. CONTRACT COLUMN ON `capture.db.bars`  ·  size: M
Verified: `bars` stores `symbol='MNQ'`, no contract identity.

**Why:** every volume and RelVol comparison **across a roll is blind**, including the RelVol filter
due to arm ~2026-10-02. Already a standing build item; this is its second independent reason.

### [ ] 6. FIX OR RETIRE `drift` OUTSIDE US HOURS  ·  size: M
**26 of 28 presses recorded `drift_error: no 5s rows since 13:30Z today (venue shut?)`.**

**Why:** his presses cluster at **05:00–11:00Z** — only 2 of 28 were in US hours — so the desk's own
direction detector is unavailable for **93% of his decisions** and writes an error into the record
instead ([[drift-read-is-blind-outside-us-hours]]). Either it reads his hours or it should say
"not applicable" rather than "error".

---

## STANDING RULES FOR THIS WORK

- ⚠⚠ **NO FITTING BELOW 30 LABELLED PRESSES — and that rule was written for positives AND
  negatives.** 28 positives with zero negatives is not 28/30 of the way there. `operator_reads_join.py`
  enforces the count and says so.
- **The nearer-term prize is telling him WHEN TO LOOK, not replacing his judgement.** That is
  learnable from alerts and outcomes — and it already worked once: 2026-09-15 10:28:22 the leg watch
  paged the 60-min milestone, he bought 58 seconds later, +$343. ⚠ n=1.
- **I propose, he says go, and silence is not go.**
