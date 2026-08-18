"""An OPEN sim position must be visible from outside the process.

★★★2026-08-18. `record_shadow_trade()` fires only on EXIT, so a variant sitting in a trade and a
variant not firing AT ALL rendered identically — in the store, on the board, and in sweep. rider_w5
taking one trade on a session its gate was true for 32 minutes had to be diagnosed by replaying the
tape four hours later. "Blocked" and "dead" must not look the same.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.shadow import ShadowSim, default_slate  # noqa: E402
from gazbot7.store import open_store  # noqa: E402


def _sim(tmp):
    sp = os.path.join(tmp, "s.db")
    return ShadowSim(open_store(sp), default_slate(), store_path=sp), f"{sp}.open.json"


def test_a_snapshot_exists_from_the_moment_the_sim_starts():
    """An empty book must be POSITIVELY stated, not implied by a missing file."""
    with tempfile.TemporaryDirectory() as tmp:
        _, path = _sim(tmp)
        assert os.path.exists(path)
        assert json.load(open(path))["open"] == {}


def test_an_open_position_is_published_with_its_cap():
    with tempfile.TemporaryDirectory() as tmp:
        sim, path = _sim(tmp)
        sim._open["rider_w5"] = {"side": "LONG", "entry_price": 1.0, "entry_atr": 2.0,
                                 "entry_ts": 1787000000, "peak": 0.0, "brk": False}
        sim._publish_open()
        row = json.load(open(path))["open"]["rider_w5"]
        assert row["side"] == "LONG"
        assert row["time_cap_s"] == 7200, "the cap travels with the position, so over-cap is visible"
        assert row["held_s"] >= 0


def test_closing_removes_it():
    with tempfile.TemporaryDirectory() as tmp:
        sim, path = _sim(tmp)
        sim._open["rider_w5"] = {"side": "LONG", "entry_ts": 1787000000}
        sim._publish_open()
        assert "rider_w5" in json.load(open(path))["open"]
        del sim._open["rider_w5"]
        sim._publish_open()
        assert json.load(open(path))["open"] == {}


def test_publishing_never_takes_the_desk_down():
    """★ FAIL-QUIET. This is observability; it must not be able to kill the shadow desk."""
    with tempfile.TemporaryDirectory() as tmp:
        sim, _ = _sim(tmp)
        sim._open_path = "/nonexistent-dir/nope/open.json"
        sim._publish_open()          # must not raise
        sim._open_path = None
        sim._publish_open()          # must not raise


def test_no_store_path_disables_it_silently():
    """Tests and ad-hoc harnesses construct ShadowSim without a path; that must stay legal."""
    with tempfile.TemporaryDirectory() as tmp:
        sim = ShadowSim(open_store(os.path.join(tmp, "x.db")), default_slate())
        assert sim._open_path is None
        sim._publish_open()
