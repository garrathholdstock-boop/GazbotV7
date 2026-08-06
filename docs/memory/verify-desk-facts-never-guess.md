---
name: verify-desk-facts-never-guess
description: "Operator rule: never state a desk fact from memory/stale read — curl/query live first; intraday P&L is a moving snapshot, not 'the day'"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d7443f59-d3b4-466f-b7e6-3903cacfd274
---

**Operator, 2026-07-10 (sharp):** "why are you guessing sometimes? we have a rule against it. it's a waste of time." Triggered by me repeating "the live desk won today by fading the descent with shorts" — a ~09:00 UTC snapshot I never re-verified. By the time the operator checked, a −$57 MNQ short (09:13) had flipped it: full-day was **LONG +$41 (100% win) / SHORT −$19 (81% win, sunk by 2 fat losers)** — longs won, shorts lost. My claim was true at the time but I let a stale narrative stand as current fact.

**Why:** stating unverified/stale desk facts as current truth wastes the operator's time and erodes trust — it's the exact failure the no-guessing rule exists to stop. Intraday P&L especially is a MOVING number.

**How to apply:**
1. Any live-desk fact (P&L, side-attribution, positions, win%) → fresh curl/canonical query FIRST (`desk_pnl.CANONICAL_DESK_WHERE`, `/api/futures/performance` header at `d['header']['today']` — see [[futures-performance-header-parse]]). Never recite from an earlier read.
2. Intraday numbers are a SNAPSHOT — label with a timestamp, never call it "the day" until the session closes.
3. If I don't have the data in hand, say "let me check" and go get it — don't reconstruct from memory and present as fact.
4. Catching my own bug and redoing it (e.g. a wrong-epoch filter) is the RIGHT behavior; the failure mode is asserting without re-checking.

Ties [[sims-on-tick-price]], [[shadow-sim-understates-losses]] (the same verify-don't-assume discipline).
