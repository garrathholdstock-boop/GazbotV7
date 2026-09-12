#!/usr/bin/env python3
"""THE GAUNTLET - every candidate cell against the addendum's three bars.

  (a) beat zero at 1.25pt measured friction
  (b) beat its own LIKE-FOR-LIKE twin by more than the twin's spread
      -> twin = SIGN-FLIP, day-blocked: the identical entry bars, the identical holds, ONLY the
         direction randomised. 100% entry overlap, verified in control_audit.py. The 5-way
         label permutation is NOT used to decide anything - it moves the entry set (measured:
         1983 -> 2646 entries, 45-100% bar overlap).
  (c) survive a DAY-BLOCK bootstrap CI that excludes zero.

Also reported: the always-long same-bar control, buy-and-hold, and the friction curve per cell.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

FRIC = 1.25
_gcache, _mcache = {}, {}

def model(bar, K, fset):
    if bar not in _gcache:
        _gcache.clear(); _gcache[bar] = R.load_bars(bar)
    key = (bar, K, fset)
    if key not in _mcache:
        _mcache.clear(); _mcache[key] = R.Model(bar, K, fset, g=_gcache[bar])
    return _mcache[key]

def dwell_signals(M, K, er_feat=None, floor=None):
    """The dwell arm's trigger, re-expressed as a signal index list (see dwell.py)."""
    sys.path.insert(0, os.path.dirname(__file__))
    from dwell import runs
    if er_feat is None:
        q, s = M.sign != 0, M.sign
    else:
        er = np.nan_to_num(M.feat[er_feat], nan=-1)
        q, s = (M.sign != 0) & (er >= floor), M.sign
    st, ln, sd = runs(q, s, M.g.sess.values)
    m = ln >= K
    return (st[m] + K - 1)

def adjudicate(spec, draws=4000):
    M = model(spec["bar"], spec["states"], spec["fset"])
    if spec.get("dwell"):
        idx = dwell_signals(M, spec["dwell"], spec.get("erfeat"), spec.get("floor"))
        if spec.get("win"):
            mod = M.g["mod"].values[idx]
            w = spec["win"]; idx = idx[(mod >= w[0]) & (mod < w[1])]
    else:
        idx = R.signals(M, clean=spec.get("clean", 2), win=spec.get("win"),
                        vz_min=spec.get("vz"), tp_min=spec.get("tp"))
    hold = spec["hold_min"] // spec["bar"]
    T = R.trades(M, idx, hold=hold, friction=FRIC, exit_mode=spec.get("exit", "time"),
                 hold_cap=hold, pull=spec.get("pull", 0.0))
    if len(T) < 60:
        return None
    ps = R.period_stats(T, M)
    sc = R.sign_control(T, draws=draws, block="day", friction=FRIC)
    lo, mid, hi = R.day_block_boot(T, friction=FRIC, draws=draws)
    al = R.trades(M, T.i.values, hold=hold, friction=FRIC, exit_mode=spec.get("exit", "time"),
                  hold_cap=hold, pull=spec.get("pull", 0.0),
                  side_override=np.ones(len(T), int))
    ash = R.trades(M, T.i.values, hold=hold, friction=FRIC, exit_mode=spec.get("exit", "time"),
                   hold_cap=hold, pull=spec.get("pull", 0.0),
                   side_override=-np.ones(len(T), int))
    # ── the bull-tape baselines at the cell's OWN bars (sibling result 2026-09-12) ──
    al_lo, al_mid, al_hi = R.day_block_boot(al, friction=FRIC, draws=1500)
    edge = mid - sc["mean"]
    out = dict(name=spec["name"], n=len(T),
               gross=T.gross.mean(), sd=T.gross.std(ddof=1), net125=mid,
               TR_n=ps["TRAIN"]["n"], TR=ps["TRAIN"]["mean"],
               VA_n=ps["VALIDATE"]["n"], VA=ps["VALIDATE"]["mean"],
               TE_n=ps["TEST"]["n"], TE=ps["TEST"]["mean"],
               twin_mean=sc["mean"], twin_sd=sc["sd"], edge_sd=edge / sc["sd"],
               twin_p=sc["p"], boot_lo=lo, boot_hi=hi,
               long_pct=100*(T.side > 0).mean(),
               always_long=al.pt.mean() if len(al) else np.nan,
               always_long_lo=al_lo, always_long_hi=al_hi,
               always_short=ash.pt.mean() if len(ash) else np.nan,
               beats_always_long=mid > al_hi,
               a_beats_zero=mid > 0,
               b_beats_twin=edge > sc["sd"],
               c_ci_excl_zero=(lo > 0),
               three_period=(ps["TRAIN"]["mean"] > 0 and ps["VALIDATE"]["mean"] > 0
                             and ps["TEST"]["mean"] > 0))
    for f in R.FRICTIONS:
        out[f"net@{f}"] = T.gross.mean() - f
    return out

