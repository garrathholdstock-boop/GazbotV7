"""The manual BUY path must PLACE AN ORDER. Executed, not imported.

★2026-08-21 WHY THIS EXISTS. Extracting do_manual_entry() destroyed its body — the helper was
reduced to a refusal and a `return True`. The file still parsed, still imported, and every other
test stayed green, because nothing in the suite ever RAN it. The button would have reported
"BUY 4 lots requested" to the operator and then silently done nothing, on a live desk, with no
error anywhere. `assert "MarketOrder" in src` does not catch that either — a string can sit in a
branch that never executes.

So this test drives the helper with fakes and asserts the ORDER REACHED THE VENUE.
"""
import asyncio, datetime as dt, types, pytest
from gazbot7 import day_rider as D


class FakeIB:
    """★2026-09-04 the fake trade now carries a real `orderStatus`. Entries go in as marketable
    LIMITS (SESSIONS §387: the paper engine fabricated a 0.1% adverse fill), and place_entry reads
    `filled`/`avgFillPrice` to book what the VENUE gave rather than what was asked for. A stub
    without those fields would fail the test for the wrong reason and hide whether the entry works."""

    def __init__(self, filled=4, avg=23000.0):
        self.orders, self.cancelled = [], []
        self._filled, self._avg = filled, avg

    def placeOrder(self, contract, order):
        self.orders.append((contract, order))
        return types.SimpleNamespace(
            order=order,
            orderStatus=types.SimpleNamespace(status="Filled", filled=self._filled,
                                              avgFillPrice=self._avg))

    def cancelOrder(self, order):
        self.cancelled.append(order)


def _run(mod_min, *, net=0.0, monkeypatch=None):
    ib = FakeIB(); out = {}
    monkeypatch.setattr(D, "drift_read",
                        lambda *a, **k: types.SimpleNamespace(price=23000.0, atr=25.0))
    # ★2026-09-04 the manual entry no longer routes through await_fill — it uses place_entry(),
    # which is exercised for real here against FakeIB's orderStatus. The stub stays for the CLOSE
    # paths, which still use await_fill.
    async def fake_fill(tr, fallback, **kw): return 23000.0
    monkeypatch.setattr(D, "await_fill", fake_fill)
    monkeypatch.setattr(D, "venue_first_ok", lambda *a, **k: True)
    cfg = types.SimpleNamespace(capture_path="/dev/null", symbol="MNQ")
    handled = asyncio.run(D.do_manual_entry(
        ("BUY", 4, [100.0, 200.0, 400.0, 600.0]), ib=ib, contract=object(), cfg=cfg,
        now=dt.datetime(2026, 8, 21, tzinfo=dt.UTC), mod=mod_min, net=net, out=out, notify=None))
    return handled, ib, out


def test_manual_buy_actually_places_the_order(monkeypatch):
    handled, ib, out = _run(9 * 60, monkeypatch=monkeypatch)      # 09:00Z — inside the CME session
    assert handled is True
    assert len(ib.orders) == 1, "THE BUTTON DID NOT PLACE AN ORDER"
    order = ib.orders[0][1]
    assert order.action == "BUY" and order.totalQuantity == 4
    assert out["entered"] is True and out["entry"] == 23000.0 and out["lots_open"] == 4
    assert out["venue_stop"] is None, "operator: 'leave them all naked'"
    assert out["closed"] is False, "the closed latch survived a manual entry"
    # $ target -> points divides by $2/pt PER LOT, never by the lot count
    assert out["manual_targets_pt"] == [50.0, 100.0, 200.0, 300.0]


@pytest.mark.parametrize("mod", [20 * 60 + 40, 20 * 60 + 55, 21 * 60 + 30])
def test_manual_buy_refused_in_the_flatten_and_halt_window(mod, monkeypatch):
    handled, ib, out = _run(mod, monkeypatch=monkeypatch)
    assert handled is True and not ib.orders, "placed an order into the flatten/halt window"
    assert "refused" in out["note"]


@pytest.mark.parametrize("mod", [22 * 60 + 1, 2 * 60, 9 * 60, 13 * 60 + 30, 20 * 60 + 39])
def test_the_full_cme_session_is_open_for_a_manual_press(mod, monkeypatch):
    """Operator, 2026-08-21: 'extend it to the full cme session.'"""
    handled, ib, out = _run(mod, monkeypatch=monkeypatch)
    assert len(ib.orders) == 1, f"minute {mod} should be tradeable by hand"


def test_manual_buy_refused_when_the_venue_does_not_reconcile(monkeypatch):
    ib = FakeIB(); out = {}
    monkeypatch.setattr(D, "venue_first_ok", lambda *a, **k: False)
    cfg = types.SimpleNamespace(capture_path="/dev/null", symbol="MNQ")
    asyncio.run(D.do_manual_entry(("BUY", 4, [100.0, 200.0, 400.0, 600.0]), ib=ib,
                contract=object(), cfg=cfg, now=dt.datetime(2026, 8, 21, tzinfo=dt.UTC),
                mod=9 * 60, net=0.0, out=out, notify=None))
    assert not ib.orders, "bypassed the venue-first gate — IBKR IS THE TRUTH"


def test_manual_entry_clears_a_stale_closed_latch(monkeypatch):
    """★ THE 13:13Z INCIDENT. Manual entry bypasses the once-per-session rule, so a press after any
    earlier exit arrives with `closed` still True from the previous trade. `owns_position` is
    (entered AND NOT closed): left True, the rider does not manage the position, claims ZERO lots to
    the reconciler, the venue's +4 reads as unaccounted, the kill switch fires, and 4 real lots sit
    naked while the dashboard shows nothing."""
    ib = FakeIB(); out = {"entered": True, "closed": True, "exit_reason": "CLOCK_FLAT_BUG"}
    monkeypatch.setattr(D, "drift_read",
                        lambda *a, **k: types.SimpleNamespace(price=29491.0, atr=25.0))
    async def fake_fill(tr, fallback, **kw): return 29491.625
    monkeypatch.setattr(D, "await_fill", fake_fill)
    monkeypatch.setattr(D, "venue_first_ok", lambda *a, **k: True)
    cfg = types.SimpleNamespace(capture_path="/dev/null", symbol="MNQ")
    asyncio.run(D.do_manual_entry(("BUY", 4, [100.0, 200.0, 400.0, 600.0]), ib=ib,
                contract=object(), cfg=cfg, now=dt.datetime(2026, 8, 21, tzinfo=dt.UTC),
                mod=13 * 60 + 13, net=0.0, out=out, notify=None))
    assert out["closed"] is False and out["entered"] is True
    assert out["exit_reason"] is None
    owns = bool(out["entered"]) and not bool(out["closed"])
    assert owns, "the rider would disown a position it had just opened"
