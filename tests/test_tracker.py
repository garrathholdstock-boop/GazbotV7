"""D3 — trade assembly: the §274-C partial-fill race, designed out."""

from __future__ import annotations

from gazbot7.store import Fill, get_trades, open_store
from gazbot7.tracker import TradeTracker


def test_adopt_seeds_position_then_close_records_trade():
    from gazbot7.store import Fill, get_trades, open_store
    store = open_store(":memory:")
    tt = TradeTracker(store, value_per_point=2.0, fee_rt=1.5)
    tt.adopt("MNQ", "SHORT", 1, 29000.0, "2026-07-15T13:00:00+00:00")  # taken over from venue
    assert tt.net_qty("MNQ") == -1.0  # reflected, no fill recorded
    tt.apply(Fill("x1", "o", "MNQ", "BUY", 1, 29100.0, "2026-07-15T14:00:00+00:00"),
             exit_reason="ADOPT_FLATTEN")  # cover fill closes it cleanly
    (tr,) = get_trades(store)
    assert tr["side"] == "SHORT" and tr["exit_reason"] == "ADOPT_FLATTEN"
    assert tr["pnl_usd"] == (29000 - 29100) * 1 * 2.0 - 1.5  # short covered higher = loss

VPP = 2.0  # MNQ $/point
FEE = 1.5


def _f(exec_id, side, qty, price, t="2026-07-15T13:00:00+00:00"):
    return Fill(exec_id=exec_id, order_id="o", symbol="MNQ", side=side, qty=qty, price=price, exec_time=t)


def _tt(tmp_path):
    store = open_store(tmp_path / "t.db")
    return TradeTracker(store, value_per_point=VPP, fee_rt=FEE), store


def test_clean_long_roundtrip(tmp_path):
    tt, store = _tt(tmp_path)
    tt.apply(_f("b", "BUY", 2, 100.0))
    tt.apply(_f("s", "SELL", 2, 105.0), exit_reason="RATCHET")
    (tr,) = get_trades(store)
    assert tr["side"] == "LONG"
    assert tr["entry_price"] == 100.0 and tr["exit_price"] == 105.0
    assert tr["pnl_usd"] == (105 - 100) * 2 * VPP - FEE  # +18.5
    assert tr["exit_reason"] == "RATCHET"  # a REAL reason
    assert tt.net_qty("MNQ") == 0


def test_partial_fill_exit_is_atomic_no_backfill(tmp_path):
    # THE D3 SCAR — this is trade 5970 replayed. 2-lot entry, exit in TWO
    # partials, a flat that arrives mid-partials. V5 dropped this to a ~2-min
    # backfill; V7 completes it atomically the instant the 2nd partial lands,
    # with the REAL exit_reason.
    tt, store = _tt(tmp_path)
    tt.apply(_f("e", "BUY", 2, 29924.75))
    # first exit partial — NOT flat yet, so NO trade must exist
    tt.apply(_f("x1", "SELL", 1, 29918.00), exit_reason="ADVERSE_CUT")
    assert get_trades(store) == []
    assert tt.net_qty("MNQ") == 1  # still 1 lot open
    # second partial brings it flat → complete NOW
    tt.apply(_f("x2", "SELL", 1, 29888.25), exit_reason="ADVERSE_CUT")

    trades = get_trades(store)
    assert len(trades) == 1
    tr = trades[0]
    assert tr["exit_reason"] == "ADVERSE_CUT"  # REAL — never RECONSTRUCTED_BACKFILL
    assert tr["exit_price"] == (29918.00 + 29888.25) / 2  # fills-VWAP exit
    assert tr["pnl_usd"] == (tr["exit_price"] - 29924.75) * 2 * VPP - FEE  # ≈ -88.0
    assert tt.net_qty("MNQ") == 0


def test_short_roundtrip_profit(tmp_path):
    tt, store = _tt(tmp_path)
    tt.apply(_f("s", "SELL", 2, 105.0))  # open short
    tt.apply(_f("b", "BUY", 2, 100.0), exit_reason="TARGET")  # cover lower = profit
    (tr,) = get_trades(store)
    assert tr["side"] == "SHORT"
    assert tr["pnl_usd"] == (105 - 100) * 2 * VPP - FEE  # +18.5


