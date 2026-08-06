---
name: analytics-capture-roadmap
description: "Hedge-fund critique of what we capture analytically + the prioritised what-to-capture-next roadmap (microstructure is the #1 gap)"
metadata: 
  node_type: memory
  type: project
  originSessionId: b341af3b-70a2-447b-81c6-5edf2d669ad6
---

Operator-requested capture review (2026-06-19), full doc `docs/ANALYTICS_CAPTURE_REVIEW.md`; the buildable
per-stream specs + dependency-ordered roadmap are in **`docs/CAPTURE_BUILD_SCOPE.md`** (operator said "scope
all of it"). Build order: #1a microstructure L1 spread/quote (keystone, irreversible, unblocks real cost) →
#3 regime labeler (cheap, conditions everything) → #5 decision-context + #6a session/roll stamps → #4
portfolio snapshot → #1b tape→OFI/CVD/VAP → #2 TCA → #6 econ-cal/parent → #1c L2 + #7 substrate. Multi-week
program; touches MD daemon (#1,#6c) + broker order path (#2) + entry path (#4,#5 = flag-and-wait). Mostly
additive capture; bounded-retention + Parquet offload from day one. NOT started — scoped only. Governing
principle: **capture the EPHEMERAL now (impossible to backfill), derive the rest later.** The "in 3 months I
wish we had that data" regret is ALWAYS about ephemeral raw streams.

**The cardinal gap: NO MICROSTRUCTURE.** We store OHLCV bars + the current gates' point-in-time features —
not the order book or the trade tape. So spread/order-flow/real-fills are absent → we had to ASSUME cost in
the peak-dip scalp analysis (couldn't truly answer net-positive). Other gaps: no TCA (paper logs $0
commission), no measured per-bar REGIME label (chop/trend — half our ideas are regime-dependent), single-
instrument tunnel vision (no portfolio/correlation/net-exposure — MNQ+MES+MYM long = one Nasdaq bet), feature
set welded to today's gates (blocks gate evolution), no decision-context/counterfactual, no event/calendar
stamps.

**Tier-1 capture (start ASAP, forward-only, can't backfill):** (1) microstructure — L1 spread/quote + tape →
order-flow imbalance / CVD / volume-at-price (the real "footprint"); (2) execution truth/TCA — submit/fill
ts, slippage, spread-at-submit (at minimum signal_price vs entry_price); (3) regime label + vol percentile
banked per cycle; (4) portfolio-state snapshot per entry; (5) full decision context (every gate's score +
rejection reasons); (6) cross-asset/parent context (NQ for MNQ, vol, DXY); (7) event/session/roll stamps.
Tier-3 (derived: returns/sweeps/walk-forward) — already handled, don't rush.

**STARTED 2026-06-19 (operator "build baby"):** **#1a microstructure L1 spread/quote DEPLOYED** (`b41ae51a`)
— reqMktData per contract (fail-soft, never breaks bars) + QuoteRecorder → `quote_snapshot` (bid/ask/spread,
5s, 14d retention, CREATE-IF-NOT-EXISTS so no migration); real spreads capturing (0.25–5.0/contract — finally
fixes "cost is assumed"); nan-skip handles CME-halt contracts (only 24h micros quote during the 22:00-23:00
UTC break; all 12 in session). **#3 regime labeler DEPLOYED** (`d76237a7`) — `alphabot/intelligence/regime_label.py`
(pure, tested 5/5) stamped per entry in edge_capture (leak-free), regime now a chop dim. KEY FINDING: desk is
**56% chop / 34% vol_expansion / 9% trend**; long-into-vol_expansion = the −$2k bleed, shorts-in-expansion win.
**#6a session_phase + #5 decision_log DEPLOYED 2026-06-20** (`5ff37ee0`, offline like #3): session_phase
(pure, tested) stamped per entry + chop dim; decision_log.parquet = recent funnel (fired+passed, 7d) +
reason + features (the counterfactual — desk PASSES 96% of cycles, rejections dominated by ATR gates
atr_not_expanding/atr_too_low = sits out low-vol). days_to_roll already = days_to_expiry. KEY COMPOUND
FINDING (regime #3 + session #6a): the desk's EDGE is shorting/fading (us_open SHORT +0.17/68%win;
shorts-in-vol_expansion +0.11) and its BLEED is its long-bias buying into those windows (us_open LONG -$883,
long-into-vol_expansion -$2k). Actionable: the long-biased desk should fade, not buy, the open/expansions.
#5 full per-non-winning-gate scores = the entry-path (flag-and-wait) extension, not built.
**#4 portfolio snapshot DEPLOYED 2026-06-20** (`5d2d9ed6`, offline — reconstructed from trades intervals at
each cycle_ts, leak-free): cluster map (eq_idx_us/eu, fx, energy, metals, crypto) + concurrent_open /
same_cluster_open / same_cluster_same_dir stamped + chop dims. FINDING: non-monotonic — moderate correlated
stacking (2-3 same-dir) best (+0.07), HEAVY (4+) the worst bucket (-0.10) → a max-correlated-positions cap is
a studyable knob (correlational/confounded). Next (scoped, not started): #1b tape→OFI/CVD/footprint → #2 TCA
(unblocked by #1a spread) → #6 econ-cal/parent → #1c L2. Also pending: #1a quote-recovery fix (re-sub
reqMktData on reconnect — only 3/12 contracts quoting after the CME-break halt; confirm at RTH sweep).
ALL of #3/#5/#6a/#4 were OFFLINE (no live touch); #1b/#2/#1c touch the MD daemon/broker (flag-and-wait). Build order in the doc §7;
offload high-volume capture to Parquet like the [[edge-spectrum-pipeline]]. Caveat: paper limits realism —
design schemas so live fills/book slot in.

**Timer-stagger fix (doc §6, PENDING — /etc systemd, operator-gated):** retention hourly `*:00` × edge-nightly
`21:05` × edge-drain `:20` pile up 21:00–21:25; edge-nightly now heavy (spectrum work) → killed retention,
stale lock (self-heals 1h). Short-term: move edge-nightly → `21:40`. Robust: shared heavy-DB-job lock to
serialise. Not done unattended.
