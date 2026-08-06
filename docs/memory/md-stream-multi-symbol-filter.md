---
name: md-stream-multi-symbol-filter
description: "MD_STREAM is MULTI-SYMBOL — every consumer MUST filter body['symbol']; adding MGC to capture made ATR read 1848 vs a true 15 and opened trades with 122x-wrong stops"
metadata:
  type: project
---

2026-08-04 22:02 UTC — the worst bug of the day, and I introduced it that afternoon.

**WHAT.** `md` publishes one bar per captured symbol on ONE stream, correctly tagged
`{"symbol": sym, ...}`. Three consumers — `tournament.py`, `shadow.py`, `strategy.py` — folded EVERY
bar into a single `MinuteBars` deque **without checking the tag**. Latent for the desk's entire life
because md only ever captured MNQ. Adding **MGC to md capture at ~17:30** armed it: gold bars (~3,300)
interleaved with MNQ bars (~29,800), and true range across that jump is astronomic.

**MEASURED DAMAGE.** `entry_atr = 1848.16` against a true **15.11 — 122x**. At the 22:00 reopen the desk
opened `abs_veto_short_A/_B` with stops **1,848 points** away instead of ~15 (~$3,700 risk/lot instead
of ~$30) and targets at 1.5R/2.5R of a bogus ATR, i.e. unreachable. **Every gate threshold is
ATR-relative**, so entries and exits were corrupted simultaneously — and the shadow desk's 36 sims,
including the stop-width and clip A/B arms built that day, were fed the same corrupt features from
17:30 onward. Any shadow row timestamped 17:30–22:07 on 08-04 is suspect.

**FIX.** `if body.get("symbol") != cfg.symbol: continue` before the fold, in all three consumers
(strategy is the retired revert target — fixed so a revert cannot resurrect it). Pinned by
`tests/test_md_symbol_filter.py`, which also asserts the guard PRECEDES the fold and that md still
tags the payload (if the tag vanished, every consumer would starve for bars — failing closed, but fatal).

## ★★ THE TRANSFERABLE LESSON
**A config change in one file armed a latent bug in three others.** Nothing in md, capture or the
consumers changed logically — only the SET OF SYMBOLS. So no test of the changed file could have caught
it, and no amount of running the desk beforehand would have either. When widening what a shared stream
carries, audit every CONSUMER of that stream, not just the producer. Related class:
[[stop-unfilled-contfuture-root-cause]], [[futures-session-flat-exchange-routing]].

**Also: `entry_atr` is PERSISTED and reused on boot-adopt** (`multislot_core` reads `row["entry_atr"]`),
so restarting does NOT repair an already-open position. A trade opened on corrupt features stays corrupt
until it closes. The 08-04 pair was left to its stop / the 20:53 EOD flatten rather than intervening on
the order path overnight — PAPER, bounded, and flagged to the operator.

Caught because the operator's event watcher showed the desk was no longer flat and I checked the stop
distance rather than just `held: True`. **`protection.held` being true says a stop EXISTS, not that it
is SANE.** Check the distance.
