"""The MANAGE path must price the position off the LIVE TAPE, never off its own entry.

★★★ 2026-09-04, FOUND LIVE ON AN OPEN POSITION. `drift_read` is anchored to the 13:30 UTC cash open
and returns price 0.0 outside it. The manage path read `px = rr.price or entry`, so outside US hours
it fell back to THE POSITION'S OWN ENTRY PRICE and compared the market against itself:

    ahead_pt  read 0 on a LONG 4 that was $220 down
    peak      never moved off entry
    trail     could never arm  (ahead is measured from peak)
    ladder    no rung could ever fire  (ahead = d * (px - entry) = 0)

Nothing errored. The heartbeat advanced every 60s and the note said "riding · trail not armed
(need +150 [fixed], at +0)". **The exit machinery was switched off and every instrument said fine** —
[[an-instrument-that-reports-healthy-about-something-it-does-not-check]], on the money path.

⚠ `entry` survives as the LAST-RESORT fallback, deliberately. With no fresh tape at all, comparing
the market against itself is inert; a stale price could fire a rung against a market that has moved.
"""
import sys
import types

sys.path.insert(0, "/home/alphabot/gazbot7/src")

import gazbot7.day_rider as dr

SRC = "/home/alphabot/gazbot7/src/gazbot7/day_rider.py"
CAP = "/home/alphabot/gazbot7/data/capture.db"


def test_the_manage_path_no_longer_prices_off_its_own_entry():
    """★ REGRESSION GUARD. `px = rr.price or entry` is the bug, in one line."""
    src = open(SRC).read()
    i = src.index("own_qty = float(st.get(\"qty\") or LOTS)")
    block = src[i:i + 2000]
    assert "px = rr.price or entry" not in block, (
        "the manage path is pricing off drift_read alone again — it returns 0.0 outside US hours "
        "and the fallback is the position's own entry, which switches the trail and ladder off")
    assert "px = entry_reference(rr, cfg) or entry" in block, (
        "the manage path must take its price from the live tape when drift_read is blind")


def test_a_blind_drift_read_still_yields_a_real_market_price():
    cfg = types.SimpleNamespace(capture_path=CAP, symbol="MNQ")
    blind = types.SimpleNamespace(price=0.0, atr=0.0)
    px = dr.entry_reference(blind, cfg)
    assert px > 20000, f"no usable market price outside US hours: {px}"


def test_the_ladder_can_fire_once_the_price_is_real():
    """The consequence, not just the value: with px == entry no rung can EVER trigger."""
    entry, d = 29647.625, 1
    ladder = list(dr.TARGET_PT)                      # 50/100/200/300pt per lot
    blind_px = entry                                 # what the bug produced
    assert all(d * (blind_px - entry) < t for t in ladder), (
        "sanity: pricing off entry means ahead is 0 and no target can be reached")
    real_px = entry + 60.0                           # a move that HAS cleared rung 1
    fired = [t for t in ladder if d * (real_px - entry) >= t]
    assert fired == [ladder[0]], f"the first rung must fire on a real price: {fired}"


def test_the_trail_arms_only_from_the_peak_so_a_frozen_peak_disables_it():
    """Why the bug disabled the trail: `ahead` is measured from PEAK, and peak never moved."""
    entry = 29647.625
    assert dr.trail_level(1, entry, entry, 0.0) is None, "a frozen peak can never arm the trail"
    armed = dr.trail_level(1, entry, entry + dr.ARM_PT + 1, 0.0)
    assert armed is not None and armed < entry + dr.ARM_PT + 1, (
        "once the peak is real the trail must arm and sit below it")


def test_the_clock_flat_fallback_is_priced_too():
    """A 0.0 fallback makes book_trade REFUSE the row — the flatten fires and the ledger loses it."""
    src = open(SRC).read()
    i = src.index('what="CLOCK_FLAT exit"')
    ctx = src[i - 400:i]
    assert "entry_reference(_fb, cfg)" in ctx, (
        "the 20:40 flatten's fallback price is still drift_read-only, which is 0.0 outside US hours")
