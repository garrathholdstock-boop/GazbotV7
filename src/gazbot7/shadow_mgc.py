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
from .levelbreak import MGC_FEE_RT, MGC_VPP
from .shadow import mgc_slate, run

SYMBOL = "MGC"
STORE = "data/shadow_mgc.db"


def mgc_cfg(base=None):
    """Gold's config: its own symbol, its own multiplier, its own fee, its own store."""
    from .config import RunConfig
    return replace(base or RunConfig(), symbol=SYMBOL, value_per_point=MGC_VPP,
                   fee_rt=MGC_FEE_RT, shadow_store_path=STORE)


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
