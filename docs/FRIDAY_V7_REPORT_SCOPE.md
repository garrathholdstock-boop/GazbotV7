# THE FRIDAY REPORT — V7 CANONICAL SCOPE (locked 2026-07-24)

> ═══════════════════════════════════════════════════════════════════════════════════════════════
> ## ★★★ THIS IS **FRIDAY REPORT — VERSION 1**. FROZEN 2026-09-04 BY OPERATOR INSTRUCTION.
> Operator, 2026-09-04: *"leave the previous scopes as friday report version 1."*
>
> **V1 is the weekly desk review** — census, gate rehab, shadow board, greenfield clusters, the
> tournament scorecard, the router review. It is NOT retired and NOT superseded; it is the standing
> weekly report and this file remains its canonical shape.
>
> **VERSION 2 is a SEPARATE, NARROWER report** with its own scope in `FRIDAY_V2_TUNNELS_AND_RUNS.md`
> — a single question (can the break out of a compression tunnel be traded automatically, bought
> with NO STOP), not a weekly review. **Do not merge the two.** V2 does not inherit V1's phase list,
> and a V1 phase must never be told to answer a V2 question.
> ═══════════════════════════════════════════════════════════════════════════════════════════════


> **★★★ IF YOU ARE THE FRIDAY-REPORT CRON (fresh Claude session, ~Fri 22:00 UTC / midnight Paris): THIS FILE IS THE REPORT SHAPE. ★★★**
> **★★2026-08-14 UPDATED — THE DESK IS MNQ-LED, NOT MNQ-ONLY.** The LIVE desk trades **MNQ**; that is
> still where the P&L and every existing gate live. But we have captured **MGC** (COMEX gold) L1 AND
> L2 since 2026-08-04 and it is now an active line of enquiry — the operator: *"we want to find some
> gates that work for mgc"*. The census runs for both symbols and phase `gf_MGC` hunts gold entries.
> ⚠ This line previously read "MNQ-ONLY … IGNORE MGC", which directly contradicted the DATA CONTRACT
> the phases also receive. A phase told both things would have dropped the gold work.
> ⚠ MGC is **$10.00/point**; MNQ is $2.00. Never price gold with the MNQ multiplier.
> ⚠ MGC gates must be **INVENTED FRESH** — never port, clone or re-tune an MNQ gate onto gold.
> Still IGNORE the old 7-contract structure (MES/M2K/MYM/MCL/MBT) in `FRIDAY_SHADOW_REPORT_SCOPE.md`
> / `FRIDAY_REPORT_MASTER.md` — those describe the RETIRED V5 desk. Build the shape below. Publish ONLY via `scripts/friday/publish_report.py` (the hard verify-gate). Data is V7: `gazbot7/data/gazbot7.db` (trades) + `gazbot7/data/shadow.db` (the shadow board) + the tape.
> **★ THE TAPE: `capture.db` IS A ROLLING WINDOW, NOT THE ARCHIVE** — book/quotes/ticks hold only
> **5 TRADING DAYS** (bars 60). ATTACHing it for anything multi-week silently returns a fifth of the
> data with no error. For history use the **Parquet lake**: `from gazbot7.lake import connect`
> (2026-07-16 onward, local or straight off Backblaze). MGC L2 is in `depth.db.depth_snap`, not
> `capture.db.book` (which is MNQ-only — IBKR allows just 3 depth subscriptions).
> Older history still exists on B2: `gaz:v5archive/alphabot/*.parquet` — the retired V5 desk,
> incl. 574 MNQ trades and 3,012 us_futures_daytrade trades. Filter to
> `discipline='us_futures_daytrade'` or `symbol IN ('MNQ','MGC')`; the rest is crypto/equities.

## ★★★ DISPOSITION — NEVER KILL A LEAD THAT HAS A GLIMMER (operator, standing, 2026-08-07)
> *"dont negatively kill everything. if theres a lead with a glimmer of hope lets put it into shadow."*
> *"i want to stop calling them graveyards. i have challenged you several times and we have resurrected
> some with better interrogation and some figuring. some are genuinely dead. some didnt qualify but
> could benefit from more work."*

**★ THE WORD "GRAVEYARD" IS RETIRED.** It told the next reader not to look, which is exactly wrong for
something that failed on SAMPLE SIZE rather than on MECHANISM — and the operator has personally
resurrected several by challenging the interrogation. **Four dispositions. Every lead gets exactly one.**

| verdict | means | required |
|---|---|---|
| **LIVE** | survived the battery AND has n | Saturday deploy candidate |
| **SHADOW** | ★ THE DEFAULT for promising-but-unproven | goes in the shadow book to accumulate n — free, riskless |
| **PARKED** | failed AS BUILT, but the mechanism has a path | ★ MUST name WHAT WOULD REVIVE IT — the specific change, data or n |
| **REFUTED** | the mechanism itself is disproven | name the test AND why there is no path |

**★ PARKED IS THE IMPORTANT NEW ONE, and it should be the common outcome.** "Didn't qualify" is NOT
"dead". A lead that lost on thin n, a wrong threshold, a missing filter, or an untested regime is
PARKED — and the entry is only complete when it says what would bring it back: *"revive if n>40"*,
*"revive with an ATR floor"*, *"revive on a trend week"*. That sentence is what makes it retrievable
instead of buried.

