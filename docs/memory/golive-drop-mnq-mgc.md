---
name: golive-drop-mnq-mgc
description: "At real-cash go-live (~$30k), drop MNQ + MGC from the live-traded futures set — margins too big"
metadata: 
  node_type: memory
  type: project
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

On the ~$30k starting balance, live IBKR **initial margins** make **MNQ (~$5.6k)** and
**MGC (~$4.0k)** too large an outlay — one of each is ~32% of the account, too concentrated
under the 10-contract aggregate cap.

**At go-live: DROP `mnq` + `mgc` from `ACTIVE_CONTRACTS`** (keep them in paper/observation),
then RE-ADD as the balance grows. MNQ is one of the strongest edges — this is a *capital
constraint, not an edge call*.

**Why:** real margins (via the broker `/margin/futures` whatIf endpoint) came in well above
textbook estimates — MNQ $5,644, MGC $4,064, MES $2,895.

**How to apply:** the constraint is also flagged in `us_futures_desk.py` above
`ACTIVE_CONTRACTS`. Operator idea (2026-06-14): once multi-week data confirms which contracts
are most profitable, build a **margin-aware contract-priority cap** that auto-favours the best
$/margin contracts and holds others out — rather than a manual drop. [[courtroom-vs-live-signal-mismatch]]
