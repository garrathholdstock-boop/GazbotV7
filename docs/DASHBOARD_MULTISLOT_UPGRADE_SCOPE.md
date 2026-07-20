# Dashboard multi-slot upgrade — SCOPE

**Status:** SCOPED, not built. Raised 2026-07-20 right after the tournament cutover (DECISIONS §348) — the `:8087` cockpit shows **FLAT/empty** because its live-holdings path was built for the single-position `status.json` shape and the tournament writes a multi-slot shape.

## The problem (what broke, precisely)

The single-position desk wrote `status.json` with **one** position:
```json
{"position": {"symbol":"MNQ","flat":false,"side":"SHORT","qty":1,"entry":28915.25,"stop":28935.25,"opened_at":"..."}, "protection":{"held":true,"verified":true,...}}
```
The tournament (`multislot_core.write_heartbeat`) writes **N** slots:
```json
{"position": [{"gate":"rgv_long","side":"LONG","qty":1.0,"entry_price":28883.5,"stop_coid":"stp-000001"}],
 "protection": {"held":true,"slots":[{...}],"unverified_cycles":0}}
```

Breakage:
1. **HARD (backend):** `web.py` `us_terminal_json` (`src/gazbot7/web.py:106`) does `pos = st.get("position")` then `pos.get("flat")`. `position` is now a **list** → `list.get` raises `AttributeError` → holdings come back empty → the cockpit renders "FLAT — no MNQ position" even with 4 slots open.
2. **Field-shape mismatch:** the tournament's slot dicts use `entry_price` (not `entry`), carry **no `stop` price** (only `stop_coid`) and **no `opened_at`** — the fields the holdings panel needs (`entry`, `stop`, `opened_at`, `held_seconds`, per-slot P&L).
3. **Hardcoded gate:** `us_terminal_json` stamps `entry_gate: "thrust"` on the holding — should be the slot's real gate.
4. **Frontend single-position assumptions:** `app.js` is list-aware for the *count* (`mnqHoldings()`, `hold.length` at :373) but the **HOLD detail panel** (:435–450), the **chart position overlays** (:316), and the **protection badge** assume one holding / the old `protection.{held,verified}` shape.

Already fine (no change needed): `/api/futures/mnq` header/rolling/blotter/curve/**gate_perf**/**leaderboard** read the `trades` table, which the tournament writes **per-gate** (coid-attributed SlotBook → `record_trade(gate=...)`). The per-gate leaderboard — the whole point of the tournament — populates as slots close. `_gate_groups` already groups by real gate.

## Required changes (phased)

### P1 — un-break the backend (small, high-value: cockpit shows live slots again)
- `web.py` `us_terminal_json`: detect `position` is a **list**; build **one `holdings` row per open slot**. Map `entry_price`→`avg`/`entry`, real `gate`→`entry_gate`, per-slot P&L vs `last` (reuse the existing `sign*(last-entry)*VPP*qty` math per slot). Tolerate the old single-dict shape too (defensive, for a revert).
- Acceptance: with 4 slots open, `/api/futures/us-terminal` returns 4 holdings, each with its gate/side/qty/entry/pnl; cockpit ribbon shows "4 open".

### P2 — enrich the heartbeat slot payload (so the panel has what it needs)
- `multislot_core.write_heartbeat`: add per-slot `stop_price` (from the slot's `SafetyManager.stop_for().stop_price`), `opened_at` (from `Slot.opened_at`), and `entry_atr`. Keep `stop_coid` (protection identity).
- `web.py`: derive `held_seconds` from `opened_at`; surface `stop` price + a per-slot **protected?** flag (does `protection.slots[i].stop_coid` exist / is the slot in `protection.slots`).

### P3 — frontend multi-slot render (`app.js` / `app.html` / css)
- HOLD detail panel: render a **row per slot** (gate · side · qty · entry · stop · P&L · time-in-trade · protected badge) instead of one position block.
- Chart overlays (:316): draw entry/stop lines per open slot (or the selected slot), not a single pair.
- Protection indicator: replace the single held/verified badge with a **per-slot** protection strip driven by `protection.slots` + `unverified_cycles` (any slot unprotected → red).
- Header "unreal" sub: already counts `hold.length` — keep; sum unrealized P&L across slots.

### P4 — tournament-native surfaces (nice-to-have, the judge view)
- A **live per-gate P&L / relegation** panel: today's realized (from `trades` by gate) + open unrealized (from slots), ranked — the "who's winning the tournament, who gets relegated" view (DECISIONS §347-B). Mostly a re-skin of the existing `gate_perf`/`leaderboard` with the open-slot unrealized folded in.
- Show `halted` (reconcile DRIFT) prominently — a halted tournament must be obvious on the cockpit.

## Notes
- Read-only view layer — **never touches the trading path** (web.py is stdlib-only, separate process). Safe to iterate without desk risk.
- The tournament's per-gate P&L is **already captured** in `trades` (§3 analytics-capture rule satisfied at the data layer); this scope is purely the VIEW catching up.
- Revert of the desk cutover (start core+strategy) restores the old single-position `status.json` shape — P1's defensive dual-shape handling keeps the cockpit working across a revert.
