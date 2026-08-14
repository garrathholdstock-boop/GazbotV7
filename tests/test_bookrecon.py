"""BOOK vs FILLS — the ledger measured against what IBKR actually executed.

★★★2026-08-14. Nothing had ever compared the two, and they were wrong together twice: 08-13's
+$1,551 of profit from orders that sold 8 lots the desk did not own (against a real −$794 that went
unbooked), and 08-14's rider booking a COMPUTED exit price 0.75pt off the fill.

Most of what follows pins what the check must REFUSE to answer. A reconciliation that scores an
unverifiable day as clean is worse than none.
"""
from gazbot7.bookrecon import (
    KNOWN,
    RIDER,
    TOURNAMENT,
    build,
    desk_of_fill,
    desk_of_trade,
    reconcile,
)

D = "2026-08-14"


def _t(day, gate, pnl, dq=None):
    return (day, gate, pnl, dq)


def _f(day, oid, side, qty, price):
    return (day, oid, side, qty, price)


# a clean 2-lot short round trip: sold 30194.25, bought 30084.25 -> 110pt x 2 x $2 = $440 gross
RT = [_f(D, "rider-73", "SELL", 2, 30194.25), _f(D, "rider-78", "BUY", 2, 30084.25)]
RT_NET = 440.00 - 2 * 1.50          # $437.00


def _one(trades, fills):
    (v,) = reconcile(trades, fills)
    return v


def test_a_matching_book_reconciles_to_zero():
    v = _one([_t(D, "day_rider", RT_NET)], RT)
    assert v.status == "OK" and v.divergence == 0.0 and v.venue == 437.00
    assert not v.is_fault


def test_the_real_0814_divergence_is_caught():
    """The rider booked its exit at 30085.00 against a fill of 30084.25 — $3 of a $437 trade. Small,
    but it is the ONLY signal that the ledger records an intended price rather than an executed one,
    and in a fast market the same bug is not small."""
    v = _one([_t(D, "day_rider", 434.00)], RT)
    assert v.status == "DIVERGENT" and v.divergence == -3.00 and v.is_fault


def test_a_day_with_no_fills_REFUSES_rather_than_passing():
    """Every rider day before 08-14 has trades and no executions. Scoring those as clean would be
    the instrument-reports-healthy-about-what-it-never-checks failure, in the one place it has
    already cost money."""
    v = _one([_t("2026-08-12", "day_rider", 224.50)], [])
    assert v.status == "NO_FILLS" and v.is_unverifiable and not v.is_fault
    assert v.venue is None and v.divergence is None, "must not invent a venue number"


def test_a_day_ending_with_an_open_position_REFUSES():
    """Realised-from-fills is not comparable to booked P&L when half the round trip is in another
    day. One guard covers both a carried position and a trade straddling midnight."""
    v = _one([_t(D, "day_rider", 100.0)], [_f(D, "rider-73", "SELL", 2, 30194.25)])
    assert v.status == "OPEN_POSITION" and v.is_unverifiable and not v.is_fault
    assert v.venue is None and v.divergence is None


def test_flagged_rows_are_counted_against_the_venue_not_dropped():
    """★ THE BUG THE FIRST VERSION HAD. Flagged rows are flagged, NEVER deleted — their executions
    are still in `fills`. Measuring only the REPORTED P&L against ALL fills manufactures a
    divergence exactly equal to the flagged amount. It would have fired on 08-04, whose two
    md_stream rows total −$255.50."""
    trades = [_t(D, "day_rider", 200.00), _t(D, "day_rider", 237.00, "EXCLUDE:whatever")]
    v = _one(trades, RT)
    assert v.status == "OK", f"flagged rows manufactured a divergence: {v.detail}"
    assert v.booked == 200.00, "the REPORTED figure must stay reported-only"
    assert "flagged" in v.detail, "…but the exclusion must be visible, never silent"


