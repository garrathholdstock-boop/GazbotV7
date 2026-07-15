# GAZBOT V7 — Build Roadmap & Drop Schedule

**Companion to `GAZBOT_V7_SCOPE.md`.** Written 2026-07-15. The stages, the drops,
and the gates. V5 keeps running the live desk the entire time; V7 earns cutover
on evidence (§Stage E), never a big-bang.

## Approved decisions (scope §16, operator 2026-07-15)
1. Fresh git repo at **`/home/alphabot/gazbot7/`**; V5 DB archived read-only at
   **`/home/alphabot/archive/v5/`**.
2. Parallel-run on the **same paper account, second clientId**.
3. **Fresh capture** from V7 go-live; research reads the V5 archive for the past.
4. **Brick #1 = the order/fill state machine.**

---

## The shape of the journey

Five stages, ~a dozen drops. The spine is front-loaded on purpose: we build the
*hardened, correct* IBKR + order layer FIRST (Stage B), because that's the whole
reason for the rewrite — everything else is simple once recording is bulletproof.
Nothing places a live-money order ever in this plan; paper throughout, real money
is a separate decision after cutover proves out.

```
A. Foundation      →  B. The hardened spine  →  C. The desk
   (repo, DB)          (IBKR, orders,            (capture, deciders,
                        position, safety)         live loop — trades paper)
                                                       ↓
                          E. Prove & cut over  ←  D. Research & watch
                          (parallel soak,          (shadow, repricer,
                           cutover)                 monitor, analytics)
```

---

## Ground rules — the per-drop discipline

Every drop is a **shippable, independently-verified increment**:
- **Definition of done** stated up front (contract); tests written *before* the
  code where a scar is involved (§11 of the scope).
- **Gate = verify end-to-end**, not just unit-green. A drop doesn't close until
  its gate is demonstrated (against paper IBKR where relevant).
- **Clean-room rule holds every drop** — V5 read as spec, never copied.
- No drop starts until the previous one's gate is green. Order matters: the spine
  must be correct before anything trades.

---

## The stages & drop schedule

★ = the load-bearing drop of its stage.

| Drop | Stage | Delivers | Effort | Gate (verify to close) |
|---|---|---|---|---|
| **D0** | A · Foundation | Fresh repo + toolchain (ib_async, pytest, ruff, DuckDB/numpy/pandas). DB **store**: clean schema, WAL, **idempotent `fills` writer**. V5 DB archived. | M | store round-trips; a dup `exec_id` is a no-op; CI + ruff green |
| **D1** | B · Spine | **IBKR primitive** — connect, heartbeat, reconnect w/ exponential backoff, **subscription re-assertion** on reconnect. Paper, read-only (account/positions). | M | survives a forced disconnect → reconnect with fill/status subs re-asserted (scar-test) |
| **D2** | B · Spine | **Order engine I** — order lifecycle (PENDING→WORKING→PARTIAL→FILLED/CANCELLED/REJECTED), submit/cancel on paper. | M | states track a real paper order correctly; cancel works; reject handled |
| **D3 ★** | B · Spine | **Order engine II — the recording state machine.** Partial-fill-aware pairing, atomic close-on-flat, `exec_id` idempotency. The §274-C race designed out. | **L** | full recording scars-suite green; a live **2-lot paper scalp records real-time, real exit_reason, ZERO backfill** |
| **D4** | B · Spine | **Position + safety** — venue-truth position + reconcile; native trail on every position; naked guard (reprotect + page); zombie re-entry fix. | M–L | naked / zombie / venue-truth scars green; every paper position carries a trail |
| **D5** | C · Desk | **Capture** — tick + bar + L2 depth ingest → V7 DB. Instrument-parameterised (MNQ live; MGC etc. capturable for shadow). | M | capture health green; MNQ 5s+tick+depth live; feed-break vs post-reboot distinguished |
| **D6** | C · Desk | **Deciders** — entry gates (thrust, reversal_grab) + exits (trail, scalp R-target, adverse/absorption cut) as **pure functions**, re-derived from the research. | M | unit tests vs known cases; identical output live-path and shadow-path |
| **D7** | C · Desk | **Live loop** — features → decide → size (1..N) → submit → manage → close. MNQ, two-sided. Paper. | M | trades paper end-to-end; sizing + long/short scars green (no cap-vs-size split) |
| **D8** | D · Research | **Shadow desk + tick repricer** — N variants (MNQ + MGC), honest `real_pnl` from day one, R-target/scalp legs first-class. | M | shadow reconciles; repricer matches; a reversal_grab variant runs + scores |
| **D9** | D · Research | **Monitor + analytics** — fills-based exec health, **real-wedge vs benign** detection, Telegram; DuckDB layer over V7 + V5 archive. | M | monitor CRITs only on a real wedge (fills ceasing), never a benign backfill |
| **D10 ★** | E · Prove | **Parallel-run + harden** — V7 paper (2nd clientId) beside V5; daily trade comparison; run through the reopen bursts that break V5. | **L (soak)** | V7 records every trade correctly (zero backfill) + shadow matches, clean through **≥ N sessions incl. reopen bursts** |
| **D11** | E · Cut over | **Cutover** — point live orders at V7; retire V5 to archive. Reversible. | S | operator sign-off; V7 is the live desk |

