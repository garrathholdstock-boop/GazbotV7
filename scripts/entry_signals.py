#!/usr/bin/env python3
"""ENTRY SIGNALS, COMPARED ON ONE TAPE WITH ONE VERDICT — the first real lab experiment.

★★★ Phase 0 / the Monday entry. docs/SCOPE_RECURSIVE_TRADING_LOOP.md.

OPERATOR, and he is describing something simpler than anything I had been testing:

    "dont just test cvd. the big legs should be easy to pjck. direction js net in one direction.
     and then for s period jt changes. its nkt didficult"

That is a different family from what `turn_measure.py` refuted. That harness tested RETRACE FROM AN
EXTREME — price gives back N x ATR from its high-water mark. He is describing **NET DIRECTION OVER A
PERIOD**: price is net one way for hours, then net the other way. A retrace rule asks "how far from
the peak"; a net-direction rule asks "which way has the last hour actually gone". They can disagree
completely — a leg that grinds up with deep pullbacks trips the retrace rule repeatedly while its
net direction never changes once.

So this compares ARMS on identical tape with an identical verdict, which is the only way to rank
them ([[agreement-is-not-independence]] — four agents once "replicated" an artefact):

  netdir_L        direction = sign(close - close[L min ago]). Turn = the sign flips.
  netdir_L_pP     the same, but the new sign must HOLD P minutes before entry.
                  ★ this is the "and then for a period it changes" half, which is what separates a
                    turn from a wobble and is the part a bare crossover leaves out.
  ema_F_S         fast EMA crosses slow EMA — the classical net-direction detector.
  retrace_M       M x ATR giveback from the extreme — THE INCUMBENT, already measured a coin.
  cvd_climax      CVD pinned >= HI then rolls below LO — the operator's own rule, the one piece of
                  entry evidence on this desk that was not a coin (31 fires, median 42.1pt).
  control         random minute, random side, matched for count per session.

⚠⚠ THE VERDICT IS A SYMMETRIC RACE and 50% IS ZERO. [[mfe-is-not-a-win-rate]]: "X% reach N points"
ignores whether the stop came first, and it inflated capitulation 29% -> 78% and shipped a losing
config. So: does +N arrive before -N, on bar HIGHS and LOWS, inside a 2h window.
⚠⚠⚠ EVERY ARM IS SCORED AGAINST THE CONTROL, not against zero. A rule that beats 50% but not a
random entry on the same tape has found the tape's drift, not an edge.
⚠ THE SEARCH IS CHARGED: the cell count is printed, because 5,026 specs once reproduced a published
t=5.83 from pure noise 13% of the time. Treat a lone standout cell as noise unless its neighbours
agree.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
_S = importlib.util.spec_from_file_location(
    "ecc", "/home/alphabot/gazbot7/scripts/entry_cvd_climax.py")
ECC = importlib.util.module_from_spec(_S)
_S.loader.exec_module(ECC)          # reuse the loader, the gauge and the race — one definition

RACE_MIN = ECC.RACE_MIN


def _atr(series, i, n=14):
    if i < n + 1:
        return 0.0
    trs = []
    for j in range(i - n + 1, i + 1):
        h, l, pc = series[j][2], series[j][3], series[j - 1][1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc), 0.25))
    return sum(trs) / n


def sig_netdir(series, look: int, persist: int = 0):
    """Turn = sign(close - close[look ago]) flips, optionally holding `persist` minutes."""
    out, prev, pending, held = [], 0, 0, 0
    for i in range(look, len(series)):
        d = series[i][1] - series[i - look][1]
        s = 1 if d > 0 else (-1 if d < 0 else 0)
        if s == 0:
            continue
        if prev == 0:
            prev = s
            continue
        if s != prev:
            if persist == 0:
                out.append((i, s)); prev = s; pending = 0
            elif pending == s:
                held += 1
                if held >= persist:
                    out.append((i, s)); prev = s; pending = 0; held = 0
            else:
                pending, held = s, 1
        else:
            pending, held = 0, 0
    return out


def sig_ema(series, fast: int, slow: int):
    kf, ks = 2 / (fast + 1), 2 / (slow + 1)
    ef = es = series[0][1]
    out, prev = [], 0
    for i in range(1, len(series)):
        c = series[i][1]
        ef += kf * (c - ef)
        es += ks * (c - es)
        s = 1 if ef > es else -1
        if prev and s != prev and i > slow:
            out.append((i, s))
        prev = s
    return out


def sig_retrace(series, mult: float):
    out = []
    if len(series) < 30:
        return out
    dirn = 1 if series[10][1] > series[0][1] else -1
    ext = series[10][1]
    for i in range(11, len(series)):
        atr = _atr(series, i)
        if atr <= 0:
            continue
        c = series[i][1]
        if dirn * (c - ext) > 0:
            ext = c
        elif dirn * (ext - c) >= mult * atr:
            dirn = -dirn
            ext = c
            out.append((i, dirn))
    return out


def sig_cvd(series, hi: float, lo: float):
    return ECC.triggers(series, ECC.gauge(series), hi, lo)


ARMS = [
    ("netdir_30",        lambda s: sig_netdir(s, 30)),
    ("netdir_60",        lambda s: sig_netdir(s, 60)),
    ("netdir_120",       lambda s: sig_netdir(s, 120)),
    ("netdir_60_p15",    lambda s: sig_netdir(s, 60, 15)),
    ("netdir_120_p30",   lambda s: sig_netdir(s, 120, 30)),
    ("ema_20_60",        lambda s: sig_ema(s, 20, 60)),
    ("ema_60_180",       lambda s: sig_ema(s, 60, 180)),
    ("retrace_15x",      lambda s: sig_retrace(s, 15.0)),
    ("cvd_climax_95_90", lambda s: sig_cvd(s, 95.0, 90.0)),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=74)
    ap.add_argument("--targets", default="50,100")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    sess = ECC.load(a.sessions)
    targets = [float(x) for x in a.targets.split(",")]
    print(f"sessions: {len(sess)}   race: +N before -N on highs/lows within {RACE_MIN}min")
    print("⚠ 50% IS ZERO. Every arm is scored against a matched RANDOM control on the same tape.\n")
    rng = random.Random(20261002)

    print(f"  {'arm':<18}{'fires/sess':>11}" + "".join(f"{('±%dpt' % t):>22}" for t in targets))
    results = {}
    for name, fn in ARMS:
        fires, ctrl = [], []
        for _s, series in sess:
            t = fn(series)
            fires += [(series, i, d) for i, d in t]
            for _ in t:
                j = rng.randrange(200, len(series) - 1)
                ctrl.append((series, j, rng.choice((-1, 1))))
        cells = {}
        row = f"  {name:<18}{len(fires) / len(sess):>11.2f}"
        for npt in targets:
            w = [x for x in (ECC.race(s, i, d, npt) for s, i, d in fires) if x is not None]
            cw = [x for x in (ECC.race(s, i, d, npt) for s, i, d in ctrl) if x is not None]
            r = 100 * sum(w) / len(w) if w else None
            c = 100 * sum(cw) / len(cw) if cw else None
            cells[npt] = {"n": len(w), "rule": r and round(r, 1), "control": c and round(c, 1),
                          "edge_pp": (round(r - c, 1) if r is not None and c is not None else None)}
            row += (f"  {r:>5.1f}% vs {c:>5.1f}% ({r - c:>+5.1f}pp)" if r is not None and c is not None
                    else f"{'n/a':>22}")
        results[name] = {"fires_per_session": round(len(fires) / len(sess), 2), "cells": cells}
        print(row)

    cellcount = len(ARMS) * len(targets)
    print(f"\n  ⚠ {cellcount} cells searched. Charge the search: a single standout cell whose "
          f"neighbours disagree is noise.")
    print("  ⚠ 'fires/sess' must land near 3-6 to be tradeable at all — the legs run ~3.1/day.")
    if a.json:
        print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
