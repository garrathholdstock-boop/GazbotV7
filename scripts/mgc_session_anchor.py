#!/usr/bin/env python3
"""MGC GREENFIELD — session-anchored opening-range break. The one untried source.

    PYTHONPATH=src .venv/bin/python scripts/mgc_session_anchor.py [--expand]

★★ WHY THIS SHAPE AND NOT THE TWO THE OPERATOR NAMED. A momentum/continuation gate and a
reversion/coil fader have BOTH been built on gold and both are documented NULLs
([[mgc-momentum-greenfield-null]], scripts/mgc_momentum_gate.py and scripts/mgc_fader.py):

  · momentum/continuation — 5 of 72 cells positive, best strips to $16; `always SHORT` (−$532) BEAT
    the direction-directed gate (−$1,274). Thrust-continuation catches 22 of 22 runs but the losers
    are indistinguishable (ATR d=+0.21, ER d=+0.12).
  · reversion/coil — Hurst on OUR tape is 0.489 (2-15min 0.490, 60-240min 0.462): a random walk.
    Reversion after ≥2 ATR extension is +0.7pp on DISJOINT windows against 1sd of 4.1pp.

The recorded conclusion is explicit: *"price (predict / react / regime-filter) and book (select /
veto) are the only two sources this desk has, and all five attacks are null. Re-opening MGC needs a
source that is neither — event/session-time structure, or cross-asset."* And: **"Do not retry by
tuning thresholds."** So this is not another sweep of the same information.

★ WHAT IS ACTUALLY NEW HERE, and why it is not just the momentum gate again:

  1. **Structure comes from the CLOCK, not from price shape.** The anchors are institutional: the
     London open, the COMEX/RTH open, and the London PM fix — the daily gold benchmark auction,
     which is a genuine scheduled liquidity event with no MNQ analogue. That is the one transferable
     finding from the literature review: the only positive controls in the OHLCV-momentum paper were
     SESSION-ANCHORED, and structure came from TIME.
  2. **It needs NO direction predictor.** Every gold null died on the same rock — nothing calls the
     SIDE (three independent signals all landed ~2pp over the best CONSTANT). Here the break of the
     opening range picks the side, exactly as the extension picks it for a fader. The clock says
     WHEN; the range says WHICH WAY.

★ DISCIPLINE. The CORE test is THREE cells — one per anchor, all other parameters fixed at defaults
chosen before looking. Only if a core cell survives does `--expand` sweep around it, and the expanded
result is placebo-controlled against random same-day entries. This ordering is deliberate: the prior
gold work found "best of 22 hour-cells beaten by 5%", i.e. exactly what 22 looks produce by chance.
The garden of forking paths is how a null becomes a false positive.

★ The exit race is resolved on TICKS, never on bar closes — a 5s bar hides which of the stop and the
target came first, and on MNQ that flattered results by 87% ([[sims-on-tick-price]]). MFE is not a
win rate ([[mfe-is-not-a-win-rate]]).

★ COSTS: MGC is $10/pt (NOT MNQ's $2) and the fee is $1.50/RT. Gold's R is small in dollars —
ATR ~1.6pt = ~$16 R — so a fixed fee is roughly TWICE as regressive on gold as on MNQ.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7 import lake  # noqa: E402

VPP = 10.0            # MGC $/point — NOT $2
FEE_RT = 1.50
SYMBOL = "MGC"

# Anchors in UTC minutes-of-day. Chosen for institutional meaning, not swept.
ANCHORS = {
    "LDN_OPEN": 7 * 60,        # London bullion market opens
    "RTH_OPEN": 13 * 60 + 30,  # COMEX / US cash open
    "PM_FIX": 15 * 60,         # London PM gold fix — the daily benchmark auction
}

# Core defaults, fixed BEFORE looking at any result.
OR_MIN = 30           # opening-range length, minutes
MARGIN_ATR = 0.15     # break must clear the range by this × ATR (MCL: a bare break loses everywhere)
STOP_ATR = 1.5
TRAIL_ATR = 3.0       # chandelier
TIME_CAP_MIN = 120
ENTRY_CUTOFF_MIN = 180  # stop looking for a break this long after the anchor


@dataclass
class Trade:
    day: str
    anchor: str
    side: int          # +1 long, -1 short
    entry: float
    exit: float
    reason: str
    minutes: float

    @property
    def pnl(self) -> float:
        return round(self.side * (self.exit - self.entry) * VPP - FEE_RT, 2)


def load(days_back: int = 60):
    con = lake.connect(symbol=SYMBOL)
    bars = con.execute(f"""
        SELECT bar_ts, open, high, low, close
        FROM bars WHERE symbol='{SYMBOL}' ORDER BY bar_ts
    """).df()
    ticks = con.execute(f"""
        SELECT ts_ms, price FROM ticks WHERE symbol='{SYMBOL}' ORDER BY ts_ms
    """).df()
    bars["ts"] = pd.to_datetime(bars["bar_ts"], unit="s", utc=True)
    ticks["ts"] = pd.to_datetime(ticks["ts_ms"], unit="ms", utc=True)
    return bars, ticks


def minute_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """5s → 1-min. ★ Resample on the TIMESTAMP, never `(bar_ts/60)*60` — DuckDB's `/` is float and
    that idiom is a silent no-op that read 5s bars as 1m for hours
    ([[duckdb-integer-division-broke-my-tape-reads]])."""
    m = bars.set_index("ts").resample("1min").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    return m.dropna()


def atr(m: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = m["close"].shift(1)
    tr = pd.concat([m["high"] - m["low"], (m["high"] - prev).abs(), (m["low"] - prev).abs()],
                   axis=1).max(axis=1)
    return tr.rolling(n).mean()


def race(tk: np.ndarray, px: np.ndarray, side: int, entry: float, stop: float,
         target: float | None, trail_atr: float | None, cap_ms: int) -> tuple[float, str, float]:
    """Walk ticks forward and return (exit_price, reason, minutes). The ORDER is the whole point."""
    if len(tk) == 0:
        return entry, "NO_TICKS", 0.0
    t0 = tk[0]
    peak = entry
    for i in range(len(tk)):
        p = px[i]
        if side > 0:
            peak = max(peak, p)
            if p <= stop:
                return stop, "STOP", (tk[i] - t0) / 60000.0
            if target is not None and p >= target:
                return target, "TARGET", (tk[i] - t0) / 60000.0
            if trail_atr is not None:
                tl = peak - trail_atr
                if p <= tl and peak > entry:
                    return tl, "TRAIL", (tk[i] - t0) / 60000.0
        else:
            peak = min(peak, p)
            if p >= stop:
                return stop, "STOP", (tk[i] - t0) / 60000.0
            if target is not None and p <= target:
                return target, "TARGET", (tk[i] - t0) / 60000.0
            if trail_atr is not None:
                tl = peak + trail_atr
                if p >= tl and peak < entry:
                    return tl, "TRAIL", (tk[i] - t0) / 60000.0
        if tk[i] - t0 >= cap_ms:
            return p, "TIME_CAP", (tk[i] - t0) / 60000.0
    return px[-1], "EOD", (tk[-1] - t0) / 60000.0


def run(anchor_name: str, anchor_min: int, m: pd.DataFrame, ticks: pd.DataFrame,
        *, or_min=OR_MIN, margin_atr=MARGIN_ATR, stop_atr=STOP_ATR,
        trail_atr=TRAIL_ATR, target_r=None, cap_min=TIME_CAP_MIN,
        jitter_min: int = 0, fade: bool = False) -> list[Trade]:
    """One trade per day per anchor. `jitter_min` shifts the anchor for the placebo control."""
    out: list[Trade] = []
    a = atr(m)
    tk_all = ticks["ts_ms"].to_numpy()
    px_all = ticks["price"].to_numpy()

    for day, dm in m.groupby(m.index.date):
        amin = anchor_min + jitter_min
        start = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=amin)
        or_end = start + pd.Timedelta(minutes=or_min)
        win = dm.loc[start:or_end]
        if len(win) < max(5, or_min // 2):
            continue
        hi, lo = win["high"].max(), win["low"].min()
        try:
            atr_v = float(a.loc[:or_end].dropna().iloc[-1])
        except (IndexError, KeyError):
            continue
        if not np.isfinite(atr_v) or atr_v <= 0:
            continue

        margin = margin_atr * atr_v
        after = dm.loc[or_end:or_end + pd.Timedelta(minutes=ENTRY_CUTOFF_MIN)]
        side = entry = None
        for ts, row in after.iterrows():
            if row["high"] >= hi + margin:
                side, entry, etime = 1, hi + margin, ts
                break
            if row["low"] <= lo - margin:
                side, entry, etime = -1, lo - margin, ts
                break
        if side is None:
            continue

        if fade:
            # ★ THE BREAK FAILS: the core run returned 6.2% / 25.0% / 37.5% win rates, i.e. the
            # opening-range break of gold reverses far more often than it runs. Taking the OTHER
            # side is ONE additional look motivated by that observed asymmetry — not a sweep — and
            # it is placebo-controlled below like everything else. It is also the shape the prior
            # gold work already leaned toward: on identical entries FADING beat CONTINUING by $932.
            side = -side
        stop = entry - side * stop_atr * atr_v
        target = entry + side * target_r * stop_atr * atr_v if target_r else None
        # ★★ RACE FROM THE TICK THAT ACTUALLY CROSSES, not from the bar's left edge. The break
        # level is touched somewhere INSIDE the signal bar; starting at the bar's open replays ticks
        # that happened BEFORE the entry existed, and any of them could spuriously trigger the stop
        # or the target. Find the crossing tick and start there.
        b0 = int(etime.value // 10**6)
        b1 = b0 + 60_000
        w0, w1 = np.searchsorted(tk_all, b0), np.searchsorted(tk_all, b1)
        seg = px_all[w0:w1]
        hit = (np.nonzero(seg >= entry)[0] if side > 0 else np.nonzero(seg <= entry)[0])
        if len(hit) == 0:
            continue                      # the level was never actually traded inside the bar
        e_ms = int(tk_all[w0 + hit[0]])
        j = np.searchsorted(tk_all, e_ms)
        k = np.searchsorted(tk_all, e_ms + cap_min * 60000 + 1)
        xp, why, mins = race(tk_all[j:k], px_all[j:k], side, entry, stop, target,
                             trail_atr * atr_v if trail_atr else None, cap_min * 60000)
        out.append(Trade(str(day), anchor_name, side, entry, xp, why, mins))
    return out


def score(trades: list[Trade]) -> dict:
    if not trades:
        return {"n": 0, "total": 0.0, "exp": 0.0, "win": 0.0, "strip_best_day": 0.0, "days": 0}
    df = pd.DataFrame([{"day": t.day, "pnl": t.pnl} for t in trades])
    by_day = df.groupby("day")["pnl"].sum()
    total = float(df["pnl"].sum())
    strip = float(total - by_day.max()) if len(by_day) else 0.0
    return {"n": len(df), "total": round(total, 2), "exp": round(total / len(df), 2),
            "win": round((df["pnl"] > 0).mean() * 100, 1), "strip_best_day": round(strip, 2),
            "days": int(len(by_day)), "green_days": int((by_day > 0).sum())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expand", action="store_true")
    ap.add_argument("--fade", action="store_true", help="take the OTHER side of the break")
    a = ap.parse_args()

    bars, ticks = load()
    m = minute_bars(bars)
    print(f"  MGC {m.index.min():%Y-%m-%d} .. {m.index.max():%Y-%m-%d} · "
          f"{m.index.normalize().nunique()} days · {len(m):,} 1-min bars · {len(ticks):,} ticks")
    print(f"  VPP ${VPP:.0f}/pt · fee ${FEE_RT:.2f}/RT · exits raced on TICKS\n")

    print(f"  ═══ CORE: 3 cells, one per anchor. OR{OR_MIN}m · margin {MARGIN_ATR}xATR · "
          f"stop {STOP_ATR}xATR · chandelier {TRAIL_ATR}xATR · cap {TIME_CAP_MIN}m"
          f"{'  [FADE: taking the other side]' if a.fade else ''} ═══")
    print(f"  {'anchor':<10}{'n':>4}{'days':>6}{'green':>7}{'win%':>7}{'exp$':>9}{'total$':>10}{'strip-best-day':>16}")
    core = {}
    for name, mins in ANCHORS.items():
        tr = run(name, mins, m, ticks, fade=a.fade)
        s = score(tr)
        core[name] = (tr, s)
        print(f"  {name:<10}{s['n']:>4}{s['days']:>6}{s.get('green_days',0):>7}{s['win']:>7.1f}"
              f"{s['exp']:>9.2f}{s['total']:>10.2f}{s['strip_best_day']:>16.2f}")

    alive = [k for k, (_t, s) in core.items() if s["total"] > 0 and s["strip_best_day"] > 0]
    print()
    if not alive:
        print("  ✗ NO core cell survives (needs total>0 AND strip-best-day>0).")
        print("    Consistent with the recorded gold nulls; the clock is not rescuing it either.")
    else:
        print(f"  ✓ survives strip-best-day: {alive}")

    if a.expand and alive:
        print("\n  ═══ EXPAND + PLACEBO (only around a surviving anchor) ═══")
        for name in alive:
            mins = ANCHORS[name]
            real = score(run(name, mins, m, ticks, fade=a.fade))["total"]
            # placebo: same machinery, anchor shifted to meaningless clock times
            pl = [score(run(name, mins, m, ticks, jitter_min=j, fade=a.fade))["total"]
                  for j in (-150, -105, -60, 45, 90, 135, 180)]
            beaten = sum(1 for p in pl if p >= real)
            print(f"  {name}: real ${real:,.2f} vs {len(pl)} shifted anchors "
                  f"[{', '.join(f'{p:,.0f}' for p in pl)}]")
            print(f"    beaten by {beaten}/{len(pl)} — "
                  f"{'NOT distinguishable from an arbitrary clock time' if beaten >= 2 else 'the ANCHOR carries it'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
