"""THE PAPER/REAL BOUNDARY, AND THE KILL SWITCHES THAT MUST STAY OFF WHILE PAPER TRADING.

★★★2026-09-26 AUDIT, findings 01/02/03/09. Three things were built during the audit that CAN close a
position or refuse an order. All three are deliberately DISARMED, and the operator's instruction is
the reason, not an oversight:

   "all approved. do automaticlalt and then send out audit agent to make sure work is sound. jusy
    dont switch on any kill seitches while paper trading. i want to be able to trade and learn."

So these tests exist to hold that line. They are the ones that must fail loudly if a future session
"finishes the job" by arming something while the desk is still on paper.
"""
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import equity_guard as eg
from gazbot7 import livemode as L

PAPER = "DUQ191770"
EG_SRC = "/home/alphabot/gazbot7/scripts/equity_guard.py"


# ── THE LINE: nothing is armed on paper ───────────────────────────────────────────────────────
def test_the_live_desk_is_on_a_PAPER_account():
    assert L.mode(PAPER) == "PAPER"


def test_no_live_account_is_configured():
    """⚠ LIVE mode is unreachable until an account is added here by hand. That is the gate."""
    assert L.live_accounts() == (), f"a live account is configured: {L.live_accounts()}"


def test_the_venue_stop_is_NOT_armed():
    """★ Finding 01 is BUILT but OFF. `live_mode.json.venue_stop_armed` is his switch to flip."""
    from gazbot7.day_rider import PLACE_VENUE_STOP
    assert PLACE_VENUE_STOP is False, "a broker-side stop was armed while paper trading"


def test_the_equity_loss_limit_is_NOT_configured():
    """★ Finding 03 is BUILT but has no limit, so its breach branch is unreachable."""
    assert L._conf().get("equity_loss_limit_usd") in (None, 0, False)


def test_live_preflight_passes_on_paper_and_checks_nothing():
    """⚠⚠ THE WHOLE POINT: the January requirements must not bind the paper desk."""
    ok, missing = L.live_preflight(PAPER)
    assert ok is True and missing == []


def test_live_preflight_REFUSES_a_live_account_until_every_requirement_is_set(tmp_path,
                                                                             monkeypatch):
    """★ And the same mechanism is what stops January starting by accident."""
    cfg = tmp_path / "live_mode.json"
    cfg.write_text(json.dumps({"live_accounts": ["U9999999"]}))
    monkeypatch.setattr(L, "CONF", str(cfg))
    assert L.mode("U9999999") == "LIVE"
    ok, missing = L.live_preflight("U9999999")
    assert ok is False
    assert len(missing) == len(L.LIVE_REQUIREMENTS), "a live account passed with nothing configured"
    assert any("venue_stop" in m for m in missing)
    assert any("equity_loss_limit" in m for m in missing)


# ── the account guard is an ACCIDENT guard, not a new failure mode ────────────────────────────
def test_an_unlisted_account_is_refused():
    try:
        L.assert_account_allowed("U1234567")
    except L.AccountNotAllowed as e:
        assert "neither the paper nor the live allowlist" in str(e)
    else:
        raise AssertionError("an unlisted account was allowed to trade")


def test_the_paper_account_is_allowed_without_touching_config():
    """⚠ PAPER_ACCOUNTS is a hard-coded FLOOR precisely so a missing or corrupt live_mode.json
    cannot un-recognise the paper account and take the desk down."""
    assert L.assert_account_allowed(PAPER) == "PAPER"


def test_the_order_guard_FAILS_OPEN_when_the_account_cannot_be_read():
    """⚠⚠ A guard against an unlikely misconfiguration must never become a new way for a live EXIT
    to fail. Only a POSITIVE identification of a wrong account refuses."""
    src = open("/home/alphabot/gazbot7/src/gazbot7/broker_adapter.py").read()
    body = src.split("def _guard_account", 1)[1].split("\n    def ", 1)[0]
    code = "\n".join(l for l in body.splitlines()
                     if not l.strip().startswith("#") and '"""' not in l)
    assert code.count("return") >= 2, "the cannot-tell paths must return, not raise"


