"""TUNNEL WATCH — the boundary tests.

★ These EXECUTE the code, they do not grep it. A source-grep test passed green on this desk while
  the code under it crashed — three times in seven days. The read-only test is the one exception
  and it is explicitly a source assertion, because the property it protects ("this file contains no
  order path") is a property OF THE SOURCE.
"""
import math
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import tunnel_watch as tw  # noqa: E402


# ── the boundary ──────────────────────────────────────────────────────────────
def test_no_order_path_in_source():
    """READ-ONLY BY CONSTRUCTION. If this fails, someone gave the notifier hands."""
    # ★ Strip COMMENTS AND STRING LITERALS before checking. The first version of this test failed
    # on the module's own docstring saying "no ib_async, no order path" — the file documenting the
    # boundary tripped the test enforcing it. Compare CODE, not prose.
    import io, tokenize
    src_path = os.path.join(ROOT, "scripts", "tunnel_watch.py")
    code = []
    with open(src_path) as fh:
        for tok in tokenize.generate_tokens(fh.readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            code.append(tok.string)
    body = " ".join(code)
    for banned in ("ib_async", "placeOrder", "MarketOrder", "cancelOrder",
                   "reqIds", "INTENTS", "gate_switches", "day_rider_claim"):
        assert banned not in body, f"tunnel_watch must not reference {banned!r} in CODE"


def test_capture_opened_read_only():
    src = open(os.path.join(ROOT, "scripts", "tunnel_watch.py")).read()
    assert "mode=ro" in src, "capture.db must be opened read-only"


def test_symbol_is_filtered():
    """MD/capture are MULTI-SYMBOL. Folding MGC into an MNQ reader made ATR read 1848 vs a true 15."""
    src = open(os.path.join(ROOT, "scripts", "tunnel_watch.py")).read()
    assert "symbol = ?" in src or "symbol=?" in src
    assert 'SYMBOL = "MNQ"' in src


def test_minute_bucketing_is_integer_not_float_division():
    """`(bar_ts/60)*60` is a NO-OP that once read 5s bars as '1m' for hours."""
    # ★ Checked on RAW source, not stripped: the bucketing lives INSIDE the SQL string literal,
    # so a token filter that drops strings drops the very expression under test. The float-division
    # check is safe on raw source only because the module's warning comment was reworded to avoid
    # containing the literal it warns about — a test that its own docs can break is a bad test.
    src = open(os.path.join(ROOT, "scripts", "tunnel_watch.py")).read()
    assert "% 60" in src, "minute bucketing must use integer modulo"
    assert re.search(r"bar_ts\s*/\s*60", src) is None, "float division by 60 is a silent no-op"


# ── the model, executed ───────────────────────────────────────────────────────
def test_filter_is_causal_prefix_stable():
    """FORWARD filtering only: the estimate for bar t must not change when later bars arrive.

    This is the look-ahead test. Viterbi/Baum-Welch smoothing would fail it, which is exactly why
    the live path uses the forward pass.
    """
    quiet = [math.exp(tw.MU[0])] * 60
    loud = [math.exp(tw.MU[1])] * 60
    short = tw.filter_states(quiet)
    long_ = tw.filter_states(quiet + loud)
    assert short == pytest.approx(long_[: len(short)], abs=1e-12)


def test_states_separate_quiet_from_active():
    quiet = tw.filter_states([math.exp(tw.MU[0])] * 40)
    loud = tw.filter_states([math.exp(tw.MU[1])] * 40)
    assert quiet[-1] > 0.9, "a run of small ranges must read QUIET"
    assert loud[-1] < 0.1, "a run of large ranges must read ACTIVE"


def test_find_tunnel_returns_none_when_active_now():
    bars = [{"m": i * 60, "hi": 100.0, "lo": 99.0, "close": 99.5, "vol": 10.0} for i in range(40)]
    post = [0.9] * 39 + [0.1]
    assert tw.find_tunnel(bars, post) is None


def test_find_tunnel_bounds_are_the_quiet_run_only():
    """The tunnel's range must come from the QUIET minutes, not from the active ones before it."""
    bars = ([{"m": i * 60, "hi": 200.0, "lo": 100.0, "close": 150.0, "vol": 10.0} for i in range(5)]
            + [{"m": (5 + i) * 60, "hi": 151.0, "lo": 149.0, "close": 150.0, "vol": 10.0} for i in range(30)])
    post = [0.1] * 5 + [0.9] * 30
    t = tw.find_tunnel(bars, post)
    assert t is not None and t["n"] == 30
    assert t["hi"] == 151.0 and t["lo"] == 149.0


def test_true_range_includes_the_gap():
    bars = [{"m": 0, "hi": 100.0, "lo": 99.0, "close": 99.5, "vol": 1.0},
            {"m": 60, "hi": 120.0, "lo": 119.0, "close": 119.5, "vol": 1.0}]
    trs = tw.true_range(bars)
    assert trs[1] > 1.0, "a gap must widen the true range, not be ignored"


def test_confirm_note_never_claims_an_edge():
    """The follow-up is 1.3 SE from a coin flip. It must read as an observation, never a signal."""
    for held in (True, False):
        note = tw.confirm_note(held).lower()
        for banned in ("confirm", "signal", "valid", "buy", "entry", "strong"):
            assert banned not in note, f"confirm_note must not imply an edge: {note!r}"


def test_session_key_rolls_at_2200z():
    from datetime import datetime, UTC
    a = tw.session_key(datetime(2026, 9, 2, 21, 59, tzinfo=UTC))
    b = tw.session_key(datetime(2026, 9, 2, 22, 1, tzinfo=UTC))
    assert a != b, "the CME session must roll at 22:00Z"


def test_read_minutes_supplies_a_real_close():
    """The model was fitted on true range off the REAL close. If the live reader stops supplying
    one, true_range() silently changes definition and the fitted thresholds no longer apply."""
    bars = tw.read_minutes(120)
    if not bars:
        pytest.skip("no capture data available")
    assert "close" in bars[-1], "read_minutes must supply the minute's real close"
    for b in bars[-20:]:
        assert b["lo"] <= b["close"] <= b["hi"], "close must lie inside the minute's range"


# ── the message is the product, so the message is tested ─────────────────────
def test_message_does_not_claim_the_withdrawn_magnitude_edge():
    """★2026-09-03. The alert used to promise "~1.75x normal 60m excursion". Re-derivation on the
    same 240 sessions with these very parameters got 1.02x in ATR / 1.08x in points, and six
    control definitions across MNQ and MGC span 0.82-1.32x. A number that survives in a live alert
    because nobody re-derives it is this desk's most expensive habit, so the text is asserted."""
    msg = tw.build_message("UP", 61, 84.0, 29190.0, 3.2, 12.4, 4)
    assert "1.75" not in msg
    assert "NO EDGE MEASURED" in msg
    assert "1.0x a normal minute" in msg


def test_message_still_carries_the_facts_the_operator_acts_on():
    msg = tw.build_message("DOWN", 61, 84.0, 29190.0, 3.2, 12.4, 4)
    assert "DOWN" in msg and "61m" in msg and "84pt" in msg and "29190" in msg
    assert "3.2x" in msg          # volume against the tunnel's own minute
    assert "12.4pt" in msg        # ATR
    assert "outside 4m" in msg


def test_message_never_reads_as_a_direction_call():
    for side in ("UP", "DOWN", "BOTH SIDES"):
        msg = tw.build_message(side, 30, 40.0, 100.0, 2.0, 5.0, 1)
        low = msg.lower()
        for word in ("buy", "sell", "long ", "short ", "target", "entry"):
            assert word not in low, (side, word)
        assert "0.50 random" in msg