def test_crossdesk_rows_belong_to_the_rider():
    """★ CAUGHT BY THE CHECK ITSELF. An exact `gate == 'day_rider'` test filed 08-06's two
    `day_rider_crossdesk` rows under the TOURNAMENT, whose fills they are not — producing a −$95.50
    tournament 'divergence' (exactly their sum) on a day the tournament's 24 fills reconcile to the
    cent. Misattribution reads as a fault in innocent code."""
    assert desk_of_trade("day_rider_crossdesk") == RIDER
    assert desk_of_trade("day_rider") == RIDER
    assert desk_of_trade("grind_long") == TOURNAMENT
    assert desk_of_trade("abs_veto_short_A") == TOURNAMENT
    assert desk_of_trade(None) == TOURNAMENT


def test_fills_are_attributed_by_order_id_prefix():
    assert desk_of_fill("rider-73") == RIDER
    assert desk_of_fill("v7-mnq-001018") == TOURNAMENT
    assert desk_of_fill("stp-000003") == TOURNAMENT
    assert desk_of_fill("") == TOURNAMENT


def test_the_two_desks_are_reconciled_separately():
    """They share one netted account, so a combined total could hide equal and opposite errors."""
    vs = {v.desk: v for v in reconcile(
        [_t(D, "day_rider", 434.00), _t(D, "grind_long", 58.50)],
        RT + [_f(D, "v7-mnq-1", "BUY", 1, 30000.0), _f(D, "v7-mnq-2", "SELL", 1, 30030.0)])}
    assert vs[RIDER].status == "DIVERGENT" and vs[RIDER].divergence == -3.00
    assert vs[TOURNAMENT].status == "OK"


def test_a_ruled_on_divergence_is_not_a_fault():
    day, (amount, _why) = "2026-08-13", KNOWN[("2026-08-13", RIDER)]
    fills = [_f(day, "rider-1", "BUY", 2, 30000.00), _f(day, "rider-2", "SELL", 2, 30000.00)]
    v = _one([_t(day, "day_rider", -amount + (-2 * 1.50))], fills)
    assert v.status == "KNOWN" and not v.is_fault
    assert "RULING" in v.note.upper()


def test_a_ruling_stops_covering_it_once_the_AMOUNT_MOVES():
    """Same principle as the notify dedupe signature: a known state stays quiet, a CHANGE is news. A
    registry keyed only on (day, desk) would swallow a second, unrelated fault on the same day."""
    day = "2026-08-13"
    fills = [_f(day, "rider-1", "BUY", 2, 30000.00), _f(day, "rider-2", "SELL", 2, 30000.00)]
    v = _one([_t(day, "day_rider", -900.00)], fills)
    assert v.status == "DIVERGENT" and v.is_fault
    assert "CHANGED" in v.detail


def test_side_spellings_from_both_sources_agree():
    """`fills` stores BUY/SELL; IBKR speaks BOT/SLD. Getting this backwards flips the sign of every
    reconciliation, which would look like a catastrophic divergence rather than a parsing bug."""
    a = build([], [_f(D, "rider-1", "SELL", 2, 30194.25), _f(D, "rider-2", "BUY", 2, 30084.25)])[0]
    b = build([], [_f(D, "rider-1", "SLD", 2, 30194.25), _f(D, "rider-2", "BOT", 2, 30084.25)])[0]
    assert a.gross == b.gross == 440.00 and a.residual == b.residual == 0.0


def test_the_fee_model_is_150_per_round_trip():
    dd = build([], RT)[0]
    assert dd.gross == 440.00
    assert dd.venue == 437.00, "2 contracts = 1 round trip per side -> $3.00, never $5"


def test_mgc_can_be_reconciled_at_its_own_multiplier():
    """Gold is $10/pt. A shared $2 constant would under-report a gold divergence 5x."""
    fills = [_f(D, "rider-1", "SELL", 1, 3050.0), _f(D, "rider-2", "BUY", 1, 3040.0)]
    (v,) = reconcile([_t(D, "day_rider", 98.50)], fills, vpp=10.0)
    assert v.venue == 98.50 and v.status == "OK"
