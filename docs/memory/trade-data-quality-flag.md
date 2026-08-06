---
name: trade-data-quality-flag
description: "gazbot7.db trades has a data_quality column — honest P&L must filter WHERE data_quality IS NULL; and both killswitches are DISABLED so \"headroom OK\" is vacuous"
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-05T12:42:19.462Z
---

**2026-08-05.** `gazbot7.db.trades` gained a nullable **`data_quality TEXT`** column. Rows **538/539** (the two `abs_veto_short` lots the MD_STREAM bug sized with 1,848-point stops, MAX_HOLD at exactly 2h, **−$255.50**) carry `EXCLUDE:md_stream_atr_corruption_20260804`. Everything else NULL.

**Any honest P&L query must now filter `WHERE data_quality IS NULL`.** `ALL 541 = −$3,573.00 · CLEAN 539 = −$3,317.50`. Marked, never deleted — the fills were real, the FEATURE that sized them was not; deleting would falsify the execution record and hide the incident.

**★ BOTH KILLSWITCHES ARE DISABLED and have been since 2026-07-16** ("its paper, we need to see action"): `max_daily_loss_usd = 0.0`, `loss_streak_halt = 0`, no `.env` or systemd override, `core.py:821` constructs RunConfig without them. So no P&L event can halt this desk. ⚠ **`sweep.py:273` reads `if cfg.loss_streak_halt and streak >= ...` — with 0 it short-circuits and ALWAYS prints "headroom OK".** That string means "no limit exists", NOT "we have room". I quoted it as reassurance and was wrong; don't repeat that. Re-arm for go-live is daily 300 / streak 4.

★ METHOD, and it is the [[md-stream-multi-symbol-filter]] lesson again: **widening a shared table means auditing every CONSUMER.** Before the ALTER I checked all five `SELECT * FROM trades` callers — all use `sqlite3.Row` named access (`store.py:202`) and `get_trades` has no callers — so a trailing column cannot shift a positional unpack. `VACUUM INTO` snapshot first (`data/snapshots/gazbot7_pre_dataquality_20260805.db`), never `cp` a live WAL DB.

★ The Paris-day boundary is 22:00 UTC, so an overnight incident lands in the NEXT day's P&L. The "−$326 bleed" alert on 08-05 was 08-04's overnight, already diagnosed — attribute before acting on a day figure. See [[verify-desk-facts-never-guess]].
