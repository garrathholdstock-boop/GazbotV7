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
PREREG = "/home/alphabot/gazbot7/data/prereg_gap_rolling.json"


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
    # ★2026-09-25 the window ROLLS now, so the invariant is stated on the slice, not on running
    # extremes: at minute m it must take the PRECEDING WINDOW_MIN minutes and nothing after.
    assert "x[0] > m - WINDOW_MIN" in body, "the window must be taken as it was AT that minute"
    assert body.index("out.append") > body.index("x[0] > m - WINDOW_MIN")


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
    # the amendment lives on the SUPERSEDED registration, which is where it was made
    old = json.load(open("/home/alphabot/gazbot7/data/prereg_gap.json"))
    assert "BEFORE ANY OUTCOME" in old["amendments"][0]["⚠ integrity"].upper()
    assert old["STATUS"].startswith("SUPERSEDED"), "the void registration must say so"


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


def test_the_rolling_window_is_declared_and_argued_from_mechanism():
    """★★★2026-09-25. Operator: "theyve been the same since i woke up this morning." The endpoints
    were CORRECT — the CVD high was set 00:26Z, the low 05:25Z, read at 09:46Z — but the anchor was
    not. A session range spans up to 24h (so a US reading is taken against overnight ASIA extremes)
    and IT ONLY EVER GROWS, so the gauge loses resolution as the day ages.
    ⚠ 180 min is argued from mechanism — it spans a full leg (his median is 43min) without reaching
    into the previous session — NOT chosen from a measured result."""
    p = json.load(open(PREREG))
    assert p["frozen"]["range_anchor"].startswith("ROLLING 180")
    assert "NOT from any measured result" in p["frozen"]["range_anchor_why"]
    src = open(SRC, encoding="utf-8").read()
    assert int(re.search(r"^WINDOW_MIN = (\d+)", src, re.M).group(1)) == 180


def test_the_cvd_LEVEL_did_not_roll_only_its_scale():
    """⚠ The CVD number means "net aggression since 22:00Z" and he has learned it that way.
    Rolling the level too would silently redefine the number under him."""
    assert "cvd_level_is_unchanged" in json.load(open(PREREG))["frozen"]


def test_the_superseded_episodes_are_archived_not_deleted_and_not_counted():
    """⚠⚠ A study whose discarded data cannot be inspected is not auditable. 25 episodes were
    collected under the session-anchored rule; they are kept, and explicitly excluded."""
    import os
    assert os.path.exists("/home/alphabot/gazbot7/data/gap_log_session_anchored.jsonl.superseded")
    st = json.load(open(PREREG))["in_sample_status"]
    assert "MUST NOT be counted" in st and "CORRECTION" in st


def test_the_false_statement_is_recorded_rather_than_quietly_fixed():
    """★★★ An earlier draft of the registration asserted 'nothing had been collected'. 25 episodes
    existed. It was written from an `ls` that had failed moments earlier rather than a check that
    succeeded — the same shape as grepping an empty file for failures and reading zero as green.
    ⚠ A scientific record that silently corrects itself is worth less than one that shows the
    correction, because the reader cannot tell which other claims were written the same way."""
    p = json.load(open(PREREG))
    assert "⚠ a false statement was caught in this file" in p
