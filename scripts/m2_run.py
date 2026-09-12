"""MOVEMENT 2 driver — fire the six gates at the frozen census's sat-out runs."""
import json, re, sys, datetime as dt
from collections import Counter, defaultdict
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from m2_idle_gates import (scan_run, price_fire, GATES, SIDE, BASE, LOTS, TK_TS, TK_PX,
                           bars_at, efficiency_ratio, compute_features, VPP, FEE, M2)

CENSUS = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
YEAR = 2026
ROW = re.compile(r"^(\d\d)-(\d\d) (\d\d):(\d\d)\s+(UP|DN)\s+([+-]\d+)\s+(\d+)\s+(sat out|caught|FOUGHT)\s+(\S+)\s+([+-]?\d+)\s+([+-]?\d+)\s+([\d.]+|—)\s+([\d.]+|—)\s+(\S+)")

runs = []
for ln in open(CENSUS):
    m = ROW.match(ln.strip())
    if not m:
        continue
    mo, d, hh, mm, dirn, move, ceil, us, gate, real, flow, amp, book, cl = m.groups()
    t = dt.datetime(YEAR, int(mo), int(d), int(hh), int(mm), tzinfo=dt.timezone.utc)
    runs.append({"t": t.strftime("%m-%d %H:%M"), "s": int(t.timestamp()), "dir": dirn,
                 "move": int(move), "ceil": int(ceil), "us": us, "gate": gate,
                 "flow": int(flow), "amp": None if amp == "—" else float(amp),
                 "book": None if book == "—" else float(book), "cluster": cl})
sat = [r for r in runs if r["us"] == "sat out"]
print(f"parsed {len(runs)} runs, {len(sat)} sat out", file=sys.stderr)

# tick coverage: capture.db ticks start 2026-08-24 00:00Z — the 08-23 22:00 run has bars only
TICK_LO = int(TK_TS[0] // 1000); TICK_HI = int(TK_TS[-1] // 1000)
priceable = [r for r in sat if r["s"] - 600 >= TICK_LO and r["s"] <= TICK_HI]
skipped = [r for r in sat if r not in priceable]
print(f"tick-priceable {len(priceable)}, skipped {[r['t'] for r in skipped]}", file=sys.stderr)

ARMS = {
    "A_as_live":   dict(atr_floor=True,  counter_veto=True,  asia=True,  vetoes=True),
    "B_no_asia":   dict(atr_floor=True,  counter_veto=True,  asia=False, vetoes=True),
    "C_no_atrfl":  dict(atr_floor=False, counter_veto=True,  asia=False, vetoes=True),
    "D_ungated":   dict(atr_floor=False, counter_veto=False, asia=False, vetoes=False),
}

def regime(atr, er):
    if er >= 0.45:  return "clean-trend"
    if er >= 0.25:  return "building"
    if atr >= 22:   return "violent-whipsaw"
    if atr < 12:    return "dead-chop"
    return "normal-chop"

def block(s):
    h = (s % 86400) / 3600.0
    if h < 7:      return "ASIA 00-07"
    if h < 13.5:   return "LONDON 07-13:30"
    if h < 21:     return "US 13:30-21"
    return "POST 21-24"

res = {"arms": {}, "runs": [r["t"] for r in priceable], "skipped": [r["t"] for r in skipped],
       "n_runs": len(runs), "n_sat": len(sat)}
for arm, cfg in ARMS.items():
    per_run, geom_tot, reas_tot = [], Counter(), defaultdict(Counter)
    for r in priceable:
        elig, fires, reasons, geom = scan_run(r["s"], r["dir"], cfg)
        for g in elig:
            geom_tot[g] += 1 if geom.get(g) else 0
            for k, v in reasons[g].items():
                reas_tot[g][k] += v
        row = {"run": r["t"], "dir": r["dir"], "move": r["move"], "ceil": r["ceil"],
               "cluster": r["cluster"], "block": block(r["s"]), "elig": elig, "fires": {}}
        for g, fi in fires.items():
            p = price_fire(g, fi["side"], fi["s"], fi["atr"])
            if p is None:
                continue
            row["fires"][g] = {**fi, "regime": regime(fi["atr"], fi["er"]),
                               "lead_s": r["s"] - fi["s"], "usd": p["usd"],
                               "entry_px": p["entry_px"],
                               "lots": p["lots"]}
        per_run.append(row)
    res["arms"][arm] = {"per_run": per_run,
                        "geom_runs": dict(geom_tot),
                        "reasons": {g: dict(c) for g, c in reas_tot.items()}}
    n = sum(len(x["fires"]) for x in per_run)
    usd = sum(f["usd"] for x in per_run for f in x["fires"].values())
    print(f"{arm}: {n} gate-fires on {sum(1 for x in per_run if x['fires'])} runs, ${usd:,.2f}", file=sys.stderr)

json.dump(res, open(f"{M2}/results.json", "w"), default=str)
print("written", file=sys.stderr)
