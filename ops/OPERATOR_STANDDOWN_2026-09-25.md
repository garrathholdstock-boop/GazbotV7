# OPERATOR STAND-DOWN — 2026-09-25, IN FORCE UNTIL HE PERSONALLY LIFTS IT

⚠⚠⚠ **THIS FILE EXISTS BECAUSE HALF THE STAND-DOWN LIVES IN AN UNTRACKED FILE.**
`data/gate_switches.env` is gitignored — deliberately, because the router rewrites it every five
minutes and tracking it would be pure churn. But the ⛔ header block inside it is not state, it is
an **OPERATOR INSTRUCTION**, and an instruction that exists only on one disk is one restart, one
restore or one header reset away from silently vanishing. The gates would then arm again and
nothing would say why.

**The guard is `tests/test_operator_standdown.py`** — it fails the moment the block leaves the
spliced window. **This file is the restore path.**

---

## WHY

Operator, 2026-09-25: *"why was grind activated? i told you to disactivate all other gates. it just
lost $200."* Then: *"yes make it durable until i lift it."*

On 09-24 he asked for every gate off. The six switch values were written and he was told the bench
would last one session, because `gate-reactivate` re-arms at Paris midnight. **That was wrong about
the mechanism.** It was the ROUTER, five minutes later, on its own regime read:

```
16:11Z  changed: {'grind_long': 'on', 'abs_veto_long': 'on'}   "ARMING THE ALIGNED LONG MOMENTUM PAIR"
16:31 / 16:35   4 fills, 4 stops, -$168.50   (trades 1082-1085)
16:50Z  the router benched the pair itself, on its own stated trigger
```

★ **SETTING SWITCH VALUES IS NOT AN INSTRUCTION TO ANYTHING.** The router receives values as bare
json; only `switch_notes()` — the top 45 lines of the header — reaches it as words.

## THE TWO HALVES — neither is sufficient alone

| | stops | lives in |
|---|---|---|
| `HOLD` in `scripts/reactivate_gates.py` | the 00:00 Paris re-arm | **tracked** |
| the ⛔ block atop `data/gate_switches.env` | the router, every 5 min | **untracked — restore from below** |

⚠ **HALF-LIFTED IS THE WORST STATE:** the router arms freely while the reopen still benches, so the
gates flicker and neither mechanism looks wrong.

## TO LIFT (operator only)
1. delete the ⛔ block from the top of `data/gate_switches.env`
2. restore `HOLD` in `scripts/reactivate_gates.py` to `frozenset({"rgv_short"})`
3. delete this file

## TO RESTORE THE HEADER BLOCK, verbatim — prepend to `data/gate_switches.env`

```
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ⛔⛔⛔ OPERATOR STAND-DOWN — 2026-09-25, IN FORCE UNTIL HE PERSONALLY LIFTS IT ⛔⛔⛔
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ROUTER: ALL SIX GATES ARE BENCHED BY OPERATOR INSTRUCTION. DO NOT ARM ANY GATE, FOR ANY REASON,
# ON ANY EVIDENCE. This is not a regime read you may overturn with a better one — it is the
# operator standing the automated book down while he trades the rider by hand. Your arming
# authority is SUSPENDED. You retain full authority to BENCH.
#
# His words, 2026-09-25 after grind_long took 4 fills / 4 stops / -$168.50: "why was grind
# activated? i told you to disactivate all other gates." Then: "yes make it durable until i lift
# it."
#
# ⚠ WHAT WENT WRONG THE FIRST TIME, so it is not repeated: on 2026-09-24 the six switches were set
# to `off` by hand and the operator was told the bench would last one session. That was WRONG about
# the mechanism. It was not the midnight re-arm that undid it — it was THIS ROUTER, five minutes
# later, doing its job on its own regime read (16:11Z "ARMING THE ALIGNED LONG MOMENTUM PAIR").
# Nothing had told the router an instruction existed. Writing switch values is not an instruction;
# THIS HEADER IS, because switch_notes() splices the top 45 lines into every prompt you receive.
#
# ⚠ TO LIFT: only the operator, and he must say so. Delete this block and remove the six gates from
# HOLD in scripts/reactivate_gates.py. Both, or the stand-down is only half-lifted.
# ⚠ THE 09-14 AND 08-28 WATCHER NOTES BELOW ARE STALE and their "LET IT RUN" is SUPERSEDED by this
# block. They are kept only because deleting history is worse than marking it.
```
