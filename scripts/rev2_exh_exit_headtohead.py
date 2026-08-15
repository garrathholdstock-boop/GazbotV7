#!/usr/bin/env python3
"""REV2 Q2 — the two exhaustion_short exits, graded against each other on ONE population.

Two studies in this report reached two different answers for the same gate and neither was ever
graded against the other:

  WIDE-STOP   (Part 1.5 §7, BUILD #1)  stop 1.5xATR, target 3.0xATR, 15-minute cap
  TIGHTCHANDx2(Part 2 §8d, written to data/exit_overrides_proposed.json)
                                       stop 1.0xATR, trail 1.5xATR off the running peak, both lots

They were measured on different populations with different engines, so "+$3,459.98" and
"+$22.8 a signal" were never comparable numbers. This runs BOTH on the SAME 87 tape-backed
exhaustion_short signals, on the SAME tick paths, under the SAME 15-minute cap, split by the
§8b rung (1-minute ER(30): BIG-TREND >=0.50, MED-TREND 0.30-0.50, else SCALP-CHOP; ATR>=22
inside chop is the STAY-OUT bucket the ladder measures but does not trade).

Then the same paired random-entry control is applied to BOTH — same day, same signal's own
geometry in ATR, random entry minute — so the question "does the policy work, or did the tape
just fall?" is answered for each of them on the same footing.

  PYTHONPATH=src ./.venv/bin/python scripts/rev2_exh_exit_headtohead.py
"""
from __future__ import annotations

import collections
import json
import random
import statistics

import numpy as np

SIGS = "/home/alphabot/gazbot7/reports/friday_v7/sections/exh_signals.json"
TAPE = "/home/alphabot/gazbot7/scratchpad/tape5s.npz"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_exh_headtohead.json"
VPP, FEE = 2.0, 1.50
CAP_MS = 900_000
DRAWS = 60
RNG = random.Random(20260815)

z = np.load(TAPE)
BTS, BH, BL, BC = z["ts"].astype(np.int64), z["h"], z["l"], z["c"]

# ---- 1-minute ER(30) for the rung, folded from the same 5s tape as §8b ----------------
_mk: dict[int, list[float]] = {}
for _i in range(len(BTS)):
    _m = int(BTS[_i]) // 60
    _r = _mk.get(_m)
    if _r is None:
        _mk[_m] = [BH[_i], BL[_i], BC[_i]]
    else:
        _r[0] = max(_r[0], BH[_i]); _r[1] = min(_r[1], BL[_i]); _r[2] = BC[_i]
_mins = sorted(_mk)
_C = np.array([_mk[m][2] for m in _mins])
ER: dict[int, float] = {}
for _i, _m in enumerate(_mins):
    if _i >= 30:
        seg = _C[_i - 30:_i + 1]
        path = float(np.abs(np.diff(seg)).sum()) or 1.0
        ER[_m] = abs(seg[-1] - seg[0]) / path


