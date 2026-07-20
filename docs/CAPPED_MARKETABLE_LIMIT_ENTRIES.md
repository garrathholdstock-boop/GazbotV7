# GAZBOT V7 — Capped Marketable-Limit Entries

**Status:** BUILT + **LIVE** 2026-07-20 (core + strategy since 14:31 UTC;
`entry_limit_buffer_pts=3.0`, `entry_timeout_s=3.0`). Operator: *"do the capped
marketable limit fix."* ⚠ Touches the entry-order path (V5's 07-15 tangle) — deployed
with the safety nets below + close first-entry watch.

---

## Why

V7 entries were **raw MARKET orders** (`core._open` → `order_type="MKT"`; verified —
there was *no* limit/tolerance anywhere, contrary to the assumption that we ran a
wide-tolerance marketable-limit). On the paper account a market order accepts any
fill, so a 2-lot entry took a **2nd lot 29pt off a tight, deep book** (id67:
avg entry dragged +14.5pt → −$156). A market order can't cap that.

## The fix

An entry is now a **marketable LIMIT, tif=IOC**:
- **limit price** = `ref_price ± entry_limit_buffer_pts`, rounded onto the tick
  (BUY → `ceil(ref + buf)`, SELL → `floor(ref − buf)`). `ref_price` is the strategy's
  decision price, carried on the OPEN intent.
- **IOC** (immediate-or-cancel): fills whatever liquidity sits within the cap *now*,
  cancels the rest. **No resting order** (so no late/stale fill), and a fill beyond
  the cap is **impossible**.
- **buffer 3.0 pts** = marketable (fills through 12 ticks — the id67 book had 32 lots
  in 4 ticks) yet caps slippage at ~$6/lot vs id67's ~$58/lot. Tunable.
- **`buffer = 0` → plain MKT** (disabled / backward-identical).
- **CLOSES / FLATTENS stay MKT** — they must fill; only entries are capped.

## The wedge guard (the load-bearing part)

An IOC that fills **nothing** (price ran past the cap in the latency window) leaves
**no fill event** — so `pending_open` would never reset and the desk would take no
further entries. `core.expire_pending_open()` (called each ~1s status cycle) cancels
any remnant and clears `pending_open` after `entry_timeout_s` still-flat, so the desk
re-fires on the next signal. A normal fill clears it via `_on_opened`.

**Partial IOC fill** (e.g. 1 of 2 lots within the cap, 2nd cancelled) → `_on_opened`
opens the venue-true qty (1 lot), arms a 1-lot stop — handled by the qty-sync fix.
A 1-lot fill is strictly better than a 29pt-slipped 2nd lot.

## Compatibility / rollback

- **Backward-compatible**: old strategy (no `price` on the intent) → core sees
  `ref=None` → falls back to MKT. Old core (ignores `price`) → MKT. Either restart
  order is safe; both restarted to get the full behaviour.
- **Rollback**: `entry_limit_buffer_pts=0` (→ MKT) + restart, or `git revert`.

## The throughput question (operator context)

Last week's 40% execution throughput was **not** from tight limits (there were none —
entries were MKT); it came from bugs since fixed (the market-hours clock, the qty
under-count, the 45s veto). A 3pt marketable-limit fills in any normal book and only
misses in a genuine >3pt gap during the ~ms submit latency (rare, and a miss is
**safe** — no bad position; the desk re-fires). So this should not regress fills; if
the miss-rate proves high, widen the buffer (more slippage tolerance) — the knob is
`entry_limit_buffer_pts`.

## Wiring
`strategy._emit_open` (adds `price`) → intent → `core._open` (LMT+IOC) →
`engine.submit(tif=)` → `broker_adapter.place` (`ibo.tif`). Timeout in `core.run`'s
1s loop via `core.expire_pending_open()`. +5 tests in `test_core.py`. Ticks via
`ticks.round_to_tick`/`tick_for`.

## References
id67 forensics: session scratchpad (fills 29148.25 + 29177.25 vs a book all at 29148).
V5 07-15 entry tangle: alphabot2 SESSIONS 2026-07-15 (MKT+STP_LMT didn't round-trip
the recording pipeline → reverted to marketable-limit + 2% buffer; that wide buffer
never capped — this replaces it with a *tight* cap + IOC).
