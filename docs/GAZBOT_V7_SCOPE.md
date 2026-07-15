# GAZBOT V7 — Scope & Charter

**Status:** Founding document. Written 2026-07-15. This is the charter for a
clean-room rewrite of the trading desk. It supersedes nothing yet — V5 keeps
running the live desk until V7 earns cutover (§14).

> **Thesis in one paragraph.** V5's only liabilities are its *code* — the
> multi-venue/multi-discipline generality, the per-contract routing, and the
> §274→§302→§303 patch archaeology that made today's incidents emergent and
> surprising. Its three real assets — the captured **data**, the hardened
> **IBKR knowledge** (which lives in incident scars, not in the tangle), and the
> **signal research** — all survive a rewrite untouched. V7 is therefore not a
> gamble on greenfield romance; it is a **radical simplification** that keeps
> every asset and deletes only the liability. One instrument (MNQ), one process,
> one clean DB, built correctly from the root causes we now understand.

---

## 1. Principles — the non-negotiables

1. **MNQ-only *live* path; instrument-agnostic *shadow/research* layer.** The
   thing that submits real orders — the order/fill engine, position, safety
   spine, live loop — is MNQ-only (that is where the simplicity + hardening win
   lives; no per-symbol routing, no venue routing, no discipline registry on the
   live path). But the **deciders are pure functions of market data**, so the
   **shadow desk and the analytics layer are instrument-agnostic** — they can
   trial strategies on **MGC** (or any captured instrument) without touching the
   live path. Multi-instrument breadth lives entirely in research/shadow, never
   in the live order path. (Operator 2026-07-15: "shadow desk can run shadow
   strategies on MGC too if we want.")
2. **One process.** The V5 broker↔strategy split + SSE event stream is the
   direct cause of the `OrderFilledV3` emission-gap class (today's incident).
   V7 is a **single process**: IBKR I/O, order/fill state, signals, and
   persistence in one address space. No cross-process fill emission, no
   replay-pending, no paired-restart rule. This one decision deletes an entire
   category of bug.
3. **Two-sided from the ground up.** Long and short are first-class and
   co-equal — not a mirror bolted onto a long-only core (the source of V5's
   `short_cap != sizing` bug). Asymmetry (e.g. the short squeeze-tail) is
   expressed in *data/params*, never in structural special-casing.
4. **1 or N contracts as one concept.** Position size is a single coherent
   quantity that the order state machine, the sizing rule, and the safety spine
   all agree on. There is exactly one place that decides "how many lots," and
   every other component reads it. No second cap that can silently disagree.
5. **Fresh, clean DB.** V7 writes its own database with a schema we actually
   like. V5's DB is archived read-only as the research/history moat (§6).
6. **Live desk + shadow desk share the SAME decider code.** Every gate/exit is a
   pure function; the live desk and the shadow sims call it *identically*. This
   structurally kills the V5 parity-drift class (equity vs crypto map drift,
   live-vs-shadow divergence).
7. **Honest by construction.** Sims price on ticks, always. Execution health is
   measured on **fills**, never submits/intents. P&L is net of fees on venue
   truth. These are not add-ons; they are how the primitives are built.
8. **Every scar is a test.** V5 is hardened because it survived ~a hundred
   incidents. V7 inherits that hardness as a **test suite** (§11), not as copied
   code. A capability isn't "ported" until its incident-scar is a red-then-green
   test.

---

## 2. The clean-room rule — NO copy-paste (this is load-bearing)

**Operator directive, verbatim intent (2026-07-15): "do not, and I repeat do
not, copy and paste code. I don't want anything inherited and we risk bringing
any old crud over."**

The method for porting a hardened capability *without* inheriting crud:

1. **Read the V5 implementation as a behavioural SPEC, not as source.** Open the
   handler *and its incident comments*. Extract: what must this survive? what are
   the edge cases it learned? Write those down as prose + tests.
2. **Close the file. Write the V7 version from the spec, from scratch,** in the
   V7 architecture, with V7 names and V7 types. Different structure by default —
   if the new code looks like the old code, you copied instead of re-deriving.
3. **Encode each learned edge case as a test first** (§11), then make it pass.
4. **Never `git show V5:… | paste`.** Never port a file. Never keep a legacy
   name "for continuity." The V5 tree is a reference library you *read*, and a
   git archive you *keep* — it is never a source of bytes for V7.

If you catch yourself typing a symbol/column/constant you didn't just re-derive
from the spec, stop — that's inheritance leaking in.

---

## 3. Scope — what V7 IS / IS NOT

**IS:**
- A single-process, MNQ-only futures desk on IBKR (paper first, real later).
- Two-sided (long + short), 1..N contracts.
- A **live desk** (submits real orders, MNQ only) and a **shadow desk** (N
  strategy variants scored on honest tick-repriced P&L; **MNQ + optionally MGC or
  any captured instrument**) running off the same feed.
- Its own clean DB; the V5 DB kept as a read-only research/history archive.
- The full **analytics/research stack** carried over as tech (§6.5): DuckDB,
  numpy, pandas, matplotlib — the tick-repricer, walk-forwards, sweeps, and
  edge-analysis tooling, re-derived fresh (never copied).

**IS NOT:**
- A multi-instrument, multi-venue, multi-discipline *live* desk. The live order
  path is MNQ only — no equity, no crypto, no EUREX/COMEX/CBOT routing. (Shadow
  strategies on other instruments are fine — they place no orders. A second
  *live* instrument is a V7.x decision made *then*, not generality baked in *now*.)
- A port. Nothing is copied (§2).
- A distributed system. One process.

---

## 4. Keep / Rebuild / Drop

| | Decision |
|---|---|
| **KEEP (read-only)** | The V5 **DB as an archive** — all history, ticks, depth, bars = the research moat. Read for backtests; never written by V7. |
| **KEEP (as spec, not code)** | The **IBKR incident knowledge** (naked spine, zombie re-entry, reconnect, venue-truth, partial-fill race) — re-expressed as V7 tests (§11). The **signal research** (thrust, reversal_grab, vol-bars) — re-expressed as pure deciders. |
| **REBUILD FRESH** | Everything that is code: IBKR I/O, order/fill state machine, position/reconcile, safety spine, signal+exit layer, desk loop, shadow desk, persistence, monitoring. |
| **DROP FOREVER** | Broker/strategy process split + SSE stream; per-contract routing; discipline registry; multi-venue; equity/crypto engines; the "brain"; the 82-HANDOVER doc system; §-patch archaeology; the alphabot/gazbot name split; every "is this reference live or dead?" ambiguity. |

---

## 5. Architecture — the layers (single process)

Stack stays **Python + `ib_async`** (the maintained ib_insync fork) — the win is
simplicity, not a new language. Async single event loop.

```
┌─────────────────────────────────────────────────────────────┐
│  gazbot7 (one process, one asyncio loop)                     │
│                                                              │
│  ib_gateway      →  connection mgmt, reconnect, subscription │
│                     re-assertion (the hardened primitive)    │
│  market_data     →  ticks + bars + L2 depth ingest → DB      │
│  order_engine    →  the fill/order STATE MACHINE (brick #1)  │
│  position        →  venue-truth position + reconcile         │
│  safety          →  native-trail coverage + naked guard      │
│  deciders/       →  PURE fns: entry gates + exits (shared    │
│                     by live + shadow, identical calls)       │
│  desk            →  the live loop: features → decide → size  │
│                     → submit → manage → close                │
│  shadow          →  N variants on the same feed, honest      │
│                     tick reprice, own tables                 │
│  monitor         →  exec health (fills-based), real-wedge    │
│                     vs benign detection, alarms/Telegram     │
│  store           →  the clean DB writer (idempotent)         │
└─────────────────────────────────────────────────────────────┘
```

Key property: **because it's one process, an order's fill updates position,
records the trade, and arms the trail in the same loop tick — atomically, with
no event to lose across a socket.** That is the structural fix for today's root
cause.

---

## 6. The DB boundary — fresh & clean; V5 as archive

- **V5 DB → archive.** `data/alphabot.db`, `ticks.db`, `depth.db` are frozen,
  copied to an archive path, kept read-only. All V5 history/gold stays queryable
  for research forever. V7 never writes them.
- **V7 DB → fresh.** New `gazbot7.db` (WAL). Capture streams (ticks/bars/depth)
  accumulate fresh from V7 go-live into V7's own store; research spanning the
  boundary reads *both* (V5 archive for the past, V7 for the present).
- **Clean core schema (illustrative — designed from V5's pain, not copied):**
  - `fills` — the immutable venue log. **Idempotent on `exec_id`** (unique). The
    one source of truth for what actually executed.
  - `orders` — intents + lifecycle status, keyed by a client order id we own.
  - `trades` — one row per closed round-trip, **assembled atomically** from
    fills, real `exit_reason` always, net-of-fees P&L. No `RECONSTRUCTED_BACKFILL`
    primary path — the backfill is a *reconciliation cross-check*, not the writer.
  - `positions` — venue-truth net position; **no legacy cached stop columns**
    (V5's `positions.stop_*` lie — they don't exist here).
  - `signals` — every fired signal + its exact outcome (submitted / blocked-why),
    fills-based, for honest through-rate.
  - `shadow_trades` + `shadow_real` — shadow sims + their tick-repriced P&L,
    with the R-target/scalp legs first-class (no V5 rtarget-leg blindness).
  - `exec_health` — the monitor's verdicts.
- **No masking flags.** V5's `reconciled_rows`/integrity-guard masking is a
  symptom of deferred recording. V7 records correctly, so nothing to mask.

### 6.5 Analytics & research stack — bring ALL the amazing tech (as toolchain, not code)

Operator 2026-07-15: "make sure we bring all our amazing tech over — DuckDB,
numpy, pandas etc." This is real V5 capability and it comes to V7 — as the
**toolchain and the patterns**, re-derived fresh (clean-room rule §2 still
holds: we adopt the libraries, we do not paste the scripts).

- **DuckDB** — the analytical layer over the DB + Parquet. Fast OLAP for
  research: reads the V7 store *and* the V5 archive (and Parquet dumps) in one
  query, so cross-boundary history "just works." The go-to for every sweep /
  cube / edge query.
- **numpy / pandas** — vectorized backtests, the faithful **tick-repricer**, the
  rapid **walk-forward** tooling, the vol-bar / reversal_grab sweeps we've been
  running. Re-expressed as clean V7 research modules.
- **matplotlib** (+ the report pipeline) — the charting for the Friday
  laboratory / edge reports.
- **Patterns kept:** honest tick-repricing, walk-forward validation, the
  edge-spectrum → confirm pipeline, capture health, resource throttling. These
  are *methods*, re-implemented; the discipline survives, the crud does not.
- **Boundary:** research/analytics is offline and read-only over data — it can
  read V5 archive + V7 live freely. It never writes the trading DB and never
  sits on the live order path, so it carries zero live-path risk. This is the
  one layer where breadth (DuckDB over everything, any instrument) is welcome.

---

## 7. Brick #1 — the order/fill state machine (the thing we do right)

This is the first and hardest brick, and the reason the rewrite is worth it. It
is designed directly from today's root cause.

**States (per order):** `PENDING → WORKING → (PARTIAL)* → FILLED | CANCELLED |
REJECTED`. **Per position round-trip:** `OPENING → OPEN → CLOSING → CLOSED`.

**The correctness invariants (each is a test in §11):**
1. **Idempotent on `exec_id`.** Every fill carries IBKR's `execId`. Applying the
   same fill twice is a no-op. Both the fast per-order path and any account-wide
   path can deliver it; the second is absorbed. (Kills the "exactly one observer,
   chosen by a race" fragility.)
2. **Partial-fill-aware pairing.** A close is not "done" until filled quantity
   reaches the position quantity. A `positionEvent(qty=0)` flat signal that
   arrives while only *part* of the exit is captured **waits for the remaining
   partials** (bounded timeout) rather than dropping to a backfill. (This is the
   exact 12:30 trade-5970 failure — designed out.)
3. **Atomic close-on-flat.** When venue confirms flat AND the exit fills are in
   hand, the `trades` row is written *now*, with the true exit price (already
   known from the fills) and the real `exit_reason`. Backfill-from-ledger exists
   only as a reconciliation *audit*, never as the primary writer.
4. **Reconnect re-asserts ALL subscriptions.** After any disconnect/1100, the
   engine re-subscribes fills/status for its *own live orders* (not just
   rehydrated open orders) before resuming. No silent post-reconnect gap.
5. **Zero naked at entry.** A newly-opened position arms its native protective
   trail in the same tick as the fill. A re-entry onto a just-flattened line
   books correctly (no "zombie" zeroed-row fall-through).
6. **Venue truth before any close/flatten.** Position sign/qty read from IBKR
   truth, never a cached book, before any reducing action.

**What this deletes vs V5:** the emission gap, the realtime-sync Fix1/Fix3
fallback, the dropped-trade-backfill-as-primary, the RECONSTRUCTED_BACKFILL
label, the false-CRIT auto-reboot cascade. None of it needs to exist because the
record is never lost in the first place.

---

## 8. Sizing — 1 or N contracts, one concept

- A single `target_size(signal, account)` rule returns the intended lot count
  (risk-bounded). The order engine opens exactly that; the safety spine protects
  exactly that; the short/long cap **is** that number — there is no second limit
  that can disagree (V5's `max_futures_short_contracts != MAX_CONTRACTS` bug is
  structurally impossible).
- N-lot exits handle partial fills natively (§7.2). Net position is the only
  position concept; no per-lot bracket bookkeeping.

---

## 9. Long / short — co-equal

- The decider returns a signed direction; the engine, sizing, and safety spine
  are direction-agnostic (sign-aware math, `abs(qty)` where needed).
- Short-specific *risk* (squeeze-tail) is handled by params/exits proven in the
  shadow desk (e.g. the reversal_grab short edge + flow filter we've been
  researching), never by structural long-only-with-a-mirror.

---

## 10. Live desk + shadow desk — shared deciders, honest reprice

- **One decider library**, pure functions: `entry_gates` (thrust, reversal_grab,
  …) and `exits` (native trail, scalp R-target, adverse/absorption cut). Live
  desk and shadow desk import and call the *same* functions — no parallel copies
  to drift.
- **Shadow desk** runs N configured variants on the live feed, records to
  `shadow_trades`, and a built-in tick-repricer scores honest `real_pnl` from
  day one (R-target/scalp legs first-class — no V5 rtarget blindness). This is
  where all research plugs in; promotion to live is evidence-gated.
- **Instrument-parameterised.** Because the deciders are pure functions of
  market data, a shadow variant is just `(decider, params, instrument)`. Default
  is MNQ, but a variant can run on **MGC** or any captured instrument — the
  shadow desk simply needs that instrument's feed captured. This gives us
  research breadth (test a gate on MGC) with **zero** additions to the MNQ-only
  live path (shadow places no orders).
- The reversal_grab / thrust / vol-bar work becomes V7 deciders directly.

---

## 11. The scars-as-tests catalog (hardened from day one, zero copy-paste)

Each row is a V5 incident. In V7 it is a **test written before the code**. This
is how we carry the hardness without carrying the code.

| Scar (V5 origin) | V7 test asserts |
|---|---|
| OrderFilledV3 partial-fill race (2026-07-15) | close waits for all exit partials before flat-completing; trade records real exit_reason, never backfill |
| Zombie re-entry (SELL onto zeroed row) | re-open onto a just-flattened line books the new position + arms its trail |
| Naked-at-entry (bracket stop cancelled ~5ms post-fill) | every open position carries a native trail within the same tick; naked → auto-reprotect + page |
| Venue-truth blindness (oversold into real shorts, book said flat) | sign/qty read from IBKR truth before any reducing action; cached book can't authorize a close |
| short_cap != sizing (silent long-only) | one size concept; a 2-lot short and 2-lot long are symmetric; no second cap |
| MKT ⟂ native trail (Error 328) | entry order type is compatible with the chosen stop; or a software trail is used — asserted, not discovered live |
| Reconnect drops OrderFilledV3 (04:37) | post-reconnect, own-order fill/status subscriptions re-asserted before resuming |
| Reconcile within seconds of a fill mints px=0 (MGC VCORR) | no synthetic zero-price execution ever reaches the trade record |
| 5s farm re-stick after gateway reboot | capture health distinguishes a real feed break from post-reboot re-subscribe; documented recovery |
| Monitor false-CRIT on benign backfill (2026-07-15) | exec health separates a real wedge (fills ceasing) from a benign partial-fill defer; no unnecessary reboot |
| Sims optimistic on 1-ATR fill / bar exits | reprice on ticks only; loss depth matches live |
| Flat-clock / session-flatten correctness | time-exits fire on the desk's own clock; EOD flatten has a no-open-window guard |

(Extend this table as V5's DECISIONS/incident history is mined — it is the V7
acceptance suite.)

---

## 12. Monitoring & safety — done right

- **Exec health on fills.** Through-rate = fills / fired-signals. A CRIT means
  *fills actually stopped*, distinguished from a benign partial-fill defer
  (today's conflation, designed out). Telegram on real CRIT only.
- **Naked guard.** Native trail on every position; a confirmed naked → reprotect
  + ungated page. One instrument makes this trivially auditable.
- **No auto-reboot cascade needed** — the emission gap doesn't exist, so the
  thing the reboot was healing doesn't occur. A genuine gateway wedge still has a
  documented single-bounce recovery, but it's rare, not routine.

---

## 13. Build sequence (the bricks, in order)

1. **Skeleton + DB store** — fresh schema, WAL, idempotent `fills` writer, tests.
2. **ib_gateway primitive** — connect, heartbeat, reconnect, subscription
   re-assertion. Prove against paper IBKR.
3. **Brick #1: order/fill state machine** (§7) — the whole scars-as-tests suite
   for fills/pairing/atomic-close green *before anything trades*.
4. **Position + reconcile** — venue truth; naked guard + native trail.
5. **Market data + capture** — ticks/bars/depth into the V7 DB.
6. **Decider library** — port thrust + reversal_grab as pure fns (from research,
   not V5 code); exits (trail, scalp R-target, cuts).
7. **Desk loop** — features → decide → size → submit → manage → close, MNQ,
   two-sided, 1..N.
8. **Shadow desk + tick repricer** — N variants, honest real_pnl.
9. **Monitor + Telegram** — fills-based health, real-wedge detection.
10. **Parallel-run harness** — V7 paper alongside V5 (§14).

---

## 14. Cutover plan — evidence-gated, never big-bang

- V5 **keeps running the live desk** throughout the build.
- V7 runs **paper, in parallel**, on the same IBKR paper account (or a second
  clientId), same feed. Both desks' trades are compared daily.
- V7 earns cutover when: it records every trade correctly (zero backfill), the
  scars-suite is green, its shadow reprice matches, and it has run clean through
  ≥ N sessions incl. reopen bursts (the exact condition that breaks V5 today).
- Cutover = point the live orders at V7, retire V5 to archive. Reversible: V5 is
  still there until we're sure.

---

## 15. Non-goals / explicitly deferred

- A second instrument (decide later, don't generalize now).
- Real-money trading (paper until the desk proves green + robust).
- A new language/framework (Python + ib_async; simplicity is the goal, not novelty).
- A dashboard rewrite (V7 exposes clean read APIs; the cockpit can follow).

---

## 16. Open decisions for Garrath

1. **Repo/paths:** fresh git repo at `/home/alphabot/gazbot7/`, V5 archive DB at
   `/home/alphabot/archive/v5/`. OK?
2. **Parallel-run account:** same paper account on a second clientId, or a
   separate paper account? (Second clientId is simplest.)
3. **Capture start:** V7 captures fresh from go-live (research reads V5 archive
   for the past). Confirm you're happy losing continuous-capture continuity at
   the boundary (the data isn't lost — it's in the archive — just split).
4. **First brick to build now:** the order/fill state machine (§7). Confirm and
   I'll write its detailed design doc + the scars-suite as the first work.
