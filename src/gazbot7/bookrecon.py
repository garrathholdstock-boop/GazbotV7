"""BOOK vs FILLS — does our P&L match what the venue actually executed?

★★★2026-08-14. `trades` is what we BELIEVE happened; `fills` is what IBKR SAYS happened. Until now
nothing compared them, and the two have been wrong together twice:

* **08-13** the ledger carried +$1,551 of profit from four orders that sold 8 lots the desk did not
  own, and omitted the −$794 those orders really cost. Book +$768.50 against a venue of −$25.50.
* **08-14** the rider booked its exit at 30085.00 when the fill was 30084.25 — $3 of a $437 trade,
  because it records a COMPUTED exit price rather than the executed one.

Neither was detectable from the ledger alone. That is the whole point of this module:
[[ibkr-is-truth-never-trust-our-books]] is only enforceable if something actually checks.

## The unit of comparison is (desk, day), and why

Per-trade matching is not possible for the tournament: it runs up to two slots concurrently against a
NETTED venue, so a single fill can belong to either slot and the venue cannot say which. Per
desk-per-day is the finest slice that is unambiguous — and it is exactly the reconciliation that was
done by hand on 08-13 and 08-14.

## What it REFUSES to answer, which is the important part

A check that returns "no divergence" on a day it could not actually verify is worse than no check —
it is [[an-instrument-that-reports-healthy-about-something-it-does-not-check]]. So:

* **`NO_FILLS`** — the desk booked trades but has no execution record for that day. This is the
  normal state for every rider day BEFORE 08-14 (see [[day-rider-fills-gap-closed]]): 1,437 fills
  going back to 07-16 and not one was the rider's. Those days are permanently unverifiable and must
  say so rather than score as clean.
* **`OPEN_POSITION`** — the day's fills do not net to flat, so the desk carried a position across the
  boundary. Realised-from-fills is then not comparable to booked P&L at all, because part of the
  round trip is in another day. One guard covers both the carried-position case and a trade that
  straddles midnight.

Only a desk-day that is flat AND has fills gets a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VPP = 2.0                       # MNQ $/point. MGC is $10 — pass it in when gold goes live.
FEE_RT = 1.50                   # venue truth over 487 fills; NEVER $5 [[mnq-fee-is-150-per-round-trip]]
CENT = 0.005                    # float-noise floor; below this two numbers are the same number

RIDER = "rider"
TOURNAMENT = "tournament"


# ★★ DIVERGENCES WE HAVE RULED ON. Keyed (day, desk) -> (amount, why).
#
# An entry here means "this exact gap is expected and is not a fault". It is matched on the AMOUNT to
# the cent: if the number moves, it stops matching and alarms again. That is deliberate and is the
# same principle as the notify dedupe signature — a known state stays quiet, a CHANGE is news. A
# registry keyed only on (day, desk) would swallow a second, unrelated fault on the same day.
KNOWN: dict[tuple[str, str], tuple[float, str]] = {
    ("2026-08-13", RIDER): (
        794.00,
        "OPERATOR RULING 2026-08-14: the naked-8-lot cost was a broken order loop, not a trading "
        "decision, and is deliberately NOT booked — the ledger is a STRATEGY book and excludes bug "
        "losses by design. Do not add a correcting row. See docs/SESSION_2026-08-13.md.",
    ),
}


@dataclass
class DeskDay:
    """One desk's trading on one UTC day, from both sides of the mirror."""

    day: str
    desk: str
    booked: float = 0.0             # sum of trades.pnl_usd over UNFLAGGED rows — what we REPORT
    flagged: float = 0.0            # sum over data_quality-flagged rows — recorded but not reported
    n_trades: int = 0
    n_flagged: int = 0
    gross: float = 0.0              # from fills: sell proceeds - buy cost, in dollars
    contracts: float = 0.0          # total contracts transacted (both directions)
    residual: float = 0.0           # net position left at day end, from fills
    n_fills: int = 0
    fee_rt: float = FEE_RT

    @property
    def venue(self) -> float:
        """Realised P&L implied by the executions, net of our fee model."""
        return round(self.gross - (self.contracts / 2.0) * self.fee_rt, 2)

    @property
    def recorded(self) -> float:
        """Our FULL execution record: reported P&L plus the rows we recorded but excluded.

        ★★ THIS, not `booked`, is what compares to the venue. Flagged rows are flagged, NEVER
        deleted — their executions are still in `fills`, so measuring reported-P&L against ALL fills
        manufactures a divergence exactly equal to the flagged amount. The first version of this
        module had that bug and it would have fired on 2026-08-04, whose two
        `EXCLUDE:md_stream_atr_corruption_20260804` rows total −$255.50.

        The two questions are different and both matter:
          · `recorded` vs venue → INTEGRITY: does our execution record match what IBKR executed?
          · `booked`            → what we report as P&L, after rulings and exclusions.
        This module answers the first. `booked` and `flagged` are carried so the second is never
        confused with it.
        """
        return round(self.booked + self.flagged, 2)

    @property
    def divergence(self) -> float:
        """recorded − venue. Positive = our record claims more than the venue actually paid."""
        return round(self.recorded - self.venue, 2)


