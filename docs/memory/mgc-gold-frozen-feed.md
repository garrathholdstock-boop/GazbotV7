---
name: mgc-gold-frozen-feed
description: "MGC (Micro Gold) frozen-feed issue is RESOLVED — real-time COMEX ticks live since ~2026-06-29; do NOT auto-exclude MGC as untradeable anymore"
metadata: 
  node_type: memory
  type: project
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

**RESOLVED 2026-07-09 (verified).** MGC (Micro Gold, COMEX) is now a **real-time live feed with full parity to MNQ/MES** — do NOT treat it as frozen/untradeable. Verified: `.env IBKR_MARKET_DATA_TYPE=1` (real-time, overriding the config.py 3=delayed default); last-60s ticks MNQ 224 / MES 224 / **MGC 224 (identical)**; **2.4M ticks streaming continuously since 2026-06-29 17:45**, 4/sec bid+ask, 0.2s fresh, prices moving normally (~$2 spread). The MD daemon logs live MGC marketPrice marching (4117→4135 over 17 min). A COMEX real-time entitlement was evidently added to the paper account around 2026-06-29, closing the gap below.

⚠ **The stale "frozen" belief has been actively misleading analysis** — the 2026-07-09 reversion forensic agent auto-excluded MGC's +EV pocket as a "frozen-feed artifact." It was wrong about the REASON: MGC is fully tradeable. (It was still right to discount that specific pocket — but because it's a ONE-trade sample artifact: +$67.88 of +$78 net came from a single fill, not because the feed is dead.) **Lesson: treat MGC as a first-class contract and judge its edges on merits; its momentum was a real CHAMP earlier.** If MGC was held observe-only *because* of the frozen feed, that blocker is GONE — re-arming is now only a margin/operator call. Related [[golive-drop-mnq-mgc]].

**HISTORICAL (the original problem, now fixed):** As of 2026-06-16 MGC streamed a FROZEN feed — md-daemon recorded bars but every one flat (one distinct price all day, e.g. 4311.1) with volume 0 (712/712 zero-volume bars vs MES's ~1700 volume), because the paper account had **no COMEX real-time market-data permission** — a data-entitlement gap, no code fix. Old diagnosis path: md-daemon :8092 `/bars?symbol=MGC` (flat OHLC vol 0) vs `bar_history` `SELECT COUNT(DISTINCT close)`=1. That state no longer holds.
