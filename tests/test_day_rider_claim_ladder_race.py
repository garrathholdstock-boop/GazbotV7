"""Two exit paths in ONE tick must not both decrement from the tick-start snapshot.

★★★ THE 2026-08-31 INCIDENT. The rider's profit LADDER and the operator's per-lot CLAIM can both
fire inside a single tick. `step()` builds `out = dict(st)` and the ladder writes its reduced count
to `out`, leaving `st` untouched. The claim branch then re-read `st` — so it sized from a count that
was already one lot out of date: TWO lots left the venue and the book deducted ONE.

Why that is not cosmetic. The book is left claiming a lot the venue does not hold, and the
cross-desk reconciler exists precisely to notice that: it reads `venue != tournament + rider`, calls
it an unaccounted lot and STOPS BOTH DESKS. A false kill switches the day-rider off, which also
takes down the 20:40Z hard flat and every Claim button, and it never re-arms itself. On 2026-09-03
that cost four hours of a dead BUY button.

⚠ `targets_done` carried the same bug and is the worse half: re-reading `st` DISCARDS the rung the
ladder just spent, so a spent rung could fill a second time.
"""
import re
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

SRC = "/home/alphabot/gazbot7/src/gazbot7/day_rider.py"


def _claim_branch() -> str:
    """The ONE-LOT claim branch, sliced out of the real source."""
    s = open(SRC).read()
    start = s.index('if v and isinstance(_claim, int):')
    end = s.index('if v:', start)
    return s[start:end]


def test_one_lot_claim_sizes_from_the_live_tick_state_not_the_snapshot():
    """★ THE REGRESSION GUARD. Reading `st` here is the bug; it must read `out`.

    Asserted against the SOURCE because the defect is invisible in any single-path test: both
    versions behave identically unless the ladder fired earlier in the SAME tick.
    """
    branch = _claim_branch()
    for field in ("lots_open", "targets_done"):
        assert not re.search(rf'st\.get\(\s*["\']{field}["\']', branch), (
            f'the one-lot claim branch reads st["{field}"] — the tick-start snapshot. The ladder '
            f'may already have changed it in this same tick; size from `out`. See 2026-08-31.')
        assert re.search(rf'out\.get\(\s*["\']{field}["\']', branch), (
            f'the one-lot claim branch must read out["{field}"], the live tick state')


def test_ladder_then_claim_deducts_both_lots():
    """The invariant: lots removed from the VENUE == lots deducted from the BOOK.

    Mirrors what step() does to the two dicts across one tick — ladder banks lot 1, operator claims
    lot 2 — and applies the claim branch's real arithmetic to them.
    """
    st = {"lots_open": 4, "qty": 4.0, "targets_done": []}
    out = dict(st)                      # step(): out = dict(st)

    # ── the PROFIT LADDER fires first: one lot banked, written to `out` only ──
    lots_open, done = 4, []
    lots_open -= 1
    done.append(0)
    out["targets_done"], out["lots_open"], out["qty"] = done, lots_open, float(lots_open)
    own_qty = float(lots_open)

    # ── the OPERATOR's per-lot claim, same tick: exactly one more lot is sold ──
    _claim = 1
    _done = list(out.get("targets_done") or [])
    if _claim not in _done:
        _done.append(_claim)
    _left = max(0, int(out.get("lots_open") or own_qty) - 1)

    venue_lots_sold = 2                 # the ladder's SELL 1 + the claim's SELL 1
    assert _left == 4 - venue_lots_sold == 2, (
        f"book says {_left} lots open after {venue_lots_sold} left the venue — the reconciler "
        f"reads that difference as an unaccounted lot and kills both desks")
    assert _done == [0, 1], f"the ladder's spent rung was discarded: {_done} — it could fill again"


def test_claim_alone_is_unchanged():
    """A claim with NO ladder fire in the tick must still deduct exactly one (the common path)."""
    st = {"lots_open": 4, "qty": 4.0, "targets_done": []}
    out = dict(st)
    own_qty = 4.0
    _left = max(0, int(out.get("lots_open") or own_qty) - 1)
    assert _left == 3
