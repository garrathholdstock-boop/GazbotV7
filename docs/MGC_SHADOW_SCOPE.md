# MGC SHADOW SERVICE — SCOPE

**Operator, 2026-08-15:** *"start building the MGC shadow service. from scratch. scope it
thoroughly. its only 2 gates."*

He is right that it is only two gates. The gates are the small part. Everything below exists because
the shadow book was built single-symbol, single-multiplier and price-only, and gold breaks all three
assumptions — three of them **silently**.

---

## 1. WHAT WE ARE BUILDING

Two gates, both from `gf_MGC` (2026-08-15), both **shadow only, never live**:

| cell | trigger | n | net (true $7.50/RT) | $/trade | win | OOS Jul | placebo |
|---|---|---:|---:|---:|---:|---|---|
| `mgc_hole_break_fade` **LONG** | 60m level break **DOWN** into a liquidity hole → **buy** | 72 | +$1,387 | +$19.27 | 63.9% | +$1,046 ✔ | 0/30 ✔ |
| `mgc_hole_break_fade` **SHORT** | 60m level break **UP** into a liquidity hole → **sell** | 85 | +$1,261 | +$14.84 | 64.7% | +$426 ✔ | 0/30 ✔ |

**Mechanism.** The break has already chosen the side. The book is asked only whether that side will
**hold** — a liquidity question, which is the one thing a book genuinely knows. This is *not* the
refuted L2 attack, which asked the book for direction and flipped sign across five disjoint samples.

Causal definitions, from the **last depth snapshot at or before the entry stamp, never the next**:

- `obstacle` — lots resting within 1.0pt **beyond** the level, in the break's path
- `support`  — lots resting within 1.0pt **behind** the level, to catch a failure
- **VACUUM** (`obstacle == 0`, 49% of breaks) → **FADE**  · +$12.47/trade
- **WALL** (`obstacle > support`, 14%) → **FOLLOW** · +$11.84/trade
- neither (37%) → **trade nothing.** Both directions lose here; this is a real finding, not a gap.

**Exit: wide chandelier, SINGLE LOT.** Not the tight scalp (negative at 1R on both survivors), not
the dual slot (Lot A cancels Lot B), not a time cap. **This is the opposite of the live MNQ slot
configuration** and is the most actionable structural finding in the gold work.

### Explicitly NOT in scope
- No live promotion. No `gate_switches.env` entry. No router wiring.
- Not the MGC day rider (parked — survives the cost correction at +$1,646, but 8 fired days).
- Not the coil bouncer — but it is **not dead either, and I said it was.** At the wrong $7.50 it
  showed −$454; at the true $4.50 it is **+$8.42, +$0.05/trade, median +$4.75**. Breakeven, on the
  line. Out of scope here because breakeven is not a shadow arm, **not** because it was refuted.
- No new IBKR depth subscription — see §3.

---

## 2. THE FOUR BLOCKERS, AND THE DECISION ON EACH

Confirmed in the live code today, not inferred:

| # | blocker | evidence | fails how | decision |
|---|---|---|---|---|
| 1 | no `level_break` gate kind | `shadow.py:232-246` dispatches 6 kinds, ends `else: e = None` | **SILENT** — variant records nothing, forever, no error | add a `level_break` branch |
| 2 | the sim never sees a book | `on_bars(bars, tape_net, window_price_delta, in_rth, now_ms, cap)` carries no depth | loud (TypeError) if attempted | pass a `book` dict, sourced from `depth.db` |
| 3 | single-symbol | `shadow.py:789` `if body.get("symbol") != cfg.symbol: continue` | **SILENT** — an MGC variant on the MNQ slate sees no gold bar and records nothing | separate process instance, `cfg.symbol="MGC"` |
| 4 | `value_per_point` is per-INSTANCE | `reprice_pending(store, cap, value_per_point=cfg.value_per_point, ...)` reprices **every** unprocessed trade with ONE multiplier | **SILENT AND WORST** — gold repriced at MNQ's $2 not $10, fee $1.50 not $7.50; a RACE between two services, so it is intermittent | **separate store** — see §4 |

