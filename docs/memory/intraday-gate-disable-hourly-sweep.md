---
name: intraday-gate-disable-hourly-sweep
description: Hourly 07-23 Paris tape+gate-bleed sweeps → operator makes educated intraday gate-disable calls; live off-switch = data/gate_switches.env
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9162c01b-c354-41a1-9fc3-162d48ae4678
---

Operator process (2026-07-21): an **intraday, human-in-the-loop** layer over the live 6-gate tournament, distinct from the Saturday roster decision ([[tournament-changes-saturday-only]]).

**The cadence — ADAPTIVE two-tier (2026-07-21):** hourly **07:00–23:00 Paris** (cron `8 5-21 * * *` UTC=CEST; re-arm each session, −1h UTC after DST). Engine = `gazbot7/scripts/hour_watch.py --json` (deterministic: tape day-type + violence + expanding?, per-gate side/style + 1h P&L + `aligned`/`fighting` the tape, disabled gates, safety, `triggers`+`escalate`; a DISABLED gate is excluded from triggers). **TIER 1 routine** (escalate=false) → ONE tight line (tape+violence+any watch); skip Telegram if the hour's dead. **TIER 2 escalate** (heavy_action on the *active* desk / violent / big_swing / drastic) → DIG IN, dissect the hour (what the tape did · who caught it vs who FOUGHT it and bled, with the exit-reason mechanism · regime-shift-or-one-off), send a DETAILED Telegram whose **first line is exactly `ATTENTION GAZ`**. Default the read to "INFO — no action needed"; recommend `/off <gate>` only if a gate is fighting AND bleeding AND the pattern holds — NEVER off one bad hour. Operator "wants to be educated, not babysitting" — I report+recommend, **he decides**.

**The off-switch (built 2026-07-21, commit `fafdfdb`):** `data/gate_switches.env` — `<gate>=off` disables a gate's NEW entries (open position still exits normally); `=on` re-enables. The tournament re-reads it **LIVE each tick (no restart)**, cached on (mtime,size). This is `tournament.read_disabled()` filtering OPEN intents. **Only the operator flips it** (or on his explicit in-session say-so). ⚠ needed one flat-window restart to activate the code.

**★1-DAY AUTO-REACTIVATION (2026-07-23 operator RULE, commit `831d455`):** an off is FOR THE DAY only — it auto-reactivates at **Paris midnight** (the trading-day boundary; daily P&L rolls there too). Discovered because `rgv_short` sat off ~2 days (07-21→23) with no expiry — the switch just held its state. Mechanism = `telegram_bot.reactivate_all()` (pure, flips every off→on) run by `scripts/reactivate_gates.py` from systemd `gazbot7-gate-reactivate.timer` (`OnCalendar=00:00 Europe/Paris`, systemd 255 handles DST, Persistent catches a missed midnight); idempotent + notifies which came back. A LONGER hold (e.g. a relegation candidate) is NOT this switch — it's the Saturday roster action (remove the spec). So to keep a gate off past midnight, re-off it daily or relegate it Saturday. rgv_short was reactivated 07-23 (overstayed).

**Why:** disable a gate tactically when the tape is clearly hostile to it that day, before it bleeds — educated damage-control, not a permanent roster change. **How to apply:** run the hourly sweep, surface tape/violence/bleed + a WHY, never disable unilaterally; roster relegate/promote stays Saturday. A Telegram command bot writing this same file (so he toggles from his phone) is a scoped follow-on — texting THIS Claude session directly is not wired.
