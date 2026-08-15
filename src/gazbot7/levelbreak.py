"""MGC LEVEL-BREAK — the gold 2x2 trigger, split by what the order book is standing on.

Built 2026-08-15 from the `gf_MGC` greenfield hunt. Two survivors, both SHADOW-only:

    mgc_holebreak_fade_long   60m level break DOWN into a liquidity hole -> BUY    n=72  +$1,387
    mgc_holebreak_fade_short  60m level break UP   into a liquidity hole -> SELL   n=85  +$1,261

priced at the TRUE gold cost of $7.50/RT (see `MGC_COST` below), and passing strip-best-3,
leave-one-day-out, a July out-of-sample leg and a 0-of-30 placebo.

★★ WHY THIS IS NOT THE REFUTED L2 ATTACK. That one asked the book, at an arbitrary moment, WHICH WAY
price would go — and it flipped sign across five disjoint samples. This asks the book nothing about
direction: **the break has already chosen the side.** It asks only whether that side will HOLD. That
is a liquidity question, and liquidity is the one thing an order book genuinely knows.

    obstacle = lots resting within `band` BEYOND the level, in the break's path
    support  = lots resting within `band` BEHIND the level, to catch a failure

    VACUUM   obstacle == 0        49% of breaks   -> FADE it    (+$12.47/trade)
    WALL     obstacle > support   14% of breaks   -> FOLLOW it  (+$11.84/trade)
    neither                       37% of breaks   -> TRADE NOTHING

That last row is a finding, not a gap: both directions lose when the book has no opinion.

★★ GOLD'S BOOK IS THIN ENOUGH FOR THIS TO BE VISIBLE — the median size resting within a point of a
break level is ONE LOT. A break either clears what is there or it does not. In MNQ depth the same
mechanic washes out.

⚠ COST. A gold round trip is $4.50 from mid, not $1.50: the desk enters marketable-limit IOC
(crosses) and exits MKT (crosses again), so the round trip pays the 0.30pt median spread ONCE —
0.15pt above mid in, 0.15pt below mid out = $3.00 — plus $1.50 commission. Gold's
R is $11-26, so the spread is a fifth to a quarter of R. Every gold number printed before 2026-08-15
used commission only, which understates the true cost by $3.00 a trade.
NEVER copy MNQ's $1.50 into a gold config that prices from mid.

⚠ RESOLUTION. This was built ON `depth.db`, a 250ms sample — MGC has no 41ms feed and there is no
free IBKR depth subscription. So shadow tests whether it holds FORWARD IN TIME; it cannot test
whether it holds at finer resolution. In a liquidity hole — precisely the state this gate selects
for — the touch may be further away than the last sample said.
"""

from __future__ import annotations

from dataclasses import dataclass

MGC_VPP = 10.0          # $ per point. NOT MNQ's 2.0.
# ★★2026-08-15 CORRECTED 7.50 -> 4.50 (audit #9). Crossing a 0.30pt spread costs 0.30pt PER ROUND
# TRIP — 0.15 above mid entering, 0.15 below mid exiting — i.e. $3.00, not $6.00. The report and the
# first scope wrote 0.30 x 2 x $10 and counted the spread twice. The LAB never made this error: its
# own note reads "MGC's spread is a flat ~0.30pt = $3.00", and its true_pnl crosses real fills and
# then subtracts commission only, which is why +$1,387 / +$1,261 are unaffected.
# ⚠ CONSEQUENCE OF THE ERROR: the coil bouncer was declared DEAD at $7.50 (-$454). At the true $4.50
# it is +$8.42, +$0.05/trade — breakeven, on the line, not refuted.
MGC_FEE_RT = 4.50       # $ per round trip from MID: $3.00 of spread + $1.50 commission.
LEVELS = 10             # depth_snap carries bid1..bid10 / ask1..ask10


@dataclass(frozen=True, slots=True)
class BookSide:
    """Resting size near a level, split by which side of the break it sits on."""

    obstacle: float     # in the break's path
    support: float      # behind the level, catching a failure


