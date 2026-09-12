#!/usr/bin/env python3
"""REV2 — Movement 2 §4, re-scored LIKE FOR LIKE.

WHY. The section's kill line read: "showing up at a RANDOM second, pointed the right way, beats the
gates' own triggers on 6 of 6." That compared a DIRECTION-HANDED control (mean $/fire WITH the run)
against a DIRECTION-BLIND gate figure (the gate's all-fires $/lot, both directions). The control was
told which way the run went; the gate was not. On that footing every gate loses by construction and
the comparison carries no information.

This re-scores it two consistent ways, and adds the significance the 0-of-6 line never had:

  A. IN-DIRECTION: the gate's own in-direction $/lot vs the WITH-the-run control.
  B. DIRECTION-BLIND: the gate's all-fires $/lot vs the mean of the WITH and AGAINST controls.

Then, because the in-direction lot counts are 2 to 10, it bootstraps: draw n_lots from the control
pool 20,000 times and report P(control mean >= gate mean). A comparison at n=2 is not a verdict and
the p-value is the honest way to say so.

Inputs (both written by the movement2_idle phase this cycle):
  reports/friday_v7/sections/m2_lab.json       per-lot replay, mech + ungated
  reports/friday_v7/sections/m2_placebo2.json  random-entry pools, WITH and "<gate>|AGAINST"

  python3 scripts/rev2_m2_indirection_control.py
"""
from __future__ import annotations

import json
import pathlib
import random

SEC = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/sections")
DRAWS = 20_000
SEED = 20260829            # fixed so the table is reproducible


def main() -> int:
    lab = json.loads((SEC / "m2_lab.json").read_text())
    plc = json.loads((SEC / "m2_placebo2.json").read_text())
    rng = random.Random(SEED)

    ung = [t for t in lab["trades"] if t.get("layer") == "ungated"]
    gates = sorted({k for k in plc if "|" not in k} | {t["gate"] for t in ung})

    rows = []
    for g in gates:
        lots = [t for t in ung if t["gate"] == g]
        ind = [t for t in lots if t.get("in_dir")]
        with_pool = plc.get(g, {}).get("pool") or []
        agn_pool = plc.get(f"{g}|AGAINST", {}).get("pool") or []
        ctl_with = plc.get(g, {}).get("mean_per_fire")
        ctl_agn = plc.get(f"{g}|AGAINST", {}).get("mean_per_fire")
        ctl_blind = None
        if ctl_with is not None and ctl_agn is not None:
            ctl_blind = (ctl_with + ctl_agn) / 2

        all_pl = round(sum(t["net"] for t in lots), 2)
        all_lot = round(all_pl / len(lots), 2) if lots else None
        ind_pl = round(sum(t["net"] for t in ind), 2)
        ind_lot = round(ind_pl / len(ind), 2) if ind else None

        # bootstrap: could n_lots random in-direction entries have produced the gate's mean?
        p_ind = None
        if ind and with_pool:
            n = len(ind)
            hits = sum(1 for _ in range(DRAWS)
                       if sum(rng.choice(with_pool) for _ in range(n)) / n >= ind_lot)
            p_ind = round(hits / DRAWS, 4)
        p_blind = None
        if lots and with_pool and agn_pool:
            n = len(lots)
            pool = with_pool + agn_pool
            hits = sum(1 for _ in range(DRAWS)
                       if sum(rng.choice(pool) for _ in range(n)) / n >= all_lot)
            p_blind = round(hits / DRAWS, 4)

        rows.append(dict(
            gate=g, lots=len(lots), all_pl=all_pl, all_lot=all_lot,
            ind_lots=len(ind), ind_pl=ind_pl, ind_lot=ind_lot,
            ctl_with=None if ctl_with is None else round(ctl_with, 2),
            ctl_against=None if ctl_agn is None else round(ctl_agn, 2),
            ctl_blind=None if ctl_blind is None else round(ctl_blind, 2),
            beats_in_direction=(None if ind_lot is None or ctl_with is None
                                else ind_lot > ctl_with),
            beats_blind=(None if all_lot is None or ctl_blind is None
                         else all_lot > ctl_blind),
            p_in_direction=p_ind, p_blind=p_blind))

    scored_i = [r for r in rows if r["beats_in_direction"] is not None]
    scored_b = [r for r in rows if r["beats_blind"] is not None]
    out = dict(
        rows=rows,
        in_direction=f"{sum(1 for r in scored_i if r['beats_in_direction'])} of {len(scored_i)}",
        direction_blind=f"{sum(1 for r in scored_b if r['beats_blind'])} of {len(scored_b)}",
        unmeasurable=[r["gate"] for r in rows if r["beats_in_direction"] is None],
        draws=DRAWS, seed=SEED)
    print(json.dumps(out, indent=2))
    (SEC / "rev2_m2_control.json").write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
