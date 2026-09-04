"""The rider must book the exit price THE VENUE GAVE IT, not the one it was looking at.

★★★2026-08-14. Every close path placed its order, slept 2s, and booked `px` — the current market
price — as the exit. On 08-14 that recorded 30085.00 against a fill of 30084.25: $3 of a $437 trade.
It was invisible until `fills` started being captured that same day
([[day-rider-fills-gap-closed]]), and it is unbounded — a market order into a gap can fill points
away from the last print.

The ENTRY side always did this correctly. These pin that both sides of a round trip are now sourced
the same way.
"""
import asyncio

from gazbot7 import day_rider as dr


class _Status:
    def __init__(self, status="Filled", avg=0.0):
        self.status, self.avgFillPrice = status, avg


class _Trade:
    def __init__(self, status="Filled", avg=0.0):
        self.orderStatus = _Status(status, avg)


def _run(tr, fallback=30085.00, **kw):
    out = {}
    px = asyncio.run(dr.await_fill(tr, fallback, what="TRAIL exit", out=out, **kw))
    return px, out


def test_the_venue_fill_price_wins():
    """The exact 08-14 case: booked 30085.00, filled 30084.25."""
    px, out = _run(_Trade("Filled", 30084.25))
    assert px == 30084.25, "booked the market price instead of the fill"
    assert out["exit_px_source"] == "fill"


def test_a_partial_average_is_used_whole():
    """avgFillPrice is the right field for a 2-lot order filling in pieces — the average IS the
    round-trip price."""
    px, _ = _run(_Trade("Filled", 30084.625))
    assert px == 30084.625


def test_it_falls_back_rather_than_refusing_to_book():
    """Refusing to book a trade we really made would be worse than booking it a tick off — a missing
    row silently corrupts every future study. But the fallback must be RECORDED and must PAGE."""
    sent = []
    px, out = _run(_Trade("Submitted", 0.0), notify=lambda m, **k: sent.append((m, k)))
    assert px == 30085.00
    assert out["exit_px_source"] == "FALLBACK:market"
    assert sent and sent[0][1].get("critical") is True, "a silent fallback re-introduces the bug"
    assert "book-vs-fills" in sent[0][0]


def test_a_garbled_fill_price_falls_back_and_does_not_raise():
    for bad in (None, "", "not-a-number"):
        px, out = _run(_Trade("Filled", bad))
        assert px == 30085.00 and out["exit_px_source"] == "FALLBACK:market"


def test_a_negative_or_zero_price_is_never_booked():
    """The V5 VCORR scar: a synthetic px=0 execution must never reach the ledger."""
    for bad in (0.0, -1.0):
        px, _ = _run(_Trade("Filled", bad))
        assert px == 30085.00


def test_every_close_path_books_the_fill_not_the_market_price():
    """A source-level guard, because this bug is INVISIBLE in behaviour until you have fills to
    compare against — which is exactly why it survived from 08-05 to 08-14."""
    import inspect
    src = inspect.getsource(dr)
    # CLOSED_ELSEWHERE is the one legitimate exception: someone else's execution, not ours to read.
    offenders = [ln.strip() for ln in src.splitlines()
                 if "book_trade(out, px," in ln and "CLOSED_ELSEWHERE" not in ln]
    assert not offenders, f"a close path still books the market price: {offenders}"
    assert 'book_trade(out, px, "CLOSED_ELSEWHERE"' in src, "the documented exception vanished"
    assert src.count("await await_fill(") == 6, (
        "expected 6 await_fill sites — the fill-sourced CLOSE paths.\n"
        "★2026-08-20 there was a SEVENTH: the operator's MANUAL BUY/SELL, an entry rather than a "
        "close, using await_fill for the same reason the closes do — book the FILL, never the "
        "market price.\n"
        "★2026-09-04 that site moved to place_entry(), which sources the same `avgFillPrice` and "
        "additionally returns the FILLED QUANTITY, because entries are now marketable LIMITS and a "
        "limit can partial-fill (SESSIONS §387). The property this test defends is unchanged and is "
        "re-asserted below for both entry paths. If this count changes again, check whether the new "
        "site is an entry or a close before touching the number.")
    # ★ THE ENTRY PATHS STILL BOOK THE FILL — now via place_entry, and they book its QUANTITY too.
    assert src.count("await place_entry(") == 2, "both entry sites must go through place_entry"
    assert "avgFillPrice" in src[src.index("async def place_entry"):src.index("async def do_manual_entry")], (
        "place_entry must source the price from the venue's avgFillPrice, not the market price")
