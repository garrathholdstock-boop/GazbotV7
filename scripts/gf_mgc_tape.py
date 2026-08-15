#!/usr/bin/env python3
"""GF_MGC — the shared, HONEST gold tape. Every gate in the gold 2x2 loads from here.

    PYTHONPATH=src .venv/bin/python scripts/gf_mgc_tape.py        # prints the audit

★ THIS MODULE EXISTS BECAUSE THE EXISTING GOLD LOADER HAS TWO DEFECTS AND ONE MISSED OPPORTUNITY,
and all three change the answer. Nothing here is a signal; it is the measuring stick.

── 1. THE MIXED-TIMEFRAME LOOK-AHEAD (a real bug in every July gold result) ──────────────────────
`scripts/mgc_session_anchor.load()` does `SELECT bar_ts,open,high,low,close FROM bars` with NO
`timeframe` filter. On the V5-archive days (07-07..07-17) the `bars` table holds FOUR timeframes for
the same instrument at once: 5s, 1m, 3m and 5m. Resampling that union to 1 minute takes
`high = max(...)` across all of them, so the 10:00 minute inherits the high of the 5-MINUTE bar
stamped 10:00 — a bar whose high is not known until 10:05.

    That is a four-minute look-ahead on every high and low, on 10 of the 18 L1 days.

It leaks into anything reading a range, an ATR or a level break: the opening-range break in
`mgc_session_anchor`, the 20-minute coil in `mgc_coil_bounce`, the ATR floor everywhere. `load_l1()`
below filters `timeframe='5s'`, which is the only timeframe present on ALL days, and the audit at the
bottom of this file quantifies what the contamination was worth.

── 2. THE COST MODEL IS 5x TOO GENEROUS ON GOLD ──────────────────────────────────────────────────
Every gold study so far charged `FEE_RT = 1.50` and raced on the TRADE tape, which silently assumes
you were filled at the last traded price on both legs. The live desk does not do that. Per
`docs/CAPPED_MARKETABLE_LIMIT_ENTRIES.md` an entry is a **marketable limit, IOC** (it CROSSES) and
"CLOSES / FLATTENS stay MKT" (they cross too). So both legs pay the spread.

    MGC median spread = 0.30 pt, FLAT round the clock, top-of-book ~5 lots.
    0.30 pt x 2 legs x $10/pt  =  $6.00  +  $1.50 fee  =  $7.50 per round trip.

Not $1.50. Five times the number every gold candidate has been judged against — and gold's ATR is
~1.6-3.6pt, so R is only ~$16-36. The spread is a QUARTER of an R. This module therefore prices
every trade TWICE and both numbers are reported:

    desk_pnl    entry/exit at mid, minus $1.50   <- the old convention, kept ONLY for comparability
    true_pnl    entry crosses, exit crosses, minus $1.50   <- the number that decides anything

── 3. ★★ THE MISSED OPPORTUNITY: L2 IS A LONGER, CONTIGUOUS PRICE TAPE THAN L1 ───────────────────
MGC L1 has a three-week hole (07-18..08-04) and gives 18 days in two islands. MGC **depth** has
**22 trading days, 07-16..08-14, with NO gap** — because `depth_capture.py` kept running through the
window where the L1 mirror did not. And `depth` carries `bid1p`/`ask1p`, so it IS a price tape at a
250ms median cadence.

    Validated on 08-13 against the trade tape: 1,378 overlapping minutes, corr 0.99985,
    median |mid - last| = 0.20pt (about half a spread, which is exactly what it should be).

That matters three ways. It CLOSES the hole, so the sample is contiguous instead of two islands. It
adds 12 days (07-20..08-04) that **no gold study has ever touched** — six refuted attacks, all of
them fitted on L1 only — which makes that block a genuine held-out leg. And racing on quotes rather
than trades is what makes the spread-honest exit above possible at all.

── COSTS ────────────────────────────────────────────────────────────────────────────────────────
MGC = $10.00/point (NOT MNQ's $2.00). Fee $1.50 per ROUND TRIP (not per side).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7 import lake  # noqa: E402

SYMBOL = "MGC"
VPP = 10.0        # MGC $/point
FEE_RT = 1.50     # per ROUND TRIP

# Session boundaries in UTC minutes-of-day. Gold is a 23-hour instrument with three genuinely
# different liquidity regimes; the clock split is institutional, not swept.
SESSIONS = {
    "ASIA":   (22 * 60, 6 * 60),        # wraps midnight
    "LONDON": (6 * 60, 13 * 60 + 30),
    "US":     (13 * 60 + 30, 20 * 60 + 60),
}

_CACHE: dict = {}


# ── loading ──────────────────────────────────────────────────────────────────────────────────────
def load_l1(con=None) -> pd.DataFrame:
    """5-SECOND bars only. The timeframe filter is the whole point — see the header."""
    con = con or lake.connect(symbol=SYMBOL)
    df = con.execute(f"""
        SELECT bar_ts, open, high, low, close, volume
        FROM bars WHERE symbol='{SYMBOL}' AND timeframe='5s' ORDER BY bar_ts
    """).df()
    df["ts"] = pd.to_datetime(df["bar_ts"], unit="s", utc=True)
    return df.set_index("ts")


def load_l1_dirty(con=None) -> pd.DataFrame:
    """The OLD loader's behaviour — every timeframe unioned. Kept ONLY so the audit can measure the
    look-ahead it introduced. Never use this for a backtest."""
    con = con or lake.connect(symbol=SYMBOL)
    df = con.execute(f"""
        SELECT bar_ts, open, high, low, close
        FROM bars WHERE symbol='{SYMBOL}' ORDER BY bar_ts
    """).df()
    df["ts"] = pd.to_datetime(df["bar_ts"], unit="s", utc=True)
    return df.set_index("ts")


def load_quotes(con=None) -> pd.DataFrame:
    """Top-of-book from depth, 250ms. This is BOTH the price tape (mid) and the exit race tape
    (bid/ask), and it is the only stream that spans all 22 days without a gap.

    `ask1p - bid1p < 5` drops a handful of one-sided/stale snapshots; `bid1p > 0` drops the empties.
    """
    con = con or lake.connect(symbol=SYMBOL)
    df = con.execute(f"""
        SELECT ts_ms, bid1p, ask1p, bid1s, ask1s
        FROM depth
        WHERE symbol='{SYMBOL}' AND bid1p > 0 AND ask1p > 0 AND ask1p - bid1p BETWEEN 0 AND 5
        ORDER BY ts_ms
    """).df()
    df["mid"] = (df["bid1p"] + df["ask1p"]) / 2.0
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    return df.set_index("ts")


def minute_bars(q: pd.DataFrame, col: str = "mid") -> pd.DataFrame:
    """1-minute OHLC. ⚠ `resample` labels a bar by its LEFT edge — the 10:00 bar's close is only
    known at 10:01. Every consumer here enters at `ts + 60s` or races from the crossing quote; see
    the trap list in docs/MGC_LEADS_2026-08-14.md."""
    m = q[col].resample("1min").ohlc().dropna()
    m.columns = ["open", "high", "low", "close"]
    return m


def build_tape(con=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The canonical pair: (1-minute bars, 250ms quote tape), 22 contiguous days.

    Bars are built from the QUOTE MID, not from L1, so that a single construction spans the whole
    window — mixing an L1-bar day with a depth-bar day would put a construction seam exactly where
    the out-of-sample leg starts, which is the one place a seam must not be.
    """
    if "tape" in _CACHE:
        return _CACHE["tape"]
    q = load_quotes(con)
    m = minute_bars(q)
    m = add_regime(m)
    _CACHE["tape"] = (m, q)
    return m, q


