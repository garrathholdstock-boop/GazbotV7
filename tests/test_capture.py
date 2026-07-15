"""D5 — capture: writers + the feed-break health classifier."""

from __future__ import annotations

from gazbot7.capture import (
    capture_health,
    open_capture,
    recent_tape,
    record_bar,
    record_book,
    record_quote,
    record_tick,
)

NOW = 1_760_000_000_000  # a fixed 'now' in ms


def _cap(tmp_path):
    return open_capture(tmp_path / "cap.db")


def test_tick_and_quote_round_trip(tmp_path):
    c = _cap(tmp_path)
    record_tick(c, "MNQ", NOW, 29950.0, 3, "buy")
    record_quote(c, "MNQ", NOW, 29949.75, 29950.0, 10, 8)
    c.commit()
    assert c.execute("SELECT price, aggressor FROM ticks").fetchone()["aggressor"] == "buy"
    q = c.execute("SELECT bid, ask FROM quotes").fetchone()
    assert q["bid"] == 29949.75 and q["ask"] == 29950.0


def test_bar_upsert_updates_in_place(tmp_path):
    c = _cap(tmp_path)
    bt = NOW // 1000
    record_bar(c, "MNQ", "5s", bt, 100, 101, 99, 100.5, 50)
    record_bar(c, "MNQ", "5s", bt, 100, 102, 99, 101.5, 80)  # same bar re-delivered
    c.commit()
    rows = c.execute("SELECT high, close, volume FROM bars").fetchall()
    assert len(rows) == 1  # upserted, not duplicated
    assert rows[0]["high"] == 102 and rows[0]["close"] == 101.5 and rows[0]["volume"] == 80


def test_book_snapshot(tmp_path):
    c = _cap(tmp_path)
    record_book(c, "MNQ", NOW, [("bid", 0, 29949.75, 12), ("ask", 0, 29950.0, 8)])
    c.commit()
    assert c.execute("SELECT COUNT(*) FROM book").fetchone()[0] == 2


def test_health_ok_when_both_fresh(tmp_path):
    c = _cap(tmp_path)
    record_tick(c, "MNQ", NOW - 1000, 29950.0, 1, "buy")  # 1s ago
    record_bar(c, "MNQ", "5s", (NOW - 3000) // 1000, 1, 1, 1, 1, 1)  # 3s ago
    c.commit()
    (h,) = capture_health(c, ["MNQ"], NOW)
    assert h.status == "OK"


def test_health_feed_break_ticks_live_bars_stale(tmp_path):
    # THE V5 scar: aggressor ticks flowing but the 5s reqRealTimeBars farm dropped.
    c = _cap(tmp_path)
    record_tick(c, "MNQ", NOW - 1000, 29950.0, 1, "buy")  # live
    record_bar(c, "MNQ", "5s", (NOW - 400_000) // 1000, 1, 1, 1, 1, 1)  # 400s stale
    c.commit()
    (h,) = capture_health(c, ["MNQ"], NOW)
    assert h.status == "FEED_BREAK"


def test_health_no_data(tmp_path):
    c = _cap(tmp_path)  # nothing captured
    (h,) = capture_health(c, ["MNQ"], NOW)
    assert h.status == "NO_DATA"


def test_recent_tape_summary(tmp_path):
    # the tape summary md publishes: net flow (buy−sell), price delta, last price
    c = _cap(tmp_path)
    record_tick(c, "MNQ", NOW - 5000, 29950.0, 4, "buy")
    record_tick(c, "MNQ", NOW - 3000, 29951.0, 3, "sell")
    record_tick(c, "MNQ", NOW - 1000, 29952.0, 5, "buy")
    record_tick(c, "MNQ", NOW - 120_000, 29900.0, 9, "buy")  # outside 60s window
    c.commit()
    net, dpx, last = recent_tape(c, "MNQ", NOW, window_s=60)
    assert net == 6.0  # 4 - 3 + 5, the stale 9 excluded
    assert dpx == 2.0  # 29952 - 29950
    assert last == 29952.0


def test_recent_tape_empty_window(tmp_path):
    c = _cap(tmp_path)
    assert recent_tape(c, "MNQ", NOW, window_s=60) == (0.0, 0.0, None)


def test_health_multi_symbol(tmp_path):
    # instrument-parameterised: MNQ healthy, MGC no data
    c = _cap(tmp_path)
    record_tick(c, "MNQ", NOW - 500, 29950.0, 1, "buy")
    record_bar(c, "MNQ", "5s", (NOW - 2000) // 1000, 1, 1, 1, 1, 1)
    c.commit()
    hs = {h.symbol: h.status for h in capture_health(c, ["MNQ", "MGC"], NOW)}
    assert hs == {"MNQ": "OK", "MGC": "NO_DATA"}
