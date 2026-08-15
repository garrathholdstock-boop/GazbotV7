#!/usr/bin/env python3
"""Adapt V7 plays.json into the shape /home/alphabot/alphabot2/scripts/friday/build_playbook.py wants.

The two files disagree on ONE field and it matters. The V7 report treats `verification` as free
text — "the test that would prove this wrong" — because that is what belongs on the report's
action card. The V5-era playbook builder treats `verification` as a CLASS
('verified' | 'bug' | 'refuted' | 'exploratory') and keys its Live-lock guardrail off it: a play
that is not 'verified' or 'bug' cannot be set Live in the picker.

Feed the V7 file to it unadapted and every one of the 38 plays lands in "exploratory", the
guardrail becomes meaningless (it locks everything, including the things that are already live),
and the free-text test string is rendered as if it were a class label.

So we translate rather than mutate: plays.json stays the report's source of truth, and this
writes a DERIVED file for the picker. The mapping is deliberately conservative — SHADOW and
PARKED both become 'exploratory' so the picker refuses to let them go Live, which is exactly the
disposition discipline the report already applies.
"""
from __future__ import annotations

import json
import pathlib

SRC = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"
DST = "/home/alphabot/gazbot7/reports/friday_v7/plays_playbook.json"

# V7 evidence tier -> the picker's verification class.
#   'verified' / 'bug'         -> may be set Live in the picker
#   'exploratory' / 'refuted'  -> Live is locked; shadow it first
TIER_TO_CLASS = {
    "LIVE": "verified",       # already deployed or backed by a survived battery
    "SHADOW": "exploratory",  # promising, unproven — the picker must refuse Live
    "PARKED": "exploratory",  # failed as built, has a named revival path
    "REFUTED": "refuted",     # a named test killed it
}

# V7 suggested_mode -> the picker's default toggle.
MODE_TO_DEFAULT = {
    "deploy": "live", "config": "live",
    "shadow-first": "shadow", "build": "shadow",
    "no-op": "skip",
}


def main():
    plays = json.loads(pathlib.Path(SRC).read_text())
    out = []
    for p in plays:
        head = p["tier"].split()[0].upper()
        vclass = TIER_TO_CLASS.get(head, "exploratory")
        default = MODE_TO_DEFAULT.get(p.get("suggested_mode", ""), "skip")
        # HOLD and NOT-AN-ACTION are, by construction, instructions NOT to change anything.
        # They belong on the card so nobody re-proposes them, but they must never default to a
        # toggle that reads as "do this".
        if p["window"] in ("HOLD", "NOT-AN-ACTION"):
            default = "skip"
        # The picker renders `rationale` as the card's body and has no field for the test, the
        # evidence number or the report's own scope notes — so fold them all in rather than
        # losing them. Overwriting `rationale` with `mechanism` alone silently dropped every
        # "★ REV2" correction on 2026-08-15: the Rev-2 pass records WHY a play was re-scoped or
        # its money restated in `rationale`/`number`, and the operator acts off this card.
        body = p.get("mechanism", "")
        for label, key in (("", "rationale"), ("The number: ", "number")):
            if p.get(key):
                body = f"{body}  ·  {label}{p[key]}"
        if p.get("verification"):
            body = f"{body}  ·  Proven wrong by: {p['verification']}"
        out.append({**p,
                    "verification": vclass,
                    "verification_test": p.get("verification", ""),
                    "suggested_mode": default,
                    "rationale": body,
                    "section_ref": f'{p["window"]} #{p["rank"]} · {p.get("section_ref", "")}'})

    pathlib.Path(DST).write_text(json.dumps(out, indent=1))
    counts = {}
    for p in out:
        counts[p["verification"]] = counts.get(p["verification"], 0) + 1
    print(f"wrote {DST} — {len(out)} plays")
    for k, v in sorted(counts.items()):
        print(f"  {k:<12} {v}")


if __name__ == "__main__":
    main()
