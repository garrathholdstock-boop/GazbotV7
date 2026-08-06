---
name: mnq-fee-is-150-per-round-trip
description: MNQ round-trip fee is $1.50 — verified from the live ledger; never let a harness default to $5.
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-01T14:20:51.014Z
---

**Venue truth: $1.50 per closed round trip.** All 487 closed trades in `data/gazbot7.db` carry `fees_usd = 1.50` exactly (`$1.21` per lot). Confirm from the ledger, never from a report.

On 2026-08-01 a NIPC acceptance replay used `FEE_RT = 5.0`, inherited from the greenfield lab's NIPC cell. It turned a **+$820 / $5.2-per-trade** result into **+$264 / $1.7**, and I reported the gate as "expected negative live" on that basis. The operator caught it. Corrected, days-green matched the lab exactly (9/12) and the lab-vs-replay gap fell from ~10× to ~3.7×.

**Why it bites so unevenly:** a fixed per-trade fee is a *regressive tax on thin-edge, high-frequency gates*. At ~$5.7 gross/trade, $5 eats 87% of the edge; $1.50 eats 26%. A gate taking 170 trades in 12 days for a few dollars each is destroyed by a fee error that a low-frequency gate would barely notice. So the same wrong constant can leave one analysis nearly unchanged and invert another.

**How to apply:** before trusting ANY sweep or replay, grep the harness for its fee constant and check it against the ledger. `grave_newsfade.py` / `grave_vacuum.py` use `1.5` correctly and note that the old `$5` was historically a stand-in for unmodelled stop slippage — that conflation is where the bad number comes from. Fee and slippage are separate: model the fee at $1.50 and slippage explicitly ([[shadow-sim-understates-losses]] — live losses run 1.1–3.1× modelled; real stops filled 7% worse than exact-level in the grind sweep). Related: [[execution-cost-autopsy-stage1]], [[friday-findings-need-adversarial-rederivation]].
