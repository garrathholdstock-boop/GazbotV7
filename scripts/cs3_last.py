"""CHOP-SCALP 2026-08-29 — the last cell standing.

Across the whole study exactly ONE costed cell in the R sweep is positive: CT13 at target 6pt /
stop 8pt (R=0.75), +$0.311/trade. This is its full battery. It is scored knowing it is a
1-of-54 survivor, so the bar it has to clear is high, not low.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, load_events
from cs3_race import sequential_live

OUT3 = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs3"
ORIG = ["2026-07-31"] + [f"2026-08-{x:02d}" for x in (3,4,5,6,7,10,11,12,13,14,17,18,19,20,21,24)]
NEW  = ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]
TP, SP = 6.0, 8.0

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
days_meta = pd.read_csv(f"{OUT}/regime_days.csv")
CHOP_DAYS = sorted(set(days_meta[days_meta.daytype == "CHOP"].date) & set(d.date))
TREND_DAYS = sorted(set(days_meta[days_meta.daytype == "TREND"].date) & set(d.date))
BASE = CHOP & (d.f_extC30 > 0) & (d.f_mv20 >= 4.0)

def run(mask, tp=TP, sp=SP, days=None):
    sub = d[mask & d.date.isin(days)] if days is not None else d[mask]
    if not len(sub): return None
    o = pd.concat([sequential_live(g, tp, sp) for _, g in sub.groupby("date")], ignore_index=True)
    return o if len(o) else None

def S(o):
    if o is None or not len(o): return dict(n=0, net=0.0, ptr=float("nan"), win=float("nan"), days=0)
    return dict(n=len(o), net=round(float(o.usd.sum()), 2), ptr=round(float(o.usd.mean()), 3),
                win=round(float((o.usd > 0).mean()), 3), days=int(o.date.nunique()),
                open=int((o.kind == "OPEN").sum()))

o = run(BASE)
res = {"cell": [TP, SP], "full": S(o)}
print(f"=== CT13 @ tp{TP}/sp{SP} (R=0.75) — full 21-day window ===")
print(f"  {S(o)}")

print("\n=== A. ORIG (searched) vs NEW (4 unseen days) ===")
for tag, days in (("ORIG", ORIG), ("NEW", NEW)):
    s = S(run(BASE, days=days)); res[f"split_{tag}"] = s
    print(f"  {tag:5s} n={s['n']:4d} net=${s['net']:>8.2f} ${s['ptr']:>7.3f}/tr win={s['win']:.0%} days={s['days']}")

print("\n=== B. LEAVE-ONE-DAY-OUT / LEAVE-K-OUT ===")
folds = [(day, len(o[o.date != day]), round(float(o[o.date != day].usd.mean()), 3))
         for day in sorted(o.date.unique())]
F = pd.DataFrame(folds, columns=["dropped", "n", "ptr"])
print(f"  LODO folds={len(F)} positive={int((F.ptr>0).sum())}/{len(F)} "
      f"min={F.ptr.min():.3f} med={F.ptr.median():.3f} max={F.ptr.max():.3f}")
dayn = o.groupby("date").usd.agg(["size", "sum"]).sort_values("sum", ascending=False)
print(f"  profitable days: {int((dayn['sum']>0).sum())}/{len(dayn)}")
print("  top 3 days: " + ", ".join(f"{k} {v['sum']:+.2f}" for k, v in dayn.head(3).iterrows()))
res["lodo"] = dict(folds=len(F), pos=int((F.ptr > 0).sum()), min=round(float(F.ptr.min()), 3),
                   med=round(float(F.ptr.median()), 3))
res["profitable_days"] = [int((dayn["sum"] > 0).sum()), len(dayn)]
for k in (1, 2, 3):
    drop = list(dayn.head(k).index)
    s = o[~o.date.isin(drop)]
    print(f"  leave-{k}-out (drop {k} best DAY{'S' if k>1 else ''}): n={len(s)} ${s.usd.sum():>8.2f} "
          f"${s.usd.mean():>7.3f}/tr")
    res[f"leave{k}out"] = dict(n=len(s), net=round(float(s.usd.sum()), 2), ptr=round(float(s.usd.mean()), 3))

print("\n=== C. STRIP-THE-BEST TRADES ===")
srt = o.sort_values("usd", ascending=False)
for k in (1, 2, 3, 5):
    s = srt.iloc[k:]
    print(f"  strip {k}: n={len(s):3d} ${s.usd.sum():>8.2f} ${s.usd.mean():>7.3f}/tr")
    res[f"strip{k}"] = dict(n=len(s), net=round(float(s.usd.sum()), 2), ptr=round(float(s.usd.mean()), 3))

print("\n=== D. WITHIN-DAY SHUFFLE PLACEBO on this single pre-specified cell ===")
rng = np.random.default_rng(20260829)
real = float(o.usd.mean())
draws = []
for _ in range(2000):
    s = d.copy()
    for f in ("f_extC30", "f_mv20"):
        s[f] = s.groupby("date")[f].transform(lambda v: rng.permutation(v.values))
    m = CHOP & (s.f_extC30 > 0) & (s.f_mv20 >= 4.0)
    sub = s[m]
    if not len(sub): continue
    oo = pd.concat([sequential_live(g, TP, SP) for _, g in sub.groupby("date")], ignore_index=True)
    if len(oo): draws.append(float(oo.usd.mean()))
    if len(draws) >= 300: break
draws = np.array(draws)
p = float((draws >= real).mean())
print(f"  real ${real:.3f}/tr   shuffle: mean=${draws.mean():.3f} p50=${np.median(draws):.3f} "
      f"p95=${np.quantile(draws,0.95):.3f}  (draws={len(draws)})")
print(f"  p(shuffle >= real) = {p:.3f}")
res["shuffle"] = dict(draws=len(draws), real=round(real, 3), mean=round(float(draws.mean()), 3),
                      p95=round(float(np.quantile(draws, 0.95)), 3), p=round(p, 4))

print("\n=== E. HOME vs OFF-HOME — does it bleed the trend days? ===")
for tag, days in (("CHOP days", CHOP_DAYS), ("TREND days", TREND_DAYS)):
    s = S(run(BASE, days=days)); res[f"on_{tag}"] = s
    print(f"  {tag:11s} n={s['n']:4d} net=${s['net']:>8.2f} ${s['ptr']:>7.3f}/tr days={s['days']}")
off = S(run((~CHOP) & (d.f_extC30 > 0) & (d.f_mv20 >= 4.0)))
res["off_regime"] = off
print(f"  same rule on NON-CHOP regime blocks: n={off['n']} ${off['net']} ${off['ptr']}/tr")
json.dump(res, open(f"{OUT3}/last_cell.json", "w"), indent=1)
print(f"\n[wrote] {OUT3}/last_cell.json")