def test_short_loss_is_negative(tmp_path):
    tt, store = _tt(tmp_path)
    tt.apply(_f("s", "SELL", 2, 100.0))  # open short
    tt.apply(_f("b", "BUY", 2, 105.0), exit_reason="STOP")  # cover higher = loss
    (tr,) = get_trades(store)
    assert tr["pnl_usd"] < 0
    assert tr["pnl_usd"] == (100 - 105) * 2 * VPP - FEE  # -21.5


def test_redelivered_fill_never_double_counts(tmp_path):
    tt, store = _tt(tmp_path)
    tt.apply(_f("b", "BUY", 2, 100.0))
    tt.apply(_f("s", "SELL", 2, 105.0), exit_reason="RATCHET")
    tt.apply(_f("s", "SELL", 2, 105.0), exit_reason="RATCHET")  # re-delivery of the close
    assert len(get_trades(store)) == 1  # not double-recorded
    assert tt.net_qty("MNQ") == 0  # position not double-moved


def test_partial_entry_then_close(tmp_path):
    # entry itself fills in two partials, then a single exit closes it
    tt, store = _tt(tmp_path)
    tt.apply(_f("e1", "BUY", 1, 100.0))
    tt.apply(_f("e2", "BUY", 1, 102.0))  # add → entry VWAP 101
    assert tt.net_qty("MNQ") == 2
    tt.apply(_f("x", "SELL", 2, 106.0), exit_reason="TARGET")
    (tr,) = get_trades(store)
    assert tr["entry_price"] == 101.0
    assert tr["pnl_usd"] == (106 - 101) * 2 * VPP - FEE


def test_overclose_flips_position(tmp_path):
    # a close that overshoots flat completes the round-trip AND opens the remainder
    # the other way — the V5 oversell-into-short scar, handled.
    tt, store = _tt(tmp_path)
    tt.apply(_f("b", "BUY", 2, 100.0))  # long 2
    tt.apply(_f("s", "SELL", 3, 105.0), exit_reason="FLIP")  # close 2, short 1
    (tr,) = get_trades(store)
    assert tr["side"] == "LONG" and tr["qty"] == 2
    assert tt.net_qty("MNQ") == -1  # now short 1


def test_gate_stamped_from_opening_fill(tmp_path):
    # The gate is taken from the OPENING intent (per-trade), not a static desk
    # value — the 2026-07-20 mislabel where every grind/rgv trade recorded 'thrust'.
    tt, store = _tt(tmp_path)  # no desk-default gate
    tt.apply(_f("b", "BUY", 1, 100.0), gate="grind")   # gate rides the opening fill
    tt.apply(_f("s", "SELL", 1, 105.0), exit_reason="CHANDELIER", gate="grind")  # ignored on exit
    (tr,) = get_trades(store)
    assert tr["gate"] == "grind"


def test_two_roundtrips_record_distinct_gates(tmp_path):
    # The actual bug's shape: two sequential trades from different gates must NOT
    # collapse to one label. grind then rgv → 'grind' then 'rgv'.
    tt, store = _tt(tmp_path)
    tt.apply(_f("b1", "BUY", 1, 100.0), gate="grind")
    tt.apply(_f("s1", "SELL", 1, 101.0), exit_reason="STOP", gate="grind")
    tt.apply(_f("b2", "BUY", 2, 200.0), gate="rgv")
    tt.apply(_f("s2", "SELL", 2, 198.0), exit_reason="ABSORPTION_CUT", gate="rgv")
    gates = [t["gate"] for t in get_trades(store)]
    assert gates == ["grind", "rgv"]


def test_gate_falls_back_to_desk_default_when_absent(tmp_path):
    # Adopted / flipped positions have no opening intent → fall back to the
    # tracker's desk-default gate rather than recording NULL.
    store = open_store(tmp_path / "t.db")
    tt = TradeTracker(store, value_per_point=VPP, fee_rt=FEE, gate="thrust")
    tt.apply(_f("b", "BUY", 1, 100.0))  # no gate passed (e.g. reconstructed/adopted path)
    tt.apply(_f("s", "SELL", 1, 105.0), exit_reason="STOP")
    (tr,) = get_trades(store)
    assert tr["gate"] == "thrust"
