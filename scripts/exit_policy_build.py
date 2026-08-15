#!/usr/bin/env python3
"""Turn the exit-ladder grid into the DEPLOYABLE per-rung policy — and refuse to change what did
not survive robustness.

A cell only earns a policy change if it clears ALL of:
  · positive $/signal on its HOME rung
  · positive after STRIP-THE-BEST-3-DAYS
  · positive LEAVE-ONE-DAY-OUT worst case
Anything else HOLDS at the live config in data/exit_overrides.json. Cells that survive but are
thin (n<40) or contradicted by the V5 archive leg are marked SHADOW, not LIVE.

Writes data/exit_overrides_proposed.json — a PROPOSAL. It does NOT touch the live file; deploying
is a Saturday decision, not a report side-effect.

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/exit_policy_build.py
"""
from __future__ import annotations
import json

GRID = json.load(open("/home/alphabot/gazbot7/data/exit_ladder_grid.json"))
LIVE = json.load(open("/home/alphabot/gazbot7/data/exit_overrides.json"))
OUT = "/home/alphabot/gazbot7/data/exit_overrides_proposed.json"

# gate family -> the LIVE gate(s) it governs
FAM2GATE = {
    "grind (mom)":         ["grind_long"],
    "thrust/absveto":      ["abs_veto_long", "abs_veto_short"],
    "rgv (fade)":          ["rgv_short"],
    "capitulation (fade)": ["capitulation_long"],
    "exhaustion (fade)":   ["exhaustion_short"],
}
RUNGS = ["BIG-TREND", "MED-TREND", "SCALP-CHOP", "STAY-OUT"]

rows = []
for fam, rungs in GRID.items():
    for rg in RUNGS:
        v7 = rungs.get(rg, {}).get("V7")
        v5 = rungs.get(rg, {}).get("V5")
        if not v7:
            continue
        survives = (v7["per"] > 0 and v7["strip3"] > 0 and
                    (v7["loo_worst"] is not None and v7["loo_worst"] > 0))
        if not survives:
            verdict, why = "HOLD", ("negative on its home rung" if v7["per"] <= 0 else
                                    "dies on strip-best-3" if v7["strip3"] <= 0 else
                                    "dies on leave-one-day-out")
        elif v7["n"] < 40:
            verdict, why = "SHADOW", f"survives but thin (n={v7['n']})"
        else:
            verdict, why = "ADOPT", "positive after strip-3 and leave-one-day-out"
        if survives and v5 and v5["per"] <= 0:
            why += " · ⚠ V5 archive leg DISAGREES"
            if verdict == "ADOPT":
                verdict = "SHADOW"
        rows.append(dict(fam=fam, rung=rg, n=v7["n"], best=v7["best"], per=v7["per"],
                         strip3=v7["strip3"], loo=v7["loo_worst"], win=v7["win"],
                         v5_per=(v5["per"] if v5 else None), v5_n=(v5["n"] if v5 else None),
                         verdict=verdict, why=why))

print(f"{'family':21}{'rung':11}{'n':>5}  {'policy':16}{'$/sig':>8}{'strip3':>8}{'LOO':>7}"
      f"{'V5 leg':>9}  {'verdict':8} why")
print("-" * 128)
for r in sorted(rows, key=lambda x: (x["fam"], RUNGS.index(x["rung"]))):
    v5s = f"{r['v5_per']:+.1f}(n{r['v5_n']})" if r["v5_per"] is not None else "—"
    print(f"{r['fam']:21}{r['rung']:11}{r['n']:>5}  {r['best']:16}{r['per']:>+8.1f}"
          f"{r['strip3']:>+8.0f}{(r['loo'] if r['loo'] is not None else 0):>+7.1f}{v5s:>9}  "
          f"{r['verdict']:8} {r['why']}")

# ── build the proposal ──
prop = json.loads(json.dumps(LIVE))          # start from live; only change what earned it
changes = []
for r in rows:
    if r["verdict"] not in ("ADOPT", "SHADOW"):
        continue
    for gate in FAM2GATE.get(r["fam"], []):
        cur = prop.setdefault(gate, {})
        rung_map = cur.setdefault("by_rung", {})
        b = r["best"]
        if b == "tightChandx2":
            spec = {"a": "tightChand", "b": "tightChand"}
        elif b == "wideChandx2":
            spec = {"a": "wideChand", "b": "wideChand"}
        elif "/" in b and "Chand" in b:
            spec = {"a_r": float(b.split("/")[0][1:]), "b": b.split("/")[1]}
        else:
            spec = {"a_r": float(b.split("/")[0][1:]), "b_r": float(b.split("/B")[1])}
        spec["status"] = r["verdict"]
        spec["evidence"] = {"n": r["n"], "per_sig": round(r["per"], 2),
                            "strip3": round(r["strip3"]), "loo_worst": round(r["loo"], 2)}
        rung_map[r["rung"]] = spec
        changes.append(f"{gate} / {r['rung']} -> {b} [{r['verdict']}]")

json.dump(prop, open(OUT, "w"), indent=1)
print(f"\nPROPOSED changes ({len(changes)}) — everything else HOLDS at the live config:")
for c in changes:
    print("  ·", c)
print(f"\nwrote {OUT}  (proposal only — the live data/exit_overrides.json is untouched)")