**★ REFUTED IS RARE AND EXPENSIVE TO CLAIM.** It requires a NAMED test (placebo-null, strip-best-1/3,
both-halves, LOO, out-of-sample) or a mechanism that provably cannot fire — AND a statement of why no
reformulation saves it. **Thin n can NEVER be REFUTED; thin n is SHADOW or PARKED, always.**

**⚠ THE FAILURE MODE THIS EXISTS TO PREVENT:** an adversarial report that re-derives everything,
refutes most of it, and lands on a page of NULLs is easy to write and useless to act on. Skepticism is
for the NUMBERS, not the DISPOSITION. Incubation is free and this desk's best gates — exhaustion_short,
abs_veto — came up through the shadow book. **If you are killing everything, the bar is set wrong, and
that is itself the finding.**

**★ EVERY SECTION ENDS WITH A DISPOSITION TABLE** — every lead touched, its verdict, and for PARKED the
revival condition / for REFUTED the named test. A section with no LIVE and no SHADOW candidates must say
so explicitly and name the ONE stone still unturned.

## ★★★ READ THE DECISION RECORD FIRST (operator, 2026-08-07)
> *"a big thing we are missing is having you read the last 3 friday reports and the actions we took in
> decisions, sessions.md etc first. for background. and then executing the friday report with that."*

**BEFORE writing any section, read these — they are DECISION RECORDS, not analytical conclusions:**
- `docs/SESSION_2026-08-04_05.md` — what was changed, why, and what it cost
- `docs/WEEKEND_2026-08-01_CHANGES.md` — the weekend that shipped 5 recommendations of which ONE survived
- `data/router_badcall_ledger.md` — every graded switch decision + the running scoreboard
- `data/router_trial_log.txt` — the tick-by-tick record with reasoning
- `/root/CLAUDE.md` — the standing constraints and the incidents

**★ WHY THESE AND NOT THE PRIOR REPORTS THEMSELVES.** Feeding in the last 3 weekly HTMLs (336KB-775KB
each) would ANCHOR every section on last week's conclusions — the exact failure this scope already has
to shout about ("assume NOTHING from any prior week"), and it fights the standing rule that findings
need adversarial RE-DERIVATION. Decision records carry what CHANGED and WHY, which is context; reports
carry what we CONCLUDED, which becomes an unearned prior. **Read the decisions, re-derive the numbers.**

**★ WHAT THIS BACKGROUND IS FOR — three things, concretely:**
1. **Do not re-recommend what is already live.** Several plays each week are "already done" — check the
   decision record before proposing anything, and label it HOLD / NOT-AN-ACTION if it is in place.
2. **Do not re-dig what was PARKED or REFUTED without new information.** If you revisit one, say what
   is NEW that justifies it (more n, a new filter, a regime that has now occurred).
3. **Close the loop on last week's plays.** `reports/friday_v7/plays.json` holds last week's 36 plays.
   ⚠ THEY CARRY NO OUTCOME FIELD — nothing has ever graded whether they were DONE or whether they
   WORKED. State that gap plainly in the report. **A full play-ledger (status + outcome per play) is
   scheduled to be BUILT on Saturday 2026-08-08** — until it exists, do what you can by hand from the
   decision record, and flag the ones you cannot resolve.

## Voice — NON-NEGOTIABLE (operator, standing)
Write **long, detailed, and in plain daily English — TO Garrath**, not maths-professor / geek talk (he's rejected the "technical nerd reading numbers" voice repeatedly). Numbers live INSIDE sentences ("it made $992 over 28 trades and beat its ceiling"), behaviour named in human words ("it bought the dip and the dip kept going"). **LOTS of tables with clear facts** — every claim is a table with n / net$ / win% / $-per-trade, never a bare assertion. Honest about thin-n / one-week / in-sample — a clean "no edge here" beats a hopeful tweak. LEAD with what SURVIVED the skeptic, never the biggest number.

## The report is the LABORATORY
Everything is **re-derived FRESH on the week's full data** — mid-week chats/studies are LEADS to test HARD, never findings to inherit. For every live knob/gate/exit ask **WHY** (what it was built to fix) and **WHAT ELSE** is out there (sweep the alternatives on the week's tick data, robustness-gated). Honest money only: score on tick-repriced `real_pnl`, never optimistic sim `pnl_usd`.

---

## STRUCTURE (front → deep-dive)

### PART 1 — THE LIVE DESK (this week)
Plain-English review of the live 6-gate paper tournament (rgv_long, grind_long, capitulation_long, thrust_short, rgv_short, exhaustion_short). The week's P&L (canonical, computed not guessed), a **per-gate card table** (net · N · win% · avg win/loss · exit-mix · best/worst trade), what actually happened (the whippy trend/chop days, the STOP_UNFILLED self-heals, the direction-router trial and how it behaved), and the day-type split (did a gate's P&L depend on trend vs chop?). Tool: `scripts/filter_check.py`, `scripts/hour_watch.py`, the tournament trades.

