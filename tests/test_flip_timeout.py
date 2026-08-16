"""BUILD #15 — capitulation_long: require_flip OR a 90-second timeout.

The live gate runs require_flip=True; the 07-25 rehab found the flip IS the edge (loose was fading
the climax itself). This does not dispute that. It asks whether the flip is worth waiting for
INDEFINITELY — a different question, and the one nobody has measured.

gate_capitulation is PURE and stateless: it sees a rolling tape window and cannot know how long a
climax has been waiting. The clock therefore lives in ShadowSim, and these tests drive it.
"""
import sqlite3

from gazbot7.shadow import ShadowSim, default_slate
from gazbot7.store import SCHEMA

CLIMAX_NO_FLIP = {"sell": 900.0, "buy": 100.0, "base": 100.0, "dpx": -5.0, "flip": False}
QUIET = {"sell": 10.0, "buy": 10.0, "base": 100.0, "dpx": 0.0, "flip": False}


class _F:
    atr = 20.0
    price = 20000.0


def _sim(name):
    v = next(x for x in default_slate() if x.name == name)
    st = sqlite3.connect(":memory:")
    st.executescript(SCHEMA)
    return ShadowSim(st, [v], value_per_point=2.0, fee_rt=1.5), v


def test_the_timeout_does_not_fire_early():
    sim, v = _sim("capit_flip_t90")
    assert sim._entry(v, _F(), 0.0, True, CLIMAX_NO_FLIP, bars=[], ts=1000) is None
    assert sim._entry(v, _F(), 0.0, True, CLIMAX_NO_FLIP, bars=[], ts=1089) is None, \
        "89s is not 90s — an off-by-one here silently changes the rule under test"


def test_the_timeout_fires_once_the_climax_has_stood_long_enough():
    sim, v = _sim("capit_flip_t90")
    sim._entry(v, _F(), 0.0, True, CLIMAX_NO_FLIP, bars=[], ts=1000)
    e = sim._entry(v, _F(), 0.0, True, CLIMAX_NO_FLIP, bars=[], ts=1090)
    assert e is not None and e.side == "LONG"


def test_the_clock_RESETS_when_the_climax_stops_holding():
    """Otherwise an old, unrelated flush authorises a much later entry — the latch bug shape that
    has bitten the day rider ([[day-rider-closed-latch-consumes-session]])."""
    sim, v = _sim("capit_flip_t90")
    sim._entry(v, _F(), 0.0, True, CLIMAX_NO_FLIP, bars=[], ts=1000)
    sim._entry(v, _F(), 0.0, True, QUIET, bars=[], ts=1030)          # climax gone -> clock cleared
    assert v.name not in sim._flip_wait
    assert sim._entry(v, _F(), 0.0, True, CLIMAX_NO_FLIP, bars=[], ts=1060) is None, \
        "a fresh flush must start a fresh clock, not inherit the old one"


def test_the_LIVE_arm_never_times_out():
    """The control must be the live rule exactly, or the pair measures two things at once."""
    sim, v = _sim("capit_flip_live")
    assert v.flip_timeout_s == 0
    for ts in (1000, 1090, 9000):
        assert sim._entry(v, _F(), 0.0, True, CLIMAX_NO_FLIP, bars=[], ts=ts) is None


def test_the_pair_differs_ONLY_in_the_timeout():
    a = next(x for x in default_slate() if x.name == "capit_flip_live")
    b = next(x for x in default_slate() if x.name == "capit_flip_t90")
    assert a.params == b.params == {"require_flip": True}
    assert (a.gate, a.side, a.target_r, a.stop_atr_mult) == (b.gate, b.side, b.target_r, b.stop_atr_mult)
    assert (a.flip_timeout_s, b.flip_timeout_s) == (0, 90)


def test_no_other_variant_carries_a_timeout():
    for v in default_slate():
        if v.name != "capit_flip_t90":
            assert v.flip_timeout_s == 0, f"{v.name} unexpectedly has a flip timeout"
