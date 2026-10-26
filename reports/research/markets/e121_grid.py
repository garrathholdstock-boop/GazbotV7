"""E121 - MGC target grid on the detector-only live-desk path (spec reports/recursive_loop/E121_change.txt). Read-only, zero Claude tokens.
    PYTHONPATH=src .venv/bin/python reports/research/markets/e121_grid.py
"""
import sys, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
src = open("/home/alphabot/gazbot7/reports/research/markets/phase4_year.py").read().split("\nstart = ")[0]
ns = {}; exec(compile(src, "p4", "exec"), ns)
DF = ns["DF"]
PARIS = ZoneInfo("Europe/Paris"); UTC = dt.timezone.utc
LOCK, CAP, LOTS = 1000.0, 2, 4
INST = {"MGC": {"pv": 10.0, "adv": 0.1, "thru": 0.1, "fee": 2.0, "targets": (3, 4, 5, 6, 7, 8, 10, 12)},
        "MNQ": {"pv": 2.0, "adv": 0.25, "thru": 0.25, "fee": 1.5, "targets": (37.5,)}}
QUARTERS = [("Q4-25", "2025-09-24", "2025-12-31"), ("Q1-26", "2026-01-01", "2026-03-31"), ("Q2-26", "2026-04-01", "2026-06-30"),
            ("Q3-26", "2026-07-01", "2026-09-30"), ("Oct-26", "2026-10-01", "2026-10-23")]


def candidates(sym):
    """every live-window slot with its side, MIL id and the outcome at every target"""
    cfg = INST[sym]
    d = ns["series"](sym, int(dt.datetime(2025, 9, 24, tzinfo=UTC).timestamp()))
    ts = d.ts.astype(int).to_numpy(); h = d.high.to_numpy(float); l = d.low.to_numpy(float); c = d.close.to_numpy(float)
    bars = list(zip(ts.tolist(), h.tolist(), l.tolist(), c.tolist()))
    piv = DF.zigzag(bars, DF.atr14(bars), lambda leg, a: 11 * a)
    cts = np.array([p[3] for p in piv]); pts = np.array([p[0] for p in piv]); nd = np.array([p[2] for p in piv])
    sess = (ts + 7200) // 86400
    rows = []
    for s_ in np.unique(sess):
        day = dt.date(1970, 1, 1) + dt.timedelta(days=int(s_)); d0 = int(dt.datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
        veto = int(dt.datetime(day.year, day.month, day.day, 5, tzinfo=PARIS).timestamp())
        flat = d0 + 20 * 3600 + 40 * 60
        e = int(np.searchsorted(ts, flat)) - 1
        if e < 0 or sess[e] != s_ or (sess == s_).sum() < 600:
            continue
        for slot in range(max(d0 + 2 * 3600, veto), d0 + 13 * 3600 + 1800, 300):
            j = int(np.searchsorted(ts, slot - 60, "right")) - 1
            if j < 0 or sess[j] != s_ or j + 1 > e:
                continue
            k = int(np.searchsorted(cts + 60, slot - 60, "right")) - 1
            if k < 0:
                continue
            dirn = int(nd[k]); fill = c[j] + dirn * cfg["adv"]
            ph, pl = h[j + 1:e + 1], l[j + 1:e + 1]
            fav = np.maximum.accumulate((ph - fill) if dirn > 0 else (fill - pl))
            final = dirn * (c[e] - fill)
            out = {}
            for T in cfg["targets"]:
                i = int(np.searchsorted(fav, T + cfg["thru"]))
                out[T] = (ts[j + 1 + i] + 60, LOTS * cfg["pv"] * T - LOTS * cfg["fee"]) if i < len(fav) else (None, LOTS * cfg["pv"] * final - LOTS * cfg["fee"])
            rows.append((int(s_), slot, int(pts[k]), out))
    return rows


def desk(rows, T):
    """flat-only path, re-entry after a hit, +$1,000 lock, MIL cap 2. -> {session: (day $, [entry $])}"""
    by = {}
    for r in rows:
        by.setdefault(r[0], []).append(r)
    res = {}
    for s_, rs in by.items():
        free, real, claims, ents = -1, 0.0, {}, []
        for _, slot, mil, out in rs:
            if slot < free or real >= LOCK or claims.get(mil, 0) >= CAP:
                continue
            ex, pnl = out[T]; real += pnl; ents.append(pnl)
            if ex is None:
                break
            free = ex; claims[mil] = claims.get(mil, 0) + 1
        res[s_] = (real, ents)
    return res


def summarise(res, lo=None, hi=None):
    k = [s for s in res if (lo is None or s >= lo) and (hi is None or s <= hi)]
    day = np.array([res[s][0] for s in k]); ents = np.array([e for s in k for e in res[s][1]]); traded = sum(1 for s in k if res[s][1])
    mean, sd = day.mean(), day.std()
    return {"sessions": len(k), "entries/day": round(len(ents) / max(len(k), 1), 2), "hit rate": f"{(ents > 0).mean():.0%}" if len(ents) else "-",
            "entries<=-1k": int((ents <= -1000).sum()), "days<=-2k": int((day <= -2000).sum()), "worst day": round(day.min()),
            "days+ (traded)": f"{(day > 0).sum() / max(traded, 1):.0%}", "$/day": round(mean), "CV": round(sd / mean, 1) if mean > 0 else "inf"}


def skey(d):
    return (int(dt.datetime.fromisoformat(d + "T00:00:00+00:00").timestamp()) + 7200) // 86400


out = []
for sym in ("MGC", "MNQ"):
    rows = candidates(sym)
    for T in INST[sym]["targets"]:
        res = desk(rows, T)
        out.append({"market": sym, "target pts": T, "target $ (4 lots)": round(LOTS * INST[sym]["pv"] * T), "period": "FULL YEAR", **summarise(res)})
        for q, a, b in QUARTERS:
            out.append({"market": sym, "target pts": T, "target $ (4 lots)": round(LOTS * INST[sym]["pv"] * T), "period": q, **summarise(res, skey(a), skey(b))})
t = pd.DataFrame(out); pd.set_option("display.width", 300); pd.set_option("display.max_rows", 200)
print(t[t.period == "FULL YEAR"].to_string(index=False))
print()
piv = t.pivot_table(index=["market", "target pts"], columns="period", values="days<=-2k", aggfunc="first")
print("days <= -$2k by quarter:\n", piv.to_string())
piv2 = t.pivot_table(index=["market", "target pts"], columns="period", values="$/day", aggfunc="first")
print("\n$/day by quarter:\n", piv2.to_string())
t.to_csv("/home/alphabot/gazbot7/reports/research/markets/e121_grid.csv", index=False)