★ Three of four fail silently. That is the whole reason this document exists: the failure mode of a
half-built MGC shadow is not a crash, it is **an armed variant with zero trades, or a full book of
gold trades priced at a fifth of reality**, discovered weeks later.

---

## 3. DATA — WHAT FEEDS IT

| need | source | note |
|---|---|---|
| MGC 1-min bars | the **`md` stream**, `T_BAR`, tagged `body["symbol"]=="MGC"` | already published — `md` has been multi-symbol since 2026-08-04. Only the shadow filter drops it. |
| MGC L2 depth | **`data/depth.db` → `depth_snap`**, 10 levels, 250ms sample | 3.4M MGC rows, 2026-07-19 → current. Written by `gazbot7-depth-capture`. |

★ **There is no free IBKR depth subscription.** All three are in use (`depth-capture` = MNQ + MGC,
`md` = MNQ). So the service **reads `depth.db`; it must not subscribe.** That is a hard constraint,
not a preference.

⚠ `depth.db` is a **250ms sample**, while `capture.db.book` is 41ms event-driven — and `capture.db`
has **no MGC depth at all**. So gold's book is coarser than MNQ's by design. The gate's own lab flags
the consequence: in a liquidity hole — *precisely the state this gate selects for* — the touch may be
further away than the last sample said. **That is the single most likely way this degrades in live
shadow, and it is why it goes to shadow rather than live.**

---

## 4. ARCHITECTURE — THE ONE REAL DECISION

**Separate service instance + separate store.**

```
gazbot7-shadow.service        symbol=MNQ  vpp=$2.00   fee=$1.50/RT  →  data/shadow.db
gazbot7-shadow-mgc.service    symbol=MGC  vpp=$10.00  fee=$7.50/RT  →  data/shadow_mgc.db
```

**Why a separate store and not a symbol column** — `shadow_trades` *has* a `symbol` column, so
sharing looks tempting. It is a trap: `reprice_pending` reprices **every** trade not yet in
`shadow_real` using the multiplier of **whichever service calls it first**. Two services on one
store means gold is intermittently priced at $2 and MNQ intermittently at $10, silently, depending on
scheduling. Symbol-scoping the repricer would mean changing shared code on the live MNQ path to fix a
problem gold created. A separate store makes the failure **structurally impossible** and touches no
live code.

Cost: the promotion board and `sim_registry` read `shadow.db` only, so MGC will not appear on the
dashboard until a later, deliberate step. That is a display gap, not a correctness one, and it is the
right trade.

⚠ **The fee is $4.50/RT from mid, not $7.50 and not $1.50.** *(Corrected 2026-08-15, audit #9 — the
line below previously read $7.50 and was wrong.)* Gold crosses on both legs, but a round trip pays
the 0.30pt spread **once**: 0.15pt above mid going in, 0.15pt below mid coming out = $3.00, plus
$1.50 commission. Writing `0.30 × 2 × $10` counts the spread twice. The **lab never made this
error** — its own note reads *"MGC's spread is a flat ~0.30pt = $3.00"* and its `true_pnl` crosses
real fills then subtracts commission only, so **+$1,387 / +$1,261 stand unchanged**.

⚠ **`REPRICER_FEE_RT` stays $1.50** and is not the same constant. The repricer already fills at the
far touch on both legs, so the spread is inside `gross` before any fee is applied; charging $4.50 on
top would double it again. $4.50 is for a harness that prices from the MID and must add the spread
itself. **Never copy MNQ's `fee_rt` into an MGC config that prices from mid.**

---

## 5. BUILD PHASES — each with the check that proves it

