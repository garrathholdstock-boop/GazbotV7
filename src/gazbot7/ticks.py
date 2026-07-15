"""GAZBOT V7 — contract tick sizes + directional price rounding (S1).

Every price that leaves the desk MUST sit on the contract's minimum price
variation, or IBKR rejects it with **Error 110** — the exact bug that left a naked
short today (a computed stop of 29478.214… on a 0.25-tick contract, rejected, so
no protection ever rested). Rounding is *directional* so it can only ever loosen a
protective stop, never silently tighten it onto noise:

* a SELL stop (protecting a long) sits below entry → **floor** (further away),
* a BUY stop (protecting a short) sits above entry → **ceil** (further away).

The price/tick ratio is rounded to 10 significant figures before floor/ceil to
kill float noise (e.g. 116312·0.25 can come back as 29077.999999998 and must not
floor a tick low). Pure + tested; applied at the safety layer (so the recorded
stop equals what rests) and again at the broker adapter (the last choke point — a
raw price can never reach IBKR). Clean-room.
"""

from __future__ import annotations

import math

# minimum price variation per contract. MNQ is the live desk; the rest are here
# for the shadow desk / future promotion.
_TICK: dict[str, float] = {
    "MNQ": 0.25, "MES": 0.25, "M2K": 0.10, "MYM": 1.0,
    "MGC": 0.10, "MCL": 0.01, "MBT": 5.0,
}
DEFAULT_TICK = 0.25


def tick_for(symbol: str) -> float:
    return _TICK.get(symbol, DEFAULT_TICK)


def round_to_tick(price: float, tick: float, *, mode: str = "nearest") -> float:
    """Round ``price`` onto the ``tick`` grid. ``mode`` = floor | ceil | nearest.
    The ratio is de-noised to 10 sig figs first so float error can't drop a tick."""
    q = round(price / tick, 10)
    if mode == "floor":
        q = math.floor(q)
    elif mode == "ceil":
        q = math.ceil(q)
    else:
        q = round(q)
    return round(q * tick, 10)


def round_stop(stop_price: float, tick: float, *, closing_side: str) -> float:
    """Round a protective stop's trigger so rounding only *loosens* it — SELL stop
    → floor (below entry, further away), BUY stop → ceil (above, further away)."""
    return round_to_tick(stop_price, tick, mode="floor" if closing_side == "SELL" else "ceil")
