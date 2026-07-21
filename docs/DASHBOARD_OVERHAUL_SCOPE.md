# GAZBOT V7 — Dashboard overhaul (scope, READ-ONLY review — NOT built)

**Status:** SCOPED 2026-07-21. A full review of the `:8087` cockpit against what the desk
actually does now (the 6-gate paper tournament), and a design for the overhaul. The cockpit
is a **V5-era single-position** view lightly patched for multi-slot; it doesn't show the one
thing that matters now — **the per-gate tournament race** — and ~⅓ of its panels are dead.
View layer only: `web.py` (stdlib, separate process) + `web_static/{app.html,app.js,app.css}`.
Never touches the trading path.

---

## 1. What the desk actually does now (the reality to reflect)

- **6 gates run concurrently** on one netted paper account, each holding its own MNQ lot(s):
  LONG rgv_long · grind_long · capitulation_long · SHORT thrust_short · rgv_short · exhaustion_short.
- **Per-gate P&L is THE metric** — realized today **+ open unrealized** — because the tournament
  **relegates the worst 2** and **promotes from the shadow board**. That race is the product.
- Each gate is its own position with its own exit stack (chandelier / 2R / give-back / native
  1-ATR stop / absorption / adverse / max-hold / **stop-unfilled**) and its own protection.
- Rich **per-slot safety**: coid-keyed naked auditor, reconcile DRIFT→halt, stop-breach guard,
  wedge-breaker, unverified-escalation — all per gate, over a netted venue.
- **Shadow board** (separate, `/shadow`) is the cheap feeder that nominates promotions.
- Kill-switches OFF (paper). Net near zero (longs + shorts).

## 2. Current dashboard audit — tab by tab

**Header:** NET/TODAY/YEST/2D/7D/30D/WIN%/Paris clock, conn dot, mkt chip, **regime chip (dead)**,
HALT banner. → Mostly fine; regime chip never populates.

**DESK tab** — the prime panel, but half of it is dead single-position furniture:
| Panel | State | Note |
|---|---|---|
| MARKET REGIME · US | ☠ **DEAD** | `regime_groups={}` in V7 — always "—" |
| UNREALISED P&L | ⚠ shallow | one summed number; doesn't say *which gates* are live |
| MARGIN DEPLOYED | ☠ **DEAD** | `margin/nlv=None` in V7 — always "—" |
| POSITIONING | ⚠ half-dead | "Net locked profit" + "Ratchet·today" are single-position concepts, always "—"; Open contracts / Today realised / Trades / Win OK |
| ROLLING 1D/7D/30D | ⚠ partial | pnl/win/N OK; **pf/maxdd always None** |
| **GATE PERFORMANCE** | ✅ works | the real per-gate P&L — but buried at the bottom, realized-only, pf often None, and only shows gates that **traded** (missing 0-trade roster gates) |
| LONG/SHORT HEALTH | ☠ **DEAD** | `long_short=[]` — never computed in `mnq_json` |
| LOSSES BY EXIT | ☠ **DEAD** | `loss_buckets=[]` — never computed |

**GATES tab** — TOP 5 / BOTTOM 5 leaderboard. Closest thing to a tournament view, BUT: realized-only
(no open unrealized), top/bottom-5 framing (not the full 6-gate roster), no relegation/promotion flag,
no live/flat status, no exit-mix. It's a generic leaderboard, not the tournament scoreboard.

**CHART tab** — hero price + ribbon (last/vwap/atr) + **DTT "distance-to-trigger" strip (dead:** `activity.gates=[]`; was single-gate thrust, meaningless for 6 gates incl. footprint). Chart now overlays all slots' entry/stop (P3). Keep the chart; DTT needs rethink or removal.

**HOLD tab** — per-slot holding cards (P1–P3, built). Only visible when holding → looks empty most of the time. This is fine but it's the *only* place the live tournament shows, and it's a secondary tab.

**TRADES tab** — realized curve + blotter (time/side/**gate**/exit/$/%). ✅ works, gate column real.

**EXEC tab** — through-rate / slippage(None) / blocked / trend. ✅ works (generic exec funnel).

**Net:** the cockpit answers "how's my single MNQ position + desk P&L" (a V5 question). It does **not**
answer the V7 questions: *which gates are winning, which are getting relegated, what's live right now,
and is everything protected.*

## 3. The overhaul — information architecture

Reframe the cockpit around the **tournament**. Priority order of what an operator needs:

