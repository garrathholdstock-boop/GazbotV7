#!/usr/bin/env python3
"""REV2 Q6 — price the exhaustion_short counter-trend bench with BOTH rulers.

The objection: SATURDAY #2 is quoted at n=26 / −$398.50, and Part 2.6 §3 proves the nightly's
scalp-2R ruler is $7.26 a trade more generous than the desk and +$25.02 a trade more generous in
TREND_UP — which is exactly the regime those 26 fires sit in. If the bench figure came off that
ruler, the report is using the ruler to refuse one number and to justify another.

So: take every exhaustion_short leg in the last 30 Paris days, label it with the router's OWN
regime at the moment of entry (gazbot7.direction_router.replay_marks, via the same fast replay
scripts/router_study.py validated against the shipped module), and print BOTH columns side by
side — what the desk actually booked, and what the nightly's scalp-2R / 1-ATR ruler would have
said about the same legs.

  PYTHONPATH=src:scripts ./.venv/bin/python scripts/rev2_counter_trend_bench.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import router_study as RS                                     # noqa: E402
from gazbot7 import direction_router as dr, pnl               # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_counter_trend_bench.json"
TAPE = "/home/alphabot/gazbot7/scratchpad/tape5s.npz"
VPP, FEE = 2.0, 1.50
DAYS = 30
GATE = "exhaustion_short"
SCALP_R, STOP_MULT, HOLD_S = 2.0, 1.0, 7200      # the nightly's ruler
CONTIG_S = 90

z = np.load(TAPE)
TS, H, L, C = z["ts"].astype(np.int64), z["h"], z["l"], z["c"]
_m: dict[int, list[float]] = {}
for i in range(len(TS)):
    k = int(TS[i]) // 60 * 60
    r = _m.get(k)
    if r is None:
        _m[k] = [float(H[i]), float(L[i]), float(C[i])]
    else:
        r[0] = max(r[0], float(H[i])); r[1] = min(r[1], float(L[i])); r[2] = float(C[i])
MT = np.array(sorted(_m))
MH = np.array([_m[t][0] for t in MT]); ML = np.array([_m[t][1] for t in MT])
MC = np.array([_m[t][2] for t in MT])


def atr14(ts_s: int) -> float:
    j = int(np.searchsorted(MT, ts_s, side="right"))
    trs = []
    for i in range(max(1, j - 15), j):
        hl = MH[i] - ML[i]
        trs.append(max(hl, abs(MH[i] - MC[i - 1]), abs(ML[i] - MC[i - 1]))
                   if MT[i] - MT[i - 1] <= CONTIG_S else hl)
    return float(sum(trs[-14:]) / len(trs[-14:])) if trs else 0.0


def scalp2r(entry: float, t0: int, atr: float) -> float | None:
    """The nightly's ruler on a SHORT: stop 1.0xATR, target 2.0R, 2-hour cap, stop wins a tie."""
    if atr <= 0:
        return None
    stop, tgt = entry + STOP_MULT * atr, entry - SCALP_R * STOP_MULT * atr
    i0 = int(np.searchsorted(TS, t0))
    last = None
    for i in range(i0, len(TS)):
        t = int(TS[i])
        if t - t0 > HOLD_S:
            break
        last = float(C[i])
        if float(H[i]) >= stop:
            return (entry - stop) * VPP - FEE
        if float(L[i]) <= tgt:
            return (entry - tgt) * VPP - FEE
    return ((entry - last) * VPP - FEE) if last is not None else None