---

## Timeline framing (effort, not promises)

- **Build (D0–D9):** roughly **3–5 weeks** of focused work. D3 (recording state
  machine) and D4 (safety) are the long poles — that's deliberate; get the spine
  right and the rest assembles fast.
- **Soak (D10):** calendar-bound, **~1–2 weeks** — it needs real paper sessions,
  including the Globex-reopen bursts that expose the exact V5 failure. Can't be
  rushed; that's the point.
- **Cutover (D11):** fast once the soak gate is green.
- **Net: ~5–7 weeks to cutover** if built steadily — dominated by the spine build
  + the soak, not by volume of code (there's little of it, that's the win).
- **Re: the "green by end of August" north-star** — the rewrite is a deliberate
  detour. V7 makes the desk *legible and correct* so the green comes from a desk
  we understand, not a patched one. If the schedule holds, cutover lands ~late
  Aug and the green-hunt resumes on clean ground. Flagging the tension honestly;
  your call already made it.

---

## Parallel tracks (what happens to V5 + the research meanwhile)

- **V5 = the live desk, frozen.** It keeps trading MNQ throughout. No new feature
  work on it — only safety fixes if something breaks. The auto-reboot + backfill
  net keep it stable (as they did today).
- **Research pauses on V5, resumes in V7 shadow at D8.** The reversal_grab / vol-bar
  findings are captured; rather than double-build them on V5, they become V7
  deciders (D6) and get forward-tested honestly in V7's shadow (D8) — where the
  repricer is correct from day one. Net: no wasted work.

---

## The gates that actually matter (don't skip)

1. **D3 gate** — a 2-lot paper scalp records real-time with zero backfill. This
   is the whole thesis of the rewrite proven in one test. If this isn't green,
   nothing downstream matters.
2. **D4 gate** — every position always carries a native trail; naked → reprotect.
   The zero-naked guarantee, structurally.
3. **D10 gate** — zero-backfill through real reopen bursts. This is the exact
   condition V5 fails today; V7 must pass it before it touches the live orders.

---

## Explicitly NOT in this journey
- Real-money trading (separate decision, post-cutover).
- A second live instrument (V7.x, decided then).
- A dashboard rewrite (V7 exposes clean read APIs; cockpit follows later).
- Any V5 code copied (clean-room, every drop).

---

## Immediate next step
Write the **D3 detailed design doc** — the order/fill state machine's states,
transitions, `exec_id` idempotency, partial-fill pairing algorithm, and the full
scars-suite as executable acceptance tests. That's brick #1's blueprint, and it's
where the build starts.
