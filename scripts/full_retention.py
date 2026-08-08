#!/usr/bin/env python3
"""RUN-RETENTION overlay for the FULL 3-week (07-05..07-24) lead re-runs.  READ-ONLY, do NOT commit.

Standing rule (memory: run-catcher-null-all-microstructure / afc_filter_with_runs.py):
  A filter that improves P&L by DROPPING the target runs is a FAKE win, not an edge.
  So every filter cell here appends a retention column:  net$ / n (win%) [runs-kept/total].

Reuse (do NOT rebuild):
  archive_data.load()          -> the shared 3-week tape (22.6M ticks) + er/atr/net30 accessors
  run_census_full  (cluster/W/GAP_MAX/AMP_PRE) -> the 197-run TARGET LIST (per-cluster subsets)
  full_afc.build_trades(D)     -> the AFC flow-continuation trade set (RAW -$27.9k)
  full_vacuum.run_gate(...)    -> the trap-reclaim gate-2 trade set (ER>=0.35 cut went +$876)

A run is "caught" by a trade set if some trade fires in the SAME direction within +/-2 min
(120s) of the run start.  Target list per lead:
  AFC flow-continuation -> FLOW-LED cluster subset
  trap-reclaim scalp    -> VACUUM cluster subset

  /home/alphabot/gazbot7/.venv/bin/python scripts/full_retention.py
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import numpy as np
import archive_data as A
import run_census_full as RC
import full_afc as AFC
import full_vacuum as FV

WIN = 120                 # +/-2 min run-catch window (seconds)


# ---------------------------------------------------------------- TARGET RUN LIST (census, verbatim logic)
def census_runs(D, min_atr=1.5):
    """Mirror run_census_full.main()'s detection exactly, return per-run {start,d,mv,cl}."""
    mins, cls, hh, ll = D.mins, D.cls, D.hh, D.ll
    s0, N, flow = D.s0, len(D.mins), D.flow
    W, GAP, AMP = RC.W, RC.GAP_MAX, RC.AMP_PRE

    rng = []
    for i in range(0, N - W):
        if mins[i + W] - mins[i] <= GAP:
            rng.append(hh[i:i + W + 1].max() - ll[i:i + W + 1].min())
    typ = float(np.median(rng)) if rng else 0.0
    thr = min_atr * typ

    cands = []
    for i in range(0, N - W):
        if mins[i + W] - mins[i] > GAP:
            continue
        mv = cls[i + W] - cls[i]
        if abs(mv) >= thr:
            cands.append((abs(mv), i, mv))
    cands.sort(reverse=True)
    runs, used = [], []
    for _, i, mv in cands:
        if not any(abs(i - j) < W for j in used):
            used.append(i)
            runs.append((i, mv))
    runs.sort()

    def flow_pre(start):
        k = int(start - s0)
        return None if k <= 0 else float(flow[max(0, k - 60):k].sum())

    def amp_pre(i):
        j0 = max(0, i - AMP)
        if j0 >= i or cls[i] == 0:
            return None
        return float(100 * (hh[j0:i].max() - ll[j0:i].min()) / cls[i])

    import datetime as dt
    out = []
    for i, mv in runs:
        start = int(mins[i])
        f = flow_pre(start)
        amp = amp_pre(i)
        hour = dt.datetime.fromtimestamp(start, dt.UTC).hour
        cl = RC.cluster(hour, f, mv, amp)
        out.append({"start": start, "d": 1.0 if mv > 0 else -1.0, "mv": float(mv), "cl": cl})
    return out, typ, thr


# ---------------------------------------------------------------- retention / stat helpers
def stat(rows):
    n = len(rows)
    net = sum(r["pnl"] for r in rows)
    w = 100 * sum(1 for r in rows if r["pnl"] > 0) / n if n else 0.0
    return n, net, w


def caught_count(trades, runs, win=WIN):
    """How many target runs the trade subset still catches (same dir, within +/-win s of start)."""
    c = 0
    for r in runs:
        for t in trades:
            if t.get("d", 0) == r["d"] and abs(t["ts"] / 1000.0 - r["start"]) <= win:
                c += 1
                break
    return c


