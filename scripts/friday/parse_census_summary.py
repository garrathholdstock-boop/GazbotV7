#!/usr/bin/env python3
"""Parse run_census.py stdout into census_summary.json (the frozen snapshot the Friday
workflow's census agent reads instead of re-running the multi-minute crunch)."""
import json
import re
import sys

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
txt = open(f"{SEC}/census_stdout.txt").read().splitlines()

runs = None
clusters = {}
sat_out = None
ceiling = 0.0
sat_rows = []
in_clusters = False

row_re = re.compile(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]?\d+)\s+(\d+)\s+(caught|FOUGHT|sat out)\b")
for ln in txt:
    m = re.search(r"·\s*(\d+)\s+runs\s+≥", ln)
    if m and runs is None:
        runs = int(m.group(1))
    r = row_re.match(ln)
    if r:
        tm, direction, mv, _ceil, us = r.group(1), r.group(2), int(r.group(3)), int(r.group(4)), r.group(5)
        if us == "sat out":
            sat_rows.append({"time": tm, "dir": direction, "move": mv})
        continue
    if "── CLUSTERS ──" in ln:
        in_clusters = True
        continue
    if in_clusters:
        cm = re.match(r"\s+(\S[\S ]*?)\s+(\d+)\s+runs\s*$", ln)
        if cm:
            clusters[cm.group(1).strip()] = int(cm.group(2))
        elif ln.strip() and not ln.startswith(" "):
            in_clusters = False
    sm = re.search(r"SAT OUT\s+(\d+)\s+runs\s+·\s+ceiling\s+\$\s*([\d.]+)", ln)
    if sm:
        sat_out = int(sm.group(1))
        ceiling = float(sm.group(2))

sat_rows.sort(key=lambda x: abs(x["move"]), reverse=True)
top25 = sat_rows[:25]
top15 = sat_rows[:15]
if sat_out is None:
    sat_out = len(sat_rows)

out = {"runs": runs or 0, "sat_out": sat_out, "ceiling": ceiling,
       "clusters": clusters, "top25": top25, "top15": top15,
       "_note": "sat-out runs by |move| desc; ceiling = sat-out hindsight $ (money on the table)"}
json.dump(out, open(f"{SEC}/census_summary.json", "w"), indent=2)
print(json.dumps({k: v for k, v in out.items() if k not in ("top25", "top15")}, indent=2))
print(f"top25 n={len(top25)} top15 n={len(top15)} · biggest sat-out: {sat_rows[0] if sat_rows else None}")
sys.stderr.write("wrote census_summary.json\n")