def band_size(book: dict, side: str, level: float, band: float) -> float:
    """Lots resting within `band` points of `level`, on `side` ("bid" | "ask").

    ASK is counted UPWARD from the level ([level, level+band]) and BID DOWNWARD
    ([level-band, level]) — each side is only meaningful in the direction it defends.
    Missing or non-finite rungs are skipped rather than treated as zero size: an absent rung is
    unknown, and calling it empty would manufacture the VACUUM this gate trades on.
    """
    total = 0.0
    for k in range(1, LEVELS + 1):
        p, s = book.get(f"{side}{k}p"), book.get(f"{side}{k}s")
        if p is None or s is None:
            continue
        try:
            p, s = float(p), float(s)
        except (TypeError, ValueError):
            continue
        if not (p == p and s == s) or p <= 0:      # NaN guard + no synthetic zero-price rungs
            continue
        if side == "ask" and level <= p <= level + band:
            total += s
        elif side == "bid" and level - band <= p <= level:
            total += s
    return total


def read_book(book: dict, brk: int, level: float, band: float) -> BookSide:
    """Split the book into obstacle/support RELATIVE TO THE BREAK'S DIRECTION.

    An UP break runs into ASKS and would be caught by BIDS; a DOWN break the reverse. Getting this
    pair the wrong way round inverts the gate silently — it would still fire, just on the mirror
    condition — so it is asserted in tests rather than trusted.
    """
    far = "ask" if brk > 0 else "bid"
    near = "bid" if brk > 0 else "ask"
    return BookSide(obstacle=band_size(book, far, level, band),
                    support=band_size(book, near, level, band))


def detect_break(highs, lows, closes, atr: float, *, look_min: int, margin_atr: float):
    """Has the LAST bar closed beyond its own `look_min`-minute extreme by `margin_atr` x ATR?

    Returns (brk, level) with brk +1 up / -1 down, or None.

    ⚠ TWO LOOK-AHEADS ARE KILLED HERE AND BOTH HAVE BITTEN THIS DESK:
      1. The extreme is taken over bars STRICTLY BEFORE the signal bar. Including the signal bar's
         own high in its own break level is circular — it can then break a level it just set.
      2. The CALLER must stamp entry at the signal bar's CLOSE, not its label. A bar labelled 10:00
         does not close until 10:01; racing from the label replays the very minute the decision was
         made. That error cost the coil gate +$906 -> +$470 on 2026-08-14.
    """
    n = look_min + 1
    if len(closes) < n or not (atr > 0):
        return None
    prior_hi = max(highs[-n:-1])
    prior_lo = min(lows[-n:-1])
    c = closes[-1]
    if c >= prior_hi + margin_atr * atr:
        return 1, float(prior_hi)
    if c <= prior_lo - margin_atr * atr:
        return -1, float(prior_lo)
    return None


def gate_level_break(highs, lows, closes, atr: float, book: dict | None, *,
                     look_min: int = 60, margin_atr: float = 0.10, fade: bool = True,
                     book_band_pt: float = 1.0, obstacle_max: float | None = None,
                     support_max: float | None = None,
                     require_obstacle_gt_support: bool = False,
                     require_book: bool = True) -> str | None:
    """Return "LONG" / "SHORT" to trade, or None.

    `fade=True` trades AGAINST the break (the two surviving reversion cells); `fade=False` with it
    (the momentum control, thin and on probation).

    ⚠ NO BOOK MEANS NO TRADE. `book=None` returns None — it never falls back to a price-only
    decision. The book condition IS the gate: without it the same trigger is the plain extension
    trigger, which loses -$3.60 to -$5.49 a trade in EVERY cell and BOTH directions at the true cost.
    Failing open here would silently convert a tested edge into a known loser.

    `require_book=False` is the ONE exception and it exists for exactly one caller: the
    `mgc_break_fade_nobook` CONTROL arm, which must trade the bare trigger so the book cut can be
    ATTRIBUTED rather than assumed. It is a measuring instrument, not a candidate — it is expected to
    lose, and the two hole arms failing to beat it would refute the whole thesis. Never set it on a
    variant intended for promotion.
    """
    hit = detect_break(highs, lows, closes, atr, look_min=look_min, margin_atr=margin_atr)
    if hit is None:
        return None
    brk, level = hit
    if book is None:
        # The control arm still needs the trigger's direction, so it skips the book rather than
        # failing closed. Every other caller stops here.
        return ("LONG" if (-brk if fade else brk) > 0 else "SHORT") if not require_book else None
    if not require_book:
        return "LONG" if (-brk if fade else brk) > 0 else "SHORT"
    b = read_book(book, brk, level, book_band_pt)
    if obstacle_max is not None and b.obstacle > obstacle_max:
        return None
    if support_max is not None and b.support > support_max:
        return None
    if require_obstacle_gt_support and not (b.obstacle > b.support):
        return None
    side = -brk if fade else brk
    return "LONG" if side > 0 else "SHORT"
