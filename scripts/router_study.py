#!/usr/bin/env python3
"""ROUTER STUDY — the weekly Friday-night interrogation of the direction-router.

Pulls the router apart on EVERY knob and asks the two operator questions:
  1. Can we optimise it?  — sweep the THRESHOLD triggers (ER_TREND x NET_MIN) AND the
     TIMINGS (STEP poll / HOLD hysteresis / WINDOW lookback / fast_exit) for the config
     that blocks the most net counter-trend loss without gutting winners.
  2. Is it blocking ENOUGH? — leakage diagnostic: of the managed faders' LOSERS the router
     let through, how many were counter-trend NEAR-MISSES the threshold just failed to catch
     (=> lower the threshold) vs genuine CHOP losses (router can't help) vs trend-FOLLOWING
     losses (a gate/exit problem, not the router's).

READ-ONLY. Reuses the LIVE router's EXACT signal via a validated fast replay (asserted equal to
gazbot7.direction_router.replay_marks on the shipped config — no drift). Sweeps on realised
`trades` labelled by regime@entry; blocked P&L = the router's effect (negative blocked = removed
losers = it helped). ⚠ realised trades are thin + partly already hand/router-gated + ONE summer
RANGE regime => illustrative lower bound, not a clean A/B. A change is a SATURDAY/operator call.

  PYTHONPATH=src .venv/bin/python scripts/router_study.py [--days 40]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict

import duckdb
import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7 import pnl  # noqa: E402

DB = "/home/alphabot/gazbot7/data/gazbot7.db"

# fader gate -> the regime it should be BENCHED in (LONG faders fade a down-move; SHORT faders fade a rise)
DOWN_FADERS = {"capitulation_long", "rgv_long"}   # bench in TREND_DOWN
UP_FADERS = {"rgv_short", "exhaustion_short"}      # bench in TREND_UP
LIVE_DOWN = {"capitulation_long"}                  # currently router-managed (down)
LIVE_UP = {"rgv_short"}                            # currently router-managed (up)

# shipped config (the incumbent to beat)
SHIPPED = dict(er=dr.ER_TREND, net=dr.NET_MIN, step=dr.STEP, hold=dr.HOLD, window=dr.WINDOW, fast=False)


def replay_fast(mins, closes, t0, t1, *, er, net, window, step, hold, fast):
    """Efficient parametric mirror of dr.replay_marks (validated equal on the shipped config)."""
    mins_a = np.asarray(mins)
    closes_a = np.asarray(closes, float)
    marks = []
    state = "CHOP"
    recent: list[str] = []
    t = max(mins[0] - (mins[0] % (step * 60)) + step * 60, int(t0))
    step_s = step * 60
    while t <= t1:
        idx = int(np.searchsorted(mins_a, t, side="right"))
        c = closes_a[max(0, idx - window):idx]
        if len(c) < 6:
            e = n = 0.0
        else:
            path = float(np.abs(np.diff(c)).sum()) or 1.0
            e = abs(c[-1] - c[0]) / path
            n = float(c[-1] - c[0])
        raw = "TREND_UP" if (e >= er and n >= net) else "TREND_DOWN" if (e >= er and n <= -net) else "CHOP"
        recent.append(raw)
        if len(recent) > hold:
            recent.pop(0)
        if len(recent) == hold:
            uniform = recent[0] if len(set(recent)) == 1 else None
            if state == "CHOP" or not fast:
                if uniform is not None and uniform != state:
                    state = uniform
            elif all(r != state for r in recent):
                state = uniform if uniform in ("TREND_UP", "TREND_DOWN") else "CHOP"
        marks.append((t, state, e, n))
        t += step_s
    return marks


def regime_at(marks, te):
    st = "CHOP"
    for mt, s, _e, _n in marks:
        if mt <= te:
            st = s
        else:
            break
    return st


def load_days(con, today0, days):
    """Return [(date, mins, closes, [(gate,pnl,te)])] per Paris day, cached once."""
    out = []
    for k in range(days - 1, -1, -1):
        t0, t1 = today0 - k * 86400, today0 - (k - 1) * 86400
        bars = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c FROM c.bars
            WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= {t0 - 45*60} AND bar_ts < {t1}
            GROUP BY 1 ORDER BY 1""").fetchall()
        trades = con.execute(f"""SELECT gate, pnl_usd, epoch(opened_at::TIMESTAMPTZ) te FROM g.trades
            WHERE symbol='MNQ' AND epoch(opened_at::TIMESTAMPTZ) >= {t0} AND epoch(opened_at::TIMESTAMPTZ) < {t1}
              AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY te""").fetchall()
        date = dt.datetime.fromtimestamp(t0 + 43200, dt.UTC).strftime("%m-%d")
        out.append((date, [b[0] for b in bars], [b[1] for b in bars], trades))
    return out


