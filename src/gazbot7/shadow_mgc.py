"""GAZBOT V7 — the MGC (gold) shadow desk. A SECOND shadow instance, deliberately isolated.

    python -m gazbot7.shadow_mgc          (systemd: gazbot7-shadow-mgc.service)

Runs the two surviving gold gates from the 2026-08-15 greenfield hunt against the same MD stream the
MNQ shadow uses, and records to its OWN store. Observe-only: it touches no account, no
`gate_switches.env`, and nothing the router reads.

★★★ WHY A SEPARATE PROCESS AND A SEPARATE STORE — THIS IS THE WHOLE DESIGN.

`repricer.reprice_pending(store, cap, value_per_point=..., fee_rt=...)` reprices EVERY shadow trade
not yet in `shadow_real` using ONE multiplier. Two services sharing `shadow.db` would therefore
price gold at MNQ's $2.00/pt instead of $10.00, and charge $1.50/RT instead of $7.50 — whichever
service happened to call first. That is a RACE: intermittent, silent, and 5x wrong in the direction
that makes a losing gate look like a winner.

Symbol-scoping the repricer was the alternative and it is worse: it means editing shared code on the
LIVE MNQ path to fix a problem gold introduced. A separate store makes the failure structurally
impossible and touches nothing live.

The cost is that `sim_registry` and the promotion board read `shadow.db` only, so MGC will not
appear on the dashboard until that is deliberately extended. A display gap is the right trade
against a silent 5x pricing error.

★★ THE THREE OTHER THINGS THAT DIFFER FROM THE MNQ INSTANCE, each of which fails SILENTLY if missed:

  1. `symbol="MGC"` — the shared MD stream is multi-symbol and the run loop drops every bar whose
     tag does not match. An MGC slate on the MNQ instance sees no gold bar, ever, and records
     nothing without erroring.
  2. `depth=DepthFeed("MGC")` — the level-break gates need the order book, which is not on Features
     and not on the bar stream. Gold's L2 lives ONLY in `depth.db`; `capture.db.book` is MNQ-only.
     Without the feed the gates fail closed and record nothing.
  3. `extras=False` — the session breaker and FootprintShadow are MNQ-specific (the footprint reads
     capture.db's tick+book loop, which has no MGC depth at all).

★ COSTS ARE GOLD'S, NOT MNQ'S: $10.00/point and $7.50 per round trip. The fee is spread-inclusive —
the desk crosses on BOTH legs (marketable-limit IOC in, MKT out) at a 0.30pt median spread. Gold's R
is $11-26, so the spread is a quarter to a half of R. Every gold number printed before 2026-08-15
used a fifth of the true cost; applying it killed the coil bouncer outright (+$470 -> -$454).
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

from .depthfeed import DepthFeed
from .levelbreak import MGC_VPP  # noqa: F401
from .shadow import mgc_slate, run

SYMBOL = "MGC"
STORE = "data/shadow_mgc.db"

# ★★★2026-08-15 AUDIT FIX #1 — THE GATE COULD NEVER FIRE, AND NOTHING WOULD HAVE SAID SO.
# RunConfig.bar_lookback defaults to 60 and MinuteBars is a deque with maxlen=60, so bars() returns
# AT MOST 60 completed bars. detect_break(look_min=60) needs 61: sixty to build the level plus the
# signal bar that breaks it. `len(closes) < 61` against a hard ceiling of 60 is unsatisfiable —
# off by exactly one, permanently, silently. shadow_mgc.db would have held zero rows forever, which
# is failure mode #2 of this build's own scope.
# 120 gives the 61 the gate needs plus headroom for the ATR-14 warm-up.
# ⚠ SIDE EFFECT, deliberate and harmless HERE: compute_features' _vwap() spans the WHOLE deque, so
# vwap / vwap_slope_atr / ext_atr are now computed over 120 bars rather than 60 on this instance.
# gate_level_break reads only highs/lows/closes and ATR-14 (a tail-14 statistic), so none of the
# affected fields reach these gates. Do NOT copy this lookback to a VWAP-based gate without
# re-measuring it.
BAR_LOOKBACK = 120

# ★★2026-08-15 AUDIT FIX #5 — THE SPREAD WAS BEING CHARGED TWICE.
# repricer.py fills the entry at the far touch AND exits at the far touch, so the round-trip spread
# is ALREADY inside `gross` before any fee is applied. Subtracting MGC_FEE_RT ($7.50 = $6.00 of
# spread + $1.50 commission) then charges the spread a second time: $6.00/trade, which is 31% of the
# LONG cell's edge and 40% of the SHORT's, in the direction that makes a winner look dead.
# The research's own `true_pnl` is crossed fills MINUS $1.50, and that is where +$1,387 / +$19.27
# come from. So the REPRICER gets commission only.
# ⚠ MGC_FEE_RT ($7.50) remains correct for any harness that fills at the MID and must add the spread
# itself. The two constants are not interchangeable — which is why they are named apart.
REPRICER_FEE_RT = 1.50


def mgc_cfg(base=None):
    """Gold's config: its own symbol, its own multiplier, its own fee, its own store."""
    from .config import RunConfig
    return replace(base or RunConfig(), symbol=SYMBOL, value_per_point=MGC_VPP,
                   fee_rt=REPRICER_FEE_RT, shadow_store_path=STORE,
                   bar_lookback=BAR_LOOKBACK)


async def main_async(max_seconds: float | None = None) -> None:
    cfg = mgc_cfg()
    feed = DepthFeed(SYMBOL)
    try:
        await run(cfg, variants=mgc_slate(), depth=feed, extras=False,
                  max_seconds=max_seconds)
    finally:
        feed.close()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