### PART 1.5 — ★ GATE & EXIT REHABILITATION (the operator's #1 recurring live-desk section)
**The standing rule (operator, 2026-07-25, reinforced 2026-07-26):** *"Never look at a gate or an exit at face value and say it's no good, bench it. If it's not working, HOW can it work — or at least show the honest TRYING."* This is a WHOLE headline section, not scattered bits — the desk earns trust by rehabilitating, and by showing every failed rehab by name, each dispositioned PARKED (with its revival condition) or REFUTED (with the named test). For EVERY red / underperforming gate this week AND every exit mechanism worth improving, run the full **rgv-treatment**:
1. **Normalize malfunctions** — system stops / naked rides / STOP_UNFILLED: what would the loss have been if the stop had worked? Strip the software failures from the strategy verdict.
2. **Corrected-cost reconstruct** — the true tick-honest P&L ($1.50/RT, $2/pt), not the raw.
3. **Root-cause** — is the bleed the BASE config, the EXIT, or the SIGNAL? (the recurring finding: ER filters FAKE, ATR floors REAL, give-back guts snap-back gates, the exit must match the edge SHAPE.)
4. **Filters that KEEP the winners** — a filter that "wins" by dropping the target winners is a FAKE win; reject it and say so (the 15/17-winners rule).
5. **Robustness** — strip-the-best, per-ISO-week, leave-one-day-out, cross-regime.
6. **Verdict pill** — FIXED (exact config) / REGIME-DEPENDENT / SHADOW / TRULY-RETIRE.
**Lead with what got rehabilitated + deployed; then show the honest FAILURES (PARKED or REFUTED)** — the NULLs are the point (e.g. the regime-conditional-exit NULL, the two-ratchet clip-mirage, the whole "capture MORE of grind's tail" question that closed across 5 independent angles). Feed the two live grind-exit shadow ledgers here too (`data/two_ratchet_shadow.json` runner-clip watch, `data/partial_shadow.json` 2R-partial smoothness). Wired as the dedicated `Rehab` phase in `friday_v7_maxdepth.workflow.js` → `part1_5_rehab.html`, placed right after Part 1. (Precedent: §355 whole-roster rehab was 4-for-4 rehabilitatable — grind/capitulation/rgv_short/exhaustion each a DIFFERENT fix.)

**★ FLAGGED rehab target THIS WEEK — abs_veto EXHAUSTION-CHASE (2026-07-26/27 overnight, ≈−$200).** abs_veto (both sides) took the ENTIRE overnight batch: 6 trades, 4 losers (all `STOP_UNFILLED`, ≈−$192), 2 winners. **Root-cause is the ENTRY, not the exit** — the STOP_UNFILLED was a red herring (the stop-breach guard bounded every loss to ≈1 ATR; the separate stop-fill fix — IBKR won't fire a resting stop's trigger on the continuous ContFuture — rides on branch `fix/stop-contract-concrete-future`, verify pending). Reconstruct MFE/MAE + entry ER/ATR/net from `capture.db`: the 4 losers had MFE **0–7pt** (adverse from the first tick) — abs_veto **CHASED an already-exhausted move**: bought the top of a +95pt up-thrust (@ER 0.52), shorted the bottom of a −97pt down-thrust, fired long into ER-0.05 chop; the 2 winners were thrusts that **CONTINUED** (MFE 32–33). The **`amp_floor`** (`atr_pct≥0.0004`≈11.4pt on MNQ) worked perfectly — it stood abs_veto down for the ENTIRE calm daytime session (ATR 6–10pt → 0 trades) — but it does NOT cover the **elevated-ATR-but-EXHAUSTED** case (overnight ATR 11–19pt cleared the floor while the move was already spent). **Rehab question:** catch the exhaustion while KEEPING the 2 continuation winners — is the 55s absorption-veto biting (it did NOT save the two worst chases)? does an **extension cap** (skip entry when net already > N·ATR) or the `fast=True` start-of-move trigger fix it? Also confirm abs_veto_long's ER≥0.20 floor is actually applied (a loser fired at reconstructed ER 0.05).

