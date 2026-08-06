---
name: desk-l2-book-consumption-scope
description: "Scope to wire the ALREADY-LIVE L2 book into the desk's decision loop (exit cut + pre-entry veto)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3c5e04a7-ccf2-4bdb-be9b-60270fb55691
  modified: 2026-08-04T11:37:10.826Z
---

2026-07-13 operator push-back: "is aggressor tape as useful as the book? the desk needs to read L2 live — otherwise what's the point." Honest answer: NO — tape is executed/backward-looking, the book is resting/forward-looking; absorption is a BOOK event, and only the book enables a PRE-ENTRY veto (see the wall before you thrust into it). The tape-only absorption cut [[golive-shadow-momentum-to-paper]] was a same-day proxy, not equal.

**Key unlock — this is a CONSUMPTION problem, not data acquisition.** `alphabot-depth-capture` (clientId 97, `reqMktDepth` 10-level, isolated, WAL) already writes `data/depth.db` LIVE on MNQ/MES/MGC — the exact 3 traded contracts — ~1s fresh, ~4/sec. The desk just doesn't read it yet. A latest-book read = 0.010ms.

**Decision:** DB-poll `depth.db?mode=ro` each cycle (Option A) = MVP — identical idiom to `_recent_mids`/`_recent_tape`; free, WAL-concurrent, preserves feed isolation (no IBKR depth-line contention). In-process `reqMktDepth` subscription (Option B) is Phase 4, only if snapshot granularity proves the ceiling. New reader `_recent_book()` with a STALENESS GUARD (>5s → None → degrade-safe, never forces/blocks a trade).

**ONE consumer (operator 2026-07-13 narrowed it): book-aware absorption CUT only.** `FUT_ABSORPTION_CUT_USE_BOOK` layered on the existing tape cut — refilling opposing wall + adverse multi-level imbalance; precedence book(fresh)→tape→no-fire. **Entry veto DROPPED** — operator: "we are not doing the entry veto, you told me it doesn't work" (pre-entry study: book/tape don't separate winners/losers before entry).

**Cadence — CONFIRMED Option ②:** leave the 5s exit runner alone (`_CADENCE_SECONDS=5`; ratchets/chandelier/flat-clock don't need speed), give the CUT its own dedicated ~1s loop (cadence a knob, default 1s) reusing the `submit_market_exit` choke point (resubmit-guard prevents double-submit with the 5s spine). Operator initially thought the runner was already 1s; agreed faster helps the reactive cut but not the rest, so ② not ① (don't 5× the whole spine). Depth feed 0.25s → 1s clean; staleness guard 2s.

**M2K — OUT** (operator: "leave M2K out, i don't have the market data"). Scope = MNQ/MES/MGC only.

**Phase 3 (book-aware cut) BUILT then RIPPED OUT 2026-07-13 — DEAD END.** Evidence (all 57 live trades, `book_vs_tape_vs_actual.py`): tape cut on every trade = +$176, book-gated = −$18 (−$194 worse). Root cause: the absorption is HIDDEN iceberg-refill (sold ~175 contracts/60s into a visible bid of ~4, price didn't move) — the top-10 depth SNAPSHOT can't see it, so L2-imbalance/wall-size confirmation only SUPPRESSED good tape cuts. **TAPE is the right absorption signal** (flow-absorbed-no-price-move). Both the pre-entry veto AND this exit confirmation died to the same finding: aggregate L2 doesn't separate. ⚠ DON'T re-propose book-confirming the cut. **Phase 2 fast loop KEPT** (flag-OFF, tape-only): `FUT_ABSORPTION_CUT_FAST_LOOP_ENABLED` — ~1s task via `FuturesRunner.evaluate_absorption_cut`, cuts via submit_market_exit, 5s spine backstop. NB the tape cut is LIVE at 5s (fired MNQ -$63.5 today), armed via `FUT_ABSORPTION_CUT_ENABLED`.

**Phase 1 BUILT 2026-07-13** (PAPER, no decision wiring): `alphabot/shared/book_features.py` = `BookSnapshot` + pure features (multi-level depth_imbalance, microprice/tilt, opposing_wall=biggest resting level on the side we consume, near_consumed_size, directional) + `read_latest_book()` degrade-safe reader w/ 2s staleness guard (stale/absent/corrupt→None, never forces/blocks a trade). 16 pins `tests/test_book_features.py`. `scripts/absorption_observe.py` now logs the full book vector (book_imb1/10, micro_tilt, opp_wall_size/dist, near_size, book_spread, book_age_s) — needs `sys.path.insert('/home/alphabot/alphabot2')` to import alphabot as a script. NEXT: Phase 2 = dedicated ~1s cut loop on tape cut; Phase 3 = book-aware (`FUT_ABSORPTION_CUT_USE_BOOK`), observe, arm on evidence.

Full scope: `docs/DESK_L2_BOOK_CONSUMPTION_SCOPE.md`.

**★2026-08-04 CAPTURE MOVED INTO V7** (operator: "move the book capture into v7 so we can use it").
Now `gazbot7-depth-capture.service` → `gazbot7/data/depth.db`, `scripts/depth_capture.py`, in
`gazbot7.slice`, swept by `sweep.py` (service in `_SOFT_SERVICES` + an L2 **freshness** check on the
data, because an active unit is not proof of capture — cf. [[router-full-roster-pin-is-silent-noop]]).
The 20 days of V5 history was MOVED not copied (same fs, no extra disk): 9.46M rows preserved.
Changes: **MNQ ONLY** (operator: "we dont need anything but mnq" — the V5 unit asked for 4 symbols and
IBKR refused the 4th with `Error 309: max 3 market depth requests`, which is why M2K silently died on
07-29); `FLUSH_S` 5.0→1.0 because a live read was up to 5s stale by design and `cl_sims.book_snapshot()`
now reads it at signal time (measured age after: **~0.9s**, was ~5s). Old `alphabot-depth-capture`
stopped + disabled — two writers on clientId 97 would fight.

**★ WHY I FAILED TO FIND THIS: I told the operator we did not persist the book at all.** We had 4.2M
MNQ snapshots. Two causes, both mine: the data lived in the tree CLAUDE.md says never to probe (I read
"alphabot2 is retired" as "alphabot2 has nothing"), and `cl_sims.build_ctx` carried a **deliberate**
exclusion whose stated reason was arithmetically wrong — "~86 contracts visible vs ~2,664/min flow, 6x
too thin". Measured: **162 contracts vs ~170/min**, i.e. the book is ~57 SECONDS of flow. The claim
also compared a *stock* of resting liquidity against a *flow rate*. Conclusion inverted; now deleted.

**⚠ BUT THE 07-13 DEAD-END ABOVE STILL STANDS — and it is the strongest objection on file.** Aggregate
L2 did NOT separate winners from losers, on all 57 live trades, because the absorption that matters is
HIDDEN iceberg refill (~175 contracts/60s absorbed into a visible bid of ~4). A 10-level snapshot cannot
see it. That killed BOTH the pre-entry veto and the book-confirmed exit cut. Any new book proposal must
answer this mechanism, not just show a backtest number. See [[ofi-veto-grind-lead]] for the one cell
that survives so far and why OFI (book *changes* over time) is arguably a different statistic from the
static imbalance/wall-size that died here — arguably, not provenly.
