# MIL ENTRY-SPACING STUDY — PRE-REGISTRATION (written before any number exists)
Operator ask (2026-10-07): "3-6 entries per day… spanned out over hours apart… MILs… Measure that over
maybe 20 days… Do it on the 7 atr measurement… a rule for entries to stop it going back in over and
over and losing… intelligent, data backed, flexible."

STATUS: read-only measurement + S2 *candidate*. Touches no brief, no S1 page, no running baseline.
L2: it is ONE candidate for S2 and competes with the two PATIENCE ideas already logged; S2 takes one.

DEFINITIONS (frozen)
- MIL = a leg of the causal retrace tracker: direction flips when the 1-min CLOSE gives back
  >= 7 x ATR14(1m, TR floor 0.25, evaluated at that bar) from the running extreme of closes.
  Tracking starts at the 22:00Z session open (warm-up); entries are only counted 02:00-13:30Z.
  An entry is assigned the leg active at its open time (causal). Sensitivity rows at 4/10/15 x are
  CONTEXT only; 7 is the number.
- Day set: every non-holdout day with clean fills in the operator's manual book (entry_source=manual,
  no BADFILL/EXCLUDE rows, not 14-18 Sep / 17-21 Aug) + the 9 S1b days. Entries grouped by distinct
  opened_at. Points/lot = pnl_usd / (2 x qty).
MEASURED (all descriptive)
 A. MILs per day and hours between MIL starts (market).
 B. Entries/day; minutes between consecutive entries; share of gaps < 30 min; for operator and S1b
    SEPARATELY.
 C. Entries per (MIL, side); share of entries that are the 2nd+ in the same MIL+side; P&L (pt/lot) of
    1st vs 2nd+; of 2nd+ split by whether the previous same-MIL+side exit was a loss or a win.
CANDIDATE RULES (no tuning; each evaluated once as a DELETION counterfactual, labelled in-sample and
an upper bound because deleting a trade ignores the path it would have changed)
 R1 one entry per MIL+side.
 R2 after a same-MIL+side exit <= 0, block same-side re-entry in that MIL (re-entry after a PROFIT
    exit is allowed — the grind-harvest exception is built into the rule, not bolted on).
 R3 as R2 but the block lifts after G minutes, G = 1/4 of the market's median MIL duration (G comes
    from A, not from a grid).
SUPPORT BAR: a rule is only worth proposing for S2 if it blocks entries whose summed pt/lot is
negative in BOTH the operator book and the S1b book. One book alone = PARK, not propose.

AMENDMENT A1 (2026-10-07, operator: "not a cap… only one trade per MIL unless it's long and drawn out")
 R4 = R1 with a drawn-out exception: the 2nd+ entry in a MIL+side is allowed when the MIL's AGE at
 that entry (minutes since the leg started, causal) >= T. T is NOT fitted: T = p75 of completed MIL
 durations in the market sample (frozen from block A; no grid). Scored once, deletion counterfactual,
 in-sample. Same both-books support bar. Also reported: 2nd+ entry P&L by MIL-age bucket, to show whether
 age actually separates winners from losers. Written before R4 was computed.
