#!/usr/bin/env python3
"""Fold the six REV2 sections' card corrections into plays.json.

★ WHY THIS EXISTS. The 2026-08-08 report was rendered at 10:17 UTC. The Rev2 self-proofread
then ran and wrote six sections (rev2_q0/q1/q2, rev2_fix0/fix1/fix2) — each of which PATCHES,
WITHDRAWS or REPLACES a play on the action card. The build was OOM-killed at 11:19 UTC before
folding any of it back in, so the published card still told the operator to ship things the
report's own Rev2 pass had refuted. That is the exact failure mode the 2026-08-01 cycle hit
("the five Rev2 answers that never landed in the published file").

Every edit below is quoted from the rev2 section that prescribes it — nothing is invented here.
The prescriptions are field-level and explicit; where a section named the replacement text, that
text is used verbatim. Idempotent: re-running detects the REV2 marker and refuses.

Revert: cp reports/friday_v7/plays.json.rev2-orig reports/friday_v7/plays.json
"""
import json
import pathlib
import sys

PLAYS = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/plays.json")
MARK = "★ REV2 CORRECTION"


def by_id(rows, pid):
    for r in rows:
        if r["id"] == pid:
            return r
    raise SystemExit(f"FATAL — play id not found: {pid}. The card changed shape; re-read the "
                     f"rev2 sections before forcing this through.")


