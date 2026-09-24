"""THE ORDER PATH IS CLOSED TO SCRIPTS.

★★★ WHY (2026-09-24). An assistant test of the no-PIN flatten POSTed to
/api/control/dayrider-claim and the rider flattened the operator's LIVE SHORT 4 three seconds
later — trade 1019, -$842.50. It was the THIRD time in one session that a test touched a live
position, and twice before it had been promised it would not happen again.

A PROMISE IS NOT A CONTROL. This is the control.

THE RULE: an endpoint that can move money must arrive FROM THE DASHBOARD. A browser fetching from
the page always sends a same-origin Referer — verified against nginx, where the operator's own
iPhone claim at 10:41:04 carried "http://178.104.170.58/v7/". A bare curl sends none, and a bare
curl is every accidental call from a shell.

⚠ THIS IS NOT SECURITY. A Referer is trivially forged; it is not meant to stop an attacker. It is
meant to make the ACCIDENT impossible, which is the failure that actually happened. Anything that
legitimately acts without a browser writes the request FILE directly — step_away.py does exactly
that and is unaffected.
"""
import re
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

WEB = "/home/alphabot/gazbot7/src/gazbot7/web.py"


def _src():
    return open(WEB).read()


def test_every_money_moving_path_is_gated():
    """⚠ The list must cover EVERY endpoint that can open or close a position. A new order endpoint
    added without this list is a new hole."""
    src = _src()
    m = re.search(r"ORDER_PATHS = \(([^)]*)\)", src, re.S)
    assert m, "the ORDER_PATHS gate is gone"
    gated = set(re.findall(r'"([^"]+)"', m.group(1)))
    assert gated == {"/api/control/claim", "/api/control/dayrider-buy",
                     "/api/control/dayrider-claim"}, f"gate list drifted: {sorted(gated)}"
    # and every POST route that reaches a *_post handler placing an order must be in it
    routes = set(re.findall(r'path == "(/api/control/[a-z-]+)"', src))
    order_like = {r for r in routes if "claim" in r or "buy" in r}
    assert order_like <= gated, f"un-gated order routes: {sorted(order_like - gated)}"


def test_the_gate_runs_BEFORE_the_handler():
    """⚠ A check after dispatch is not a check — the claim file would already be written."""
    src = _src()
    i = src.index("def do_POST(self):")
    gate = src.index("if path in self.ORDER_PATHS", i)
    first = src.index('if path == "/api/control/claim"', i)
    assert gate < first, "the gate runs after the first handler — too late"


def test_data_capture_paths_are_NOT_gated():
    """⚠ `pass` and `clienterr` record data and place nothing. Gating them would cost the sample
    (PASS is the blocker for the whole operator-model programme) for no safety at all."""
    src = _src()
    m = re.search(r"ORDER_PATHS = \(([^)]*)\)", src, re.S)
    gated = m.group(1)
    for open_path in ("/api/control/pass", "/api/control/clienterr"):
        assert open_path not in gated, f"{open_path} was gated — it places no order"


def test_a_same_origin_referer_passes_and_a_bare_call_does_not():
    """★ The operator's own iPhone claim carried Referer http://178.104.170.58/v7/ — the guard must
    let that through, or it has broken every button to prevent a bug I caused."""
    src = _src()
    i = src.index("def _from_dashboard(self)")
    body = src[i:i + 400]
    assert '"Referer"' in body and '"Origin"' in body, "the guard ignores both headers"
    assert '"/v7" in ref' in body, "a same-origin dashboard referer would be rejected"


def test_the_reason_is_written_down_next_to_the_guard():
    """⚠ A guard whose purpose is not recorded gets deleted by the next person who finds it
    inconvenient — and this one was paid for with $842.50 of somebody else's money."""
    src = _src()
    i = src.index("ORDER_PATHS")
    ctx = src[max(0, i - 2000):i]
    assert "trade 1019" in ctx and "THREE SECONDS" in ctx
    assert "A promise is not a control." in ctx