def main() -> None:
    t = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(t).timestamp() if isinstance(t, str) else t.timestamp()
    RS._register_bounds(today0, DAYS)
    con = duckdb.connect()
    con.execute(f"ATTACH '{dr.CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{RS.DB}' AS g (TYPE sqlite, READ_ONLY)")
    daydata = RS.load_days(con, today0, DAYS)
    detail = {}
    for k in range(DAYS - 1, -1, -1):
        t0, t1 = today0 - k * 86400, today0 - (k - 1) * 86400
        date = dt.datetime.fromtimestamp(t0 + 43200, dt.UTC).strftime("%m-%d")
        detail[date] = con.execute(f"""
            SELECT gate, pnl_usd, epoch(opened_at::TIMESTAMPTZ) te, entry_price, data_quality
            FROM g.trades WHERE symbol='MNQ' AND gate LIKE '{GATE}%'
              AND epoch(opened_at::TIMESTAMPTZ) >= {t0} AND epoch(opened_at::TIMESTAMPTZ) < {t1}
              AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY te""").fetchall()
    con.close()

    rows = []
    for date, mins, closes, _tr in daydata:
        marks = (RS.replay_fast(mins, closes, int(RS._t0(date, daydata)),
                                int(RS._t1(date, daydata)), **RS.SHIPPED) if mins else [])
        for gate, p, te, ep, dq in detail.get(date, []):
            if dq is not None:
                continue                       # quarantined rows never enter a verdict
            reg = RS.regime_at(marks, te) if marks else "CHOP"
            atr = atr14(int(te))
            rows.append({"day": date, "gate": gate, "regime": reg, "live": float(p),
                         "atr": round(atr, 2), "scalp2r": scalp2r(float(ep), int(te), atr)})

    print(f"{len(rows)} clean {GATE} legs over {DAYS} Paris days\n")
    print(f"{'regime':12s}{'legs':>5s}{'LIVE two-lot $':>16s}{'$/leg':>8s}"
          f"{'nightly scalp-2R $':>20s}{'$/leg':>8s}{'ruler gap/leg':>14s}")
    res = {"days": DAYS, "gate": GATE, "n": len(rows), "by_regime": {}}
    for reg in ("TREND_UP", "CHOP", "TREND_DOWN"):
        sub = [r for r in rows if r["regime"] == reg]
        if not sub:
            continue
        lv = sum(r["live"] for r in sub)
        sc = [r["scalp2r"] for r in sub if r["scalp2r"] is not None]
        sct = sum(sc)
        res["by_regime"][reg] = {
            "legs": len(sub), "live": round(lv, 2), "live_per_leg": round(lv / len(sub), 2),
            "scalp2r_legs": len(sc), "scalp2r": round(sct, 2),
            "scalp2r_per_leg": round(sct / len(sc), 2) if sc else None,
            "ruler_gap_per_leg": round(sct / len(sc) - lv / len(sub), 2) if sc else None}
        e = res["by_regime"][reg]
        print(f"{reg:12s}{len(sub):5d}{lv:16,.2f}{e['live_per_leg']:8.2f}"
              f"{sct:20,.2f}{e['scalp2r_per_leg']:8.2f}{e['ruler_gap_per_leg']:+14.2f}")

    ct = [r for r in rows if r["regime"] == "TREND_UP"]
    day = collections.defaultdict(float)
    for r in ct:
        day[r["day"]] += r["live"]
    tot = sum(day.values())
    worst = min(day.values())
    res["counter_trend"] = {
        "legs": len(ct), "live": round(tot, 2),
        "live_per_leg": round(tot / len(ct), 2) if ct else 0,
        "days": len(day), "days_negative": sum(1 for v in day.values() if v < 0),
        "strip_worst_day": round(tot - worst, 2),
        "lodo_worst": round(min(tot - v for v in day.values()), 2),
        "per_day": {k: round(v, 2) for k, v in sorted(day.items())}}
    c = res["counter_trend"]
    print(f"\nTHE BENCH CASE, on the ruler the desk actually trades:")
    print(f"  {c['legs']} counter-trend legs, ${c['live']:,.2f}, ${c['live_per_leg']:.2f} a leg, "
          f"over {c['days']} days, negative on {c['days_negative']} of {c['days']}")
    print(f"  strip the worst day ${c['strip_worst_day']:,.2f}   "
          f"leave-one-day-out worst fold ${c['lodo_worst']:,.2f}")
    print("  per day: " + ", ".join(f"{k} {v:+.2f}" for k, v in c["per_day"].items()))

    json.dump({**res, "legs": rows}, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