CANDS = [
  dict(name="INCUMBENT 15m/3/base clean2 90m",  bar=15, states=3, fset="base", clean=2, hold_min=90),
  dict(name="INCUMBENT 15m/3/base clean2 60m",  bar=15, states=3, fset="base", clean=2, hold_min=60),
  dict(name="INCUMBENT 15m/3/base clean0 60m",  bar=15, states=3, fset="base", clean=0, hold_min=60),
  dict(name="GRIDA best 3-period 15m/5/drift OPEN 180m", bar=15, states=5, fset="drift",
       clean=0, win=(810, 960), hold_min=180),
  dict(name="GRIDA best-t 30m/3/base_vol clean2 EUUS 180m", bar=30, states=3, fset="base_vol",
       clean=2, win=(480, 1200), hold_min=180),
  dict(name="GRIDA 30m/3/base_vol clean2 LDN 180m", bar=30, states=3, fset="base_vol",
       clean=2, win=(480, 810), hold_min=180),
  dict(name="GRIDA 15m/5/drift clean0 RTH 180m", bar=15, states=5, fset="drift",
       clean=0, win=(810, 1200), hold_min=180),
  dict(name="DWELL K=1 STATE 90m (the incumbent trigger)", bar=15, states=3, fset="base",
       dwell=1, hold_min=90),
  dict(name="DWELL K=3 STATE 60m", bar=15, states=3, fset="base", dwell=3, hold_min=60),
  dict(name="DWELL K=6 STATE 120m", bar=15, states=3, fset="base", dwell=6, hold_min=120),
  dict(name="DWELL K=5 BOTH er8>=.3 60m", bar=15, states=3, fset="base", dwell=5,
       erfeat="er8", floor=0.3, hold_min=60),
  dict(name="DWELL K=6 BOTH er8>=.45 60m", bar=15, states=3, fset="base", dwell=6,
       erfeat="er8", floor=0.45, hold_min=60),
  dict(name="DWELL K=5 BOTH er4>=.4 90m", bar=15, states=3, fset="base", dwell=5,
       erfeat="er4", floor=0.4, hold_min=90),
  dict(name="DWELL K=4 BOTH er4>=.4 90m", bar=15, states=3, fset="base", dwell=4,
       erfeat="er4", floor=0.4, hold_min=90),
  dict(name="REVERT exit 15m/3/base clean2 cap90m", bar=15, states=3, fset="base", clean=2,
       hold_min=90, exit="revert"),
]
if __name__ == "__main__":
    extra = sys.argv[1] if len(sys.argv) > 1 else None
    cands = list(CANDS)
    if extra and os.path.exists(extra):
        cands += json.load(open(extra))
    rows = [r for r in (adjudicate(c) for c in cands) if r]
    D = pd.DataFrame(rows)
    D.to_csv(f"{R.ART}/tables/adjudication.csv", index=False)
    pd.set_option("display.width", 250)
    print("THE GAUNTLET  ·  friction 1.25pt  ·  twin = day-blocked SIGN-FLIP on identical bars\n")
    print(D[["name", "n", "gross", "sd", "net125", "TR", "VA", "TE", "three_period"]]
          .round(2).to_string(index=False))
    print("\nCONTROLS AND CONFIDENCE")
    print(D[["name", "n", "net125", "twin_mean", "twin_sd", "edge_sd", "twin_p",
             "boot_lo", "boot_hi"]].round(2).to_string(index=False))
    print("\nTHE BULL-TAPE BASELINES - same entry bars, same hold, direction forced")
    print("  (this lake runs MNQ 24,352 -> 29,560, +21%: a long is paid for existing)")
    print(D[["name", "n", "long_pct", "net125", "always_long", "always_long_lo",
             "always_long_hi", "always_short", "beats_always_long"]].round(2)
          .to_string(index=False))
    print("\nTHE THREE BARS  (a) net>0 @1.25  (b) beats twin by >1 twin-sd  (c) bootstrap CI excludes 0")
    print(D[["name", "a_beats_zero", "b_beats_twin", "c_ci_excl_zero", "three_period"]]
          .to_string(index=False))
    print("\nFRICTION SENSITIVITY per candidate (net pt/trade)")
    print(D[["name", "n"] + [f"net@{f}" for f in R.FRICTIONS]].round(2).to_string(index=False))
    surv = D[D.a_beats_zero & D.b_beats_twin & D.c_ci_excl_zero]
    print(f"\nCELLS CLEARING ALL THREE BARS: {len(surv)} of {len(D)}")
    if len(surv):
        print(surv[["name", "n", "net125", "edge_sd", "boot_lo", "boot_hi"]].round(2)
              .to_string(index=False))
