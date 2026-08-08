"""CADENCE — the one place the desk decides how fast it is allowed to see things.

Operator, 2026-08-03: "Friday backtests, shadow desk and live desk should absolutely be the same.
If they are not, we are lying to ourselves."

He is right, and before this module the desk had THREE different answers:

    live desk        1s      md.py publishes T_TAPE every tape_interval_s=1.0
    shadow desk      1 MINUTE  ShadowSim.on_bars runs off the 1-minute aggregator — 60x coarser
    Friday scripts   250ms ticks / 5s bars / paired-overlap, chosen per script

So the shadow book — the thing used as ground truth for whether a stay-out call was right — was not
measuring the desk we actually run. And NIPC's lab number survived two rounds of validation while
being wrong, partly because its replay drove the tracker at raw tick rate against production's 1s.

★ THE RULE, AND WHY IT IS NOT A SINGLE NUMBER.

    DECISIONS / ENTRIES  ->  DECISION_MS (1000)
    STOPS / TARGETS / EXITS -> EXEC_MS (250)

These differ on purpose, because reality is asymmetric:

  * We can only ENTER when we look. A backtest that fills an entry at a level observed only in the
    raw tick stream is assuming precision the desk does not have — it polls once a second and sees a
    SNAPSHOT, never the extremes traversed in between. Modelling entries at 250ms flatters us.
  * We get STOPPED whether we look or not. The protective STP rests at the venue and triggers on any
    tick. Modelling exits at 1s HIDES real losses — exactly the effect measured at 5s, where 87% of
    flushes vanished against a 250ms baseline ([[backtest-on-5s-250ms-persist-all]]).

Unify everything at 1s and we are optimistic on the loss side. Unify at 250ms and we are optimistic
on the entry side. Both lie; they just lie in opposite directions. The honest rule is to model each
side at the resolution reality imposes on it, and to apply that rule identically everywhere.

WHY NOT JUST MAKE THE DESK FASTER: measured 2026-08-03 on NIPC, the most tick-sensitive gate we own,
going from raw ticks to 1s cost ~11% ($375 -> $334). Against that: engineering, CPU, new failure
surface, and a robust NULL on 22.6M ticks saying run starts are unpredictable at microstructure scale
([[run-catcher-null-all-microstructure]]). Fix the measurement, not the speed.

USAGE
    from gazbot7.cadence import DECISION_MS, EXEC_MS, downsample, describe
    prints = downsample(raw_ticks, DECISION_MS)   # what the desk would actually have SEEN
    # ... but race stops/targets over the RAW ticks, not the downsampled ones.
"""
from __future__ import annotations

DECISION_MS = 1000    # matches md.py tape_interval_s=1.0 — what the desk can act on
EXEC_MS = 250         # matches capture's tick cadence — what the venue does to us
BAR_S = 5             # the finest bar the desk stores (capture.db timeframe='5s')


def downsample(prints, every_ms: int = DECISION_MS):
    """Reduce a (ts_ms, price) stream to the LAST print in each bucket — which is precisely what a
    poll at that interval observes. Not the mean, not the extreme: a poll sees whatever the tape
    happened to be showing at that instant.

    Use for ENTRY/DECISION logic only. Racing a stop over downsampled prints is the bug this module
    exists to prevent: it silently deletes the intra-bucket excursion that would really have hit you.
    """
    if not every_ms:
        return list(prints)
    buckets: dict[int, tuple] = {}
    for ts, px in prints:
        buckets[int(ts) // every_ms] = (int(ts), float(px))
    return [buckets[k] for k in sorted(buckets)]


def describe() -> str:
    return (f"decisions/entries {DECISION_MS}ms (live md.py tape_interval_s) · "
            f"stops/targets {EXEC_MS}ms (venue tick) · bars {BAR_S}s")


def assert_matches_live(decision_ms: int, exec_ms: int) -> None:
    """Call from a sim's setup so a harness that quietly disagrees with the desk fails loudly rather
    than producing a number nobody can compare to anything."""
    if (decision_ms, exec_ms) != (DECISION_MS, EXEC_MS):
        raise ValueError(
            f"cadence mismatch: this harness runs decisions@{decision_ms}ms exits@{exec_ms}ms but the "
            f"live desk is decisions@{DECISION_MS}ms exits@{EXEC_MS}ms. Either fix the harness or "
            f"change gazbot7.cadence deliberately — do not let them drift.")