# ── the equity guard: measures always, acts never (on paper) ──────────────────────────────────
def test_it_reads_the_money_the_desk_never_read():
    for tag in ("NetLiquidation", "ExcessLiquidity", "UnrealizedPnL", "RealizedPnL"):
        assert tag in eg.TAGS, f"{tag} is the point of this script"


def test_the_limit_is_on_OPEN_PLUS_REALISED_not_realised_alone():
    """★★ Finding 03's second hole: the $250 gate rule counts realised P&L only, so an open
    -$2,000 never trips it. This one must see the open position."""
    v = eg.assess({"UnrealizedPnL": -900.0, "RealizedPnL": -100.0}, ours=-100.0,
                  limit=500.0, floor=None)
    assert v["breach"] is True, "an open loss must count toward the limit"
    assert v["ib_total_pnl"] == -1000.0


def test_realised_alone_would_NOT_have_tripped_it():
    """The contrast, stated explicitly so the difference from the incumbent is pinned."""
    v = eg.assess({"UnrealizedPnL": -900.0, "RealizedPnL": -100.0}, ours=-100.0,
                  limit=500.0, floor=None)
    assert abs(v["ib_realized"]) < 500.0 and v["breach"] is True


def test_it_reconciles_IB_against_our_own_book():
    """★ Finding 02: nothing has ever compared the broker's realised P&L to our ledger on a
    cadence. A persistent divergence means every decision is made from a wrong number."""
    v = eg.assess({"RealizedPnL": -149.38}, ours=-69.00, limit=None, floor=None)
    assert v["book_divergence"] == -80.38


def test_an_unreadable_ledger_gives_NO_divergence_rather_than_a_wrong_one():
    v = eg.assess({"RealizedPnL": -149.38}, ours=float("nan"), limit=None, floor=None)
    assert v["book_divergence"] is None


def test_no_limit_configured_means_no_breach_is_possible():
    """⚠ THE DISARMED STATE, as a behaviour rather than a comment."""
    v = eg.assess({"UnrealizedPnL": -99999.0, "RealizedPnL": -99999.0}, ours=0.0,
                  limit=None, floor=None)
    assert v["breach"] is False


def test_the_margin_floor_is_separate_from_the_loss_limit():
    v = eg.assess({"ExcessLiquidity": 1200.0, "UnrealizedPnL": 0.0, "RealizedPnL": 0.0},
                  ours=0.0, limit=None, floor=5000.0)
    assert v["margin_breach"] is True and v["breach"] is False


def test_the_flatten_path_requires_LIVE_and_is_asserted_against_the_SOURCE():
    """⚠⚠⚠ THE GUARD ON THE GUARD. `request_flatten` must be reachable only behind a LIVE check."""
    src = open(EG_SRC).read()
    body = src.split("if verdict[\"breach\"]:", 1)[1]
    call = body.index("request_flatten(")
    guard = body[:call]
    assert 'mode == "LIVE"' in guard, "the flatten path is not gated on LIVE mode"


def test_it_has_NO_order_path_at_all():
    """★ Like step_away, it writes the claim file his own button writes and nothing else. No
    placeOrder, no MarketOrder, no cancel — asserted against the source."""
    src = open(EG_SRC).read()
    for banned in ("placeOrder", "MarketOrder", "LimitOrder", "cancelOrder", "StopOrder"):
        assert banned not in src, f"{banned} must never appear in a read-only guard"
    assert "readonly=True" in src


def test_the_session_boundary_is_the_2200Z_reopen():
    """★ A calendar-day reset would clear the limit mid-session — the one moment it must not.
    Same boundary as daily_loss_limit and step_away, and a test pins it."""
    import datetime as dt
    assert eg.session_start(dt.datetime(2026, 9, 26, 21, 0, tzinfo=dt.UTC)).day == 25
    assert eg.session_start(dt.datetime(2026, 9, 26, 23, 0, tzinfo=dt.UTC)).day == 26


def test_it_excludes_flagged_rows_from_our_side_of_the_reconciliation():
    """⚠ The operator's standing rule is LABEL, never adjust: a bug-caused fill is not a trading
    result, so the comparison is 'clean book vs broker'."""
    src = open(EG_SRC).read()
    assert "data_quality is null" in src
