"""GAZBOT V7 — THE DRIFT DETECTOR: which way is the day leaning, and is it confirmed?

Operator, 2026-08-05: "dashboard needs a way to indicate to me the way the day is leaning. so i know.
then when its confirmed we buy 2 lots."

★ ONE SOURCE OF TRUTH, DELIBERATELY. The dashboard panel and the live service both call `read()` here.
If each computed its own "leaning" they would drift apart and the operator would be shown one thing
while the desk acted on another — the exact class of failure that had four V5 surfaces each summing
P&L differently (see pnl.py's docstring).

★ IT IS A DRIFT DETECTOR, NOT A DAY PREDICTOR — the naming matters because it sets expectations.
It measures which way price has *efficiently already moved* since the US open. Over 31 sessions of MNQ
that early drift persisted to the close 22 times (71%); on 9 it reversed. So `confirmed` means "the tape
has committed", never "the day will end this way".

★ THE TWO METRICS, and why these and not the dozen others tested:
    EFFICIENCY  |net| / total path travelled. Separates big days from small at effect size d=+1.22 by
                15:00, measured in a diagnostic with no P&L in it — i.e. validated independently of any
                trading rule, before the rule was built.
    ROUNDTRIP   |net| / range. The desk's own untradeable-day discriminator (untradeable.py), validated
                07-29/30 green vs 07-31 untradeable.
  Thresholds 0.15 / 0.45 come from the minute-by-minute sweep: nothing fires before ~9 minutes because
  the metrics need bars to mean anything, and the plateau is 9-12 min with a peak at 10.

★ MEASURED ON MINUTE BARS AGGREGATED FROM 5s, because that is exactly what the backtest used. Feeding
it raw 5s bars would change `path` (many more increments ⇒ lower efficiency) and silently move the
thresholds. Same bars, same numbers, or the live desk is not running what was tested.

★ CAUSAL BY CONSTRUCTION — every field uses only 13:30..now. Nothing here can see forward. That was the
flaw in the first version of this work: a "detection" defined as "never returned to the open" read the
future and looked far better than anything achievable live.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass, field

OPEN_UTC_MIN = 13 * 60 + 30      # 13:30 UTC US cash open — the session anchor
CLOSE_UTC_MIN = 21 * 60          # 21:00 UTC = 23:00 Paris = the CME halt. NEVER hold past it.
MIN_BARS = 9                     # below this the metrics are noise (nothing fired 1-8 min in the sweep)
ER_MIN = 0.15
RT_MIN = 0.45


@dataclass
class DriftRead:
    ok: bool = False                 # enough data to say anything at all
    minutes: int = 0
    direction: str = ""              # "UP" | "DOWN" | "" (flat/unknown)
    net_pt: float = 0.0
    range_pt: float = 0.0
    efficiency: float = 0.0
    roundtrip: float = 0.0
    confirmed: bool = False
    price: float = 0.0
    open_px: float = 0.0
    # how far each metric is from its threshold — the dashboard shows this so the operator can see it
    # BUILDING rather than only learn about it at the moment it fires.
    er_needed: float = 0.0
    rt_needed: float = 0.0
    blockers: list = field(default_factory=list)
    detail: str = ""


def _minute_bars(rows):
    """5s rows -> one bar per minute. MUST match the backtest's aggregation exactly."""
    by = {}
    for ts, hi, lo, cl in rows:
        m = (int(ts) // 60) * 60
        b = by.get(m)
        if b is None:
            by[m] = [hi, lo, cl, ts]
        else:
            b[0] = max(b[0], hi)
            b[1] = min(b[1], lo)
            if ts >= b[3]:
                b[2], b[3] = cl, ts
    return [(m, v[0], v[1], v[2]) for m, v in sorted(by.items())]


def compute(bars) -> DriftRead:
    """Pure: minute bars since the US open -> the leaning. No I/O, so it is unit-testable."""
    r = DriftRead()
    if not bars:
        r.detail = "no bars since the open"
        return r
    r.minutes = len(bars)
    o = bars[0][3]
    cl = bars[-1][3]
    r.open_px, r.price = o, cl
    net = cl - o
    rng = max(b[1] for b in bars) - min(b[2] for b in bars)
    path = sum(abs(bars[i][3] - bars[i - 1][3]) for i in range(1, len(bars)))
    r.net_pt, r.range_pt = net, rng
    if len(bars) < MIN_BARS:
        r.blockers.append(f"only {len(bars)}m of tape (need {MIN_BARS})")
        r.detail = f"too early — {len(bars)}m since the open"
        return r
    if rng <= 0 or path <= 0:
        r.blockers.append("no range yet")
        r.detail = "no measurable range"
        return r
    r.ok = True
    r.efficiency = abs(net) / path
    r.roundtrip = abs(net) / rng
    r.direction = "UP" if net > 0 else ("DOWN" if net < 0 else "")
    # what each metric still needs, in its own units — actionable rather than opaque
    r.er_needed = max(0.0, ER_MIN - r.efficiency)
    r.rt_needed = max(0.0, RT_MIN - r.roundtrip)
    if r.efficiency < ER_MIN:
        r.blockers.append(f"efficiency {r.efficiency:.2f} < {ER_MIN}")
    if r.roundtrip < RT_MIN:
        r.blockers.append(f"roundtrip {r.roundtrip:.2f} < {RT_MIN}")
    if not r.direction:
        r.blockers.append("net is flat")
    r.confirmed = not r.blockers
    r.detail = (f"{r.direction or 'FLAT'} {net:+.0f}pt on a {rng:.0f}pt range · "
                f"efficiency {r.efficiency:.2f} · roundtrip {r.roundtrip:.2f}"
                + ("" if r.confirmed else " · " + "; ".join(r.blockers)))
    return r


def read(capture_path: str, symbol: str = "MNQ", now: dt.datetime | None = None) -> DriftRead:
    """Live read from capture.db. Fail-quiet: a bad read returns ok=False, never raises — a dashboard
    panel and an order-placing service must both degrade to 'I don't know', never to a wrong answer."""
    now = now or dt.datetime.now(dt.UTC)
    mod = now.hour * 60 + now.minute
    if not (OPEN_UTC_MIN <= mod <= CLOSE_UTC_MIN):
        r = DriftRead()
        r.detail = ("before the 13:30 UTC open" if mod < OPEN_UTC_MIN
                    else "after the 21:00 UTC flat — never hold overnight")
        return r
    start = now.replace(hour=13, minute=30, second=0, microsecond=0)
    try:
        c = sqlite3.connect(f"file:{capture_path}?mode=ro", uri=True, timeout=5)
        rows = c.execute(
            "SELECT bar_ts, high, low, close FROM bars WHERE symbol=? AND timeframe='5s' "
            "AND bar_ts>=? ORDER BY bar_ts", (symbol, int(start.timestamp()))).fetchall()
        c.close()
    except Exception as e:
        r = DriftRead()
        r.detail = f"capture read failed: {str(e)[:60]}"
        return r
    return compute(_minute_bars([(a, float(b), float(cc), float(d)) for a, b, cc, d in rows]))
