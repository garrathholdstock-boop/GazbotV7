#!/usr/bin/env python3
"""MOVEMENT 2 — analysis: scoreboards, regime splits, robustness. Prints; writes nothing."""
import json
from collections import defaultdict

LAB = "/home/alphabot/gazbot7/reports/friday_v7/sections/m2_lab.json"
SWP = "/home/alphabot/gazbot7/reports/friday_v7/sections/m2_sweep.json"


def regime(r):
    a, e = r["atr"], r["er"]
    if a >= 22 and e < 0.25:
        return "VIOLENT-WHIPSAW"
    if e >= 0.40:
        return "CLEAN-TREND"
    if e >= 0.25:
        return "BUILDING"
    if a < 12:
        return "DEAD-CHOP"
    return "NORMAL-CHOP"


def tod(h):
    return "ASIA 00-07" if h < 7 else "LONDON 07-13" if h < 13 else "US 13-21" if h < 21 else "POST 21-24"


def stat(ts):
    n = len(ts)
    net = sum(t["net"] for t in ts)
    w = sum(1 for t in ts if t["net"] > 0)
    return n, net, (100 * w / n if n else 0.0), (net / n if n else 0.0)


def line(label, ts, pad=34):
    n, net, wr, pt = stat(ts)
    return f"{label:<{pad}} n={n:4d}  net=${net:+9.2f}  win={wr:5.1f}%  $/lot={pt:+8.2f}"


def main():
    lab = json.load(open(LAB))
    runs = {r["tm"]: r for r in lab["runs"]}
    for r in runs.values():
        if "atr" in r:
            r["regime"] = regime(r)
            r["tod"] = tod(r["hour"])
    tr = lab["trades"]
    for t in tr:
        r = runs[t["run"]]
        t["regime"] = r.get("regime", "NO-TAPE")
        t["tod"] = r.get("tod", "?")
        t["day"] = t["run"][:5]
        t["ceil"] = r["ceil"]

    print("=" * 100)
    print("A. POPULATION")
    sat = [r for r in runs.values()]
    print(f"  sat-out runs {len(sat)} · ceiling ${sum(r['ceil'] for r in sat):,} · "
          f"decision-seconds {sum(r.get('n_snaps_mech',0) for r in sat):,}")
    for k in ("regime", "tod"):
        d = defaultdict(lambda: [0, 0])
        for r in sat:
            d[r.get(k, "NO-TAPE")][0] += 1
            d[r.get(k, "NO-TAPE")][1] += r["ceil"]
        print(f"  by {k}: " + " · ".join(f"{a} n={b[0]} ceil=${b[1]:,}" for a, b in sorted(d.items())))

    for lay in ("mech", "ungated"):
        T = [t for t in tr if t["layer"] == lay]
        print("\n" + "=" * 100)
        print(f"B. SCOREBOARD — layer {lay.upper()}")
        print("  " + line("ALL fires (both directions)", T))
        ind = [t for t in T if t["in_dir"]]
        print("  " + line("IN-DIRECTION only", ind))
        print()
        for g in sorted({t["gate"] for t in T}):
            v = [t for t in T if t["gate"] == g]
            f = len({(t["run"], t["entry_ms"]) for t in v})
            rr = len({t["run"] for t in v})
            vi = [t for t in v if t["in_dir"]]
            print(f"  {g:20s} fires={f:3d} runs={rr:3d} " + line("", v, 0) +
                  f"   || in-dir n={len(vi)} ${sum(x['net'] for x in vi):+8.2f}")
        for g in sorted({t["gate"] for t in T}):
            v = [t for t in T if t["gate"] == g]
            print(f"\n   {g} by regime:")
            for k in sorted({t["regime"] for t in v}):
                print("      " + line(k, [t for t in v if t["regime"] == k], 20))
            print(f"   {g} by session:")
            for k in sorted({t["tod"] for t in v}):
                print("      " + line(k, [t for t in v if t["tod"] == k], 20))

    # ── robustness on the ungated in-direction book ─────────────────────────────────────
    print("\n" + "=" * 100)
    print("C. ROBUSTNESS — ungated, in-direction")
    ind = [t for t in tr if t["layer"] == "ungated" and t["in_dir"]]
    n, net, wr, pl = stat(ind)
    print("  " + line("headline", ind))
    s = sorted(ind, key=lambda t: -t["net"])
    for k in (1, 2, 3):
        print("  " + line(f"strip best {k} lots", s[k:]))
    days = sorted({t["day"] for t in ind})
    print(f"  days with fires: {len(days)} of 5 — {days}")
    for d in days:
        print("      " + line(f"day {d}", [t for t in ind if t["day"] == d], 20))
    for d in days:
        print("      " + line(f"LODO drop {d}", [t for t in ind if t["day"] != d], 20))

    # ── the sweep ───────────────────────────────────────────────────────────────────────
    try:
        sw = json.load(open(SWP))
    except FileNotFoundError:
        return
    for t in sw:
        r = runs[t["run"]]
        t["regime"] = r.get("regime", "NO-TAPE")
        t["tod"] = r.get("tod", "?")
    print("\n" + "=" * 100)
    print("D. THRESHOLD SWEEP — each cell relaxes ONE binding constraint")
    for g in sorted({t["gate"] for t in sw}):
        print(f"\n  ── {g} ──")
        cells = []
        for c in sorted({t["cell"] for t in sw if t["gate"] == g}):
            v = [t for t in sw if t["gate"] == g and t["cell"] == c]
            vi = [t for t in v if t["in_dir"]]
            f = len({(t["run"], t["entry_ms"]) for t in v})
            rr = len({t["run"] for t in v})
            n, net, wrr, pl = stat(v)
            ni, neti, wri, pli = stat(vi)
            s = sorted(v, key=lambda t: -t["net"])
            _, net3, _, _ = stat(s[3:])
            cells.append((c, f, rr, n, net, wrr, pl, ni, neti, net3))
        print(f"    {'cell':<22}{'fires':>6}{'runs':>5}{'lots':>6}{'net$':>10}{'win%':>7}"
              f"{'$/lot':>8}{'inD n':>7}{'inD $':>9}{'strip3$':>10}")
        for c in cells:
            print(f"    {c[0]:<22}{c[1]:>6}{c[2]:>5}{c[3]:>6}{c[4]:>+10.2f}{c[5]:>7.1f}"
                  f"{c[6]:>+8.2f}{c[7]:>7}{c[8]:>+9.2f}{c[9]:>+10.2f}")
        # regime split for the best cell by in-dir $
        best = max(cells, key=lambda c: c[8])
        v = [t for t in sw if t["gate"] == g and t["cell"] == best[0]]
        if v:
            print(f"    best-by-in-dir cell '{best[0]}' by regime:")
            for k in sorted({t["regime"] for t in v}):
                print("        " + line(k, [t for t in v if t["regime"] == k], 20))


if __name__ == "__main__":
    main()