def main():
    rows = json.loads(PLAYS.read_text())
    if any(MARK in json.dumps(r) for r in rows):
        print("plays.json already carries the REV2 marker — nothing to do (idempotent).")
        return 0

    # ─────────────────────────────────────────────────────────────────────────────────────
    # SATURDAY #1 — grind_long.  Source: REV2 · Q1 §10 "The exact change" + §"THE ONE-LINE
    # ANSWER" + §"⚠ SAY THIS OUT LOUD BEFORE SHIPPING" + §"⚠ THE OPERATIONAL FACT", and the
    # honesty note in REV2 · Q2.
    # The card said "ext ceiling 2.0 → 3.0". Q1 §10 says DELETE the ext_hi override so it falls
    # back to gate_grind's own default of 4.0 — everything from 3.0 up scores identically
    # (+$5,893 / +$6,081 / +$5,981 / +$6,262), so the literal is not load-bearing and pinning a
    # new one re-fits the thing the revert is undoing.
    # ─────────────────────────────────────────────────────────────────────────────────────
    p = by_id(rows, "grind-long-revert-atr22-ext30-0808")
    p["topic"] = ("grind_long: put the ATR floor back to 22 and DELETE the extension ceiling "
                  "(not 3.0 — delete it)")
    p["play"] = (
        f"{MARK} (REV2 · Q1 §10) — the mechanism changed, the direction did not. Revert the "
        "2026-08-01 change: ATR floor 10 → 22 in deciders.py::ATR_FLOOR, and DELETE the "
        '"ext_hi": 2.0 key from the grind_long SlotSpec so it falls back to gate_grind\'s own '
        "default of 4.0. The earlier card said 'ext 2.0 → 3.0'; do not pin 3.0. Everything from "
        "3.0 upward scores identically (+$5,893 / +$6,081 / +$5,981 / +$6,262), so there is no "
        "optimum to find and 2.0 is a $2,210 tax. Two literals: one changes, one is removed. "
        "Change nothing else — the exit (start_k 3.5 / lock_r 6.0 / lock_k 0.5), the 1.0×ATR "
        "stop, Lot A's 2.5R, base_size=2, slope_min 0.4, ext_lo 0.3 and fast_slope=True all "
        "survive their own sweeps.")
    p["arms_when"] = (
        "ATR1m ≥ 22 at signal; below 22 the gate does not arm at all. No extension-ceiling "
        "override — the gate default (4.0) applies. ⚠ OPERATIONAL: grind_long is NOT in "
        "reactivate_gates.py::HOLD (which holds only nipc_long/nipc_short), so "
        "gazbot7-gate-reactivate.timer flips it back on at 22:00 UTC Sunday regardless of what "
        "this report concludes. 'It stays off' is not achievable by doing nothing — either ship "
        "the config change and let it re-arm into a gate that self-gates at ATR 22, or add "
        "grind_long to HOLD. There is no third state.")
    p["number"] = (
        f"{MARK} — the headline was a DELTA, not a P&L, and the recommended cell is +$4,151 "
        "(+$6,081.2 − $1,929.9), not +$3,964. Window and shape must travel with it: 11 "
        "tick-honest sessions, 165 legs, of which 21 runner events are the ENTIRE result — strip "
        "them and the configuration is +$380.70 over 144 legs ($2.64/leg, a rounding error above "
        "the fee). 77% of the gain (+$4,708 of +$6,081) was already available under the "
        "pre-08-01 config, so this is a revert to a previously-shipped cell, not a new "
        "optimisation. ⚠ THE LIVE FILLS DO NOT SUPPORT IT (REV2 · Q2): all 6 post-card grind legs "
        "fired at ATR14 ≥ 22 (23.98, 23.98, 33.50) — the reverted floor would not have blocked "
        "one of them, so −$172.00 is not evidence for this play. The case rests entirely on the "
        "11-session replay leg-count (744 → 155). Part 2.5's −$958 is a different population "
        "answering a different question; never quote it in the same sentence.")
    p["kill"] = (
        f"{MARK} — write the review criterion before the first bad week, because P&L alone "
        "cannot judge this: 20 admitted legs MINIMUM, and judge on whether 4R events appear at "
        "anything near the expected 12.7% rate. A fortnight with no expansion days will produce a "
        "flat result that is NOT evidence the change was wrong. Hard kill: fewer than 15 of 19 "
        "target-winners retained on fresh tape, or a negative $/leg over 40 live legs.")
    p["revert"] = ("Set ATR_FLOOR['grind_long'] back to 10.0 and re-add \"ext_hi\": 2.0 to the "
                   "SlotSpec. One line each; the gate returns to exactly this week's behaviour.")
    p["section_ref"] = "Part 3.2 (REV2 · Q1) — supersedes Part 1.5 §1/§10, Part 2.5 LEAD 3, Part 2.6 §6/§(b)"

    # ─────────────────────────────────────────────────────────────────────────────────────
    # SATURDAY #2 — abs_veto_short.  Source: REV2 · FIX2 §3 "The edit, exactly" (which names the
    # replacement text field by field) and REV2 · Q0 §8 "What to ship" / §9 Disposition.
    # The ER30 ≥ 0.35 arming floor is REFUTED and WITHDRAWN. Everything else in the play ships
    # unchanged. Q0: "Play #2's topic, play, arms_when, number and kill fields all need the ER
    # clause struck; the rationale stands as written."
    # ─────────────────────────────────────────────────────────────────────────────────────
    p = by_id(rows, "absveto-short-arm-by-default-er035-0808")
    p["topic"] = "abs_veto_short: arm it by default"
    p["play"] = (
        f"{MARK} (REV2 · Q0 + FIX2, two independent derivations) — the ER30 ≥ 0.35 arming floor "
        "is WITHDRAWN as REFUTED; every other half of this play ships unchanged. Stop running "
        "abs_veto_short as a 22-minute discretionary window: arm it by default, delete the two "
        "bad bench rules (the US-session violent-whipsaw bench and 'bench on a stop-out pair'), "
        "fix the 22:00 auto re-arm, and add the one new entry veto from the rehab — BUILDING × "
        "US-SESSION. Do NOT add an ER floor of any kind, to either twin. The floor was justified "
        "as 'mirroring grind's'; deciders.ER_FLOOR is {} — every floor was deleted on 08-01 and "
        "the deletion is pinned by tests/test_deciders.py::test_er_floors_all_deleted. There is "
        "no floor to mirror.")
    p["arms_when"] = (
        "Armed by default. No ER condition of any kind. One per-entry veto: skip when "
        "regime=BUILDING and 13:30 ≤ UTC < 20:00.")
    p["number"] = (
        "+$2,497.50 vs +$2,290.50 baseline, 15/15 winners kept, +$913.50 out of sample. The "
        "signal is +$2,290.50 over 159 fires / 17 days / 4-of-4 weeks green / positive in all "
        "five regimes, and 53 of 54 filters tested LOSE to just letting it fire. Over the 96.7% "
        "of the week it was benched, the identically-configured twin made +$1,064.50; the router "
        "armed it for the 9% in which it lost −$559.00 on nine lots without a single winner. The "
        "BUILDING × US-SESSION veto is worth +$207.00 · 15/15 winners · strip-3 +$1,987.00 · net "
        "at the 98.5th placebo percentile — but still n=8, re-look at n≥25. "
        f"{MARK} — WITHDRAWN: the ER30 ≥ 0.35 floor keeps 5 of 15 winners, discards +$1,363 of "
        "profitable trades, takes OOS +$809 → +$363, fires zero times in wk29, is −$3,863 pooled "
        "across nine exits, sits at the 77th placebo percentile on winner retention (random "
        "expects 3.4 of 15), is a spike not a plateau (0.325/0.35/0.375 = +$849/+$927/+$679), its "
        "own live evidence dies at strip-1 (+$550.50 → +$14.50), and it silently SUBSUMES AND "
        "DELETES the BUILDING × US veto rather than adding to it.")
    p["kill"] = ("Review after 15 fires armed-by-default; re-bench if the armed book is negative "
                 "over those 15.")
    p["section_ref"] = ("Part 3.1 (REV2 · Q0) + Part 3.6 (REV2 · FIX2) — supersede Part 2.6 §8 "
                        "Saturday #1/#2; extend Part 1.5 rehab_abs_veto_short §5")

    # ─────────────────────────────────────────────────────────────────────────────────────
    # SATURDAY #3 — REPLACED IN FULL.  Source: REV2 · FIX0 §5 "The replacement card — paste this
    # over plays.json rank 3", field by field. The old card named the chandelier, which this play
    # does not touch; the edit actually resolves every sub-slot to exit="scalp" and leaves zero
    # chandeliers in the live slate.
    # ─────────────────────────────────────────────────────────────────────────────────────
    p = by_id(rows, "chandelier-regime-key-width-0808")
    p["id"] = "lotb-rung-widen-atrsplit24-0808"
    p["topic"] = ("Lot B rung: widen it to a fixed 6R and move the quiet-tape clip's ATR gate "
                  "22 → 24")
    p["play"] = (
        f"{MARK} (REV2 · FIX0) — the old card ('regime-key the chandelier width') named a "
        "mechanism this play does not touch and could not be typed into any file the desk reads. "
        "Replaced in full. Edit the six non-NIPC rows of data/exit_overrides.json to "
        '{"a_r": 3.0, "b": 6.0, "atr_split": 24, "lo": {"a_usd": 40, "b_r": 1.75, '
        '"b_floor_usd": 60}}. NIPC keeps its proven {"a_r":2.0,"b":2.5} pair. Three numbers per '
        "row, no code change, no new mechanism.")
    p["mechanism"] = (
        "Lot B fixed-R rung + the quiet-tape clip's ATR threshold. NOT the chandelier — this edit "
        "resolves every sub-slot to exit=\"scalp\" and leaves ZERO chandeliers in the slate.")
    p["arms_when"] = (
        "Entry ATR ≥ 24 only, frozen at entry (slot_strategy.py:422). Below 24 the $40 / 1.75R · "
        "$60 clip is unchanged — it is rank 1 of 28 in two of the four regime cells and 100% of "
        "quiet-tape behaviour is preserved. There is no ER term. Exit selector only; arms and "
        "benches nothing.")
    p["exit"] = (
        "Lot B: fixed 6.0R rung above the split. Lot A: changes on all six gates to 3.0R — "
        "abs_veto_long 1.0→3.0, exhaustion_short 0.75→3.0, capitulation_long / rgv_short / "
        "abs_veto_short 1.5→3.0, grind_long 2.5→3.0.")
    p["number"] = (
        "Config-only, as shipped: archive −$2,932 → +$92 (+$3,024) over 20 sessions, 20/20 LODO "
        "folds positive, min +$1,259; pre-window −$1,859 → +$891; symptom week −$1,073 → −$799. "
        "⚠ Better in only 2 of 4 ISO weeks (W31 +4,557 vs +1,683 and W32 −799 vs −1,073 win; W29 "
        "−954 vs −910 and W30 −2,712 vs −2,632 lose). NOT strictly dominant.")
    p["owner"] = ("Garrath — six rows of data/exit_overrides.json, then "
                  "systemctl restart gazbot7-tournament (overrides are read at slate build; "
                  "confirm the live slate via scaleout_slots(), never source)")
    p["revert"] = ("git checkout data/exit_overrides.json + restart. The file is git-tracked and "
                   "every startup journals its resolved ladder to config_journal.jsonl "
                   "(scripts/config_at.py --diff).")
    p["kill"] = (
        "If the ATR ≥ 24 population goes negative over 20 fresh sessions, or the LODO minimum "
        "drops below zero on the next re-cut, revert. ⚠ READ THIS FIRST: the parameter-plateau "
        "test FAILED (4 of 35 threshold cells positive), 6 of 16 in-cell sessions are green, two "
        "days (07-27, 07-23) carry two-thirds of the edge, and strip-best inverts at top-8 "
        "(−$422). The DIRECTION is robust; the KNOB is not. Size accordingly.")
    p["verification"] = (
        "20 more sessions; re-run the LODO fold and confirm the minimum stays positive. "
        "FOLLOW-UP, NOT THIS PLAY: er_split — the ER30 key, a code change on three lines, better "
        "on every axis (archive +$25, week +$156, LODO floor +$345, 4/4 vs 2/4 ISO weeks) but "
        "margins are small and it needs a deploy. QUEUED, not shipped, and its AND/OR spec must "
        "be resolved first (FIX0 §3).")
    p["section_ref"] = "Part 3.4 (REV2 · FIX0) — replaces Part 2.6 §8 Saturday #3 and the Part 1.5 chandelier lead row"

    # ─────────────────────────────────────────────────────────────────────────────────────
    # HOLD #1 — abs_veto_long.  Source: REV2 · FIX1 §E "THE EDITS THAT REMOVE THE CONTRADICTION",
    # play field, verbatim.  The arms_when field additionally carried a cross-reference to "the
    # ER30 ≥ 0.35 floor that abs_veto_short is getting" — abs_veto_short is no longer getting it,
    # so that clause is struck too or the card contradicts itself.
    # ─────────────────────────────────────────────────────────────────────────────────────
    p = by_id(rows, "hold-absveto-long-0808")
    p["play"] = (
        f"{MARK} (REV2 · FIX1 §E) — No config change this week. Do not add an ER floor — the long "
        "twin's ER profile is the mirror of the short's. Two leads that earlier drafts proposed "
        "are not being deployed and are dispositioned in Part 2 §11: a US-only session guard "
        "(REFUTED — it would bench a positive LONDON book) and a wider Lot B (REFUTED as stated; "
        "a narrower US-chop-only tightChand x2 variant is SHADOW at n=13).")
    p["topic"] = ("abs_veto_long — leave it alone this week. 'Do not touch its exit' over-claims; "
                  "two leads are parked, not absent.")
    p["arms_when"] = (
        "Armed. It only fires when a burst is still going 55 seconds later, which is exactly the "
        "behaviour this week rewarded. Do NOT give it an ER30 floor — the long twin is positive "
        f"in ALL four ER bands (+$4.04 / +$9.40 / +$10.69 / +$7.77 per trade). {MARK} — the "
        "earlier card said 'the floor abs_veto_short is getting'; that floor was WITHDRAWN "
        "(Part 3.1 / Part 3.6), so neither twin gets one.")
    p["number"] = (
        "Sixteen entries, thirty-two lots, +$566.00 at a 62% strike rate, average winner +$47.60 "
        "against an average loser of −$32.20. Still positive if you delete ANY single day "
        "(+$235.50 / +$635.00 / +$582.00 / +$245.50) and still +$363 if you delete its three best "
        f"lots. {MARK} — the '−$258.50 overnight problem' is an ASIA problem and Asia is already "
        "blocked at config level; excluding it the non-US book is +$0.59/lot all-time. The "
        "earlier '−$0.90 above ER 0.35' figure was a live-book sampling artefact.")
    p["section_ref"] = "Part 3.5 (REV2 · FIX1) — resolves HOLD #1 against Part 2 §4, §5, §9, §11"

    # ─────────────────────────────────────────────────────────────────────────────────────
    # BUILD #13 — ext_hi.  This play says "Do NOT remove it on this evidence"; REV2 · Q1 §10 is
    # the later, deeper derivation and removes it. Left on the card (the card keeps refuted rows
    # so nobody re-proposes them) but flagged as superseded, because two rows telling the
    # operator opposite things about the same key is exactly the defect Rev2 was run to find.
    # ─────────────────────────────────────────────────────────────────────────────────────
    p = by_id(rows, "grind-ext-hi-regime-conditional-0808")
    p["topic"] = ("grind_long's ext_hi ceiling — SUPERSEDED by Part 3.2 (REV2 · Q1). Kept on the "
                  "card so the reasoning is not re-proposed.")
    p["play"] = (
        f"{MARK} — SUPERSEDED. This row said 'Do NOT remove it on this evidence', and on the "
        "Movement-2 sat-out-run population that was right: a ceiling judged on exactly the trades "
        "it was designed to skip cannot be judged there. REV2 · Q1 §10 re-derived it on the "
        "tick-honest book and on the 128 live router-gated lots and removes it on BOTH — "
        "everything from 3.0 up scores identically, the live 128 agrees more strongly (the "
        "ceiling deletes 12 real lots worth +$389 at 50% win). Do the SATURDAY #1 deletion; do "
        "not also run this re-derivation.")
    p["tier"] = "REFUTED"
    p["section_ref"] = "Movement 2 §4 — superseded by Part 3.2 (REV2 · Q1 §10)"

    PLAYS.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    n = sum(1 for r in rows if MARK in json.dumps(r, ensure_ascii=False))
    print(f"plays.json rewritten — {n} plays carry the REV2 correction marker, {len(rows)} total.")
    print("  SATURDAY #1 grind-long-revert-atr22-ext30-0808   amended (Q1 §10: delete ext_hi, not 3.0)")
    print("  SATURDAY #2 absveto-short-arm-by-default-er035   amended (Q0+FIX2: ER floor WITHDRAWN)")
    print("  SATURDAY #3 chandelier-regime-key-width-0808  →  lotb-rung-widen-atrsplit24-0808 (FIX0 §5, replaced in full)")
    print("  HOLD #1     hold-absveto-long-0808               amended (FIX1 §E)")
    print("  BUILD #13   grind-ext-hi-regime-conditional      marked SUPERSEDED by Q1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
