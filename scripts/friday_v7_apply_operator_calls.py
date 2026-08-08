#!/usr/bin/env python3
"""Apply the operator's three decisions of 2026-08-08, taken after the pick review.

  1. SATURDAY #10 — grind_long is EXEMPT from the atr_split 22 -> 24 move. The other five
     non-NIPC rows still take 24.
  2. MONDAY #2 (router timing) — DEFERRED one week. It confounds with MONDAY #1 by the
     report's own admission ("a stickier router is a chop optimisation"), so shipping both
     measures the chop idea twice and attributes neither.
  3. MONDAY #1 — an explicit abs_veto_short CARVE-OUT clause, so the chop bench does not
     contradict SATURDAY #1 or bias its 15-fire review.

⚠ HONESTY NOTE ON (1), which must travel with the play. FIX0's +$3,024 archive delta was
measured with ALL SIX non-NIPC rows at atr_split 24. Exempting grind_long means the SHIPPED
config is no longer the TESTED config, and the direction of that difference is UNMEASURED --
it could help or hurt. The exemption is a judgement that protects a mechanism we understand
(grind's result is 21 runner events out of 165 legs; the clip caps Lot B at 1.75R floored $60,
which truncates runners) over a cell we measured once. Re-running FIX0's archive with grind
exempted is on the play's verification field; until that is done, do not quote +$3,024 as the
expected value of what is actually deployed.

Measured on this week's tape (1m bars from capture.db, ATR14): ATR >= 22 is 9.9% of the week,
ATR in [22,24) is 1.9% -- so 19.3% of grind-eligible time falls in the band the split move
would newly clip.

Revert: cp reports/friday_v7/plays.json.pre-operator-calls reports/friday_v7/plays.json
"""
import json
import pathlib
import sys

PLAYS = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/plays.json")
BACKUP = PLAYS.with_suffix(".json.pre-operator-calls")
MARK = "★ OPERATOR CALL 2026-08-08"

# MONDAY, re-ranked so the deferred play sits last in its own window.
MONDAY_ORDER = [
    "chop-avoidance-is-the-biggest-number-0808",
    "fix-midnight-reopen-reversion-only-0808",
    "meter-stayout-45-and-no-preopen-0808",
    "vol-expansion-not-a-rearm-trigger-0808",
    "grade-the-bad-days-0808",
    "router-timing-window45-hold3-0808",      # DEFERRED — last, so it is not worked by habit
]


