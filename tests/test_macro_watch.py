"""THE MACRO TRACKER — context only, and it must say so about every number it prints.

Operator asked for oil, DXY, the 10-year and VIX as backdrop. These tests guard the three ways a
context tracker turns into a liability on this desk.
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

SRC = "/home/alphabot/gazbot7/scripts/macro_watch.py"


def test_the_connection_is_readonly_and_always_disconnected():
    """★★★ THE 2026-09-17 LESSON. The gateway's accept queue filled and every new connection hung
    for 5.5 hours while the rider held 4 lots blind. A leaked socket here is a CLOSE-WAIT on the
    gateway, and this is a CONTEXT tracker — it must never be what costs a claim."""
    src = open(SRC).read()
    assert "readonly=True" in src, "the macro tracker opens a writable broker connection"
    assert "finally:" in src and "ib.disconnect()" in src, "the connection is not guaranteed closed"
    for banned in ("placeOrder", "MarketOrder", "LimitOrder", "gate_switches",
                   "day_rider_claim", "day_rider_buy"):
        assert banned not in src, f"the tracker reached for {banned}"


def test_it_uses_a_free_client_id():
    """⚠ A clientId collision makes the venue read fail while the caller still looks healthy —
    that exact shape is documented in day_rider_watchdog's hb_age_s()."""
    import macro_watch as mw
    assert mw.CLIENT_ID not in (0, 2, 4, 5, 6, 8), (
        f"clientId {mw.CLIENT_ID} collides with a desk service")


def test_VIX_is_flagged_DELAYED_everywhere_it_appears():
    """⚠⚠ VIX needs reqMarketDataType(3) on this account — it is ~15 minutes stale. A delayed
    number presented as live is the instrument-reports-healthy failure this desk keeps meeting."""
    import macro_watch as mw
    vix = [s for s in mw.SERIES if s[0] == "VIX"][0]
    assert vix[4] is True, "VIX is no longer marked as the delayed/index case"
    assert "DELAYED" in vix[3], "the VIX label no longer warns that it is delayed"
    src = open(SRC).read()
    assert '"delayed": bool(is_index)' in src, "the stored record no longer carries the delay flag"
    assert "reqMarketDataType(3)" in src


def test_the_ten_year_says_it_is_a_PRICE_not_a_yield():
    """⚠ ZN is the NOTE FUTURE: it moves INVERSE to yield. 'TEN is up' meaning 'yields are down' is
    exactly the sign error that turns context into a wrong read."""
    import macro_watch as mw
    ten = [s for s in mw.SERIES if s[0] == "TEN"][0]
    assert "inverse" in ten[3].lower() and "price" in ten[3].lower()


def test_oil_names_WHICH_oil():
    """⚠ FRED spot read 107.02 on 15-Sep while the front future read 95.24 on the 18th. Quoting
    them interchangeably is the cost-constant class of error ($7.50 gold, and the rest)."""
    import macro_watch as mw
    oil = [s for s in mw.SERIES if s[0] == "OIL"][0]
    assert "front" in oil[3].lower() and oil[2] == "NYMEX"
    assert "not spot" in open(SRC).read()


def test_it_is_quiet_on_a_blip_and_loud_on_a_streak():
    """⚠ Paging on every transient trains him to swipe past criticals; never paging is how 5.5
    hours went by unnoticed."""
    src = open(SRC).read()
    assert "(6, 24)" in src, "the blind-streak escalation changed — re-check the cadence"
    assert "os.remove(BLIND)" in src, "a good read must end the streak"
    assert "critical=False" in src, "a context outage must not page as a safety critical"


def test_it_claims_no_edge():
    """⚠⚠ These four are carried because he asked for the backdrop, NOT because they have been
    tested against MNQ or MGC. The file must keep saying so."""
    assert "MEASURES NO EDGE" in open(SRC).read()