def eval_config(daydata, down_off, up_off, cfg, per_day=False):
    """Router P&L on the managed universe for one config. Returns totals + optional per-day deltas."""
    base = blocked = blk_win = blk_los = 0.0
    n_blk = 0
    per = []
    universe = down_off | up_off
    for date, mins, closes, trades in daydata:
        uni_trades = [(gate, p, te) for gate, p, te in trades if gate in universe]
        if not uni_trades:
            continue
        marks = replay_fast(mins, closes, int(_t0(date, daydata)), int(_t1(date, daydata)), **cfg) if mins else []
        d_base = d_blk = 0.0
        for gate, p, te in uni_trades:
            d_base += p
            reg = regime_at(marks, te) if marks else "CHOP"
            off = down_off if reg == "TREND_DOWN" else up_off if reg == "TREND_UP" else set()
            if gate in off:
                d_blk += p
                n_blk += 1
                blk_los += p if p < 0 else 0.0
                blk_win += p if p > 0 else 0.0
        base += d_base
        blocked += d_blk
        if per_day:
            per.append((date, d_base, d_base - d_blk, -d_blk))
    return {"base": base, "router": base - blocked, "delta": -blocked, "n_blk": n_blk,
            "blk_win": blk_win, "blk_los": blk_los, "per": per}


# day-bounds helpers (daydata carries date only; recompute epochs from index)
_BOUNDS: dict = {}


def _register_bounds(today0, days):
    for k in range(days - 1, -1, -1):
        t0, t1 = today0 - k * 86400, today0 - (k - 1) * 86400
        date = dt.datetime.fromtimestamp(t0 + 43200, dt.UTC).strftime("%m-%d")
        _BOUNDS[date] = (t0, t1)


def _t0(date, _dd):
    return _BOUNDS[date][0]


def _t1(date, _dd):
    return _BOUNDS[date][1]


def leakage(daydata, down_off, up_off, cfg):
    """Is it blocking ENOUGH? Classify the managed faders' ALLOWED losers."""
    universe = down_off | up_off
    cats = defaultdict(lambda: [0, 0.0])   # cat -> [n, pnl]
    for date, mins, closes, trades in daydata:
        marks = replay_fast(mins, closes, int(_t0(date, daydata)), int(_t1(date, daydata)), **cfg) if mins else []
        for gate, p, te in trades:
            if gate not in universe:
                continue
            reg = regime_at(marks, te) if marks else "CHOP"
            off = down_off if reg == "TREND_DOWN" else up_off if reg == "TREND_UP" else set()
            if gate in off:
                cats["BLOCKED (router caught it)"][0] += 1
                cats["BLOCKED (router caught it)"][1] += p
                continue
            if p >= 0:
                cats["allowed winner (correct)"][0] += 1
                cats["allowed winner (correct)"][1] += p
                continue
            # an ALLOWED LOSER — why did the router let it through?
            want = "TREND_DOWN" if gate in down_off else "TREND_UP"
            e, n = _regime_metrics_at(marks, te)
            near = (e >= cfg["er"] - 0.10) and (
                (want == "TREND_DOWN" and n <= -(cfg["net"] - 20)) or
                (want == "TREND_UP" and n >= (cfg["net"] - 20)))
            if reg == want:
                cats["leak: off-regime but not held (hysteresis lag)"][0] += 1  # rare: shouldn't happen post-block
                cats["leak: off-regime but not held (hysteresis lag)"][1] += p
            elif near:
                cats["LEAK: counter-trend NEAR-MISS (lower threshold?)"][0] += 1
                cats["LEAK: counter-trend NEAR-MISS (lower threshold?)"][1] += p
            elif reg == "CHOP":
                cats["chop loss (router can't help)"][0] += 1
                cats["chop loss (router can't help)"][1] += p
            else:
                cats["trend-FOLLOWING loss (gate/exit problem)"][0] += 1
                cats["trend-FOLLOWING loss (gate/exit problem)"][1] += p
    return cats


