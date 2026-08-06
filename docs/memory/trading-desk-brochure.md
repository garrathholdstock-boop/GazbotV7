---
name: trading-desk-brochure
description: "Canonical GAZBOT V5 product brochure = docs/TRADING_DESK_BROCHURE.md; \"update the trading desk brochure\" → re-scan the CODE (not memory) and refresh it"
metadata: 
  node_type: memory
  type: project
  originSessionId: b98efc3a-63db-4236-bd2a-69cc1a89a6f2
---

The operator's **canonical product/engineering brochure** lives at **`docs/TRADING_DESK_BROCHURE.md`**.

**Trigger:** when Garrath says "update the trading desk brochure" (or similar), that's the file. **HOW to update (operator's hard rule 2026-06-20): SCAN THE CURRENT CODE, do NOT write from memory** — verify every risk/mechanism/number claim against the source, then refresh. Re-measure the metrics (Python files/lines, test files/lines/count, migrations, services, commits, docs) each time rather than reusing stale numbers. Matter-of-fact, no hype ("if we're selling it"), code-true.

**Content (~10 pages):** what it is · the desk (12 micro futures, eurex+us disciplines) · market data (5m/3m/1m + 5s + 250ms L1, the plane) · execution path · **RISK ARCHITECTURE — centerpiece = ZERO TOLERANCE FOR NAKED POSITIONS** (`stop_coverage_audit.py` + `_flatten_executor` + `safe_flatten_verdict`: audit reads IBKR truth → a position confirmed un-stopped for `FLATTEN_CONFIRM_CYCLES=2` past `BOOT_SETTLE_S=120` is MARKET-flattened, NOT re-stopped, bounded so it can't oversell; `BROKER_STOP_COVERAGE_FLATTEN_ON_NAKED`) + native GTC trailing stops + venue-truth exit gate + kill switch + gross/position caps + daily-loss cutoff + profit-ratchet + flat-clock + session flatten · reliability + the ~18 daemons · the analytics platform (edge-spectrum lake + courtroom [walk-forward/FDR/deflated-Sharpe] + the gate cube + the cockpit) · engineering metrics + significance (NOTE: more test code than app code) · the operating model · honest status (paper; 250ms arming; courtroom accumulating; cube interface in-build; MGC observe-only).

**History:** v1 short version was `docs/GAZBOT_V5_PRODUCT_BROCHURE.md`; the 10-page expansion (fork `feat/brochure-v5`, 2026-06-20) is renamed to `docs/TRADING_DESK_BROCHURE.md` on merge — that's the one to maintain going forward. Related: [[chop-scalp-study]] (the cube), the product scope docs in `docs/`.