def rung(atr: float, ts_ms: int) -> str:
    er = ER.get(int(ts_ms // 1000) // 60, 0.0)
    if er >= 0.50:
        return "BIG-TREND"
    if er >= 0.30:
        return "MED-TREND"
    if atr >= 22:
        return "STAY-OUT"
    return "SCALP-CHOP"


# ---- the two exits, both on a SHORT, both fed the same (t_ms, price) path -------------
def wide_stop(path, entry, atr, cap=CAP_MS):
    """stop 1.5xATR / target 3.0xATR / 15-min cap. Stop wins a same-tick race."""
    stop, tgt = entry + 1.5 * atr, entry - 3.0 * atr
    last = None
    for t, px in path:
        if t < 0:
            continue
        last = px
        if px >= stop:
            return (entry - stop) * VPP - FEE, "STOP"
        if px <= tgt:
            return (entry - tgt) * VPP - FEE, "TARGET"
        if t >= cap:
            return (entry - px) * VPP - FEE, "TIME"
    return ((entry - last) * VPP - FEE, "TIME") if last is not None else None


def tight_chand(path, entry, atr, cap=CAP_MS):
    """stop 1.0xATR, trail 1.5xATR off the running favourable peak. 15-min cap."""
    stop = entry + 1.0 * atr
    peak = 0.0
    last = None
    for t, px in path:
        if t < 0:
            continue
        last = px
        if px >= stop:
            return (entry - stop) * VPP - FEE, "STOP"
        peak = max(peak, entry - px)
        trail = peak - 1.5 * atr
        if peak > 0 and trail > 0 and (entry - px) <= trail:
            return trail * VPP - FEE, "CHANDELIER"
        if t >= cap:
            return (entry - px) * VPP - FEE, "TIME"
    return ((entry - last) * VPP - FEE, "TIME") if last is not None else None


POLICIES = {"WIDE 1.5xATR stop / 3.0xATR target": wide_stop,
            "TIGHT CHANDELIER x2 (1.0xATR stop, 1.5xATR trail)": tight_chand}


def bar_path(ts_ms: int, cap_ms: int = CAP_MS) -> list[tuple[int, float]]:
    """A synthetic tick path from the 5s tape — used only for the random-entry control, where
    a stored tick path does not exist. High and low are emitted in the ORDER THAT HURTS: for a
    short, the bar's high (adverse) first, so a same-bar stop-vs-target race is lost, matching
    the conservative convention in both source studies."""
    i0 = int(np.searchsorted(BTS, ts_ms // 1000))
    if i0 >= len(BTS) or abs(int(BTS[min(i0, len(BTS) - 1)]) * 1000 - ts_ms) > 600_000:
        return []
    j1 = min(i0 + cap_ms // 5000, len(BTS))
    out = []
    for i in range(i0, j1):
        t = int(BTS[i]) * 1000 - ts_ms
        out += [(t, float(BH[i])), (t, float(BL[i])), (t, float(BC[i]))]
    return out


def main() -> None:
    S = [s for s in json.load(open(SIGS))["signals"] if s["path_n"] > 0 and s["atr"]]
    for s in S:
        s["rung"] = rung(s["atr"], s["ts_ms"])
    print(f"{len(S)} tape-backed exhaustion_short signals, live net "
          f"${sum(s['pnl'] for s in S):,.2f}")
    print("rungs: " + ", ".join(f"{k} {v}" for k, v in
                                collections.Counter(s["rung"] for s in S).most_common()))

    res = {"n": len(S), "live_net": round(sum(s["pnl"] for s in S), 2), "by_rung": {},
           "overall": {}, "control": {}}

    print(f"\n{'rung':12s}{'n':>4s}  " + "".join(f"{p[:28]:>30s}" for p in POLICIES))
    rows = collections.defaultdict(dict)
    for pname, fn in POLICIES.items():
        per_rung = collections.defaultdict(list)
        allv, days = [], collections.defaultdict(float)
        exits = collections.Counter()
        for s in S:
            r = fn(s["path"], s["entry"], s["atr"])
            if not r:
                continue
            v = r[0] * s["n_legs"]
            per_rung[s["rung"]].append(v)
            allv.append(v)
            days[s["date"]] += v
            exits[r[1]] += 1
        for rg, v in per_rung.items():
            rows[rg][pname] = (len(v), sum(v), sum(v) / len(v))
        best3 = sorted(allv, reverse=True)[:3]
        res["overall"][pname] = {
            "n": len(allv), "net": round(sum(allv), 2),
            "per_sig": round(sum(allv) / len(allv), 2),
            "win_pct": round(100.0 * sum(1 for v in allv if v > 0) / len(allv), 1),
            "strip3": round(sum(allv) - sum(best3), 2),
            "lodo_worst": round(min(sum(allv) - v for v in days.values()), 2),
            "days_green": sum(1 for v in days.values() if v > 0), "days": len(days),
            "exits": dict(exits)}
    for rg in ("BIG-TREND", "MED-TREND", "SCALP-CHOP", "STAY-OUT"):
        if rg not in rows:
            continue
        line = f"{rg:12s}"
        n = 0
        for pname in POLICIES:
            c = rows[rg].get(pname)
            n = c[0]
            line += f"{c[1]:>16,.2f} ({c[2]:+6.1f}/sig)"
        print(f"{rg:12s}{n:4d}  " + "".join(
            f"{rows[rg][p][1]:>18,.2f} ({rows[rg][p][2]:+7.1f})" for p in POLICIES))
        res["by_rung"][rg] = {p: {"n": rows[rg][p][0], "net": round(rows[rg][p][1], 2),
                                  "per_sig": round(rows[rg][p][2], 2)} for p in POLICIES}
    print()
    for p, o in res["overall"].items():
        print(f"{p:52s} n={o['n']:3d} net ${o['net']:9,.2f} ${o['per_sig']:+7.2f}/sig "
              f"win {o['win_pct']:4.1f}% strip3 ${o['strip3']:9,.2f} "
              f"LODOworst ${o['lodo_worst']:9,.2f} green {o['days_green']}/{o['days']} {o['exits']}")

    # ── the same paired random-entry control for BOTH policies ────────────────────────
    span = collections.defaultdict(lambda: [10 ** 15, 0])
    for s in S:
        d = span[s["date"]]
        d[0], d[1] = min(d[0], s["ts_ms"]), max(d[1], s["ts_ms"])
    print(f"\nrandom-entry control, {DRAWS} paired books (same signal geometry + day, random minute)")
    for pname, fn in POLICIES.items():
        real = 0.0
        for s in S:
            p = bar_path(s["ts_ms"])
            if p:
                r = fn(p, s["entry"], s["atr"])
                if r:
                    real += r[0] * s["n_legs"]
        draws = []
        for k in range(DRAWS):
            tot = 0.0
            for s in S:
                a, b = span[s["date"]]
                t0 = RNG.randint(a, max(b, a + 60_000))
                p = bar_path(t0)
                if not p:
                    continue
                e = p[2][1]                       # that bar's close = the entry we would have got
                r = fn(p, e, s["atr"])
                if r:
                    tot += r[0] * s["n_legs"]
            draws.append(tot)
        draws.sort()
        pct = 100.0 * sum(1 for v in draws if v < real) / len(draws)
        res["control"][pname] = {"real_on_bars": round(real, 2),
                                 "random_mean": round(statistics.mean(draws), 2),
                                 "random_p95": round(draws[int(0.95 * len(draws))], 2),
                                 "random_max": round(draws[-1], 2),
                                 "real_pctile": round(pct, 1),
                                 "entry_alpha": round(real - statistics.mean(draws), 2)}
        c = res["control"][pname]
        print(f"{pname:52s} REAL ${c['real_on_bars']:9,.2f} | random mean ${c['random_mean']:9,.2f} "
              f"p95 ${c['random_p95']:9,.2f} max ${c['random_max']:9,.2f} | pctile {c['real_pctile']:5.1f} "
              f"| alpha ${c['entry_alpha']:9,.2f}")

    # ── horizon sensitivity. The 15-minute cap is the WIDE policy's own spec but it is HARSH
    # on a chandelier, which is built to ride; §8b gave it 60 minutes. So both are re-run on the
    # 5s tape at 15 and at 60 minutes, to be sure the head-to-head is not an artefact of the cap.
    print("\nhorizon sensitivity (5s tape, both policies, same entries)")
    res["horizon"] = {}
    for cap_min in (15, 30, 60):
        cap = cap_min * 60_000
        line = f"  {cap_min:2d} min  "
        for pname, fn in POLICIES.items():
            tot, n = 0.0, 0
            for s in S:
                p = bar_path(s["ts_ms"], cap)
                if not p:
                    continue
                r = fn(p, s["entry"], s["atr"], cap)
                if r:
                    tot += r[0] * s["n_legs"]
                    n += 1
            res["horizon"].setdefault(pname, {})[f"{cap_min}min"] = {
                "n": n, "net": round(tot, 2), "per_sig": round(tot / n, 2) if n else 0}
            line += f"{pname[:5]:>6s} ${tot:9,.2f} (${tot/n:+6.2f}/sig)  "
        print(line)

    json.dump(res, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