**A. Desk header (always visible) — the one-glance state.**
Total today P&L (realized) · open unrealized (Σ slots) · **# gates live / 6** · flat-or-holding ·
**SAFETY light** (green / amber "unverified" / red "naked or HALTED") · Paris clock. Kill HALT-only;
make it a real safety pill driven by `core_health.json` (`halted`, `protection.held`, per-slot
`stop_coid` present, `unverified_cycles`).

**B. ★ TOURNAMENT tab = the new centerpiece (replaces/absorbs GATES).**
The **full 6-gate roster** (from `tournament_slots()`, so 0-trade gates still show), each row:
`gate · side · LIVE/flat · open-unreal · today-realized · TOTAL today · N · win% · PF · exit-mix spark · RANK`,
sorted by total, with **relegation flags** (bottom-2 highlighted red = canned candidates) and a
promotion hint (from shadow). Click → per-gate drill (that gate's trades + exit breakdown).
This is "who's winning, who gets relegated" front-and-center.

**C. LIVE SLOTS strip (on the Tournament tab or its own).**
One tile per currently-open gate: side · qty · entry · last · **open P&L** · stop · time-in-trade ·
**protected/NAKED**. (This is today's HOLD-tab content, promoted to a first-class strip so the live
desk is visible without switching tabs.)

**D. Keep, lightly:** CHART (price + all-slot overlays; drop/rework DTT), TRADES (curve + blotter),
EXEC (funnel).

**E. Cut the dead furniture:** MARKET REGIME, MARGIN DEPLOYED, Net-locked-profit, Ratchet. Either
delete or replace their DESK-tab space with tournament content. Compute **LOSSES BY EXIT** (data
exists — it's just not wired) and keep it — it tells us *how* gates bleed (stop vs absorption vs
stop-unfilled). Fill ROLLING's PF/maxDD or drop those columns.

## 4. Backend changes (`web.py`)

1. **NEW `/api/futures/tournament`** — the roster rollup. Import `tournament_slots()` for the full
   6-gate roster; for each gate combine: today-realized + N + win% + PF + exit-mix (from `trades`,
   grouped by gate) **and** open-unrealized + live status + protection (from `status.json` slots +
   last price). Return ranked, with a relegation flag (bottom-2 by total). One call feeds B + C.
2. **Extend `us_terminal_json`** (or a small `/api/futures/safety`) to surface the desk safety pill:
   `halted`, any-naked (a held slot with no `stop_coid`), `unverified_cycles`, #live/6.
3. **Wire the already-shaped-but-empty** `loss_buckets` (group today's losing trades by `exit_reason`)
   and, if kept, `long_short`. Add PF/maxDD to rolling or drop the columns.
4. Leave `/api/shadow/*` and `/api/futures/{bars,execution}` as-is.

## 5. Frontend changes (`app.html` / `app.js` / `app.css`)

- New **Tournament** tab + panel (roster table + live-slots strip); demote/merge the old GATES tab.
- Rework the DESK tab: header safety pill, drop dead panels, keep the useful rollups.
- `renderTournament()` off the new endpoint; keep `renderHolding` content as the live-slots strip.
- Poll cadence: roster + slots on the fast loop (~2–5s) so the race + open P&L feel live.

## 6. Phasing
- **P1 — backend `/api/futures/tournament` + safety fields** (no UI yet; verify JSON).
- **P2 — Tournament tab (roster + relegation) + live-slots strip.**
- **P3 — desk header safety pill; cut dead panels; wire loss-buckets.**
- **P4 — chart DTT rework; PF/maxDD; polish.**
Each phase is shippable and read-only (no desk risk); `gazbot7-web` restart to deploy `web.py`.

## 7. Test plan
- `/api/futures/tournament`: full 6-gate roster even with 0 trades for a gate; realized+open combine
  correctly; relegation flags the bottom-2; a held slot shows open-unreal + protected.
- safety pill: naked slot (no stop_coid) → red; unverified>0 → amber; halted → red.
- loss_buckets groups by exit_reason; blotter/curve unchanged.
- All existing endpoints still 200 (regression).

## 8. Non-goals / risks
- Read-only view; **never touches trading**. Safe to iterate; deploy = `gazbot7-web` restart.
- Not merging the `/shadow` board here — a "promotion candidates" hint can link to it (P4+).
- The 6-gate roster couples the view to `tournament_slots()` — acceptable (single source of truth);
  if the slate changes the roster follows automatically.