@dataclass
class Verdict:
    day: str
    desk: str
    status: str                     # OK | DIVERGENT | KNOWN | NO_FILLS | OPEN_POSITION
    booked: float
    venue: float | None
    divergence: float | None
    detail: str
    note: str = ""
    context: dict = field(default_factory=dict)

    @property
    def is_fault(self) -> bool:
        """Only an UNEXPLAINED divergence is a fault.

        `NO_FILLS` and `OPEN_POSITION` are honest refusals, not faults — they are surfaced so nobody
        reads them as clean, but they must not page. `KNOWN` is a ruling.
        """
        return self.status == "DIVERGENT"

    @property
    def is_unverifiable(self) -> bool:
        return self.status in ("NO_FILLS", "OPEN_POSITION")


def judge(dd: DeskDay) -> Verdict:
    """Turn one desk-day into a verdict. Pure — no I/O, no clock."""
    base = dict(day=dd.day, desk=dd.desk, booked=round(dd.booked, 2))
    flag = (f" (+${dd.flagged:,.2f} in {dd.n_flagged} flagged row(s), recorded but not reported)"
            if dd.n_flagged else "")

    if dd.n_fills == 0:
        return Verdict(
            **base, venue=None, divergence=None, status="NO_FILLS",
            detail=(f"{dd.n_trades} trade(s) booked, NO execution record — cannot be verified{flag}"),
            note=("Normal for every day-rider day before 2026-08-14; its fills were never captured. "
                  "IBKR's reqExecutions reaches back only ~24h, so these days are permanently "
                  "unverifiable. NOT a clean bill of health."),
            context={"n_trades": dd.n_trades},
        )

    if abs(dd.residual) > 1e-9:
        return Verdict(
            **base, venue=None, divergence=None, status="OPEN_POSITION",
            detail=(f"fills net to {dd.residual:+g}, not flat — the round trip crosses the day "
                    f"boundary, so realised-from-fills is not comparable to booked P&L"),
            note="Re-check once the position closes; the day it closes carries the whole round trip.",
            context={"residual": dd.residual, "n_fills": dd.n_fills},
        )

    div = dd.divergence
    known = KNOWN.get((dd.day, dd.desk))
    if known is not None and abs(abs(div) - known[0]) <= CENT:
        return Verdict(
            **base, venue=dd.venue, divergence=div, status="KNOWN",
            detail=f"divergence ${div:+,.2f} is a ruled-on exception, not a fault",
            note=known[1], context={"n_fills": dd.n_fills},
        )

    if abs(div) <= CENT:
        return Verdict(
            **base, venue=dd.venue, divergence=div, status="OK",
            detail=f"record matches the venue (${dd.venue:,.2f}) across {dd.n_fills} fills{flag}",
            context={"n_fills": dd.n_fills},
        )

    extra = ""
    if known is not None:
        # The amount moved off the ruling — that is NEWS, not a covered exception.
        extra = (f" ⚠ a ruling exists for this desk-day at ${known[0]:,.2f} but the divergence is now "
                 f"${abs(div):,.2f} — the gap CHANGED, so it is no longer covered.")
    return Verdict(
        **base, venue=dd.venue, divergence=div, status="DIVERGENT",
        detail=(f"record ${dd.recorded:,.2f} vs venue ${dd.venue:,.2f} — divergence ${div:+,.2f} "
                f"across {dd.n_fills} fills{flag}{extra}"),
        note=("record > venue means we recorded profit the venue did not pay. Check the booked exit "
              "price against the closing fill first: the rider records a COMPUTED exit, not the "
              "executed one (08-14: booked 30085.00, filled 30084.25)."),
        context={"n_fills": dd.n_fills, "n_trades": dd.n_trades},
    )