def _regime_metrics_at(marks, te):
    e = n = 0.0
    for mt, _s, ee, nn in marks:
        if mt <= te:
            e, n = ee, nn
        else:
            break
    return e, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=40)
    days = ap.parse_args().days
    t = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(t).timestamp() if isinstance(t, str) else t.timestamp()
    _register_bounds(today0, days)
    con = duckdb.connect()
    con.execute(f"ATTACH '{dr.CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    daydata = load_days(con, today0, days)
    con.close()

    # ---- drift guard: fast replay must match the shipped module logic ----
    for date, mins, closes, _ in daydata:
        if len(mins) > dr.WINDOW:
            a = [(m[0], m[1]) for m in replay_fast(mins, closes, int(_t0(date, daydata)), int(_t1(date, daydata)),
                 er=dr.ER_TREND, net=dr.NET_MIN, window=dr.WINDOW, step=dr.STEP, hold=dr.HOLD, fast=False)]
            b = [(m[0], m[1]) for m in dr.replay_marks(mins, closes, int(_t0(date, daydata)), int(_t1(date, daydata)))]
            assert a == b, f"DRIFT vs module on {date}!"
    print("✓ fast-replay validated identical to gazbot7.direction_router.replay_marks (shipped config)\n")

    print(f"ROUTER STUDY — last {days} Paris days · realised MNQ trades")
    print(f"SHIPPED: ER>={SHIPPED['er']} |net|>={SHIPPED['net']}pt window={SHIPPED['window']}m "
          f"step={SHIPPED['step']}m hold={SHIPPED['hold']} fast_exit={SHIPPED['fast']}")
    print(f"LIVE managed: DOWN_OFF={sorted(LIVE_DOWN)} UP_OFF={sorted(LIVE_UP)}\n")

    for label, (down, up) in [("LIVE managed set {capitulation_long, rgv_short}", (LIVE_DOWN, LIVE_UP)),
                              ("FULL historical fader set (+rgv_long, +exhaustion_short)", (DOWN_FADERS, UP_FADERS))]:
        print("=" * 92)
        print(f"UNIVERSE: {label}")
        print("=" * 92)
        cur = eval_config(daydata, down, up, SHIPPED, per_day=True)
        print(f"  baseline (no router)  ${cur['base']:+.0f}   ·   router NOW  ${cur['router']:+.0f} "
              f"(Δ{cur['delta']:+.0f})  ·  blocked {cur['n_blk']} trades "
              f"(losers ${cur['blk_los']:+.0f} / winners ${cur['blk_win']:+.0f})")

        # (1) THRESHOLD TRIGGER SWEEP — ER x NET at shipped timing
        print("\n  (1) THRESHOLD SWEEP — router Δ vs baseline (shipped timing). '*'=current, '·'=no change:")
        ers = [0.15, 0.20, 0.25, 0.30, 0.35]
        nets = [20, 30, 40, 50, 60]
        print("        NET→ " + "".join(f"{nm:>8}" for nm in nets))
        for er in ers:
            row = f"   ER {er:.2f} "
            for nm in nets:
                cfg = dict(SHIPPED, er=er, net=float(nm))
                d = eval_config(daydata, down, up, cfg)["delta"]
                star = "*" if (abs(er - SHIPPED["er"]) < 1e-9 and abs(nm - SHIPPED["net"]) < 1e-9) else " "
                cell = f"{d:+.0f}{star}" if d else f"·{star}"
                row += f"{cell:>8}"
            print(row)

        # (2) full-grid joint best (thresholds x timings)
        best = None
        grid = 0
        for er in ers:
            for nm in nets:
                for step in (5, 15):
                    for hold in (1, 2, 3):
                        for window in (20, 30, 45):
                            for fast in (False, True):
                                cfg = dict(er=er, net=float(nm), step=step, hold=hold, window=window, fast=fast)
                                r = eval_config(daydata, down, up, cfg, per_day=True)
                                grid += 1
                                if best is None or r["router"] > best[1]["router"]:
                                    best = (cfg, r)
        bc, br = best
        pos = sum(1 for _d, b0, r0, _blk in br["per"] if r0 > b0)
        neg = sum(1 for _d, b0, r0, _blk in br["per"] if r0 < b0)
        worst = min((r0 - b0 for _d, b0, r0, _blk in br["per"]), default=0.0)
        print(f"\n  (2) JOINT BEST over {grid} configs (thresholds×timings):")
        print(f"      ER>={bc['er']} |net|>={bc['net']:.0f} window={bc['window']}m step={bc['step']}m "
              f"hold={bc['hold']} fast_exit={bc['fast']}")
        print(f"      router ${br['router']:+.0f} (Δ{br['delta']:+.0f} vs baseline; +${br['router']-cur['router']:.0f} "
              f"vs shipped) · blocked {br['n_blk']} (losers ${br['blk_los']:+.0f}/winners ${br['blk_win']:+.0f})")
        print(f"      robustness: {pos} days helped / {neg} hurt · worst single day Δ ${worst:+.0f}")

        # (3) is it blocking ENOUGH — leakage at the CURRENT config
        print("\n  (3) BLOCKING ENOUGH? — managed faders' trades classified (shipped config):")
        cats = leakage(daydata, down, up, SHIPPED)
        order = ["BLOCKED (router caught it)", "allowed winner (correct)",
                 "LEAK: counter-trend NEAR-MISS (lower threshold?)", "chop loss (router can't help)",
                 "trend-FOLLOWING loss (gate/exit problem)", "leak: off-regime but not held (hysteresis lag)"]
        for cat in order:
            n, p = cats.get(cat, [0, 0.0])
            if n:
                print(f"        {cat:52} n={n:3}  ${p:+.0f}")
        print()

    print("⚠ realised trades are thin, one summer RANGE regime, partly already hand/router-gated. "
          "Illustrative lower bound — a change is a SATURDAY/operator call, ideally re-run after a TREND week.")


if __name__ == "__main__":
    main()