### PART 2 — THE SHADOW DESK & PROMOTION
The shadow board ranked by honest `real_pnl` (all-time + this week). **Best sims for promotion**, each with a robustness read (not just the top number):
- **★ abs_veto_55s** — the lead promotion candidate for Monday. Present the full robustness battery (`scripts/abs_veto_robustness.py`): headline, per-day spread, **regime split (chop vs trend)**, walk-forward halves, head-to-head vs un-vetoed thrust. Honest caveats (sample size, concentration). **★ NEW 2026-07-24 — it is a TWO-SIDED gate and BOTH sides earn:** this week LONG +$488 (48%w) AND SHORT +$538 (50%w) = +$1,025 (it is `thrust_loose` + a 55s continuation-confirm that drops ~44% of raw thrusts by re-requiring the burst to persist). **Promote it TWO-SIDED, not short-only** — the live `thrust_short` leaves the long side on the table. Also present the new shadow A/B added today (`thrust_short_raw` vs `thrust_short_absveto55`, short-only + chandelier mirroring the live slot) seeded after `thrust_short` took 3 SPIKE-ENTRY stops (−$127) in the 07-24 violence.
- **Relegation view — REFRAMED 2026-07-24 (do NOT call `rgv_short` a relegation candidate).** The operator's rule: a gate runs TWO-SIDED with INDEPENDENTLY-tuned per-side thresholds; you never relegate a *direction*, you tune the *side*. `rgv_short` is **regime-dependent, not defective** — LIVE proof today: it bled −$345 (13 fires) shorting a choppy up-grind unfiltered, then RECOVERED +$183 aligned on the very next hour's down-trend. Its problem is regime + being unfiltered on chop, not the short direction. So: rank the gates by WHY (day-type / exit-reason), but the *recommendation* is per-side tuning + the router, NOT relegating a side. The long-faders (`rgv_long`/`capitulation_long`) = KEEP + router guard (the router IS the fix — validated live today as it benched them correctly on the down-legs).
- **★ GRIND EXIT SHADOW — two-ratchet runner-clip watch (NEW 2026-07-26).** Run `scripts/two_ratchet_shadow_watch.py` (no `--ping` — the report presents it; the daily cron owns live alerts) and present a subsection from `data/two_ratchet_shadow.json`. Context: grind_long deployed the **pure-6.0 threshold-chandelier** (start_k 3.5 / lock_r 6.0 / lock_k 0.5) on 2026-07-26. The **two-ratchet** (a 2nd mop-up ratchet arm4.0/disarm4.5/b_k1.25 layered on it) was tested three ways (composite, high-arm fall-back, two-ratchet) and REJECTED every time — the reverser $ is inseparable from the runner-retrace zone (only ~$299 cleanly claimable in 2 trades; wk30 delta $0, strip-3 $0). It is SHADOWED to watch the ONE thing the summer-range archive cannot produce: a **RUNNER-CLIP on a real trend day** (the ~17 rMFE≥4R runners carry ~263% of grind's net — they ARE the edge). Present: cumulative shadow-two-ratchet net vs live pure-6.0 net, runner count, and EVERY runner-clip (date, rMFE_R, live$ vs shadow$, $ given up). **Verdict logic:** a clip fired → the two-ratchet stays dead, finding confirmed; ZERO clips over a genuine trend week → EVIDENCE FOR reconsidering it. This is the durable home of the watch (the daily session cron is belt-and-suspenders only).
- **★ GRIND EXIT SHADOW — 2R-partial smoothness (NEW 2026-07-26).** Run `scripts/partial_shadow_watch.py` and present from `data/partial_shadow.json`. The 2R-partial (Lot A scalp-2R banks certainty + Lot B rides the pure-6.0 chandelier for the tail; grind is base_size=2 so it's free) is the ONLY exit lever that survived — but it's a **VARIANCE lever, not a mean-raiser** (backtest: daily-vol −29%, maxDD −24%, worst-day −34%, green-day 53→60%, for a ~$665/3wk mean give-up that is entirely the tail forfeit on the ~17 runners, ~75% offset by reverser gains). Present baseline (deployed 2-lot chandelier) vs partial: cumulative net + mean give-up, daily std, max drawdown, worst day, green-day/week %, and the two equity curves so the smoothing is visible. **Verdict = the operator's mean-vs-smoothness CHOICE, NOT pass/fail** — is the shallower drawdown worth the small mean cost this week. (Regime-conditional exit was a NULL — do not shadow it. Memory `chandelier-momentum-exit-tuning`.)
- The over-trading caveat baked in (shadow overstates — nominates; paper judges).

### PART 2.5 — MID-WEEK MUSINGS (every lead, tested HARD — its own chapter)

**★★★ THIS WEEK — 2026-08-07. Everything below this block that is dated 07-24 is a STALE PRIOR-WEEK
EXAMPLE of the KIND of lead to test; these are THIS week's actual leads. Test each one HARD.**

**(1) ARM FOR PERIODS, NOT RUNS — the week's headline conceptual finding.** Reference case 2026-08-04:
`abs_veto_long` was armed ONCE by the durable router at 04:20Z, unprompted, and left untouched for 18
hours. It lost 6 trades in the ER-0.06 morning chop (−$173.50) then won 10 STRAIGHT in the ER-0.29 /
ATR-doubled afternoon (+$504.00) across FIVE separate entries spanning 13:32–15:40. Day +$330.50.
**Arming is a PERMISSION WINDOW, not a run-timing problem** — the morning losses were the price of the
option. ⚠ THIS EXPOSES AN UNRESOLVED CONTRADICTION the report must settle: three consecutive stopped
pairs is a textbook "wall of STOP → bench" trigger, and applying it on 08-04 would have cost the entire
+$504. "Bench on losses" and "arm for periods" are directly opposed policies. **Quantify which is right,
and state the discriminator** (the 08-04 evidence says it is the REGIME the losses occurred in, not the
losses themselves). Confirmed live 08-07: the same gate went 6-for-8 across four entries for +$248.50.

**(2) DETECTION LATENCY — measured, and it is bad.** Across 324 run episodes in 33 sessions, at the
moment run-state FIRST fires: median **119pt already moved**, median **16pt left**, capture ratio 12%,
**54% of episodes have <20pt remaining** (unusable after costs), only 5% have >50% left. A 49-config
grid search, fitted on the first 23 days and tested on 12 UNTOUCHED days, gives W=10 / net≥60 / ER≥0.55
= **38% usable vs 32%** for the current W=30 / net≥80 / ER≥0.35 (capture 19% vs 12%; strip-best-day
37% vs 31%, so neither rests on one session). REAL but MODEST, and it costs +68% more alerts.
**Report the ceiling honestly: no config in the grid passed ~40%.** Predicting run STARTS is already a
banked NULL on 22.6M ticks — so the verdict the report should reach is whether run-state is better used
as a BENCH instrument (reliable in the negative) than an ARM one, and whether a DWELL requirement beats
a sharper threshold.

**(3) CHURN IS INVISIBLE AT $0 — a new metric the ledger was blind to.** 2026-08-07, 12:30→16:35:
**20 switch changes, only 4 produced a trade.** The other 16 each grade ◻ NEUTRAL in isolation, so the
per-decision scoreboard read clean while the desk armed and benched the same three gates on
3-to-16-minute cycles. **The RATE is the metric** — report changes/hour and changes-that-fired/total
for the week (08-07 was 5/hour and 20%). Three identified causes to test: (a) **threshold hysteresis
with no dwell** — run-state declares at ER≥0.35 and holds at ≥0.30, and with ER sitting exactly on 0.30
a full longs→shorts→longs round trip happened in 8 minutes; (b) **arming a gate whose own geometry
blocks it** — `grind_long` armed at ext 6.11 ATR against its `ext_hi` of 2.0, guaranteed $0; (c) **vol
ratio'd against a window CONTAINING the spike**, which makes rising ATR look like decay (caused one bad
re-arm and one bad refusal the same afternoon). **Recommend a dwell-time spec.**

**(4) THRESHOLD NOISE AT THE ENTRY — quantify it.** `drift`'s efficiency oscillates across its own 0.15
floor: on 08-07 it read 0.157 → 0.114 → 0.150 → 0.158 inside eight minutes, so detection time varies by
~8 minutes and ~50 points depending purely on when you sample. The live service samples once a minute
on a PARTIAL bar; a first-crossing backtest enters systematically earlier. **Report the size of this
sampling bias and whether a 2-of-3-minute confirmation removes it without killing detections.**

**(5) THE WEEK'S INSTRUMENT FAILURES — three tools returned confident wrong numbers.** (a) `capture.db`
keeps 5 TRADING days, so `nipc_replay.py` and `claim_audit.py`, which ATTACH it, silently ran on 6 of 12
days and 2 of 14 claims — zero rows, not an error. (b) `(bar_ts/60)*60` is a NO-OP in DuckDB (float
division), so a hand-rolled tape read consumed 5s bars as 1m bars, understating ER ~4x and ATR ~6x.
(c) `signal_journal.suppressed_by` is NULL in all 596 rows despite being in the INSERT, so
`COALESCE(...,'TAKEN')` reports every fire as taken — including on benched gates on a zero-fill day.
**These are not anecdotes: they mean a number in a prior report may be wrong. Audit the tooling the
report itself depends on and say plainly which past figures are now suspect.**

**(6b) ⚠⚠ THE DAY RIDER HAS NO LEDGER — DO NOT REPORT ITS P&L AS $0, REPORT THE GAP.**
Discovered 2026-08-07 21:40Z: `day_rider.py` contains ZERO references to `record_trade` or the store —
it has never written a trade row. Its 2026-08-07 trade (SHORT 2 @ 29567.25, entered 14:12Z, flattened
at the 20:40 clock, **-252.8pt = roughly -$1,010**) exists ONLY as `ahead_pt` in
`data/day_rider_state.json`, which is overwritten each session. The ONLY `day_rider*` rows in the trade
table are `day_rider_crossdesk` (n=2, -$95.50, 08-06) — and those were written by the TOURNAMENT because
it saw fills on its own clientId. **So the only day-rider activity ever recorded is the cross-desk
FLATTEN BUG; the strategy itself has never been recorded once.**
`pnl.realized(desk="day_rider")` therefore returns $0.00 / n=0 and is technically correct — there is
nothing to read. **The section must state this plainly as a MEASUREMENT GAP, reconstruct what it can
from `day_rider_state.json` + the raw tape, and NOT present $0 as a result.** A `record_trade` write
path is scheduled to be BUILT Saturday 2026-08-08 alongside the play ledger. Until then the day-rider
cannot be graded, only remembered — say so.

**(6) ★ THE DAY RIDER IS ITS OWN SECTION THIS WEEK — see the DAY RIDER section. One additional
BACKTEST THE OPERATOR HAS EXPLICITLY REQUESTED FOR THIS REPORT: the REGIME-EXIT TAIL TRADE-OFF.**
Tonight's deployed change is the ATR-scaled trail (arm 4xATR, trail 2xATR) which backtested $7,341 vs
$3,732 for the fixed +150pt/100pt rule over 35 detected sessions on identical entries. But a
REGIME-EXIT (leave when efficiency decays below ~0.10, i.e. the tape stops being the tape that
justified entry) produced a completely different RISK SHAPE: **worst day −$548 instead of −$2,453 (a
78% tail cut) for a total of $5,500 instead of $7,341, and days-green 40% instead of 71%.** The
operator's question, verbatim: is that trade worth it? **Backtest it properly** — sweep the efficiency
exit threshold, test regime-exit COMBINED with the ATR trail (whichever fires first), report the full
distribution not just the total (median, worst decile, days-green, and how often a trade that is
−250pt at 15:00 recovers), and give a recommendation with the risk-appetite trade-off stated in plain
English. ⚠ Re-derive independently; do NOT inherit the numbers above.

**(7) SHARED-ACCOUNT ARCHITECTURE — three defects found and fixed live this week, all the same family:
an order or a position outliving the thing that owned it.** (a) a redundant MKT close was *forgotten*
rather than cancelled when a stop won the race, and filled into a **phantom opposite position**
(−$35.50 live); (b) `_stop_seq` restarts at 0 so a restarted desk re-mints `stp-000001` refs that are
STILL RESTING at IBKR — and fills attribute BY REF, which is the 08-06 mis-attribution mechanism;
(c) `reconcile()` compared the tournament's slots against the WHOLE account net, so the day-rider's
legitimate 2 lots read as a leak and **halted the desk for 24 minutes with its entire safety block
skipped**. All three now have regression tests. **The report should ask the generalising question:
what else on this desk assumes it is the only participant?**
Each mid-week lead walked in plain English: the test and the honest verdict (HELD → where it landed / REFUTED → why). Nothing silently dropped. **★ NIGHTLY-ROLLUP WEEK-IN-REVIEW (operator 2026-07-28 — "monitor each night, fold into Friday"):** roll up EVERY `data/router_nightly/*.json` (`scripts/router_nightly.py`) + `data/selector_nightly/*.json` (`scripts/selector_nightly.py`) for the week. ROUTER: per-day net value (blocked-losses-saved − wins-missed) + leakage (managed-gate losers while ON, by regime) → net-positive / over-benching / where leaking. SELECTOR: per-day optimal-pick % + regret ($ vs best-of-3) + selector-vs-fixed + systematic wrong-pick pattern (WIDE-in-violence / TIGHT-on-runners). Show the week TREND; both tick-honest ESTIMATES (benched/non-chosen exits never ran) — say so. The durable home of the nightly monitoring; the router_study below then OPTIMISES off it. **★ FLAGGED THIS WEEK — interrogate the DIRECTION-ROUTER's architecture (operator, 2026-07-24):** we built a router on a **15-min timer** that replays the Paris-day regime from capture, flips `gate_switches.env`, and benches the counter-trend reversion faders (2-mark hysteresis). It works (backtest +$580 Mon–Thu, no negative day; live-validated overnight). But the report's job is to ask **is this the BEST way to achieve the objective, or is there a more ELEGANT one?**
- **OBJECTIVE (state it plainly):** stop a gate trading *against a proven trend* (the direction-blind ER bands fade a clean down-trend), reactively, without over-clipping the chop days the faders earn on.
- **WHAT WE BUILT + its costs (from live data):** a polling timer + switch-file. Known costs surfaced this week — **reaction lag** (can't bench until a trend is proven ~15-30min in; `rgv_short` −$64.5 fading a fresh up-move before the bench), **sticky-exit** (over-holds a trend through alternating chop — the fast_exit fix backtested +$0 so it's dormant), **whipsaw churn** on a fast-flipping day, and a **partial-bar-vs-replay** artifact between live runs and clean replays.
- **WHAT ELSE — research + BUILD + BACKTEST the alternatives** against the current router on the week's data: (a) **per-gate direction-guard IN-CODE** — a directional veto inside each fader's gate function (no long-fade when VWAP-slope/net-bias is down), per-tick, no polling lag, no switch-file, no separate service (the Saturday option-A end-state); (b) **event-driven flip** (bench on a confirmed regime-change event, not a 15-min poll); (c) **continuous in-tournament regime gating** (the tournament computes regime each tick and gates the open directly — no router service, no file at all); (d) tuning the timer granularity. For each: does it cut the reaction-lag / whipsaw the polling router can't, and does it keep the +$580? Verdict: keep the router as-is, or migrate to a more elegant mechanism — with the backtest to back it. This is a genuine architecture question the report should answer, not assert.

**★ FLAGGED THIS WEEK #2 — the rgv ABSORPTION-CONFIRM: LIVE at 12:27 then REMOVED at 14:06 UTC (both operator, 2026-07-24) — tell the FULL arc, it's the week's best lesson in forward-validation.** (1) It went live 12:27: `rgv_long`/`rgv_short` delay entry 35s and only fade if the faded move ABSORBS (`deciders.confirm_absorption`), ER band removed — justified by a ONE-week tick-honest grid (rgv book −$556 → +$228, 35s/62%w). (2) It came OFF at 14:06: a **2-week** tick-honest re-test (`scripts/rgv_confirm_layer.py`, 07-15..17 + 07-20..24) showed the confirm is a **blunt exposure cut, not a stabiliser** — it DESTROYS the short side's robust tight-ext edge (2-wk net **+$670 raw → −$180 confirmed** at ext3.0/turn0.15) and only marginally trims the weak long bleed; the one-week win didn't survive a second regime. rgv reverted to raw base (ext 2.0, no ER band, no confirm). (3) Then LIVE forward evidence the SAME afternoon sharpened it into a **regime-specific verdict**: unfiltered `rgv_short` bled **−$345 (13 fires)** shorting a choppy up-grind (ER 0.06) — the confirm would have blocked those knife-shorts — but then **RECOVERED +$183** aligned on the next hour's clean down-trend (ER 0.29). **So the confirm's value is REGIME-SPECIFIC: it earns its keep in chop / counter-grind, is dead weight on a clean aligned trend.** **THE A/B (do this): 3 phases** off `data/rgv_confirm_live_at.json` (`live_at_epoch` + `confirm_removed_at_epoch`) — pre-12:27 (ER-band) → 12:27–14:06 (confirm) → post-14:06 (raw base). Net/win%/$/tr/participation per phase; be honest each phase is only a few thin live hours. Verdict the report should reach: NOT "confirm good" or "confirm bad" — **"confirm is a regime-conditional filter; the open question is whether to re-enable it ONLY when the router reads chop."** Tools: `rgv_confirm_layer.py`, `absorption_confirm_{sweep,grid}.py`, `abs_veto_explain.py`.

**★ FLAGGED THIS WEEK #3 — rgv PER-SIDE BASE GRID + the cross-week REGIME test (2026-07-24). The two-sided-gate principle, proven.** Tick-honest per-side sweep of the raw `gate_reversal_grab` base (`scripts/rgv_base_grid.py`, ext_min × turn_atr × flow_min, exit repriced on capture.db ticks). Findings to narrate: (a) **the two sides want OPPOSITE bases** — SHORT's own optimum (ext 2.0, flow 25) vs LONG's (ext 3.0, no flow); mirroring short→long costs −$481, mirroring long→short leaves +$457 on the table. (b) **The flow-confirm is regime-luck** — helped short this week (+), was CATASTROPHIC last week (−$600 to −$810); keep flow OFF. (c) **The asymmetry is REGIME, not structural** — re-run on last week (07-15..17): both weeks leaned down yet the sides swapped leadership and the best cell drifted, so a single week's optimum is partly overfit. This **vindicates the router and refutes relegating a direction** — which is the whole point of the two-sided-gate rule (see the reframed Relegation view above). (d) **The one cross-week-robust edge: SHORT at tight-ext (2.5–3.0), no flow, no confirm** (~+$300 both weeks); LONG has no stable green zone → it's a **router problem, not a filter one.** Saturday's per-side-tuning candidate: move rgv SHORT to a tight-ext base, formalise LONG as router-only. Present the grids as tables (the operator loves clear per-cell facts).

### PART 3 — ★ HOW WE GRAB THE BIG RUNS (the closing deep-dive — the section the operator loves)
Cold and tape-first: **ignore what the desk did mid-week**; start from the raw L1/L2 tape and ask where the money was and whether we showed up. **MNQ-led but now two-symbol**, and deep (our tape + 58.9M-row L2 book). Movement 1 runs a census for
MNQ **and** MGC; the greenfield movement includes a dedicated gold hunt (`gf_MGC`). THREE MOVEMENTS:

**Movement 1 — the full runs census (the long table).** Tool: `scripts/run_census.py`. Every 15-min move ≥ **1.5× MNQ's typical range** — the FULL census, EVERY run, **never a top-N** (07-17 wrongly showed top-30 of 207 — do not repeat). Columns per run: `time · dir · move(pt) · $ 1-lot ceiling · us (caught/FOUGHT/sat) · GATE · real$ · flow (net aggressor) · pre-run amp% · L2 book (far-side depletion) · cause-cluster`. Then: the **cause-cluster taxonomy** (VACUUM / FLOW-LED / OPEN-NEWS / UNCLASS) with a per-cluster caught/fought/sat + ceiling-$ table; the **pre-run signal funnel** (rvol/atr%/vwap-dist/vwap-slope by cluster) with the honest-null callout when the tape doesn't lead; the **per-run L2 book read** (did depth telegraph the move?); and the **ceiling-vs-honest-money reconciliation** (caught N → +$X of $Y ceiling = conversion%; fought → wash; sat-out → $0 = the money on the table), tied to the actual gate.

**Movement 2 — the idle-gate lab.** Could the desk's EXISTING gates have caught the misses? Fire them mechanically on every run, all week: `rule→gate | trigger | exit`, a scoreboard (`fires · net$ · win% · $/fire · big-moves-caught X/N · verdict`), a cumulative-P&L curve, a why-each-loses paragraph, a `DON'T ARM`/`HONEST NULL` verdict. A null is a result.

**★ MAXIMUM DEPTH MANDATE (operator 2026-07-24):** build this like a hedge-fund research team, not a single pass. Run a LARGE multi-agent workflow — MANY agents: multiple per movement, a dedicated greenfield agent PER cause-cluster (VACUUM / FLOW-LED / OPEN-NEWS / UNCLASS), per-run order-book dissections, and an adversarial SKEPTIC that re-runs EVERY surviving claim from scratch. Depth over brevity. The census must be frozen ONCE (run `run_census.py` on the completed week) and every movement reads that same frozen snapshot (no sliding-window drift).

**Movement 3 — the greenfield lab (invent gates from scratch, backtest to death). ★ DO NOT GIVE UP — the escalating hunt (operator 2026-07-24):** the FULL census mixes marginal 75pt runs with 300pt monsters; the monsters may carry a cleaner footprint the marginal ones wash out. So this is a LOOP, not one attempt:
1. Invent ~5 candidate gates on the FULL sat-out census, backtest tick-honest. If one survives robustness → present it (SHADOW).
2. **If all 5 die → DO NOT STOP. Narrow to the TOP 25 runs by size** (the biggest, cleanest moves) and hunt again — stronger footprints may separate there. Fresh candidates, fresh backtests.
3. **Still nothing → narrow to the TOP 15.** Try again. A team of hedge-fund analysts would not give up after one null; neither do we.
4. Show EVERY attempt at EVERY narrowing level — every failed candidate at full-census, at top-25, at top-15 — each PARKED with what would revive it, or REFUTED with the test that killed it — that trail IS the value (where does an edge start to appear as we filter to the strongest runs?). Only after the top-15 hunt also comes up empty is a NULL the honest verdict — and even then, name the ONE stone still unturned for next week. The escalation itself often reveals the edge: report the size-threshold at which a footprint becomes tradeable, if any.

Start from the specific missed-run clusters. **Family A (catchable) vs Family B (uncatchable)** precursor split (dissect the 10 min before each run). THE FAILURES, shown by name with their losing stats — the operator's favourite honesty device. ★ Each one dispositioned: **PARKED** with the specific condition that would revive it (more n, a filter, a regime), or **REFUTED** with the named test and why no reformulation saves it. Never "grave" — that word retired 2026-08-07 because leads buried under it have since been resurrected by better interrogation. A mechanical `Component | Rule` spec per survivor (thrust/participation/entry/stop/exit/costs) + what was left out and why. Full backtest apparatus: the **parameter sweep** (edge only appearing as n collapses = curve-fit tell), a cumulative-P&L curve, the excursion "killer statistic," a 250ms **book-imbalance separation** table, a **day-by-day** table, and the robustness kills — **strip-the-3-best-trades**, **long/short symmetry**, **cost-stress**, and an **out-of-sample leg** (archive days / held-out window). Every invented gate carries a **`big-moves-caught: X/N`** column against the exact runs the census proved we missed (the "stitch" 07-17 dropped). Verdict pills `LIVE`/`SHADOW`/`PARKED`/`REFUTED` + a skeptic-caveat list, then a second adversarial re-run that downgrades even survivors. Never a premature green light. Backtest tools: `scripts/gate_backtest_tickhonest.py`, `scripts/footprint_backtest_duck.py` (tick+L2, DuckDB).

---

## Tooling (V7-native)
- `scripts/run_census.py` — Movement-1 census (V7 rebuild of the V5 `footprint_scorecard.py missed`, which was hardcoded to the retired alphabot.db/ticks.db).
- `scripts/gate_backtest_tickhonest.py` · `scripts/footprint_backtest_duck.py` — greenfield backtests, tick-honest + L2.
- `scripts/abs_veto_robustness.py` — the promotion battery.
- `scripts/two_ratchet_shadow_watch.py` — the grind-exit two-ratchet runner-clip watch (READ-ONLY; reprices live grind_long trades under pure-6.0 vs two-ratchet, flags runner-clips → `data/two_ratchet_shadow.json`).
- `scripts/partial_shadow_watch.py` — the grind-exit 2R-partial smoothness watch (READ-ONLY; reprices live grind_long trades as 2-lot chandelier baseline vs Lot-A-scalp-2R + Lot-B-chandelier, tracks variance/drawdown/curve → `data/partial_shadow.json`).
- `scripts/rgv_base_grid.py` — per-side rgv base sweep (tick-honest), `--since/--until` for the cross-week regime test. `scripts/rgv_confirm_layer.py` — the confirm on/off across both weeks (the exposure-cut finding). `scripts/momentum_veto_sweep.py` — momentum-gate veto sweep.
- DuckDB + pandas for ALL analytics (the standing rule). Publish via `scripts/friday/publish_report.py` (hard gate: ≥20 sections, ≥25k words — a thin report is refused).
- ★ **CHARTS: RUN CHARTS ONLY** (operator, 2026-08-01). He does NOT want generic statistical figures — the stats are read as prose + fact-tables, and a proofreader must NEVER flag "no charts" as a defect. The old blanket `≥15 charts` gate is RETIRED.
  **What he DOES want, and loves:** a **price chart of the RUN itself** — the real price path of a big move / case-study session with **where we entered and where we exited marked on it** ("I love seeing the chart and when we jumped and when we exited"). This is visual trade review, not decoration.
  **Where:** Movement 1 (chart the biggest runs, marked caught / fought / sat-out), the Part-1 live-desk case-study days (mark every gate entry + exit on the day's path), and any greenfield candidate presented with trades. Inline self-contained SVG built from `capture.db` ticks + the REAL fills — never an external image, CDN or JS library.

## Do-not-repeat (the 07-17 regression)
Full census not top-N · the 9+ columns incl. flow/amp/$-ceiling/book · the cluster taxonomy + pre-run funnel + per-run L2 read · ceiling-vs-real reconciliation · greenfield STARTED from the missed runs with a big-moves-caught column · full param sweep + cumulative curve + excursion + book-separation tables + OOS leg. This section is the last and biggest; it is where the report earns its keep.
