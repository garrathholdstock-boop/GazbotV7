"""MOVEMENT 2 — the two tests that decide whether the null is about TIMING or MECHANISM.
(1) LOOKBACK SWEEP: is 10 min just too short a window?  (2) PLACEBO: do these gates fire
any LESS often before a run than in a random 10-min slice of the same tape? If the rates
match, the gates carry no information about runs at all."""
import json, re, sys, random, datetime as dt
from collections import Counter
sys.path.insert(0, "/home/alphabot/gazbot7/scripts"); sys.path.insert(0, "/home/alphabot/gazbot7/src")
from m2_idle_gates import (scan_run, price_fire, GATES, SIDE, TK_TS, M2)
import m2_run as R                                     # reuse the census parse

ARM_LIVE = dict(atr_floor=True,  counter_veto=True,  asia=True,  vetoes=True)
ARM_UNG  = dict(atr_floor=False, counter_veto=False, asia=False, vetoes=False)
runs = R.priceable
out = {}

# ── 1) lookback sweep ─────────────────────────────────────────────────────────
sweep = {}
for lb in (600, 1200, 1800, 3600):
    for name, arm in (("as_live", ARM_LIVE), ("ungated", ARM_UNG)):
        nfire = Counter(); usd = 0.0; runs_hit = 0
        for r in runs:
            if r["s"] - lb < int(TK_TS[0] // 1000):
                continue
            elig, fires, reasons, geom = scan_run(r["s"], r["dir"], arm, lookback_s=lb)
            if fires:
                runs_hit += 1
            for g, fi in fires.items():
                nfire[g] += 1
                p = price_fire(g, fi["side"], fi["s"], fi["atr"])
                if p:
                    usd += p["usd"]
        sweep[f"{name}_{lb//60}m"] = {"fires": dict(nfire), "n": sum(nfire.values()),
                                      "runs_hit": runs_hit, "usd": round(usd, 2)}
        print(f"lookback {lb//60:>2}m {name:8s}: {sum(nfire.values()):3d} fires on "
              f"{runs_hit:2d}/{len(runs)} runs  ${usd:,.2f}  {dict(nfire)}", file=sys.stderr)
out["lookback_sweep"] = sweep

# ── 2) placebo: random 10-min windows on the same tape ────────────────────────
LO, HI = int(TK_TS[0] // 1000) + 700, int(TK_TS[-1] // 1000) - 8000
bad = [r["s"] for r in R.runs]
rnd = random.Random(20260829)
picks, tries = [], 0
while len(picks) < 250 and tries < 20000:
    tries += 1
    s = rnd.randrange(LO, HI)
    if any(abs(s - b) < 1800 for b in bad):
        continue
    picks.append(s)
plac = {}
for name, arm in (("as_live", ARM_LIVE), ("ungated", ARM_UNG)):
    n = Counter(); windows = Counter(); usd = Counter()
    for s in picks:
        for d in ("UP", "DN"):                          # both directions, same as a run window
            elig, fires, reasons, geom = scan_run(s, d, arm)
            for g, fi in fires.items():
                n[g] += 1
                p = price_fire(g, fi["side"], fi["s"], fi["atr"])
                if p:
                    usd[g] += p["usd"]
        windows["w"] += 1
    plac[name] = {"windows": len(picks), "fires": dict(n), "usd": {k: round(v, 2) for k, v in usd.items()}}
    print(f"placebo {name}: {len(picks)} random windows → {dict(n)}  ${sum(usd.values()):,.2f}", file=sys.stderr)
out["placebo"] = plac
json.dump(out, open(f"{M2}/extra.json", "w"))
print("written", file=sys.stderr)