def desk_of_fill(order_id: str) -> str:
    """Which desk placed this execution?

    The rider's rows are written by `day_rider.record_own_fills` with a `rider-<orderId>` prefix
    precisely so this is unambiguous; everything else (`v7-mnq-*`, `stp-*`) is the tournament's.
    """
    return RIDER if (order_id or "").startswith("rider-") else TOURNAMENT


def desk_of_trade(gate: str) -> str:
    """Which desk booked this trade?

    ★★ PREFIX, not equality — and the check itself caught this. An exact `== "day_rider"` test filed
    the two `day_rider_crossdesk` rows of 2026-08-06 under the TOURNAMENT, whose fills they are not
    (they are the rider's cross-desk flatten, clientId 4, and the rider had no fills before 08-14).
    That produced a −$95.50 "tournament divergence" — exactly their sum — on the one day the
    tournament's own 24 fills reconcile to the cent. A misattribution reads as a fault in innocent
    code, which is the most expensive kind of false alarm.

    Any `day_rider*` gate is the rider's. Today that is `day_rider` and `day_rider_crossdesk`.
    """
    return RIDER if (gate or "").startswith("day_rider") else TOURNAMENT


def build(trade_rows, fill_rows, *, vpp: float = VPP, fee_rt: float = FEE_RT) -> list[DeskDay]:
    """Fold raw rows into desk-days.

    `trade_rows`: (day, gate, pnl_usd, data_quality) — pass ALL rows, flagged included; this
                  module needs both sides to compare our full record against the venue.
    `fill_rows` : (day, order_id, side, qty, price)
    """
    out: dict[tuple[str, str], DeskDay] = {}

    def slot(day, desk):
        return out.setdefault((day, desk), DeskDay(day=day, desk=desk, fee_rt=fee_rt))

    for day, gate, pnl, dq in trade_rows:
        d = slot(day, desk_of_trade(gate))
        if dq is None:
            d.booked += float(pnl or 0.0)
            d.n_trades += 1
        else:
            d.flagged += float(pnl or 0.0)
            d.n_flagged += 1

    for day, order_id, side, qty, price in fill_rows:
        d = slot(day, desk_of_fill(order_id))
        sign = 1.0 if str(side).upper() in ("SELL", "SLD") else -1.0
        d.gross += sign * float(price) * float(qty) * vpp
        d.residual += -sign * float(qty)
        d.contracts += float(qty)
        d.n_fills += 1

    return [out[k] for k in sorted(out)]


def reconcile(trade_rows, fill_rows, *, vpp: float = VPP, fee_rt: float = FEE_RT) -> list[Verdict]:
    return [judge(d) for d in build(trade_rows, fill_rows, vpp=vpp, fee_rt=fee_rt)]
