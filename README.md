# GAZBOT V7

A clean-room rewrite of the trading desk. **MNQ-only live futures desk** (one
process, two-sided, 1..N contracts) + an **instrument-agnostic shadow desk** for
trialling strategies (MNQ, MGC, …). Fresh clean DB; the V5 desk's DB is kept as a
read-only research/history archive.

## Status
**Pre-D0.** This repo is scaffolded but the build has not started. V5
(`/home/alphabot/alphabot2`) remains the live desk until V7 earns cutover.

## The one rule that matters
**No code is copied from V5.** Ever. V5 is read as a *behavioural specification*
only — every hardened capability is re-derived from scratch here, and every V5
incident becomes a test written before the code. If V7 code looks like V5 code,
it was copied instead of re-derived. See `docs/GAZBOT_V7_SCOPE.md` §2.

## Read these first
- **`docs/GAZBOT_V7_SCOPE.md`** — the charter: principles, architecture, the DB
  boundary, the order/fill state machine (brick #1), the scars-as-tests catalog.
- **`docs/GAZBOT_V7_ROADMAP.md`** — the journey: 5 stages, the drop schedule
  (D0–D11), the gates.

## Approved decisions
- Repo: `/home/alphabot/gazbot7/`. V5 archive DB: `/home/alphabot/archive/v5/`.
- Parallel-run: same paper account, second clientId.
- Fresh capture from go-live; research reads the V5 archive for the past.
- First brick: the order/fill state machine (scope §7 / roadmap D3).

## Stack
Python + `ib_async`, single asyncio loop. DuckDB / numpy / pandas / matplotlib
for the analytics + research layer. One process — no broker/strategy split.
