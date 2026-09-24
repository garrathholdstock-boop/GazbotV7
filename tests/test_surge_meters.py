"""PULSE AND FLOW — "is this surge backed and real?" (2026-09-24)

Operator, after RVOL was fixed and STILL read ~1.0 through a thrusty open: "i feel like i need 1
and 2. shows me if a surge is backed and real."

★ WHY NOT JUST FIX RVOL HARDER. RVOL asks "unusual FOR THIS TIME OF DAY", so it sits at ~1.0
through every open BY CONSTRUCTION — today's thrusts are compared with other days' thrusts, and the
open is the most stereotyped part of the session. No amount of correcting it makes it answer "is
this move backed", because that is a question about NOW vs THE MINUTES BEFORE IT.

⚠⚠⚠ THE MEASURED CLAIM IS ORDERING, NOT PREDICTION. 5 sessions, n=170: backed +5.25pt median over
the next 5 min vs +0.50pt unbacked. It orders correctly and it is NOT a result — minutes inside a
session are not independent draws. Pre-registered in data/prereg_surge.json for a forward verdict.
"""
import json
import re

WEB = "/home/alphabot/gazbot7/src/gazbot7/web.py"
JS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.js"
LOGGER = "/home/alphabot/gazbot7/scripts/surge_log.py"
PREREG = "/home/alphabot/gazbot7/data/prereg_surge.json"


def _fn(path, name, end="\ndef "):
    return open(path, encoding="utf-8").read().split(f"def {name}(", 1)[1].split(end, 1)[0]


def _code(src):
    """Comments AND the docstring stripped — assert what RUNS, not what the file explains.

    ⚠ This shape has now bitten FOUR times in one day. The prose that documents a rule necessarily
    quotes the thing the rule forbids, so any raw-text search finds it in the explanation and the
    test fails on correct code. Dropping `#` lines was not enough: `surge_meters` explains the
    neutral-aggressor rule in its DOCSTRING.
    """
    body = src.split('"""', 2)
    src = body[2] if len(body) > 2 else src
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def test_neutral_aggressor_is_excluded_never_split():
    """⚠⚠ 'neutral' is 13% of the MNQ tape. Assigning it pro-rata would MANUFACTURE imbalance out
    of trades nobody lifted or hit — a signal invented by the arithmetic rather than measured."""
    c = _code(_fn(WEB, "surge_meters"))
    assert "aggressor='buy'" in c and "aggressor='sell'" in c
    assert "neutral" not in c, "neutral must never appear in the flow arithmetic"


def test_pulse_has_no_cross_day_baseline():
    """★ THE WHOLE POINT. PULSE compares this minute with THIS SESSION's previous 15, so the
    Sep->Dec roll that is currently dragging RVOL's 10-day median cannot touch it. `bars` carries
    no contract column, and this is the meter that does not care."""
    c = _code(_fn(WEB, "surge_meters"))
    assert "86400" not in c, "a day offset means a cross-day baseline crept in"


def test_pulse_baseline_is_a_median():
    """⚠ One spike minute inside the lookback would raise the bar and hide the very expansion the
    meter exists to show."""
    c = _code(_fn(WEB, "surge_meters"))
    assert "sorted(prev)" in c


def test_a_shut_venue_reports_absent_not_zero():
    """⚠ A dash, never a confident 0.00x. A shut venue and a dead feed produce the same silence,
    and this desk has already read one as the other."""
    c = _code(_fn(WEB, "surge_meters"))
    assert "is_open" in c and 'out["open"] = False' in c


def test_the_ui_states_it_is_descriptive():
    """⚠⚠ Green must mean "volume is expanding", never "this will continue". The operator will act
    on this cell during a move, which is exactly when a predictive reading would cost money."""
    js = open(JS, encoding="utf-8").read()
    blk = js.split("PULSE AND FLOW", 1)[1].split("POSITION AGE IS A GUARD", 1)[0]
    assert "DESCRIPTIVE" in blk
    html = open("/home/alphabot/gazbot7/src/gazbot7/web_static/app.html", encoding="utf-8").read()
    for cell in ("ctx-pulse", "ctx-flow"):
        seg = html.split(cell, 1)[0][-700:]
        assert "DESCRIPTIVE" in seg, f"{cell} tooltip does not say it is descriptive"


def test_flow_is_rendered_signed():
    """⚠ A bare '42%' reads as a magnitude. He needs the SIDE at a glance — who is crossing."""
    js = open(JS, encoding="utf-8").read()
    assert 'sg.flow > 0 ? "+"' in js


def test_the_logger_writes_only_its_own_log():
    """⚠⚠⚠ READ-ONLY. No order path, no switch file, no request file."""
    src = open(LOGGER, encoding="utf-8").read()
    for forbidden in ("day_rider_claim", "day_rider_buy", "gate_switches", "operator_pass",
                      "placeOrder", "reqIds"):
        assert forbidden not in src, f"the surge logger references {forbidden}"


def test_the_logger_signs_continuation_by_the_surge_direction():
    """⚠ Storing a raw price delta would need re-signing at read time, and one forgotten sign flip
    inverts the entire verdict."""
    assert '* d}' in open(LOGGER, encoding="utf-8").read().replace(" ", "") or \
           '"cont_pt"' in open(LOGGER, encoding="utf-8").read()
    src = _code(open(LOGGER, encoding="utf-8").read())
    assert "* d, 2)" in src


def test_the_logger_reads_a_minute_whose_outcome_already_exists():
    """★ It logs the minute that ended HORIZON_MIN ago, so the forward outcome is already on the
    tape. A log that needs a second pass to fill outcomes in is a log that silently keeps half its
    rows."""
    src = _code(open(LOGGER, encoding="utf-8").read())
    assert "(HORIZON_MIN + 1) * 60" in src


def test_the_prereg_freezes_the_thresholds_and_admits_the_in_sample_window():
    p = json.load(open(PREREG))
    assert p["frozen"]["pulse_backed"] == 1.5 and p["frozen"]["flow_aligned"] == 0.15
    assert p["minimum_sessions"] >= 40 and p["minimum_n"] >= 400
    note = p["in_sample_not_a_result"]["note"].lower()
    assert "not evidence" in note and "found in" in note, (
        "the discovery window must be labelled as such — quoting it as the result is the whole "
        "failure this file exists to prevent")
    assert "DAY-CLUSTERED" in p["verdict_rule"], "per-observation CIs are inflated ~10x here"


def test_the_logger_thresholds_match_the_preregistration():
    """★ READ BOTH AND COMPARE — never assert the same literal in two places, which is exactly how
    a pair of constants drifts while every test still passes."""
    src = open(LOGGER, encoding="utf-8").read()
    p = json.load(open(PREREG))["frozen"]
    got = {k: float(re.search(rf"^{k.upper()}\s*=\s*([\d.]+)", src, re.M).group(1))
           for k in ("surge_pt",)}
    assert got["surge_pt"] == p["surge_definition_pt"]
    assert float(re.search(r"^PULSE_BACKED\s*=\s*([\d.]+)", src, re.M).group(1)) == p["pulse_backed"]
    assert float(re.search(r"^FLOW_ALIGNED\s*=\s*([\d.]+)", src, re.M).group(1)) == p["flow_aligned"]
    assert int(re.search(r"^HORIZON_MIN\s*=\s*(\d+)", src, re.M).group(1)) == p["horizon_min"]
