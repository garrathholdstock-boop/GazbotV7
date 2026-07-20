# GAZBOT V7 — Multi-Slot Paper Tournament (scope, NOT built)

**Status:** SCOPED 2026-07-20. NOT built. A significant core refactor — reverses
V7's single-position simplification — so it gets its own build with full rigor and a
phased rollout. Owner: core + a new tournament controller.

---

## 1. Why (the operator's insight, backed by today's audit)

The shadow board is **structurally too optimistic** — the 2026-07-20 audit measured
shadow-grind at **~$460/day above achievable-live**, from three idealizations paper
does not have: it ignores the single-position constraint (2.2× the trades), enters at
hindsight-clean bar-closes (~5pt better), and takes trades against the tape a real
desk refuses (25/47 grind trades, net −$67). The shadow overstated grind so badly it
**disagreed in sign** with the live desk (+$46 vs −$418, same day).

Operator conclusion (verbatim): *"we use paper trading as our shadow desk. shadow is
far too optimistic. lets just put all the gates we like into paper. its far more
realistic."* And the account solution: *"you dont need multiple paper accounts — lift
max total contract holdings to 6, 1 per gate, 6 max gates at a time. best ones from
shadow get promoted and worst couple from paper get canned."*

**The model:** the paper account becomes a **6-slot, multi-position tournament** of
gates on **real fills**. Shadow = the cheap feeder (nominates). Paper = the judge
(relegates). Real money stays a later rung.

## 2. The design

