# gate_switches.env comment header, archived 2026-08-26
# Removed because switch_notes() splices the TOP 45 lines into EVERY router prompt and these
# had become an unmanaged FIFO of expired carve-outs. Nothing here is deleted — it is history.

# ★★2026-08-24T13:46Z OPEN-HOUR WATCHER ARMED abs_veto_short on a CONFIRMED
# break — ER 0.35>=0.35 · ATR 20>=18 · bias -418pt DOWN · NEW EXTREME (28962 vs H29473/L28962)
# Operator standing instruction 2026-08-05: "if a huge trend develops you arm gates
# immediately and let them run". This is the aligned-momentum arming that did NOT happen
# for 17 minutes on 08-04. ROUTER: this was a full break-trio pass, not a delta blip —
# LET IT RUN unless the trend STRUCTURE breaks ([[us-open-dont-bench-trend-rider]]:
# hold aligned momentum THROUGH open stop-outs). You retain full authority to bench;
# this watcher will NOT re-arm today whatever you decide, so there is no tug-of-war.
# ★★2026-08-21T14:03Z OPEN-HOUR WATCHER ARMED abs_veto_short on a CONFIRMED
# break — ER 0.36>=0.35 · ATR 22>=18 · bias -56pt DOWN · NEW EXTREME (29268 vs H29531/L29268)
# Operator standing instruction 2026-08-05: "if a huge trend develops you arm gates
# immediately and let them run". This is the aligned-momentum arming that did NOT happen
# for 17 minutes on 08-04. ROUTER: this was a full break-trio pass, not a delta blip —
# LET IT RUN unless the trend STRUCTURE breaks ([[us-open-dont-bench-trend-rider]]:
# hold aligned momentum THROUGH open stop-outs). You retain full authority to bench;
# this watcher will NOT re-arm today whatever you decide, so there is no tug-of-war.
# ★★2026-08-19T18:15Z OPERATOR BENCH — abs_veto_short OFF.
# "turn abs veto short off. i dont want to give back all profit."
# Day ran +$182 at 14:30 (both legs claimed) and gave it ALL back to -$29 with a 6-trade
# losing streak. ROUTER: this gate is PINNED in router_tick_durable.py until 21:55Z — do not
# propose changes to it. Blocks NEW entries only; opens still exit, stops untouched.
# ★★2026-08-13T13:58Z OPEN-HOUR WATCHER ARMED grind_long on a CONFIRMED
# break — ER 0.45>=0.35 · ATR 18>=18 · bias +357pt UP · NEW EXTREME (30174 vs H30174/L29782)
# Operator standing instruction 2026-08-05: "if a huge trend develops you arm gates
# immediately and let them run". This is the aligned-momentum arming that did NOT happen
# for 17 minutes on 08-04. ROUTER: this was a full break-trio pass, not a delta blip —
# LET IT RUN unless the trend STRUCTURE breaks ([[us-open-dont-bench-trend-rider]]:
# hold aligned momentum THROUGH open stop-outs). You retain full authority to bench;
# this watcher will NOT re-arm today whatever you decide, so there is no tug-of-war.
# ★★★2026-08-11T14:1xZ — OPERATOR CARVE-OUT (expires 16:00Z, then normal rules resume).
# Operator watching the reversal: "huge up run now why arent we arming longs. way too slow."
# ARM abs_veto_long. HONOUR THIS UNTIL 16:00Z — do not re-bench it on the 60-min segment alone.
# THE 60-MIN SEGMENT IS BLIND TO THIS MOVE and that is an instrument fault, not a judgement call:
#   last 15min UP +113pt ER 0.704 | 20min UP +115pt ER 0.470 | 30min UP +74pt ER 0.188
#   last 60min DOWN -70pt ER 0.103   <- the ONLY window the direction rule sees
# The hour opened ABOVE the dump, so a 60-min net averages a V-reversal away to nothing.
# ⚠ WHY ONLY abs_veto_long, and why the operator's read is only HALF right:
#   · STRUCTURE HAS NOT BROKEN. Price 29774 is 59% of the 2h range (low 29636 / high 29871.5) —
#     this is a RETRACE of the open dump, not a break to new highs. MONDAY #4's trio is NOT met:
#     ER climbing YES, vol expanding YES vs baseline, structure break NO.
#   · Vol is already rolling over: mean 1m range by 15-min block 8.6 -> 28.3 -> 31.9 -> 22.0.
#     Sustained ER on CONTRACTING vol decays in 20-35min (vol-expansion-is-the-binding-leg).
#   · So abs_veto_long ONLY — a VETO gate: it needs a real thrust that SURVIVES the 55s re-test,
#     so it cannot chase a fading bounce. Veto-gates are ~0-cost armed; churners buy the reversal.
#   · grind_long STAYS BENCHED: last-hr ATR 13 vs ATR_FLOOR 22. Arming it is theatre - it was
#     refused 750 times this morning at atr=7.8. Do not arm a gate below its own entry floor.
#   · capitulation_long STAYS BENCHED: long-side reversion into this tape, and its shadow family
#     is the day's worst board (capit_loose -478.5, live_mirror -274.5).
# Day is +$298.50; the 14:01 exhaustion_short pair already paid -$122.00 into this reversal.
# ★★★2026-08-09T11:0xZ — SATURDAY #1 + MONDAY #1 SHIPPED. abs_veto_short IS ARMED BY DEFAULT.
# SHIPPED TODAY (router side, scripts/router_tick_durable.py):
#   · Armed by default. The two bad bench rules are DELETED: the VIOLENT-WHIPSAW bench (old rule
#     (b), ATR>=19pt AND ER30<0.25) and "bench on a stop-out pair". DO NOT RE-CREATE EITHER.
#   · EXEMPT FROM THE CHOP BENCH (MONDAY #1). When you bench momentum on confirmed chop, this gate
#     STAYS ARMED. Grade the chop bench on the non-carved-out book only.
#   · The 22:00 reopen keeps it armed: reactivate_gates.py starts only grind_long / abs_veto_long
#     benched (MONDAY #2), and abs_veto_short is deliberately NOT in that set.
# WHY: +$2,290.50 over 159 fires / 17 days, 4-of-4 weeks green, POSITIVE IN ALL FIVE REGIMES
#   INCLUDING CHOP, and 53 of 54 filters tested LOSE to just letting it fire. Over the 96.7% of last
#   week it sat benched its shadow twin made +$1,064.50; the router armed it for the 9% in which it
#   lost -$559.00. The arming was backwards on BOTH sides.
# ⚠ NOT SHIPPED, and do not assume it is filtering: the BUILDING x 13:30-20:00Z per-entry veto that
#   SATURDAY #1 also calls for is NOT in the live code. No BUILDING regime exists anywhere in src/ —
#   it lives only in a backtest harness whose cut points are sample percentiles. The gate is armed
#   by default with NO new veto in front of it. Deferred to the Saturday window, deliberately.
# ⛔ NO ER FLOOR ON THIS GATE, EVER. "ER30>=0.35" is REFUTED (keeps 5 of 15 winners, bins $1,363,
#   dies at strip-1). deciders.ER_FLOOR is {} and the deletion is pinned by tests/test_deciders.py.
# ★ BENCH AUTHORITY YOU RETAIN, and nothing else: execution pathology (naked stop, absurd
#   entry_atr, MAX_HOLD stacking), and the standing DIRECTION rule (day-bias UP>=+40 -> bench
#   shorts). A losing run is NOT a reason — the review below judges it, not a bad hour.
# ★ REVIEW: after 15 fires armed-by-default, re-bench if the armed book is negative over those 15.
#   COUNT THEM — the count starts at the 2026-08-09 22:00Z reopen, not before.
# ⛔ EVERYTHING BELOW DATED 2026-08-07 IS EXPIRED intraday commentary — its own "(d) 17:00Z hard
#   re-judge" passed two days ago, and its price levels (29760, 29674.50) are from Thursday. In
#   particular its "TIGHT LEASH ... bench on (a) ONE stop-out pair" for abs_veto_short is exactly
#   the rule SATURDAY #1 DELETED. Ignore that block; it is retained only as history.
# ★★★2026-08-07T16:27Z RUN SHORT — flipping the book to the aligned side.
# RUN STATE: RUN SHORT, -97pt over 43m, began 15:44Z at 29812. Aligned side = SHORT.
#   ER 10m 0.87 / 15m 0.72 / 30m 0.43 (accelerating) · ATR14 19.6 = x1.47 SESSION · participation x2.43
# ★ capitulation_long OFF — MY OWN LEASH TRIGGER (b) FIRED, the one I wrote at 16:21: 'bench on
#   RUN STATE declaring a RUN in EITHER direction (then it is counter-trend or chasing)'. It is a
#   dip-buyer and this is a declared down-run: it would buy every knife on the way down. Honouring
#   the replacement leash exactly as written — which is the point of having written it.
# ★ abs_veto_long OFF — counter-trend LONG in a declared RUN SHORT (in-run counter wins 0-6%).
# ★ abs_veto_short ON — the aligned gate. ER is strong and ACCELERATING (0.43->0.72->0.87 as the
#   window shortens), vol is expanding against the SESSION baseline (x1.47, not x-vs-spike), and
#   participation is x2.43 — this is a real move with real volume behind it, not drift.
# ⚠ THE HONEST WEAKNESS, stated: STRUCTURE has NOT confirmed — price 29715 is still 40.5pt ABOVE
#   the 2h low 29674.50, so this is a hard pullback that RUN STATE has declared, not a break to new
#   lows. Two legs strong, one absent. I am arming on the declared run + the operator's (e)
#   lean-optimistic directive, NOT on a complete trio. Grade it as such.
# ⚠ exhaustion_short LEFT ON deliberately — it fades exhausted UP moves, so in a down-run its setup
#   simply will not appear. Inert, not counter-trend; no reason to touch it.
# ⚠ TIGHT LEASH (this gate is 0-for-3 today for -$155.50): bench on (a) ONE stop-out pair,
#   (b) ER15 back under 0.30, (c) price reclaiming 29760, (d) 17:00Z hard re-judge.
# ★★2026-08-07T16:21Z capitulation_long KEPT ARMED after a stop-out pair — JUDGEMENT CALL, and it
# goes against the letter of my own 13:17 leash. Recording it so it can be graded either way.
#   16:19:26 A LONG 29800.25 -> 29788.25  -$25.50 STOP
#   16:19:26 B LONG 29800.50 -> 29788.00  -$26.50 STOP     -$52.00 in 20 seconds
# ★ WHY THE 13:17 LEASH IS TREATED AS EXPIRED, not ignored: it read 'bench on its FIRST stop-out
#   pair' and its STATED REASON was 'in-run counter is genuinely bad, and I am overriding that stat
#   on mechanism grounds, so it must prove it'. That leash existed to BOUND AN OVERRIDE — keeping a
#   fader armed COUNTER-TREND inside a declared RUN SHORT. RUN STATE is now NO-RUN, the gate is
#   armed under normal policy rather than under that override, so the bound expired with the thing
#   it bounded. My error was writing a trigger without an expiry, not applying it now.
# ★ THE EVIDENCE FOR KEEPING IT: regime is NO-RUN with ATR14 x0.93 session — quiet chop, which is
#   capitulation's HOME tape, the exact condition it made +$207 in at 12:29. Net on the day it is
#   still +$155.00 (2 targets, 1 stop pair). [[arm-for-periods-not-runs-0804]]: a losing streak is
#   NOT by itself a bench trigger — ask whether the REGIME explains it, and here it does (bought a
#   dip that kept going, bounded to $49 by a tight 12pt stop).
# ⚠ I ALSO ARGUED TO BENCH THIS GATE FOUR TIMES THIS MORNING AND WAS WRONG EVERY TIME
#   ([[dont-bench-a-coiled-gate-on-quiet-tape]]). That is a reason to distrust my instinct to bench
#   it, NOT a reason to keep it armed forever — hence a real replacement leash below.
# ⚠ FRESH LEASH, with an expiry this time: BENCH capitulation_long on ANY of
#   (a) a SECOND stop-out pair today (i.e. one more), regardless of regime;
#   (b) RUN STATE declaring a RUN in EITHER direction (then it is counter-trend or chasing);
#   (c) 17:30Z hard re-judge.
# ★★2026-08-07T15:23Z exhaustion_short BENCHED — RUN LONG declared, and this is (c2)'s OWN
# stated exception, not the direction rule I carved it out of.
# RUN STATE: RUN LONG, +84pt/32m, began 14:51Z at 29694.5. Aligned side = LONG. exhaustion_short is
# a SHORT fader, so it is now COUNTER-TREND in a declared run, where in-run counter wins 0-6%.
# ★ THE DISTINCTION THAT MATTERS: (c2) removed ONE trigger — benching on the DAY-BIAS SIGN. It
#   explicitly preserved 'bench it when a trend/run is genuinely running against the fade'. That is
#   exactly this. Benching on MECHANISM, not on the sign of the day.
# ⚠ It goes off GREEN: +$104.00 today on 2 fires (A +$54 TARGET, B +$50 CHANDELIER) — the carve-out's
#   first sample and it paid. Benching a winner because the regime turned is the correct call, not a
#   verdict on the gate. Re-arm it the moment the run dies.
# ★ NOT arming the momentum longs, and the missing leg is STRUCTURE: price 29779 is NOT a new
#   extreme (2h high 29805.50, session high 29859.25) — a rally inside the range, not a break. Also
#   RUN STATE's own warning fires: vol is 0.66x session average, and it says a run on collapsing
#   volume is DRIFT, not a move. grind_long is structurally BLOCKED anyway (ext +9.77 ATR vs its
#   ext_hi 2.0). Arm the aligned longs on a genuine new high with participation, not before.
# ⚠ RE-JUDGE: arm aligned longs on a new session high with vol >= 1x session; re-arm
#   exhaustion_short when RUN STATE returns to NO-RUN.
# ★★2026-08-07T14:09Z abs_veto_short BENCHED — MY OWN TRIGGER (b), not the agent's argument.
# ER15 0.279 is under the 0.30 line I wrote at 14:06. The premise decayed FAST: ER15 0.545 -> 0.279
# in three minutes, 10m ER 0.08, 30m ER 0.13, price bounced 28pt off the 29634 low to 29663.
# The break stalled. Armed 14:06, benched 14:09, NEVER FIRED — cost $0. The expiry did its job.
# ★★ WORTH RECORDING FOR THE LEDGER — the open-hour agent told me to ARM at 14:05 and to BENCH at
#    14:08, three minutes apart, and its BENCH case was WEAKER than its own ARM case:
#      - it cited '0-for-3 today, every exit a STOP' — the exact losses it had itself correctly
#        discounted at 14:05 as 'counter-trend shorts fired INTO THE UP LEG'. Same facts, opposite
#        conclusion, no new evidence.
#      - it cited 'day-ER 0.03' — the DILUTED DAY AGGREGATE this file names as a standing error.
#      - 'a wall of stops paying it nothing' is the mechanical rule that on 08-04 would have fired
#        at 11:45 and cost the entire +$504 ([[arm-for-periods-not-runs-0804]]).
#    I am benching because MY WRITTEN NUMBER FIRED. Had it not, I would have held against that
#    advice. An agent that argues both sides within three minutes is a signal to check the tape,
#    not an instruction — and the written trigger is what makes that distinction decidable.
# ⚠ vol is still x3.75 session baseline (ATR14 45.2). This is a VIOLENT tape. Re-arm only on a
#   fresh trio with ER15 back over 0.35, not on the next 5-minute lurch.
# ★★★2026-08-07T14:06Z abs_veto_short ARMED — aligned short into a confirmed downside break.
# TWO INDEPENDENT AGENTS AGREE, on different features:
#   my d2 trio check: new 2-HOUR LOW 29634.75, ER climbing 30m 0.26 -> 20m 0.36 -> 10m 0.48,
#                     ATR14 39.8 vs SESSION baseline 11.9 = x3.35 expansion, 30m net -153pt.
#   open-hour agent [ACT]: 3 consecutive lower-high/lower-low 5m bars broke the 13:26-13:51 floor
#                     29683 -> 29616, net_atr_5 -1.84, ER15 0.545 vs ER30 0.188, ATR 33 -> 38.1.
# ★★ THE ARGUMENT THAT CHANGED MY MIND, and it is the ledger's own principle: I was about to hold
#    until my 14:15 clock because this gate is 0-for-3 today for -$249.50. But ALL of those were
#    COUNTER-TREND shorts fired INTO THE UP LEG at 13:30/13:33. This is a DOWN leg. Judging a gate
#    on its performance in the opposite regime is the exact aggregate error the file keeps catching
#    (SEGREGATE BY REGIME, ALWAYS). My 'ER 0.26 is at its whipsaw bench line' objection was also the
#    DILUTED 30m window — ER15 is 0.545, miles clear of the 0.25 line.
# ★ Waiting 9 more minutes for an arbitrary clock while two agents call [ACT] on a confirmed break
#   is the hesitation the operator's (e) directive exists to stop. Overriding my own 14:15 note
#   deliberately and on stated evidence, not by forgetting it.
# ⚠ exhaustion_short deliberately LEFT OFF — this is an EXTENSION, not a roll-over fade; wrong tool.
# ⚠ EXPIRY, tight because this gate has real failure history: bench on (a) ONE stop-out pair,
#   (b) ER15 back under 0.30, (c) price reclaiming 29700, (d) hard re-judge 14:40Z.
# ★★★2026-08-07T13:52Z abs_veto_long RE-BENCHED — the 13:50 auto-re-arm was made on a FALSE NUMBER.
# The tick's stated premise was 'ATR14 39.1 -> 27pt, the open spike is over, so this is now plain
# chop'. MEASURED FROM THE TAPE AT 13:51: ATR14 = 42.1pt. Vol did NOT decay - it went UP from the
# 39.1 of 13:36. The re-arm therefore rests on a number that is not real, and carve-out (c) ('bench
# abs_veto_long on VIOLENCE, not on chop') actually argues the OPPOSITE way at ATR 42.
# Segment right now: 20m ER 0.03 on an 83pt range, 30m ER 0.11 — still whipsaw, not chop, not trend.
# ★ THE OPERATOR SAID 'narrow it' AT 13:38 AND THAT INSTRUCTION STANDS. The durable tick does not
#   read the chat, and my 13:38 note here was PROSE — the tick reasoned straight past it. Prose in
#   this file does not bind the tick; only router_tick_durable.py guidance does. Fixed there now.
# ⚠ HOLD: capitulation_long ONLY until 14:20Z. Re-arm before then ONLY on a real trio (structure +
#   ER climbing + vol EXPANDING measured against the SESSION baseline, not against the spike).
# ★★★2026-08-07T13:38Z NARROWED TO ONE GATE — operator: 'narrow it'.
# BENCHED: grind_long, abs_veto_long, exhaustion_short.  KEPT: capitulation_long ONLY.
# WHY: the 13:30 open is a VIOLENT WHIPSAW, not a trend. Since 13:25 the tape has travelled 206pt
# of PATH for 30pt of NET (efficiency 0.146), 109pt range in 11 minutes, ATR14 doubled to 39.1pt:
#   13:28 29696 -> 13:34 29805 (+109 in 6min) -> 13:36 29744 (-61 in 2min)
# We were armed FOUR gates wide and on BOTH SIDES (3 longs + exhaustion_short). In a whipsaw that is
# the maximum-bleed configuration: whichever way it lurches something fires and is stopped on the
# snapback. Today already proves it — three short entries stopped in 90s for -$280, of which ~$100
# was pure SLIPPAGE (stops filling 11-20pt THROUGH their level in 39-ATR tape).
# ★ WHY capitulation_long IS THE ONE KEPT: it is the only gate that has made money today (+$207 at
#   12:29), and its mechanism BUYS FLUSHES rather than chasing extension — the one edge that is not
#   automatically destroyed by a snapback. It keeps its 13:17 leash: bench on its FIRST stop-out pair.
# ⚠ This is a RISK-CONTROL narrowing in a named bad regime, NOT a view that the move is over and NOT
#   a retreat to blanket caution. Re-arm the aligned side the moment this resolves into a real trio
#   (ER climbing AND vol expanding AND structure) — [[arm-for-periods-not-runs-0804]] still governs.
# ⚠ RE-JUDGE 14:00Z, or immediately if 30-min ER climbs back over 0.30 with the range holding.
# ★★★2026-08-07T13:36Z LONGS ARMED — DIRECT OPERATOR INSTRUCTION ('arm longs. missed it again').
# The 13:30 cash open reversed the short leg violently: 29694 -> 29753 in ~90s, taking out three
# short entries (abs_veto_short -$120, phantom -$35.50, exhaustion_short -$125). The desk was short
# into the reversal and is now flat, having paid ~$100 of that in SLIPPAGE alone.
# ARMED: grind_long + abs_veto_long. capitulation_long already on.
# ★ grind_long is ELIGIBLE this time and that is the point: ext is +0.38 ATR, INSIDE its ext_hi=2.0
#   anti-chase ceiling (at 12:45 it was 6.11 ATR and structurally blocked, which is why arming it
#   then was a no-op). Price 29751, ATR 32.3 — vol is high and the gate can actually fire.
# ⚠ STATED HONESTLY: 30m net is -52.2pt with ER 0.14, so this is NOT a confirmed aligned long run —
#   it is a violent open reversal. 5m/10m ER 0.10/0.15 is chop-grade. I am arming on the OPERATOR'S
#   INSTRUCTION and on the reversal's direction, not on a trio. Grade it as an operator call.
# ⚠ EXPIRY: bench the momentum longs on (a) a stop-out PAIR, (b) price losing 29700, or (c) 14:20Z
#   re-judge. capitulation_long keeps its own first-stop-pair leash from 13:17.
# ★★2026-08-07T13:31Z abs_veto_short BENCHED — MY OWN EXPIRY TRIGGER (a) FIRED, exactly as written.
# 'bench on ANY of (a) a stop-out PAIR - one, not two, because this gate's failure mode is shorting a
# climax and it has now done that once for real money.' It has now done it twice.
#   A SHORT 29695.00 -> 29724.00  -$59.50 STOP  (13:29:01 -> 13:30:00)
#   B SHORT 29694.50 -> 29724.00  -$60.50 STOP  (13:29:01 -> 13:30:01)
#                                 -$120.00 in 59 SECONDS
# ★ THE CASH OPEN REVERSED IT INSTANTLY. Filled 29s before 13:30, stopped 30s after it.
# ⚠ SLIPPAGE: stops were 29713/29712.5, both filled at 29724 — ~11pt THROUGH the stop, ~$44 of the
#   $120 loss. That is the open-gap slippage [[execution-cost-autopsy-stage1]] flags as a real leak,
#   not a modelling artefact. A 2-lot short held into the bell pays it in full.
# ★ HONEST NOTE FOR THE LEDGER: the operator was right that my REFUSAL reasoning was bad (3 of 4
#   reasons failed, one used a wrong ATR denominator). The arming DECISION was defensible and the
#   entry was good — 29695 is ~35pt off the run low, NOT the 66pt-below-the-break climax short that
#   cost -$129.50 on 08-06. Process improved; outcome still negative. Both are true and neither
#   cancels the other. Do NOT re-derive 'never arm this gate' from one 59-second loss, and do NOT
#   re-derive 'my caution was right' either — the reasons I gave were still wrong.
# ⚠ DO NOT RE-ARM before the 14:15Z re-judge, and only then on a FRESH read: this is now 3 stop-out
#   pairs in 3 armings across 08-06/08-07 for a cumulative -$249.50.
# ★★2026-08-07T13:24Z exhaustion_short ARMED — OPERATOR CARVE-OUT ('yes do the exhaustion short
# carve out too'). Codified in router_tick_durable.py guidance (c2) so the headless tick honours it.
# WHY: it was benched 6 times by the router and armed 0 times — it only ever reached 'on' via the
# 22:00 reactivation. BOTH logged bench reasons were the DIRECTION rule ('day-bias UP >= +40 -> bench
# shorts'), which exists to stop MOMENTUM shorts fighting an up-day. exhaustion_short is a FADER —
# shorting an exhausted up-move IS its job — so that rule removed it exactly when its setup forms.
# ★ COST OF BEING ARMED IS ~ZERO: ZERO fires in signal_journal across 08-04..08-07, against
#   grind_long 377 / abs_veto_short 124 / abs_veto_long 89. It cannot churn; rarity IS the filter.
# ⚠ THIS IS AN OPTION, NOT A CONVICTION — stated plainly so nobody later reads it as validated:
#   live n=71 +$81.50 (53.5%, +$1.15/tr) BUT strip-best-1 = -$135.50, strip-best-2 = -$230.50,
#   days green 5/10, last two sessions -$99.50 and -$141.00. ONE day (07-30 +$217) carries it all.
#   The operator has chosen to pay ~nothing to be present for a rare setup. Next ~20 fires decide it.
# ⚠ THE CARVE-OUT REMOVES ONE TRIGGER ONLY — day-bias SIGN. The VALIDATED fader bench still stands
#   (+$810 non-overlap, n=25): bench it when a trend/run genuinely runs against a fade, on violent
#   whipsaw, or on execution pathology. Bench on the MECHANISM being wrong, never on the day's sign.
# ★★★2026-08-07T13:20Z abs_veto_short ARMED — operator challenged my refusal and he was RIGHT.
# I declined at 13:17 on four reasons. Three were wrong and one was self-contradicting:
#  (1) '105pt extended' — this is RUN-TIMING reasoning, which is exactly what today's 08-04 work
#      refutes: arming is a PERMISSION WINDOW, not an attempt to catch one entry. On 08-04 the gate
#      was armed once and took FIVE bites over 2h16m. Being late to bite #1 is irrelevant.
#  (2) 'ATR contracting 16.6 vs ATR60 19.4' — FACTUALLY WRONG FRAMING. ATR60 contains the violent
#      12:30 spike. Against the SESSION baseline: ATR x1.61 and volume x3.70. Vol is EXPANDING and
#      participation is ~4x. I chose the denominator that supported the cautious answer.
#  (3) 'the 13:30 open reverses things' — being flat through the open is a documented COST, not
#      safety, and abs_veto is a VETO gate: self-filtering, ~0-cost armed. That is precisely the
#      gate class [[us-open-arm-veto-gates-not-churners]] says to ARM at the open. This argued FOR.
#  (4) '08-06 lost -$129.50 doing this' — that arming was on last-hr ER 0.19 'trend', marginal. This
#      is a DECLARED RUN at 30m ER 0.50 sustained, -125pt, volume 3.7x. Same gate, different evidence.
#      The 08-06 ledger lesson was 'do not arm on SHADOW P&L with an unquantified entry gap', not
#      'never arm this gate in a run'. I misapplied my own precedent.
# ★ RUN STATE says RUN SHORT and says ARM THE ALIGNED GATES; the operator's standing directive today
#   is lean optimistic. Both pointed one way and I talked myself out of it.
# ⚠ WRITTEN EXPIRY (this is a real risk and it must be bounded): BENCH abs_veto_short on ANY of
#   (a) a stop-out PAIR — one, not two, because this gate's failure mode is shorting a climax and it
#       has now done that once for real money;
#   (b) 30-min ER falling under 0.25;
#   (c) price reclaiming 29790 (the run's midpoint) — that invalidates the short structure;
#   (d) 14:15Z hard re-judge if none of the above has fired.
# ★★2026-08-07T13:17Z RUN SHORT — benching the counter-trend momentum long, keeping the fader.
# RUN STATE declares RUN SHORT: -105pt from the 12:45 high 29824, 30m ER 0.43 / 15m ER 0.60, volume
# holding (42.7k last 15m vs 40.6k prior). We were armed LONG-ONLY into it. In-run COUNTER-trend is
# 0-6% win rate, so this is the one call the run-state doctrine is unambiguous about.
# ★ abs_veto_long OFF — a counter-trend momentum long in a confirmed short run. Armed 12:35, never
#   fired, so this costs nothing to undo. Clear call.
# ★ capitulation_long STAYS ON, deliberately, and this is a judgement not an oversight: it is a
#   FLUSH-BUYER, and a sustained down-leg is where its setup actually forms. It is today's only
#   earner (+$207 at 12:29 on exactly this mechanism) and benching a coiled fader on regime alone is
#   the error I made four times this morning ([[dont-bench-a-coiled-gate-on-quiet-tape]]).
#   ⚠ IT IS ON A SHORT LEASH: bench it on its FIRST stop-out pair — in-run counter is genuinely bad,
#   and I am overriding that stat on mechanism grounds, so it must prove it.
# ★ NOT arming abs_veto_short, despite RUN STATE saying arm-aligned. Reason, stated so it can be
#   graded: 08-06 13:20 armed this exact gate on a confirmed short break and it SHORTED THE CLIMAX
#   66pt below the break low for -$129.50 (the ledger's one clear BAD call). We are 105pt into this
#   move, ATR is CONTRACTING (16.6 vs ATR60 19.4 - the vol leg is weakening, not expanding), and the
#   13:30 cash open is 13 minutes away and routinely reverses the pre-open move. Arming a short into
#   an extended leg on fading vol minutes before the open is the same trade that lost 08-06.
#   ⚠ RE-JUDGE AT 13:35Z: if the run survives the open with ER>=0.35 AND ATR expanding again, ARM it
#   then - that is a better entry than chasing it now, and the operator's lean-optimistic directive
#   is about not sitting out CONFIRMED windows, not about chasing extensions.
# ★★2026-08-07T12:45Z grind_long ARMED — Claude, under the operator's standing directive for today
# ("you do everything as you see. just lean optimistic rather than super cautious").
# TRIO CONFIRMED: new session high 29813 (5th break in 13 min), 15m ER 0.83 / 30m ER 0.64,
# ATR 16->30 (x1.9 expansion). This is a run, not a blip — the aligned side is LONG.
# ★ WHY grind AND NOT just abs_veto_long: grind is CONTINUATION-ON-PULLBACK, so it structurally
#   CANNOT buy the extension — it either gets a retracement (a good entry) or it does not fire.
#   Price is +5.48 ATR above VWAP; on 08-04 at +6.06 ATR it produced ZERO signals and cost $0.
#   That makes it a cheap option here, not a churn risk. It DID fire at 12:33:07 @29718 while benched.
# ⚠ WRITTEN EXPIRY so this cannot become a permanent arming: BENCH grind_long when EITHER
#   (a) 30-min ER falls back under 0.25, or (b) price loses the 29720 breakout shelf, or
#   (c) two stop-outs in the same 30 min. Re-judge at the 13:30 cash open regardless.
# ⚠ Per [[arm-for-periods-not-runs-0804]] a losing streak alone is NOT the bench trigger — ask first
#   whether the REGIME still supports the mechanism.
# ★★2026-08-06T14:19Z abs_veto_long ARMED — OPERATOR DECISION, after he caught the desk sitting out
# a +297pt climb ("the chart shows a 300 point climb since 1530"). He is right and I was wrong twice:
#   (a) I "corrected" him by measuring from the 22:00 session open (-50pt) when the frame that matters
#       is the US open — 13:30 UTC 29352 -> 29650 = +297pt, +408pt off the 29241 low.
#   (b) I declined THREE open-hour [ACT] calls to arm longs during that move.
# ★ WHY THE REFUSALS WERE WRONG: the router (and I) kept citing the DAY aggregate — meter 87 STAY-OUT,
#   "93% of the day's move given back", day-ER 0.00 — which is diluted by the morning chop. This is the
#   exact error the 08-04 ledger entry names: judge the SEGMENT, not the day. The segment has trended
#   one-way for ~45min on last-hr ER 0.29-0.30 with ATR expanding 23->32 and a fresh day high 29653.
# ★ My other two reasons also decayed: the shadow board flipped (grind_fast -127 -> +115/54tr, so the
#   momentum family is now the GREEN one), and the orphan-order risk is real but does NOT block arming —
#   an orphan fires whether we are flat or not. I overweighted it.
# ★ abs_veto_long ONLY, not grind_long: veto-gate, self-filtering, ~0-cost if it does not fire, per
#   [[us-open-arm-veto-gates-not-churners]]. grind is the churner and the move is already +297 extended.
# ⚠ THE RISK I AM TAKING, STATED: entering here is buying a leg that has already run 297pt — the mirror
#   of abs_veto_short selling the bottom at 29253 for -$129.50 two hours ago. BENCH ON A SECOND STOP-OUT
#   (not the first — a veto-gate deserves one, and benching on the first is what made today's shorts a
#   one-shot). Also bench if last-hr ER decays back under 0.18.
# ★★2026-08-06T13:34Z abs_veto_short BENCHED — first stop-out pair, exactly the trigger I set.
# Fired into the 13:31 break and BOTH lots stopped at 13:33:45 for -$129.50:
#   A short 29253.50 -> STOP 29275.50  -$45.50    B short 29254.00 -> STOP 29295.25  -$84.00
# ★ IT SHORTED THE EXTENSION, NOT THE BREAK. Entries at ~29253 are 66pt BELOW the 29319 break low —
#   it sold the climax of the flush and the bounce to 29295 took both lots out inside ~2 minutes.
#   Lot B lost nearly 2x Lot A because the wider chandelier gave the bounce more room to run.
# ★★ THIS IS THE FIFTH ARMING OF THIS GATE IN 15 HOURS AND THE FIRST THAT COST MONEY. The other four
#   (20:00, 22:35, 08:15, 11:05) were $0 ONLY because no setup appeared — luck, not the rule working.
#   ⚠ And this one had the FULL TRIO: real new extreme, ER 0.40 sustained, vol present (watcher ATR 18).
#   The trio being satisfied did not help. That is evidence against the ARMING RULE itself, not just
#   against the vol threshold — do not "fix" this by tuning the ATR floor. See [[vol-expansion-is-the-binding-leg]].
# ★★★2026-08-06T13:09Z NIPC BENCHED — THE OPERATOR'S WRITTEN KILL CRITERION TRIPPED.
# "bench immediately if cumulative <= -$400". Cumulative is EXACTLY -$400.00 on n=47 (12 wins, 26%).
# Today it opened its 13:00-15:00 window and took 4 fills in 9 minutes: 3 STOPs, 1 TARGET, net -$29.50.
#   nipc_long_A  -66.0/17   nipc_long_B  -31.5/16
#   nipc_short_A -127.5/7   nipc_short_B -175.0/7   <- shorts are 76% of the loss on 30% of the fills
# ★ This is the pre-agreed rule firing, not a judgement call — benched without waiting for confirmation
#   exactly as the criterion was written, and the operator was paged at the same moment.
# ⚠ THE REGIME FILTER'S FIRST OUT-OF-SAMPLE DAY ENDED HERE. nipc_short was re-armed 08-05 16:51 behind
#   deciders.NIPC_REGIME_FILTER after the 0-for-10 retirement; it is now 0-for-... plus one target today
#   and still carries the majority of the drawdown. The filter did NOT rescue the short side.
# Re-arming is a fresh OPERATOR decision. Do NOT auto-arm: nipc is in reactivate_gates.py HOLD.
# ★★2026-08-05T16:51Z nipc_short RE-ARMED behind the new REGIME FILTER (operator: "build the
# filter and re-arm both sides"). Both sides on; entries now blocked in dead-chop, violent-whipsaw and
# normal-chop (deciders.nipc_bad_regime), leaving in-between-building and clean-trend.
# ★ WHY SHORT IS BACK: my "retire it, 0-for-10 means broken" call was WRONG. Replaying the same tape
#   went 0-for-8 on shorts too — when model and desk agree the EDGE is absent, not the code. In the lab
#   SHORT is the BETTER side (+$255/n=57, +$4.5/tr vs LONG +$139/n=50, +$2.8/tr).
# ⚠ AND MY "+$10.5/trade" PROJECTION WAS ALSO WRONG — it came from post-hoc BUCKETING. Applied at
#   DETECTION the filter changes the trade population (the tracker does not consume a setup it refuses),
#   so the lab reads +$270/n=62 (+$4.4/tr) against blanket +$397/n=128 (+$3.1/tr): better per trade,
#   LOWER total, half the fires. On 08-05 it cut -$390 to -$176 by removing all 11 whipsaw fires.
# ★ SO IT IS AN EXPOSURE REDUCER, NOT AN EDGE FIX. That is still the right thing while nipc sits $29.50
#   from the -$400 kill line: halving fire count buys evidence-gathering time instead of tripping on
#   churn. Judge it on that, not on a per-trade edge it has not demonstrated.
# ⚠ Filter is IN-SAMPLE (same window that produced the gate). Tomorrow is its first out-of-sample day.
#   Revert: deciders.NIPC_REGIME_FILTER = False.
# ★★2026-08-05T16:39Z NIPC REVIEW ACTED (operator: "bench short. give long another run
# tomorrow see what the replay says"). The n>=40 review the operator scheduled on 08-01 came DUE today
# at n=43.
#   LIVE RECORD  n=43  -$370.50  26% win  -$8.62/trade   (replay says +$3.10/trade)
#   LONG   n=33   -$97.50  11W (33%)  = -$2.95/tr  -> a ~$6 gap, thin-edge underperformance
#   SHORT  n=10  -$273.00   0W ( 0%)  = -$27.30/tr -> a ~$30 gap and NEVER ONCE WON
# ★ nipc_short RETIRED-IN-PLACE: 0-for-10 is not variance — at the replay's 34.6% win rate the odds of
#   zero wins in ten are 1.3%, and the LAB expected SHORT to be the BETTER side (+$629 vs LONG +$192).
#   That pattern says the short implementation is broken, not that the edge is missing. It carries 74%
#   of nipc's entire loss. Do NOT re-arm it without a diagnosed and fixed cause.
# ★ nipc_long ARMED for 2026-08-06, explicitly to be REPLAY-PAIRED afterwards. -$2.95/trade against a
#   replay of +$3.10 is a fixable gap, and it took 3 targets today.
# ⚠ The operator's -$400 cumulative kill criterion is still live and is $29.50 away. Benching short
#   removes the side generating the loss, but if LONG alone takes it past -$400, bench and report.
# ⚠ nipc remains in reactivate_gates.py HOLD, so nipc_long is armed HERE and deliberately, not by the
#   midnight re-arm.
# ★★★2026-08-05T14:35Z ALL GATES BENCHED — OPERATOR INSTRUCTION.
# "we are being destroyed i was wrong to enable all gates. bench everything and resume normal
# router/claude decisions."
#
# ★★ THE 13:32 DO-NOT-BENCH OVERRIDE IS HEREBY REVOKED. Router, you have FULL normal authority
# again: bench and arm on your own regime judgement exactly as before, with no carve-out standing
# over you. Nothing in this file overrides you as of now.
#
# WHY, for the record: today was a 230pt-range roundtrip with day-ER 0.03 and every gate fired into
# it. 25 clean trades, 4 wins, -$534. Two separate agents independently called for benching grind at
# 13:37 and abs_veto_short at 14:26.
# ★ The operator's 13:32 arming was NOT the error it looks like — at that moment the desk had been
# flat through a +263pt move and being flat through the open is a real cost. The tape then failed
# every break it made. Judge the decision on what was knowable at 13:32, not on the outcome.
#
# ★★ NEW STANDING RULE, operator 2026-08-05: NEVER HOLD OVERNIGHT. EVER.
# Any strategy, study or gate that would carry a position through the CME halt is out of scope.
# Flat by 21:00 UTC (23:00 Paris). This is not a preference to be traded off — it is a constraint.
# ★★2026-08-05T14:08Z nipc_long + nipc_short BENCHED on operator instruction ("turn NIPC off").
# Ran 13:00-14:00 today on the operator's earlier call. It was the desk's BEST gate over that window
# (+$118.50 on 5 fires / 3 targets while grind_long was -$172), so this is not a bench for failing.
# ★ IT REMAINS IN reactivate_gates.py HOLD, so it will NOT auto-arm at the 22:00 reopen. Re-arming is
# a fresh operator decision, as it was this morning.
# ★ THE SESSION'S FIRES ARE THE ASSET: pair them against scripts/nipc_replay.py over the same window
# to attack the live/replay divergence (replay +$3.1/tr vs live -$9.33/tr before today). Today ADDED
# live fires in a window we can replay — that is exactly the sample the diagnosis needed.
# ★★2026-08-05T13:43Z grind_long BENCHED on operator instruction ("bench grind").
# It was the only bleeder: 6 fires in the hour, 5 stopped, -$172.00 (Lot B 3-for-3, -$123.50), all
# chasing reclaims into ER30 ~0.10 chop after the 30023 poke failed 93pt off the high.
# ★ THE LONG SIDE IS NOT GIVEN UP — nipc_long is +$118.50 on 5 fires / 3 targets over the same hour
# and the same direction. It waits for the pullback and enters the resume; grind chased the reclaim.
# The other four gates stay ARMED and the 13:32 DO-NOT-BENCH override still stands for them.
# ★★★2026-08-05T13:32Z DIRECT OPERATOR INSTRUCTION — ARMED grind_long, abs_veto_long,
# abs_veto_short, exhaustion_short. Operator: "nothing is armed dude. i dont like this. we are
# missing money being too cautious. arm both abs vetos, grind and exhaustion short."
#
# ★★ ROUTER: DO NOT BENCH THESE FOUR TODAY. This is not a tick-level judgement you are being asked
# to re-evaluate — it is a standing operator decision that OVERRIDES the dead-tape / break-trio /
# untradeable-meter reasoning you would otherwise apply. You benched abs_veto_long at 12:40 and
# AGAIN at 12:50, 22 seconds after the session armed it, on "no break to arm into". That mechanical
# read is defensible in isolation and it is exactly what the operator is overruling: being flat
# through the US open is a COST, not safety ([[intelligent-routing-not-blanket-benching]]).
# You retain bench authority ONLY for: (1) execution pathology — naked stop, absurd entry_atr,
# stacking MAX_HOLDs; (2) nipc at <= -$400 cumulative. NOT for chop, NOT for a failing break trio,
# NOT for a red day aggregate. If you believe one of these four should come off, say so in `reason`
# and leave the switch alone — the operator decides, not the tick.
# EXPIRY: this override lasts the 2026-08-05 Paris session. At the 22:00 UTC reopen the normal
# policy resumes and you judge them fresh.
# ★ CLAUDE ROUTER-TUNE TRIAL — 2026-07-29 Paris day (operator-authorized, PAPER, benching-only).
# Revert: cp gate_switches.env.pre-trial gate_switches.env; sudo systemctl enable --now gazbot7-direction-router.timer
# ★2026-08-04 13:52 armed on the confirmed break; ★★BENCHED AGAIN 14:16 ON OPERATOR INSTRUCTION
# ("its fine. just thoight it could go ok. leave it off").
# It never fired in the 24 minutes it was armed — ZERO signals, so the arming cost nothing and the
# clip lift bought nothing. Diagnosis of the non-firing: price ran to +6.06 ATR above VWAP on a one-way
# move, and grind is a CONTINUATION-ON-PULLBACK gate — a trend that never retraces to VWAP offers it no
# setup. Removing its ext_hi=2.0 ceiling did NOT make it fire either, so the binding condition is the
# pullback geometry, not the anti-chase filter. Worth remembering: grind is not the gate for a one-way
# run, it is the gate for a trend that BREATHES.
# Do not re-arm today. It re-arms by policy at the 22:00 UTC reopen and the router judges it fresh then.
# ★2026-08-05 12:50 US-OPEN CARVE-OUT (operator: "make sure we have gates ready to go for us open").
# ARMED for the 13:30 open. The router benched this at 12:40 on a correct read — break trio 0-of-3,
# day-ER 0.03, ATR 12pt, dead tape — and if the tape were the whole story it should stay benched.
# The open is the exception standing guidance carves out: abs_veto is a VETO-gate (thrust + 55s
# absorption veto), so it is ~0-cost armed — it self-filters rather than churning, which is the whole
# reason [[us-open-arm-veto-gates-not-churners]] says arm veto-gates and bench churners at the open.
# Being flat through the open is a COST, not safety.
# LONG only: day bias UP +134pt, so the aligned side is long and abs_veto_short stays benched.
#
# ⚠ WRITTEN EXPIRY, so this cannot be rationalised into a permanent arming the way the 08-04
# carve-outs nearly were: BENCH AGAIN AT 14:00 UTC unless the open has delivered a real vol
# expansion — ATR >= 18pt AND last-hr ER >= 0.25. A dead open is not a reason to keep it on.
# Also bench immediately on a second stop-out (it already cost -$69 at 12:31 in dead tape).
# Today's shadow is red across every mechanism (~-$2,200 if all gates were armed), so this is a
# deliberately NARROW arming of the single best gate, not an opening of the roster.
# ★2026-08-01: exhaustion_short fade-scalp trial continues, but re-cut to A@0.75R + B k1.5 chandelier
# (exit_overrides.json) and NO LONGER PINNED — the weekend re-derivation found the BENCH matters more than
# the R for this gate (no exit rescues a violent-whipsaw entry at any R), so the router must be free to bench it.
# ★2026-08-04 13:30 armed on operator instruction; ★★BENCHED AGAIN 13:59 — THE CARVE-OUT EXPIRED.
# It was armed on the argument "day-ER 0.06 across a 431pt range = churny roundtrip, not a clean trend,
# so both sides pay", with a written expiry: bench when ER climbs into a genuine sustained trend.
# THAT CONDITION HAS NOW FIRED: last-hr ER 0.34-0.43 (trend), ATR 21->24pt expanding, new day high
# 29501, bias UP +559pt, last-hr net +258. A counter-trend gate is armed against a clean run.
# ⚠ I ALMOST HID BEHIND MY OWN THRESHOLD. I had written the expiry as "day-ER >= 0.18" and day-ER is
# only 0.10 — but day-ER is diluted by the SAME morning chop I just refused to judge grind_long on
# minutes earlier. Segregating by regime to ARM grind and then invoking a chop-diluted day aggregate to
# KEEP shorts armed is having it both ways. The correct expiry test is the segment, not the day.
# Caught by the new open-hour watcher (scripts/open_hour_watch.py) on its very first live verdict.
# Cost of the arming: ZERO realised — abs_veto_short took no trades in the 29 minutes it was on.
# ★2026-08-01 (operator pick, Friday report): rgv_short BENCHED — it was armed live while every section
# verdicts it SHADOW. 11 fires, −$142, negative at every exit rung (1.5R −$32 → chandelier −$190), strip-best-1
# −$242, red in every exit-lab cell; −$154.5 on 3 automated fills. This is a BENCH, explicitly NOT a retirement:
# retiring on 11 fires is as unjustified as arming on 11. The shadow keeps running; re-look when n grows.
# ★2026-08-01 NEW GATE — nipc (news_impulse_pullback), the Friday M3 greenfield survivor.
# Self-gates to 13:00-15:00 UTC, OFF in dead-chop (ATR1m<18 AND ER15<0.35), Lot A 2.0R / Lot B 2.5R,
# 20-min cap, flat 15:30 UTC, base_size=1 per side — so 2 lots per signal under the scale-out slate
# (the lab headline was 1 lot; its 2-lot cell was +$5,199 lab vs +$98 on our replay).
#
# ★★ ACCEPTANCE REPLAY — scripts/nipc_replay.py runs the SHIPPED decider over the lab's own 12 days.
# First pass "failed" at +$264 / $1.7 per trade, but that run used FEE_RT = $5.00/RT inherited from the
# greenfield lab's NIPC cell. The operator caught it: venue truth is $1.50/RT — all 487 closed trades in
# gazbot7.db carry fees_usd = 1.50 exactly. Corrected re-run (2026-08-01):
#     HOME n=159 · +$820 · $5.2/trade · 34.6% win · 9 of 12 days green · worst day −$102
#     lab   n=171 · +$2,676 @ $5/RT, which at the real fee is ≈ +$3,275 · $19.1/trade · 9 of 12 green
# So the honest gap is ~3.7x on money, NOT the 10x first reported, and DAYS-GREEN NOW MATCHES THE LAB
# EXACTLY (9/12). The win rate is unchanged by fees and is still short (34.6% vs 43.3%) — the residual
# divergence is real and lives in the lab's exit accounting, since the ENTRY population reproduces
# (all 6 published ablation counts within ~7%).
# Why the fee error mattered so much HERE and almost nowhere else: a fixed per-trade cost is a
# regressive tax on a thin-edge high-frequency gate. At ~$5.7 gross/trade, $5 eats 87% of the edge and
# $1.50 eats 26%. It was never a NIPC-specific finding — it was a cost bug.
#
# ★ ARMED 2026-08-01 by the operator. On our OWN tick-honest replay this is a genuinely positive edge
# (+$5.2/trade, both sides green — LONG +$192 / SHORT +$629 — and non-negative in all five regime
# buckets), not the break-even-to-negative construct the first pass suggested. It is still short of the
# lab and is one summer fortnight on MNQ, so treat the size as a direction, not a promise.
# ★ KILL CRITERION, agreed up front so it cannot be rationalised later — review at n>=40 signals or
# Fri 2026-08-07, whichever comes first. Live $/signal materially below the replay's ~$5.2 (not merely
# below the lab's ~$19) retires it. Bench immediately if cumulative <= -$400.
# The router may bench it freely (not pinned); it is no longer held from the nightly re-arm.
# ★2026-08-03 BENCHED after session 1 (n=15, -$280) — NOT for losing, but because its signals are
# currently UNINTERPRETABLE. Replaying the SHIPPED decider over today's own ticks gives +$375 (11 HOME
# signals) against the live desk's -$280 on 15 — a $655 gap in the OPPOSITE direction. They also fire on
# DIFFERENT setups: live took nothing before 13:34:52 while the replay took 6 signals in 13:03-13:32
# (3 of them targets), and where they do coincide live's fills are worse — 14:47 replay entered 28724.75
# for a TARGET, live entered 28727.00 three seconds later for a STOP. Live median hold 24s vs the
# replay's 1.7min; stops:targets 22:8 vs 6:5.
# Until that is explained every further session adds data that cannot count toward the n>=40 review.
# Re-arm only once the divergence is diagnosed AND the replay reproduces live within a stated tolerance.
# ⚠ This gate must NOT be auto-armed by reactivate_gates.py while benched for this reason — if it is
# still benched at the next Paris midnight, add it back to that script's HOLD set.
# ★★2026-08-05 12:55 ARMED ON EXPLICIT OPERATOR INSTRUCTION — "we just need to run nipc and see how
# it goes. i dont care if it loses. we are on paper this is what its for."
# This OVERRIDES the 08-03 bench, and the override is deliberate, not an oversight. The recorded
# re-arm condition was "diagnosed AND the replay reproduces live within a stated tolerance": the
# divergence IS diagnosed (trigger-timing 59%, one lost exit race 38%) but it does NOT reproduce —
# nightly replay +$3.1/tr (n=128, at the true $1.50 fee) against live -$9.33/tr (n=30), a ~$13/trade
# gap in the OPPOSITE direction, still unexplained. The operator has weighed that and chosen to run
# it anyway on a paper account to gather live signal. That is a legitimate call: the divergence
# cannot be diagnosed further WITHOUT live fires to compare against the replay.
#
# ★ WHAT THIS RUN IS FOR — record it now so the data is interpretable later: every fire adds a
# live/replay PAIR. Run scripts/nipc_replay.py over the same session and compare entry timing and
# fills trade-by-trade. That is the missing input, and no amount of replay-only work produces it.
# The 08-03 session gave 30 fires; another 2-hour window roughly doubles the sample.
#
# ⚠ THE OPERATOR'S OWN WRITTEN KILL CRITERION IS STILL ACTIVE AND IS CLOSE: "bench immediately if
# cumulative <= -$400". Live is at -$280.00, so there is $120 of headroom. If it trips I will bench
# and say so rather than silently ride through it — lifting that number is the operator's call, not
# mine to assume from "i dont care if it loses".
# ⚠ Self-gates to 13:00-15:00 UTC and OFF in dead-chop (ATR1m<18 AND ER15<0.35). ATR is 12pt right
# now, so its own filter may keep it flat until the open brings vol — a quiet start is the gate
# working, not the gate broken.
# ⚠ Still in reactivate_gates.py HOLD, so it will NOT auto-re-arm at the 22:00 reopen if anything
# benches it. Deliberate: a re-arm after a bench should be a fresh decision.
