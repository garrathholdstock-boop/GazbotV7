"""The Sunday-reopen flatten. Operator, 2026-08-22: "flatten at the reopen".

It must: do nothing without a marker; treat an UNREADABLE venue as NOT flat (that is the exact
failure that created the carry); press Claim through the rider's normal path rather than touching
the broker; and disable itself once flat so a forgotten timer can never flatten a future position.
"""
import importlib.util, json, os, sys, types, pytest

spec = importlib.util.spec_from_file_location("wf", "/home/alphabot/gazbot7/scripts/weekend_flatten.py")
wf = importlib.util.module_from_spec(spec); spec.loader.exec_module(wf)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    marker = tmp_path / "pending.json"; claim = tmp_path / "claim.txt"; env = tmp_path / "env"
    monkeypatch.setattr(wf, "MARKER", str(marker))
    monkeypatch.setattr(wf, "CLAIM", str(claim))
    monkeypatch.setattr(wf, "ENV", str(env))
    pages = []
    monkeypatch.setattr(wf, "page", lambda m: pages.append(m))
    monkeypatch.setattr(wf.subprocess, "run", lambda *a, **k: None)
    return types.SimpleNamespace(marker=marker, claim=claim, env=env, pages=pages)


def _arm(rig):
    rig.marker.write_text(json.dumps({"symbol": "MNQ", "qty": 4.0, "opened": "2026-08-21"}))


def _venue(monkeypatch, net):
    async def f(symbol="MNQ"): return net
    monkeypatch.setattr(wf, "venue_net", f)


def test_no_marker_is_a_no_op(rig, monkeypatch):
    _venue(monkeypatch, 4.0)
    assert wf.main() == 0
    assert not rig.pages and not rig.claim.exists(), "acted with no job armed"


def test_an_unreadable_venue_is_not_treated_as_flat(rig, monkeypatch):
    """★ THE FAILURE THAT CAUSED THE CARRY. A dead gateway must never read as 'done'."""
    _arm(rig); _venue(monkeypatch, None)
    wf.main()
    assert rig.marker.exists(), "disarmed itself on a venue it could not read"
    assert not rig.claim.exists()
    assert "cannot read IBKR" in rig.pages[0]


def test_holding_presses_claim_through_the_rider(rig, monkeypatch):
    _arm(rig); _venue(monkeypatch, 4.0)
    wf.main()
    assert rig.claim.exists(), "no claim written — nothing would flatten"
    assert rig.claim.read_text().strip(), "claim file empty"
    assert rig.env.read_text().strip() == "day_rider=on", "rider left off; the claim would rot"
    assert rig.marker.exists(), "disarmed before confirming flat"


def test_a_bare_stamp_means_claim_ALL(rig, monkeypatch):
    """The rider reads a bare ISO stamp as 'flatten everything'; a lot suffix would close one lot."""
    _arm(rig); _venue(monkeypatch, 4.0)
    wf.main()
    assert "|" not in rig.claim.read_text(), "wrote a PER-LOT claim — 3 lots would stay open"


def test_flat_disarms_and_confirms(rig, monkeypatch):
    _arm(rig); _venue(monkeypatch, 0.0)
    wf.main()
    assert not rig.marker.exists(), "left itself armed — it could flatten a future position"
    assert "COMPLETE" in rig.pages[0]


def test_it_never_places_an_order_itself(rig):
    src = open("/home/alphabot/gazbot7/scripts/weekend_flatten.py").read()
    assert "placeOrder" not in src and "MarketOrder" not in src, \
        "the 2026-08-06 rule: only the rider talks to the broker"
    assert "readonly=True" in src, "its venue read must be read-only"