- **One paper account**, position cap lifted to **N (≈6)** contracts total.
- **N gate slots**, each holding its **own 1 lot**, running **concurrently** (NOT
  first-to-fire — that's the current single-position desk; this replaces it).
- Each slot: its own entry (its gate), its own exit stack (stop / chandelier /
  give-back / 2R per the gate), its own 1-ATR stop, its own risk.
- **Pipeline:**
  - **Tier 1 — shadow** (unchanged, cheap): many gates, free, optimistic. Its job
    shrinks to *nominate* candidates. Its **dollars are no longer trusted**.
  - **Tier 2 — paper tournament** (this doc): N slots on real fills. **Promote** the
    shadow's best into an open slot; **relegate** paper's worst-2 over a rolling
    window. This tier is the truth.
  - Real money: separate, later, a sizing decision — not part of this.

## 3. ★ The central challenge — per-gate attribution over a NETTED venue

**This is the hard part, and it's exactly what V7's single-position design was built
to avoid.** IBKR nets position **per contract, per account** — not per gate, and NOT
per clientId (multiple API clients on one account share the same netted MNQ position).
So if 3 gate slots each hold 1 MNQ long and 1 holds a short, the venue shows **net +2
MNQ** and has no idea which lot belongs to which gate.

Everything downstream inherits this:
- **P&L attribution** — each gate's realized P&L must be computed from the entry/exit
  prices the *desk* assigns to that gate's lot (a logical sub-ledger), because the
  venue only knows the net. This is the V5 attribution nightmare V7 deleted; it comes
  back here.
- **Stops** — each slot wants its own 1-ATR stop, but an IBKR stop reduces the *net*.
  When a stop fills, **which slot did it close?** The desk must attribute it (by stop
  coid → slot). Feasible but must be exact (a mis-attribution corrupts a gate's score).
- **Naked / coverage** — "every position covered by a stop" becomes "the **net**
  position is covered by the **sum** of the slots' stops," AND each slot's logical lot
  has its own stop. Aggregate coverage ≠ per-slot coverage; the auditor needs both.
- **Fills** — a single MNQ fill could satisfy two slots' orders; fills must be routed
  to the slot whose order (coid) they belong to (the engine keys on order_id, so this
  is tractable — but the tracker/position layer must fan out per slot).

**Design decision required (operator input):**
- **(A) Full logical sub-ledger** — a `SlotBook` per gate (side/qty/entry/stop/peak),
  each fill/stop attributed by coid; the venue net is a *cross-check* only (`sum of
  slot qtys == venue net`, else DRIFT → halt, like today's reconcile). Most faithful,
  most work, the V5-attribution-class risk.
- **(B) Constrain to avoid opposing lots** — e.g. all slots same-side-only, or block a
  slot whose fill would net against another. Simpler netting, but distorts the test
  (rgv-long + grind-short must both be allowed to be honest).
- **Recommended: (A)**, because the whole point is *honest* per-gate P&L; (B) changes
  what's measured. But (A) is where the effort and the bug risk concentrate.

## 4. Per-slot safety spine (the today's-bug-class, ×N)

Every hardening we shipped **today** was single-position; each must go **per-slot**:
- one-position guard → **per-gate** guard (a gate already holding won't re-open; a slot
  is free or occupied).
- naked-watchdog / arm-time stop-confirm → per slot's stop (over the netted book).
- **qty under-count** (partial-fill sync) → per slot (a slot's multi-lot... though slots
  are 1 lot, so simpler — but the attribution of a partial across slots is new).
- **wedge-breaker** (stuck-exit re-fire) → per slot.
- **give-back / risk-sizing / capped-limit** → per slot (capped-limit + coid seeding
  already help; they're inherited).

**Reality check:** running N slots means each of today's incident classes (naked lot,
stuck exit, drift) can fire on any slot independently. This refactor needs the same
day-of-rigor we just spent, **per slot** — that is the cost, stated plainly.

## 5. The tournament controller (promotion / relegation)

A new controller (cron or in-loop) that:
- **Promotes** a shadow-leading gate into a free/relegated slot after it leads the
  shadow board for a **promotion window** (operator: how long?).
- **Relegates** the paper tournament's **worst-2** over a **rolling window** (operator:
  metric — net P&L? Sharpe? per-trade EV? — and window — days?).
- Hysteresis so a gate isn't promoted/relegated on a blip (the governor churn lesson).
- Writes the slate + each slot's live paper P&L to a surface (`/v7/` tournament tab).

## 6. Open questions for the operator (decide before build)

1. **Attribution model** — (A) full sub-ledger [recommended] vs (B) constrained. §3.
2. **Relegation metric + window** — worst-2 by *what*, over how many days.
3. **Promotion cadence** — how long a shadow gate must lead to earn a slot.
4. **N** — 6 slots? and the total-contract cap = N.
5. **Sizing separation** — confirm the tournament is a *ranking* rig (1 lot/gate); real-
   money size is a separate later decision, not derived from tournament exposure.
6. **Does this REPLACE the current two-gate live desk, or run alongside it?** (The
   current grind+rgv single-position desk would presumably become 2 of the N slots.)

## 7. Risks

- **Reverses V7's single-position simplification** — the deliberate hardening choice
  (MNQ-only, one position) that made the safety spine tractable. This is the single
  biggest architectural decision in the doc; it re-admits the multi-strategy-one-
  instrument attribution complexity by design.
- **6× exposure** on the paper account (fine for paper; note it's not the real-money
  risk profile).
- **Attribution bugs corrupt the very scores the tournament exists to produce** — a
  mis-attributed stop makes a good gate look bad or vice-versa. The cross-check
  (`sum slots == venue net`) is load-bearing.

## 8. Test plan (before any live paper run)

- SlotBook attribution: fills/stops routed to the right slot by coid; `sum == net`.
- Two slots, opposing sides → venue nets correctly, each slot's P&L is independent.
- A stop fill on a netted book attributes to the correct slot; the other slot untouched.
- Each per-slot safety mechanism (naked/wedge/give-back/qty) fires independently.
- Reconcile DRIFT when `sum slots != venue net` → halt (mirrors today's single-pos guard).
- Controller: promotion after window; relegation of worst-2; hysteresis (no churn).

## 9. Phased rollout

1. Build the SlotBook + per-slot safety over the netted book; test hard (§8).
2. Run **2 slots** (the current grind + rgv) in multi-position paper — prove the
   attribution + safety before adding slots. Compare to the single-position desk.
3. Widen to N slots; wire the shadow→promote and paper→relegate controller.
4. The shadow board demotes to feeder; its dollars stop being quoted as achievable.

## References
Audit: SESSIONS 2026-07-20 (shadow-grind +$460/day over live; opposite sign).
Single-position rationale: `GAZBOT_V7_SCOPE.md §1`. The attribution class V7 deleted:
alphabot2 memory `projector-conid-dedup-scope`, `futures-trade-multiplier-recording`.
Inherited guards: `CAPPED_MARKETABLE_LIMIT_ENTRIES.md`, `RISK_BOUNDED_SIZING.md`,
`GIVEBACK_EXIT_SCOPE.md`, `EXIT_WEDGE_BREAKER_SCOPE.md`.
