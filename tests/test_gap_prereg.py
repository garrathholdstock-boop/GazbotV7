"""THE PX/CVD GAP RULE — pre-registered, collected forward (2026-09-24).

Operator asked for worked examples of the PX·CVD pair and produced `65·10`: a 55-point
disagreement the SHIPPED rule IGNORES, because bearish needs px>=85 and bullish needs px<=15. The
widest divergence of the four he named gets no colour at all. He found the hole by asking for
examples; no test had.

⚠⚠ This desk spent the same day learning what an 80-cell search on 5 sessions produces. So the
replacement rule is PRE-REGISTERED before a single outcome is computed, and the threshold is
INHERITED rather than chosen.
"""
import json
import re

SRC = "/home/alphabot/gazbot7/scripts/gap_log.py"
PREREG = "/home/alphabot/gazbot7/data/prereg_gap.json"


def _code(src):
    b = src.split('"""', 2)
    src = b[2] if len(b) > 2 else src
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def test_the_threshold_is_inherited_from_the_incumbent_not_fitted():
    """★★★ THE INTEGRITY OF THE WHOLE EXERCISE. 35 is the minimum gap the SHIPPED rule already
    implies — 85/50 and 15/50 are both gaps of 35 — so no number here was selected by looking at
    data. If a future session 'optimises' it, the count restarts at zero and the prereg is void."""
    p = json.load(open(PREREG))
    assert p["frozen"]["gap_threshold"] == 35
    assert "NOT FITTED" in p["frozen"]["gap_threshold_provenance"]
    src = open(SRC, encoding="utf-8").read()
    assert float(re.search(r"^GAP = ([\d.]+)", src, re.M).group(1)) == p["frozen"]["gap_threshold"]


def test_the_unit_is_an_EPISODE_not_a_minute():
    """⚠⚠ A gap persists for many consecutive minutes. Counting minutes would score ONE divergence
    forty times and inflate n by the LENGTH of episodes rather than their NUMBER — the same trap as
    counting scale-out exit rows instead of entries."""
    c = _code(open(SRC, encoding="utf-8").read())
    assert "d_cur == d_prev" in c, "an episode must fire only on the lean APPEARING or FLIPPING"
    assert "EPISODE" in json.load(open(PREREG))["frozen"]["unit_of_observation"].upper()


def test_the_primary_horizon_is_declared_in_advance():
    """⚠ Recording four horizons and later picking the best is a four-cell search."""
    p = json.load(open(PREREG))
    assert p["frozen"]["primary_horizon_min"] == 30
    src = open(SRC, encoding="utf-8").read()
    assert int(re.search(r"^HORIZON = (\d+)", src, re.M).group(1)) == p["frozen"]["primary_horizon_min"]


def test_the_incumbent_is_scored_on_the_same_episodes():
    """⚠ A CONTROL IS SUPPOSED TO LOSE — but it must be MEASURED, not assumed. Replacing a live
    rule with one that merely MATCHES it is churn, so the verdict requires beating BOTH."""
    c = _code(open(SRC, encoding="utf-8").read())
    assert "def incumbent(" in c and '"incumbent": incumbent(cur)' in c
    v = json.load(open(PREREG))["verdict_rule"]
    assert "INCUMBENT" in v.upper() and "REFUTED" in v.upper()


def test_the_verdict_uses_day_clustered_intervals():
    v = json.load(open(PREREG))["verdict_rule"]
    assert "DAY-CLUSTERED" in v.upper()


def test_positions_use_the_range_AS_IT_WAS_never_the_finished_session():
    """⚠⚠⚠ THE LOOK-AHEAD THAT QUIETLY KILLS STUDIES HERE. Scoring a 10:00 minute against the
    session's FINAL high and low lets the rule see the rest of the day."""
    c = _code(open(SRC, encoding="utf-8").read())
    body = c.split("def build(", 1)[1].split("\ndef ", 1)[0]
    assert "max(phi, p)" in body and "min(plo, p)" in body, "running extremes, updated per minute"
    assert body.index("out.append") > body.index("max(phi, p)")


def test_the_outcome_is_signed_by_the_lean():
    """⚠ A bearish lean must score a FALL as positive. Storing a raw delta would need re-signing at
    read time and one forgotten flip inverts the entire verdict."""
    c = _code(open(SRC, encoding="utf-8").read())
    assert "* d_cur, 2)" in c


def test_it_is_single_pass_with_the_outcome_already_on_the_tape():
    """★ It evaluates the minute that ended HORIZON ago. A log needing a second pass to fill
    outcomes in is a log that silently keeps half its rows."""
    c = _code(open(SRC, encoding="utf-8").read())
    assert "HORIZON - 1" in c


def test_the_warm_up_exists_and_its_amendment_is_recorded():
    """⚠⚠ A 'position in the range' is undefined while the range is near zero. The first mechanism
    check produced 100·65 and 0·100 on a three-minute-old session. The fix is recorded as an
    AMENDMENT, with the fact that it was made BEFORE any outcome was examined — otherwise a repair
    and a fit are indistinguishable from the outside."""
    src = open(SRC, encoding="utf-8").read()
    assert "WARM_MIN" in src and "WARM_RANGE_PT" in src
    a = json.load(open(PREREG))["amendments"][0]
    assert "BEFORE ANY OUTCOME" in a["⚠ integrity"].upper()


def test_the_warm_up_counts_minutes_SEEN_not_minutes_KEPT():
    """⚠ `len(out)` as the counter would never reach the warm-up, because nothing is appended until
    the warm-up passes — the detector would be silent forever and look merely quiet."""
    c = _code(open(SRC, encoding="utf-8").read())
    assert "seen >= WARM_MIN" in c and "seen += 1" in c


def test_no_in_sample_numbers_were_recorded():
    """★★★ The 5 sessions of tick history were spent on the PULSE/FLOW study. Reusing them here
    would make this the 81st cell of the same search."""
    p = json.load(open(PREREG))
    assert p["in_sample_status"].startswith("NONE")


def test_it_writes_only_its_own_files():
    """⚠⚠⚠ READ-ONLY. No order path, no switch file, no request file."""
    src = open(SRC, encoding="utf-8").read()
    for forbidden in ("day_rider_claim", "day_rider_buy", "gate_switches", "placeOrder"):
        assert forbidden not in src
