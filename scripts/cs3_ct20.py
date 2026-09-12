"""CHOP-SCALP 2026-08-29 — CT20, the only cell in the 1,280-cell necessary-condition scan that
both CLEARS THE FRICTION and is not beaten by its own matched null.

CT20 = on chop tape, at a 10-min extreme, fade when the 60-SECOND move into that extreme is in the
top 5% (f_mv60 >= q95). Frictionless 30s drift +1.315 pt, t=2.57, n=216, p(null>=real)=0.065.

⚠ It was FOUND by that search, on the same tape it is scored on. Everything below is the attempt to
kill it: cost it, split it, hold out days, strip its best trades, sweep its parameters, and check it
does not simply live off the trend days it was never meant to trade.

⚠ FEE $1.50/round trip, MNQ $2.00/pt. Cost model imported.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, SLIP_STOP_PT, load_events
from cs2_sweep import sequential
from cs3_race import sequential_live

OUT3 = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs3"
ORIG = ["2026-07-31"] + [f"2026-08-{x:02d}" for x in (3,4,5,6,7,10,11,12,13,14,17,18,19,20,21,24)]
NEW  = ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
THR = float(d.f_mv60[CHOP].quantile(0.95))
print(f"[CT20] f_mv60 q95 on chop tape = {THR:.3f} pt")
BASE = CHOP & (d.f_mv60 >= THR)
print(f"[CT20] {int(BASE.sum())} events over {d[BASE].date.nunique()} days")

def ev(mask, tp, sp, days=None):
    sub = d[mask & d.date.isin(days)] if days is not None else d[mask]
    if not len(sub):
        return None
    o = pd.concat([sequential_live(g, tp, sp) for _, g in sub.groupby("date")],
                  ignore_index=True)
    return o if len(o) else None

def S(o):
    if o is None or len(o) == 0:
        return dict(n=0, net=0.0, ptr=float("nan"), win=float("nan"), days=0, open=0)
    return dict(n=len(o), net=round(float(o.usd.sum()), 2), ptr=round(float(o.usd.mean()), 3),
                win=round(float((o.usd > 0).mean()), 3), days=int(o.date.nunique()),
                open=int((o.kind == "OPEN").sum()))

res = {"threshold_q95_pt": round(THR, 3), "events": int(BASE.sum())}
GRID = [(t, s) for t in (1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0) for s in (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)]

# ---- 1. COST IT. The whole grid, not the best cell. ---------------------------------
print("\n=== 1. COSTED — the full target/stop grid (the drift is 1.31pt; friction is 1.00-1.25pt) ===")
rows = []
for tp, sp in GRID:
    o = ev(BASE, tp, sp)
    if o is None or len(o) < 20:
        continue
    s = S(o); s.update(tp=tp, sp=sp)
    rows.append(s)
P = pd.DataFrame(rows)
P.to_csv(f"{OUT3}/ct20_grid.csv", index=False)
print(f"cells={len(P)}  positive={int((P.ptr>0).sum())} ({(P.ptr>0).mean():.0%})  "
      f"median $/tr={P.ptr.median():.3f}  best={P.ptr.max():.3f}")
print(P.sort_values("ptr", ascending=False).head(8).to_string(index=False))
res["grid"] = dict(cells=len(P), pos=int((P.ptr > 0).sum()), med_ptr=round(float(P.ptr.median()), 3),
                   best_ptr=round(float(P.ptr.max()), 3))

if (P.ptr > 0).sum() == 0:
    print("\n★ EVERY costed cell is negative. The 1.31pt frictionless drift does not survive "
          "the 1.00-1.25pt round trip. CT20 dies here.")
    res["verdict"] = "DEAD: no positive costed cell"
else:
    b = P.sort_values("ptr", ascending=False).iloc[0]
    TP, SP = float(b.tp), float(b.sp)
    print(f"\n[best cell] tp={TP} sp={SP}  n={int(b.n)}  ${b.net}  ${b.ptr}/tr  win={b.win:.0%}")
    res["best_cell"] = dict(tp=TP, sp=SP, **S(ev(BASE, TP, SP)))

    # ---- 2. IS / OOS on the frozen threshold --------------------------------------
    print("\n=== 2. ORIG (17d, searched) vs NEW (4d, unseen when the feature set was built) ===")
    for tag, days in (("ORIG", ORIG), ("NEW", NEW)):
        s = S(ev(BASE, TP, SP, days)); res[f"split_{tag}"] = s
        print(f"  {tag:5s} n={s['n']:4d} net=${s['net']:>9.2f} ${s['ptr']:>7.3f}/tr "
              f"win={s['win']:.0%} days={s['days']}")

    # ---- 3. leave-one-day-out ------------------------------------------------------
    o = ev(BASE, TP, SP)
    print("\n=== 3. LEAVE-ONE-DAY-OUT (21 folds) ===")
    folds = []
    for day in sorted(o.date.unique()):
        s = o[o.date != day]
        folds.append((day, len(s), round(float(s.usd.mean()), 3)))
    F = pd.DataFrame(folds, columns=["dropped", "n", "ptr"])
    print(f"  folds={len(F)}  positive={int((F.ptr>0).sum())}/{len(F)}  "
          f"min={F.ptr.min():.3f} median={F.ptr.median():.3f} max={F.ptr.max():.3f}")
    res["lodo"] = dict(folds=len(F), pos=int((F.ptr > 0).sum()), min=round(float(F.ptr.min()), 3),
                       med=round(float(F.ptr.median()), 3))
    dayn = o.groupby("date").usd.agg(["size", "sum"]).sort_values("sum", ascending=False)
    print("  per-day net (top/bottom 4):")
    print("   " + dayn.head(4).round(2).to_string().replace("\n", "\n   "))
    print("   " + dayn.tail(4).round(2).to_string().replace("\n", "\n   "))
    res["per_day"] = {k: [int(v["size"]), round(float(v["sum"]), 2)] for k, v in dayn.iterrows()}
    # leave-K-out: the LODO-cannot-fail memory
    top2 = list(dayn.head(2).index)
    s2 = o[~o.date.isin(top2)]
    print(f"  leave-2-out (drop the 2 best DAYS {top2}): n={len(s2)} ${s2.usd.sum():.2f} "
          f"${s2.usd.mean():.3f}/tr")
    res["leave2out"] = dict(dropped=top2, n=len(s2), net=round(float(s2.usd.sum()), 2),
                            ptr=round(float(s2.usd.mean()), 3))

    # ---- 4. strip-the-best ---------------------------------------------------------
    print("\n=== 4. STRIP-THE-BEST TRADES ===")
    srt = o.sort_values("usd", ascending=False)
    for k in (1, 3, 5, 10):
        s = srt.iloc[k:]
        print(f"  strip {k:2d}: n={len(s):4d} ${s.usd.sum():>9.2f} ${s.usd.mean():>7.3f}/tr")
        res[f"strip{k}"] = dict(n=len(s), net=round(float(s.usd.sum()), 2),
                                ptr=round(float(s.usd.mean()), 3))

    # ---- 5. does it bleed the TREND days it was never meant to trade? ---------------
    print("\n=== 5. OFF-HOME REGIME — the same rule on non-chop tape ===")
    days_meta = pd.read_csv(f"{OUT}/regime_days.csv")
    chop_days = set(days_meta[days_meta.daytype == "CHOP"].date) & set(d.date)
    trend_days = set(days_meta[days_meta.daytype == "TREND"].date) & set(d.date)
    OFF = (~CHOP) & (d.f_mv60 >= THR)
    so = S(ev(OFF, TP, SP))
    print(f"  non-chop regime blocks: n={so['n']} ${so['net']} ${so['ptr']}/tr win={so['win']:.0%}")
    res["off_regime"] = so
    print(f"\n=== 6. PER CHOP DAY (must hold on ALL of them) — {sorted(chop_days)} ===")
    cd = o[o.date.isin(chop_days)]
    per = cd.groupby("date").usd.agg(["size", "sum"])
    print("   " + per.round(2).to_string().replace("\n", "\n   ") if len(per) else "   (none)")
    print(f"  chop-day total: n={len(cd)} ${cd.usd.sum():.2f}  "
          f"green on {int((per['sum']>0).sum())}/{len(chop_days)} chop days  "
          f"= ${cd.usd.sum()/max(len(chop_days),1):.2f} per chop day")
    res["chop_days"] = {"days": sorted(chop_days), "n": len(cd),
                        "net": round(float(cd.usd.sum()), 2),
                        "green": int((per["sum"] > 0).sum()) if len(per) else 0,
                        "per_day": {k: [int(v["size"]), round(float(v["sum"]), 2)] for k, v in per.iterrows()}}

json.dump(res, open(f"{OUT3}/ct20.json", "w"), indent=1)
print(f"\n[wrote] {OUT3}/ct20.json")
