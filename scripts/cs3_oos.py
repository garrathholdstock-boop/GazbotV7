"""CHOP-SCALP 2026-08-29 — THE PRE-REGISTERED OUT-OF-SAMPLE TEST.

The 2026-08-25 study searched 07-31..08-24 and named three finalists with FROZEN parameters.
Four trading days have happened since. This runs those exact rules, unchanged, on tape that did
not exist when they were chosen. No re-tuning, no cell search, no re-fitting of the median
thresholds -- the `f_refill` median that defines CT15 is the one measured on the ORIGINAL window,
because a median re-estimated on the new tape would be a second fit.

★ HONESTY ON THE OOS BOUNDARY. The prior write-up is dated 2026-08-25 23:39Z and its event tape
stops at 08-24. 08-25's session closed 21:00Z that day, so 08-25 was *available* though unused.
Both legs are reported: STRICT (08-26..08-28, unambiguously later) and WIDE (08-25..08-28).

⚠ FEE $1.50/round trip, MNQ $2.00/pt. Cost model imported, never re-declared.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, SLIP_STOP_PT, load_events
from cs2_sweep import sequential, F, CANDS, GRID

ORIG_DAYS = ["2026-07-31", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07",
             "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14",
             "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24"]
NEW_WIDE = ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]
NEW_STRICT = ["2026-08-26", "2026-08-27", "2026-08-28"]

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
have = sorted(d.date.unique())
print(f"[events] {len(d):,} rows over {len(have)} days {have[0]}..{have[-1]}")
print(f"[new days present] {[x for x in NEW_WIDE if x in set(have)]}")

# ---- the FROZEN thresholds, estimated on the ORIGINAL window only -----------------
orig = d.date.isin(ORIG_DAYS)
REFILL_MED = float(d.f_refill[CHOP & orig].median())
print(f"[frozen] CT15 refill median (ORIGINAL window only) = {REFILL_MED:.3f}")

FIN = {
 "CT13  close@30m-ext + 20s thrust>=4pt      tp6/sp10":
     (CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4.0), 6.0, 10.0),
 "CT16  close@30m-ext + 20s thrust>=5pt      tp8/sp10":
     (CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 5.0), 8.0, 10.0),
 "CT15  CT13 + 41ms refill >= frozen median  tp8/sp10":
     (CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4.0) & (d.f_refill >= REFILL_MED), 8.0, 10.0),
 "CT0   naive chop fade (control)            tp6/sp10":
     (CHOP, 6.0, 10.0),
}

def run(mask, tp, sp, days):
    sub = d[mask & d.date.isin(days)]
    if not len(sub):
        return pd.DataFrame(columns=["usd", "date", "kind"])
    parts = [sequential(g.sort_values("dts"), tp, sp) for _, g in sub.groupby("date")]
    return pd.concat(parts, ignore_index=True)

def S(o):
    if o is None or len(o) == 0:
        return dict(n=0, net=0.0, ptr=float("nan"), win=float("nan"), days=0, open=0)
    return dict(n=len(o), net=round(float(o.usd.sum()), 2), ptr=round(float(o.usd.mean()), 3),
                win=round(float((o.usd > 0).mean()), 3), days=int(o.date.nunique()),
                open=int((o.kind == "OPEN").sum()))

res = {"refill_median_frozen": round(REFILL_MED, 3), "cands": {}}
print("\n=== PRE-REGISTERED OOS: frozen rules on tape chosen after they were ===")
hdr = f"{'candidate':52s} {'leg':8s} {'n':>4s} {'net':>9s} {'$/tr':>8s} {'win':>6s} {'days':>5s} {'open':>5s}"
print(hdr); print("-" * len(hdr))
for lab, (m, tp, sp) in FIN.items():
    row = {}
    for tag, days in (("IN-SAMP", ORIG_DAYS), ("OOS-wide", NEW_WIDE), ("OOS-strict", NEW_STRICT)):
        o = run(m, tp, sp, days)
        s = S(o); row[tag] = s
        row[tag]["per_day"] = {k: [int(v['size']), round(float(v['sum']), 2)]
                               for k, v in o.groupby("date").usd.agg(["size", "sum"]).iterrows()} if len(o) else {}
        print(f"{lab:52s} {tag:8s} {s['n']:>4d} {s['net']:>9.2f} "
              f"{s['ptr']:>8.3f} {s['win']:>6.1%} {s['days']:>5d} {s['open']:>5d}"
              if s['n'] else f"{lab:52s} {tag:8s} {0:>4d} {'--':>9s} {'--':>8s} {'--':>6s} {0:>5d} {0:>5d}")
    res["cands"][lab] = row
    for tag in ("OOS-wide",):
        if row[tag]["per_day"]:
            print(f"{'':52s}          per-day: {row[tag]['per_day']}")

json.dump(res, open(f"{OUT}/oos.json", "w"), indent=1)
print(f"\n[wrote] {OUT}/oos.json")