# ── regime, derived from GOLD's own distribution ─────────────────────────────────────────────────
def atr(m: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = m["close"].shift(1)
    tr = pd.concat([m["high"] - m["low"], (m["high"] - prev).abs(),
                    (m["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def eff_ratio(close: pd.Series, n: int = 30) -> pd.Series:
    """Kaufman efficiency: net distance / path travelled. Dimensionless, so it transfers across
    instruments where a point threshold cannot."""
    net = close.diff(n).abs()
    path = close.diff().abs().rolling(n).sum()
    return (net / path).replace([np.inf, -np.inf], np.nan)


def session_of(idx: pd.DatetimeIndex) -> pd.Series:
    mod = idx.hour * 60 + idx.minute
    out = pd.Series("ASIA", index=idx)
    out[(mod >= 6 * 60) & (mod < 13 * 60 + 30)] = "LONDON"
    out[(mod >= 13 * 60 + 30) & (mod < 21 * 60)] = "US"
    return out


def add_regime(m: pd.DataFrame) -> pd.DataFrame:
    """Label every minute with ATR level, efficiency and a five-way regime.

    ★ The cut points are GOLD's OWN percentiles, computed on this tape — not MNQ constants, and not
    round numbers chosen by hand. That is the one methodology from the 08-14 session that survived:
    the transferable quantity is the SELECTIVITY, never the number.

    ★ Everything here is causal. ATR and ER look backward only, and the percentile cuts are taken on
    the whole sample, which is a mild in-sample convenience for LABELLING (not for the signal) —
    stated so it is not mistaken for a peek.
    """
    m = m.copy()
    m["atr"] = atr(m)
    m["er"] = eff_ratio(m["close"])
    m["session"] = session_of(m.index).values
    m["day"] = m.index.strftime("%Y-%m-%d")

    a_lo, a_hi = m["atr"].quantile(0.33), m["atr"].quantile(0.67)
    e_lo, e_hi = m["er"].quantile(0.40), m["er"].quantile(0.75)
    m.attrs["cuts"] = {"atr_p33": a_lo, "atr_p67": a_hi, "er_p40": e_lo, "er_p75": e_hi}

    reg = pd.Series("NORMAL_CHOP", index=m.index)
    reg[(m["atr"] <= a_lo) & (m["er"] <= e_hi)] = "DEAD_CHOP"
    reg[(m["atr"] >= a_hi) & (m["er"] >= e_hi)] = "CLEAN_TREND"
    reg[(m["atr"] >= a_hi) & (m["er"] <= e_lo)] = "VIOLENT_WHIPSAW"
    reg[(m["atr"].between(a_lo, a_hi, inclusive="neither")) & (m["er"] >= e_hi)] = "BUILDING"
    m["regime"] = reg.values
    return m


# ── the honest trade ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Trade:
    """One round trip, priced BOTH ways. `desk_pnl` is the old $1.50-only convention kept for
    comparability with prior gold work; `true_pnl` is what the account would actually see."""
    day: str
    tag: str
    side: int              # +1 long, -1 short
    ts_in: pd.Timestamp
    ts_out: pd.Timestamp
    mid_in: float
    mid_out: float
    fill_in: float         # crossed
    fill_out: float        # crossed
    reason: str
    regime: str
    session: str
    atr_in: float
    minutes: float

    @property
    def desk_pnl(self) -> float:
        return round(self.side * (self.mid_out - self.mid_in) * VPP - FEE_RT, 2)

    @property
    def true_pnl(self) -> float:
        return round(self.side * (self.fill_out - self.fill_in) * VPP - FEE_RT, 2)

    @property
    def r_mult(self) -> float:
        r = self.atr_in * VPP
        return round(self.true_pnl / r, 3) if r else 0.0


def race(qt: np.ndarray, bid: np.ndarray, ask: np.ndarray, side: int, *,
         fill_in: float, mid_in: float, stop: float, target: float | None,
         trail: float | None, cap_ms: int, arm_at: float | None = None
         ) -> tuple[float, float, str, float, float, float]:
    """Walk the 250ms QUOTE tape forward. Returns
    (fill_out, mid_out, reason, minutes, mfe_pt, mae_pt).

    ★ THE ORDER OF THE CHECKS IS THE WHOLE POINT — a bar close hides which of the stop and the
    target came first, and on MNQ resolving that on ticks rather than bars cut a result by 87%.

    ★ SPREAD-HONEST BY CONSTRUCTION. A long is measured against the BID (what it can sell at) and a
    short against the ASK. So a long's stop triggers when the bid breaks it and the long exits AT the
    bid — no phantom fill at the midpoint, which is what every previous gold study booked.

    `arm_at` implements a chandelier that only starts trailing once price has run this far (in
    points) in favour; None = trail from the first quote.
    """
    if len(qt) == 0:
        return fill_in, mid_in, "NO_TAPE", 0.0, 0.0, 0.0
    t0 = qt[0]
    peak = mid_in
    mfe = mae = 0.0
    armed = arm_at is None
    for i in range(len(qt)):
        b, a = bid[i], ask[i]
        mid = (b + a) / 2.0
        exc = side * (mid - mid_in)
        mfe = max(mfe, exc)
        mae = min(mae, exc)
        if side > 0:
            peak = max(peak, b)
            if not armed and (b - fill_in) >= (arm_at or 0):
                armed = True
            if b <= stop:
                return b, mid, "STOP", (qt[i] - t0) / 60000.0, mfe, mae
            if target is not None and b >= target:
                return b, mid, "TARGET", (qt[i] - t0) / 60000.0, mfe, mae
            if trail is not None and armed and peak > fill_in:
                if b <= peak - trail:
                    return b, mid, "TRAIL", (qt[i] - t0) / 60000.0, mfe, mae
        else:
            peak = min(peak, a)
            if not armed and (fill_in - a) >= (arm_at or 0):
                armed = True
            if a >= stop:
                return a, mid, "STOP", (qt[i] - t0) / 60000.0, mfe, mae
            if target is not None and a <= target:
                return a, mid, "TARGET", (qt[i] - t0) / 60000.0, mfe, mae
            if trail is not None and armed and peak < fill_in:
                if a >= peak + trail:
                    return a, mid, "TRAIL", (qt[i] - t0) / 60000.0, mfe, mae
        if qt[i] - t0 >= cap_ms:
            out = b if side > 0 else a
            return out, mid, "TIME_CAP", (qt[i] - t0) / 60000.0, mfe, mae
    out = bid[-1] if side > 0 else ask[-1]
    return out, (bid[-1] + ask[-1]) / 2.0, "EOD", (qt[-1] - t0) / 60000.0, mfe, mae


def summarise(trades: list[Trade], field: str = "true_pnl") -> dict:
    if not trades:
        return {"n": 0, "net": 0.0, "win": 0.0, "per": 0.0, "med": 0.0}
    v = np.array([getattr(t, field) for t in trades])
    return {"n": len(v), "net": round(float(v.sum()), 2),
            "win": round(100.0 * float((v > 0).mean()), 1),
            "per": round(float(v.mean()), 2), "med": round(float(np.median(v)), 2)}


def by(trades: list[Trade], key, field: str = "true_pnl") -> pd.DataFrame:
    rows = {}
    for t in trades:
        rows.setdefault(key(t), []).append(t)
    out = [dict(k=k, **summarise(v, field)) for k, v in sorted(rows.items(), key=lambda kv: str(kv[0]))]
    return pd.DataFrame(out)


# ── audit ────────────────────────────────────────────────────────────────────────────────────────
def _audit() -> None:
    con = lake.connect(symbol=SYMBOL)
    print("=" * 100)
    print("GF_MGC TAPE AUDIT")
    print("=" * 100)

    q = load_quotes(con)
    print(f"\nQUOTE TAPE  rows={len(q):,}  {q.index.min()} .. {q.index.max()}")
    days = sorted(set(q.index.strftime("%Y-%m-%d")))
    print(f"            {len(days)} trading days, contiguous: {days[0]} .. {days[-1]}")
    print(f"            median spread {q['ask1p'].sub(q['bid1p']).median():.2f} pt "
          f"= ${q['ask1p'].sub(q['bid1p']).median() * VPP:.2f}   "
          f"top-of-book median {q[['bid1s', 'ask1s']].sum(axis=1).median():.0f} lots")
    print(f"            TRUE round-trip cost = 2 x spread x $10 + $1.50 = "
          f"${q['ask1p'].sub(q['bid1p']).median() * 2 * VPP + FEE_RT:.2f}   (studies so far used $1.50)")

    l1 = load_l1(con)
    l1days = sorted(set(l1.index.strftime("%Y-%m-%d")))
    print(f"\nL1 5s BARS  {len(l1days)} days   {l1days[0]} .. {l1days[-1]}")
    print(f"            L2-only days (never hunted by ANY gold study): "
          f"{sorted(set(days) - set(l1days))}")

    # ── the mixed-timeframe look-ahead, quantified ──
    print("\n" + "-" * 100)
    print("DEFECT 1 — the mixed-timeframe look-ahead in the existing loader")
    print("-" * 100)
    dirty = load_l1_dirty(con)
    cl = dirty.resample("1min").agg(high=("high", "max"), low=("low", "min")).dropna()
    clean = load_l1(con).resample("1min").agg(high=("high", "max"), low=("low", "min")).dropna()
    j = clean.join(cl, lsuffix="_clean", rsuffix="_dirty", how="inner").dropna()
    jul = j[j.index < "2026-07-18"]
    infl = (jul["high_dirty"] - jul["low_dirty"]) - (jul["high_clean"] - jul["low_clean"])
    print(f"  July (V5-archive) minutes compared: {len(jul):,}")
    print(f"  minutes whose RANGE is inflated by future bars: {int((infl > 1e-9).sum()):,} "
          f"({100.0 * (infl > 1e-9).mean():.1f}%)")
    print(f"  mean inflation {infl.mean():.3f} pt   p95 {infl.quantile(0.95):.3f} pt   "
          f"max {infl.max():.3f} pt")
    print(f"  in ATR terms: the clean 1-min range averages {(jul['high_clean'] - jul['low_clean']).mean():.3f} pt, "
          f"so the leak is worth {100.0 * infl.mean() / max((jul['high_clean'] - jul['low_clean']).mean(), 1e-9):.0f}% of a bar")
    aug = j[j.index >= "2026-08-01"]
    infl_a = (aug["high_dirty"] - aug["low_dirty"]) - (aug["high_clean"] - aug["low_clean"])
    print(f"  August days (5s only, control): inflated minutes = {int((infl_a > 1e-9).sum())}  <- expected 0")

    # ── regime census ──
    print("\n" + "-" * 100)
    print("THE TAPE, SEGMENTED — gold's own percentile cuts")
    print("-" * 100)
    m, _ = build_tape(con)
    c = m.attrs["cuts"]
    print(f"  ATR p33 {c['atr_p33']:.3f} pt   p67 {c['atr_p67']:.3f} pt      "
          f"ER p40 {c['er_p40']:.3f}   p75 {c['er_p75']:.3f}")
    print()
    g = m.groupby("regime").agg(minutes=("close", "size"), atr=("atr", "median"), er=("er", "median"))
    g["share%"] = (100.0 * g["minutes"] / len(m)).round(1)
    print(g.sort_values("minutes", ascending=False).to_string())
    print()
    print(pd.crosstab(m["regime"], m["session"]).to_string())
    return None


if __name__ == "__main__":
    _audit()
