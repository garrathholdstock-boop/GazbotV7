#!/usr/bin/env python3
"""Repoint the card's internal cross-references after the 2026-08-08 re-rank, and make them
self-checking from now on.

★ THE PROBLEM. Plays refer to each other by POSITION — "see MONDAY #4", "the auditor is built
(BUILD #2)". Positions are exactly what a re-rank changes, so every such reference rotted the
moment the card was reordered: "see MONDAY #4" pointed at the chop off-switch when it was
written and points at the untradeable meter now. Nothing detected it, because a stale pointer
is still a syntactically valid sentence.

★ THE FIX. Each reference carries the target's ID alongside its position —
`MONDAY #1 (chop-avoidance-is-the-biggest-number-0808)`. The position stays readable for a
human; the id makes the pair CHECKABLE. `friday_v7_build.py` now asserts, at pre-flight, that
every such pair resolves to a play actually sitting at that window and rank, and refuses to
build if one does not. A re-rank that forgets to update a reference is now a hard failure
instead of a document that quietly misdirects the operator.

Revert: cp reports/friday_v7/plays.json.pre-xref reports/friday_v7/plays.json
"""
import json
import pathlib
import sys

PLAYS = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/plays.json")
BACKUP = PLAYS.with_suffix(".json.pre-xref")

# (play id, field, exact old text, new text) — every one verified against the current ranking.
FIXES = [
    # "Do the SATURDAY #1 deletion" — the grind_long revert, which moved #1 -> #2 when
    # abs_veto_short took the top slot.
    ("grind-ext-hi-regime-conditional-0808", "play",
     "Do the SATURDAY #1 deletion",
     "Do the SATURDAY #2 (grind-long-revert-atr22-ext30-0808) deletion"),

    # The orphan-stop auditor was promoted BUILD #2 -> SATURDAY #3.
    ("not-odr-as-a-gate-or-beside-day-rider-0808", "number",
     "auditor is built (BUILD #2)",
     "auditor is built (SATURDAY #3, orphan-stop-auditor-on-a-timer-0808)"),

    # The chop off-switch moved MONDAY #4 -> MONDAY #1.
    ("not-any-chop-scalp-0808", "rationale",
     "see MONDAY #4",
     "see MONDAY #1 (chop-avoidance-is-the-biggest-number-0808)"),

    # Two in one sentence. "the chandelier regime-key (SATURDAY #3)" is doubly wrong now: that
    # play was REPLACED in full by REV2 FIX0 (it was never a chandelier play) and it moved to
    # SATURDAY #10. The quiet-clip carve-out moved BUILD #12 -> BUILD #14.
    ("not-the-exit-ladder-guess-0808", "number",
     "the chandelier regime-key (SATURDAY #3) and the quiet-clip carve-out (BUILD #12)",
     "the Lot B rung widening (SATURDAY #10, lotb-rung-widen-atrsplit24-0808 — renamed from "
     "'chandelier regime-key' by REV2 FIX0, which found it touches no chandelier) and the "
     "quiet-clip carve-out (BUILD #14, quiet-clip-regime-carveout-0808)"),

    # Already correct, but pin the id so the guard can verify it.
    ("exhaustion-short-exit-revert-8-12-120-0808", "play",
     "BLOCKED on BUILD #1 (fix-shadow-repricer-stop-detection-0808)",
     "BLOCKED on BUILD #1 (fix-shadow-repricer-stop-detection-0808)"),
]


def main():
    rows = json.loads(PLAYS.read_text())
    byid = {r["id"]: r for r in rows}
    BACKUP.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    applied, already = 0, 0
    for pid, field, old, new in FIXES:
        r = byid.get(pid)
        if r is None:
            raise SystemExit(f"FATAL — no such play: {pid}")
        text = r.get(field, "")
        if new in text and old != new:
            already += 1
            continue
        if old not in text:
            raise SystemExit(
                f"FATAL — {pid}.{field} does not contain the expected text.\n"
                f"  looking for: {old!r}\n  field reads: {text[:300]!r}\n"
                f"The card changed under this script; re-derive the fixes before forcing it.")
        r[field] = text.replace(old, new)
        applied += 1
        print(f"  {pid}.{field}\n      {old!r}\n   -> {new!r}")

    PLAYS.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{applied} cross-reference(s) repointed, {already} already current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