def main():
    rows = json.loads(PLAYS.read_text())
    byid = {r["id"]: r for r in rows}
    if any(MARK in json.dumps(r, ensure_ascii=False) for r in rows):
        print("operator calls already applied — nothing to do (idempotent).")
        return 0
    BACKUP.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    # ── 1 · the grind exemption on SATURDAY #10 ──────────────────────────────────────────
    p = byid["lotb-rung-widen-atrsplit24-0808"]
    p["play"] = p["play"].replace(
        'Edit the six non-NIPC rows of data/exit_overrides.json to '
        '{"a_r": 3.0, "b": 6.0, "atr_split": 24, "lo": {"a_usd": 40, "b_r": 1.75, '
        '"b_floor_usd": 60}}. NIPC keeps its proven {"a_r":2.0,"b":2.5} pair.',
        'Edit FIVE of the six non-NIPC rows of data/exit_overrides.json to '
        '{"a_r": 3.0, "b": 6.0, "atr_split": 24, "lo": {"a_usd": 40, "b_r": 1.75, '
        '"b_floor_usd": 60}}. NIPC keeps its proven {"a_r":2.0,"b":2.5} pair. '
        f'{MARK} — grind_long is EXEMPT from the split move: it takes "a_r": 3.0 and '
        '"b": 6.0 like the rest, but KEEPS "atr_split": 22. ')
    p["arms_when"] = (
        f'{MARK} — grind_long keeps atr_split 22; the other five take 24. WHY: SATURDAY #2 '
        "(grind-long-revert-atr22-ext30-0808) sets grind's entry ATR floor to 22, and REV2 Q1 "
        "§10 relied on the clip being INERT for the gate at that floor (\"leave it in as a "
        "fail-safe\"). Moving the split to 24 un-inerts it for the ATR 22–24 band — 19.3% of "
        "grind-eligible time on this week's tape — and the clip caps Lot B at 1.75R floored "
        "$60, which truncates exactly the 21 runner events that ARE grind's +$4,151 case. "
        "The two plays would have partially cancelled. " + p["arms_when"])
    p["number"] = (
        p["number"] + f" ⚠ {MARK} — the +$3,024 was measured with ALL SIX rows at 24. With "
        "grind exempted the shipped config is NOT the tested config and the direction of that "
        "difference is UNMEASURED. This is a judgement that protects a mechanism we understand "
        "(runners carry grind) over a cell we measured once — not a free lunch. Do not quote "
        "+$3,024 as the expected value of what is deployed until the archive is re-run.")
    p["verification"] = (
        "★ FIRST: re-run FIX0's 20-session archive with grind_long held at atr_split 22 and "
        "report the honest delta — the +$3,024 no longer describes the deployed config. "
        + p["verification"])
    p["revert"] = ("git checkout data/exit_overrides.json + restart. Partial revert of just the "
                   "exemption: set grind_long's atr_split to 24 to match the other five. "
                   + p["revert"])

    # ── 2 · defer MONDAY #2 one week ─────────────────────────────────────────────────────
    p = byid["router-timing-window45-hold3-0808"]
    p["deferred_until"] = "one clean week of MONDAY #1 (chop-avoidance-is-the-biggest-number-0808)"
    p["deferred_reason"] = (
        "Confounds with MONDAY #1. WINDOW 30→45 and HOLD 2→3 make the router stickier, which "
        "lengthens every bench the chop filter triggers — and this play's own kill criterion "
        "says it outright: \"A stickier router is a chop optimisation.\" Shipping both in the "
        "same window ships the chop idea twice and attributes neither, for a +$502 play against "
        "the largest single number in the report. It is deferred, NOT rejected: the evidence is "
        "good (interior peak on four axes, LOO-positive on both universes, both universes rank "
        "every cell identically). Ship it once the chop filter has a clean week to be measured "
        "against.")
    p["topic"] = "DEFERRED ONE WEEK · " + p["topic"]
    p["play"] = (f"{MARK} — HOLD until the chop filter has had a clean week. " + p["play"])
    p["operator_pick"] = "skip"
    p["status"] = "DEFERRED"

    # ── 3 · the abs_veto_short carve-out on MONDAY #1 ────────────────────────────────────
    p = byid["chop-avoidance-is-the-biggest-number-0808"]
    p["play"] = (
        p["play"] + f" {MARK} — CARVE-OUT: abs_veto_short is EXEMPT from the chop bench for the "
        "duration of its 15-fire review (SATURDAY #1, absveto-short-arm-by-default-er035-0808). "
        "It is the only gate on this card with per-regime evidence that positively contradicts a "
        "blanket bench — +$2,290.50 over 159 fires across 17 days, POSITIVE IN ALL FIVE REGIMES, "
        "chop included, with 53 of 54 filters tested losing to just letting it fire. Benching it "
        "in chop would cost money AND corrupt the experiment, because the 15 fires you review "
        "would be drawn from a biased subset and you would conclude something about arm-by-"
        "default that is really about the chop filter.")
    p["arms_when"] = (
        "Bench the book when the tape is in a confirmed chop block — EXCEPT abs_veto_short, "
        "which stays armed through chop until its 15-fire review completes. Reversion gates "
        "keep their existing treatment. " + str(p.get("arms_when", "")).lstrip())
    p["kill"] = (
        p["kill"] + f" {MARK} — separately: if the carve-out is what makes chop-benching look "
        "bad, that is a finding about abs_veto_short, not about chop. Grade the two "
        "independently — the carve-out exists precisely so they CAN be graded independently.")
    p["verification"] = (
        "Grade the chop bench on the non-carved-out book only, so abs_veto_short's 15 fires stay "
        "a clean experiment. " + str(p.get("verification", "")).lstrip())

    # re-rank MONDAY
    for i, pid in enumerate(MONDAY_ORDER, start=1):
        assert byid[pid]["window"] == "MONDAY", pid
        byid[pid]["rank"] = i

    PLAYS.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print("applied 3 operator calls:")
    print("  SATURDAY #10  grind_long EXEMPT from atr_split 22→24 (keeps 22)")
    print("                + honesty note: +$3,024 no longer describes the shipped config")
    print("  MONDAY   #2 → #6  router timing DEFERRED one week (confounds with MONDAY #1)")
    print("  MONDAY   #1   abs_veto_short CARVE-OUT clause added to play/arms_when/kill/verify")
    print("\n  MONDAY re-ranked:")
    for i, pid in enumerate(MONDAY_ORDER, start=1):
        d = " [DEFERRED]" if byid[pid].get("deferred_until") else ""
        print(f"    {i}. {pid}{d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