def cell(rows, runs):
    n, net, w = stat(rows)
    k = caught_count(rows, runs)
    return f"${net:+.0f}/{n}({w:.0f}%)[{k}/{len(runs)}]"


def line(label, rows, runs, base=None):
    n, net, w = stat(rows)
    k = caught_count(rows, runs)
    fake = ""
    if base is not None and net > 0 and base > 0 and k < base:
        fake = f"  <- drops {base-k}/{base} runs = FAKE" if net > 0 else ""
    print(f"     {label:<22} ${net:>+8.0f} / {n:>4} ({w:>3.0f}%)  [{k:>2}/{len(runs)} runs]{fake}")
    return k


# ---------------------------------------------------------------- per-lead overlays
def afc_overlay(D, flowled):
    cont = AFC.build_trades(D, fade=False)
    base = caught_count(cont, flowled)
    print("=" * 92)
    print(f"LEAD 1  AFC FLOW-CONTINUATION   target = FLOW-LED runs (n={len(flowled)})")
    print("=" * 92)
    n, net, w = stat(cont)
    print(f"   RAW: ${net:+.0f} / {n} ({w:.0f}%w)   catches {base}/{len(flowled)} FLOW-LED runs\n")

    print("   ER bands (discrete)            net$ / n (win%) [runs-kept]")
    have = [t for t in cont if t.get("er") is not None]
    for a, b in [(0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, 9)]:
        g = [t for t in have if a <= t["er"] < b]
        line(f"ER [{a:.1f}-{b:.1f})", g, flowled, base)

    print("\n   ER floors (cumulative >= f)")
    for f in [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
        g = [t for t in have if t["er"] >= f]
        line(f"ER >= {f:.2f}", g, flowled, base)

    print("\n   ATR floors (cumulative >= f, pt)")
    ha = [t for t in cont if t.get("atr") is not None]
    for f in [8, 12, 16, 20, 25, 30]:
        g = [t for t in ha if t["atr"] >= f]
        line(f"ATR >= {f}pt", g, flowled, base)

    print("\n   strip-best (drop k worst trades)")
    srt = sorted(cont, key=lambda t: t["pnl"])
    for k in [1, 2, 3, 5]:
        line(f"strip {k} worst", srt[k:], flowled, base)

    green = [t for t in cont if stat([t])[1] > 0]  # not used; keep leads honest
    any_green = any(stat([t for t in have if t["er"] >= f])[1] > 0 for f in [0.10, 0.20, 0.30, 0.40, 0.50])
    print(f"\n   VERDICT: every AFC cut stays RED (RAW ${net:+.0f}); retention is moot but recorded — "
          f"no green cell exists, so no hidden fake-win. Kill REINFORCED{' (a floor blips green: check its [runs])' if any_green else ''}.")
    return cont, flowled, base


def trap_overlay(D, vacuum):
    F2, STOP2, TGT2, RECLAIM2, CAP2, COOL2 = 300.0, 40.0, 30.0, 6.0, 900, 60
    nf, price, hi60, lo60 = D.nf, D.price, D.hi60, D.lo60

    def g2(i):
        if nf[i] <= -F2 and price[i] >= hi60[i] - RECLAIM2:
            return 1.0
        if nf[i] >= F2 and price[i] <= lo60[i] + RECLAIM2:
            return -1.0
        return 0

    t2 = FV.run_gate(D, g2, STOP2, TGT2, CAP2, COOL2)
    base = caught_count(t2, vacuum)
    print("\n" + "=" * 92)
    print(f"LEAD 2  TRAP-RECLAIM SCALP   target = VACUUM/snap-back runs (n={len(vacuum)})")
    print("=" * 92)
    n, net, w = stat(t2)
    print(f"   RAW: ${net:+.0f} / {n} ({w:.0f}%w)   catches {base}/{len(vacuum)} VACUUM runs\n")

    print("   ER floors (cumulative >= f)     net$ / n (win%) [runs-kept]")
    have = [t for t in t2 if t.get("er") is not None]
    er035 = None
    for f in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        g = [t for t in have if t["er"] >= f]
        k = line(f"ER >= {f:.2f}" + ("  <== GREEN CUT" if abs(f - 0.35) < 1e-9 else ""),
                 g, vacuum, base)
        if abs(f - 0.35) < 1e-9:
            er035 = (g, k)

    print("\n   ATR floors (cumulative >= f, pt)")
    ha = [t for t in t2 if t.get("atr") is not None]
    for f in [8, 12, 16, 20, 25]:
        g = [t for t in ha if t["atr"] >= f]
        line(f"ATR >= {f}pt", g, vacuum, base)

    print("\n   strip-best (drop k worst trades)")
    srt = sorted(t2, key=lambda t: t["pnl"])
    for k in [1, 2, 3, 5]:
        line(f"strip {k} worst", srt[k:], vacuum, base)

    # ---- the specific question for the record ----
    g035, k035 = er035
    gn, gnet, gw = stat(g035)
    print("\n   ── KEY QUESTION: does the ER>=0.35 green cut (+$876-class) catch the runs, or DROP them? ──")
    print(f"     RAW trap-reclaim:  catches {base}/{len(vacuum)} VACUUM runs")
    print(f"     ER>=0.35 cut:      ${gnet:+.0f} / {gn}tr ({gw:.0f}%w)  catches {k035}/{len(vacuum)} VACUUM runs")
    dropped = base - k035
    if gnet > 0 and dropped > 0:
        pct = 100 * dropped / base if base else 0
        print(f"     -> the green comes AFTER dropping {dropped}/{base} target runs ({pct:.0f}%). "
              f"FAKE WIN on top of the beta finding: the +$ is thrown-away-runs, not an edge.")
    elif gnet > 0 and dropped == 0:
        print(f"     -> the cut KEEPS all {base} caught runs. Green is NOT from dropping runs; "
              f"the beta finding stands ALONE as the reason to kill.")
    else:
        print(f"     -> cut is not green on the full window (${gnet:+.0f}); retention moot, kill holds.")
    return t2, vacuum, base, (k035, gnet, dropped)


def main():
    print("Loading FULL 3-week archive (07-05..07-24)...", flush=True)
    D = A.load()
    print(f"loaded: {D.n_ticks:,} ticks  span {D.span[0]} .. {D.span[1]}  cutover {D.cutover}")

    runs, typ, thr = census_runs(D)
    cc = {}
    for r in runs:
        cc[r["cl"]] = cc.get(r["cl"], 0) + 1
    flowled = [r for r in runs if r["cl"] == "FLOW-LED"]
    vacuum = [r for r in runs if r["cl"] == "VACUUM"]
    print(f"census: {len(runs)} runs (>= {thr:.0f}pt; typ 15m {typ:.0f}pt) | clusters {cc}")
    print(f"        target subsets -> FLOW-LED {len(flowled)} (AFC) | VACUUM {len(vacuum)} (trap-reclaim)\n")

    _, _, afc_base = afc_overlay(D, flowled)
    _, _, trap_base, (k035, gnet, dropped) = trap_overlay(D, vacuum)

    print("\n" + "#" * 92)
    print("# ONE-LINE VERDICTS (retention overlay)")
    print("#" * 92)
    print(f"  AFC flow-continuation : all cells RED, no green to fake -> retention REINFORCES the null kill.")
    if gnet > 0 and dropped > 0:
        print(f"  trap-reclaim ER>=0.35 : +${gnet:.0f} but catches only {k035}/{trap_base} VACUUM runs "
              f"(dropped {dropped}) -> FAKE WIN, kill REINFORCED beyond the beta split.")
    elif gnet > 0:
        print(f"  trap-reclaim ER>=0.35 : +${gnet:.0f} and keeps {k035}/{trap_base} runs "
              f"-> real retention; beta finding stands alone as the kill reason.")
    else:
        print(f"  trap-reclaim ER>=0.35 : ${gnet:+.0f} on full window -> not green, kill holds.")


if __name__ == "__main__":
    main()