| # | phase | done when |
|---|---|---|
| 1 | `gate_level_break` decider (pure) + `obstacle`/`support` from a book dict | unit tests: VACUUM fades, WALL follows, "neither" returns None, missing book → **None (fail closed)** |
| 2 | `book_at(ts)` reader over `depth.db` — last snapshot **at or before** the stamp | test: never returns a FUTURE snapshot; returns None on a gap rather than the next row |
| 3 | `on_bars(..., book=...)` + a `level_break` branch in `_entry` | test: a variant with kind `level_break` actually FIRES (the §2 blocker-1 guard) |
| 4 | `gazbot7-shadow-mgc.service` — own store, `symbol=MGC`, vpp 10.0, repricer fee 1.50 | starts, folds MGC bars, writes to `shadow_mgc.db`, and **writes nothing to `shadow.db`** |
| 5 | the two variants on an MGC slate | after one session: non-zero trades, and repriced P&L present |
| 6 | registry + board | `sim_registry` learns `shadow_mgc.db`; dashboard later |

**Phase 5 is the one that must not be skipped.** "Armed" is not "recording" — the whole point of §2
is that three of the four blockers produce an armed variant that silently records nothing. The
acceptance test is **trades in the table after a live session**, not a clean start-up.

---

## 6. FAILURE MODES TO WATCH, in order of nastiness

1. **Gold repriced at $2/pt** — 5× overstatement, silent. Prevented structurally by §4.
2. **Armed but recording nothing** — the three silent blockers. Caught only by phase 5.
3. **Book read from the future** — using the snapshot *after* the entry stamp is a look-ahead that
   would flatter exactly the feature this gate trades on. Phase 2's test exists for this.
4. **`depth.db` gaps** — the reader must return `None` and the gate must fail closed, never reach for
   the nearest row.
5. **Fee wrong in EITHER direction** — $1.50 where mid-pricing needs $4.50 flatters a gate by
   $3.00/trade; $4.50 where the repricer already crossed charges it twice and buries one. The
   $7.50 error did the second, and it is what made me call the coil bouncer dead.

---

## 7. HONEST STATE

Both gates are **shadow candidates on a 15-session book**, passing strip-3, leave-one-day-out, a July
OOS leg and a 0/30 placebo — genuinely better evidenced than anything gold has produced before, and
still not proof. The operator's standing rule applies: *thin n is a SHADOW ARM, never a kill and
never a live promotion.* The goal is weeks of forward recording, not a promotion decision.


---

## 8. AUDIT #8 — THE LAB AND PRODUCTION DO NOT READ THE SAME TAPE (open, and it is not closed by this)

The lab built its 1-minute OHLC from the **depth mid** (`minute_bars(q, col="mid")`, a resample of
the 250ms quote book). The live shadow folds **md's trade bars**. Gold prints sporadically, so the
mid tape has **29,565 minutes to the trade tape's 13,440** over 2026-07-16 → 08-14 — and a 60-minute
extreme taken from one is not the 60-minute extreme of the other.

Measured (`scripts/gf_mgc_barsource.py`), same window, same 250ms race, same cost:

| | fires | in both |
|---|---:|---:|
| depth-mid (lab) | 1,588 | 644 |
| md trade bars (production) | 724 | 644 |

**Only 41% of the lab's fires exist on production's tape**, though 89% of production's were in the
lab's set — production is close to a *subset*, not a different gate. At the shipped 45-minute
cooldown the surviving subset is the **better** half: n=158 at **+$6.16/trade** against −$3.88 for
the fires only the mid tape sees, and n=158 sits right on the lab's shipped n=157.

⚠ **Two things stop this being an all-clear, and both matter more than the headline.**
1. **The sign flips without the cooldown.** Un-cooled, the same comparison says production is the
   *worse* half (−$3.51/tr vs the mid tape's +$0.20). A conclusion that inverts on one parameter is
   not a robust conclusion.
2. **This harness does not reproduce the report's magnitude** — +$276 on mid bars where the report
   has +$2,648. It is a faithful *contrast* (one rule, two inputs, everything else held) but its
   *levels* are not the report's, so do not quote them as the gate's expectancy.

**Decision: production stays on md trade bars.** They are its natural input and the shipped-config
evidence does not argue against them. But **the +$1,387 / +$1,261 headline is a depth-mid number and
is NOT production's forward expectation.** The shadow's job is to produce the trade-bar number
honestly over weeks. Until it has, treat the gold cells as unquantified in the direction that
matters.
