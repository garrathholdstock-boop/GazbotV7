"""THE CVD GAUGE IS A SHARE OF VOLUME, NOT A POSITION IN A RANGE.

★★★2026-09-30. Operator: "rescale the cvd gauge to % of volume." He asked because he had watched it
mislead him: "cvd is hard left and tape has been grinding north". Both readings were correct — a
position-in-range gauge PINS for as long as the level keeps trending, since each new minute sets a new
3-hour extreme. Pinned-left meant "sellers are STILL net-aggressing" and reads as "sellers are spent".

Measured over 49 sessions: after a left pin, +1.0pt over the next hour against a +1.8pt baseline, fell
49% vs 48%. A coin. And the level it scaled is a thin residual — -16,301 on ~2.9M contracts is 0.5% of
volume, given a confident 0-100 scale.
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import web

SRC = "/home/alphabot/gazbot7/src/gazbot7/web.py"
JS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.js"


def test_the_scale_is_the_measured_percentile_not_an_invented_number():
    """⚠ 20% is the 99th percentile of |press| over 1,356 five-minute buckets; 12.4% is the 90%
    band. A new value needs a new measurement, which is why they are named constants."""
    assert web.PRESS_SCALE == 20.0
    assert web.PRESS_BAND == 12.4


def test_the_window_is_short_because_he_asked_for_NOW():
    assert web.PRESS_WINDOW_MIN == 5


def test_pressure_is_a_share_of_volume_so_it_CANNOT_pin():
    """★ THE WHOLE POINT. A share has fixed bounds, so no amount of persistent one-sided aggression
    can drive the marker to an end and hold it there — which is precisely what the old scale did."""
    src = open(SRC).read()
    body = src.split('out["press"]', 1)[0].rsplit("try:", 1)[1] + src.split('out["press"]', 1)[1][:400]
    assert "SUM(size)" in body, "it must divide by volume"
    assert "100.0 *" in src.split('out["press"] = ', 1)[1][:60]


def test_the_gauge_endpoints_are_the_scale_itself():
    """⚠ The old gauge's endpoints MOVED, and once printed SESSION numbers under a 3-HOUR dot —
    labels implying 65% where the marker sat at 43%. Fixed bounds cannot do that."""
    js = open(JS).read()
    block = js.split('rescale the cvd gauge to % of volume', 1)[1].split("const z =", 1)[0]
    assert 'setTxt("rg-cv-lo", "-" + sc + "%")' in block
    assert 'setTxt("rg-cv-hi", "+" + sc + "%")' in block


def test_zero_is_always_the_midpoint():
    """★ The zero tick existed because neutral drifted — it sat at 39% on 09-24 and he read 43% as
    'back on the sellers side'. On a symmetric share scale neutral is 50% by construction, so the
    entire class of bug is removed rather than patched."""
    # ⚠ Sliced by STRUCTURE with comments stripped, not by a fixed width. My first cut took 700
    # characters after the marker and the explanatory comment pushed the code past it — the same
    # fixed-slice trap that cut 2026 off after April in the event-calendar parser, and that I hit
    # once already today at 900 characters. Count what RUNS.
    js = open(JS).read()
    seg = js.split('ZERO IS NOW ALWAYS THE MIDPOINT', 1)[1].split("const cdot", 1)[0]
    code = "\n".join(l for l in seg.splitlines()
                     if not l.strip().startswith(("/*", "*", "//", "⚠", "★")))
    assert 'z.style.left = "50%"' in code
    assert "z.hidden = false" in code


def test_the_dot_colour_describes_the_SAME_span_as_the_marker():
    """⚠ The dot used to be coloured by the cumulative level while the marker showed a rolling
    window — marker and colour describing different spans."""
    js = open(JS).read()
    assert "cdot.style.background = cv.press == null" in js
    assert "cdot.style.background = cv.cvd == null" not in js


def test_the_tooltip_states_the_weakness_and_the_volume_it_rests_on():
    """⚠ r=+0.36 against price move in the same 5 minutes — real and weak. And a 5-minute reading on
    2,000 contracts is not the same statement as one on 40,000; the old gauge gave both the same
    confident dot. tunnel_watch shipped a number it had not earned; this states its own limit."""
    js = open(JS).read()
    assert "r=+0.36" in js
    assert "press_vol" in js
    assert "contracts." in js


def test_cvd_pos_SURVIVES_for_the_divergence_pair_and_the_prereg():
    """⚠⚠ scripts/gap_log.py computes its OWN positions, so the pre-registered gap study
    (data/prereg_gap_rolling.json) is untouched — but the divergence pair he audits by eye reads
    cvd_pos from here. Removing it would silently blank a number he uses."""
    src = open(SRC).read()
    assert 'out["px_pos"], out["cvd_pos"]' in src
    js = open(JS).read()
    assert "cv.cvd_pos" in js


def test_the_level_he_learned_is_unchanged():
    """⚠ 'net aggression since 22:00Z' is the meaning he has learned. Only the SCALE was rescaled."""
    src = open(SRC).read()
    assert 'out["cvd"] = int(st["cvd"])' in src


def test_the_gap_study_is_not_touched_by_this_change():
    gl = open("/home/alphabot/gazbot7/scripts/gap_log.py").read()
    assert "cvd_meter" not in gl, "gap_log must keep computing its own positions"


# ──────────────────────────────────────────────────────────────────────────────────────────────
# ★★★2026-10-02 THE TESTS ABOVE ALL ASSERT ON SOURCE TEXT, AND THAT IS WHY THEY MISSED A REAL BUG.
# The press query shipped BELOW `c.close()`, so every live call raised ProgrammingError into a bare
# `except` and the dashboard served `press: null` while all ten tests passed. My own "live" check
# built its OWN sqlite connection and printed a healthy number, so it confirmed the formula and
# never the call path. These two call `cvd_meter()` for real against a temp DB.
# ⚠ `is_open` is forced rather than read: cvd_meter returns early when the venue is shut, and a test
#   that only passes during trading hours is method trap #10 (37 tests once failed only 00-07 UTC).
# ──────────────────────────────────────────────────────────────────────────────────────────────
import sqlite3 as _sq
import time as _t
import pytest
import pytest as _pt


def _cap_db(tmp_path, ticks):
    """A capture.db with the two tables cvd_meter reads. `ticks` = (ms_ago, size, aggressor)."""
    p = tmp_path / "capture.db"
    c = _sq.connect(p)
    c.execute("CREATE TABLE ticks (symbol TEXT, ts_ms INTEGER, size REAL, aggressor TEXT)")
    c.execute("CREATE TABLE bars (symbol TEXT, timeframe TEXT, bar_ts INTEGER, "
              "high REAL, low REAL, close REAL)")
    now_ms = int(_t.time() * 1000)
    for ago, size, agg in ticks:
        c.execute("INSERT INTO ticks VALUES ('MNQ',?,?,?)", (now_ms - ago, size, agg))
    now_s = int(_t.time())
    for i in range(20):
        c.execute("INSERT INTO bars VALUES ('MNQ','5s',?,?,?,?)",
                  (now_s - i * 5, 30900.0, 30880.0, 30890.0))
    c.commit(); c.close()
    return str(p)


@_pt.fixture
def _open_venue(monkeypatch):
    from gazbot7 import session, web
    monkeypatch.setattr(session, "is_open", lambda *a, **k: True)
    web._CVD.clear()                      # never inherit another test's session state
    yield
    web._CVD.clear()


def test_press_is_populated_through_the_REAL_call_path(tmp_path, _open_venue):
    """THE REGRESSION TEST FOR THE CLOSED-CONNECTION BUG. If the query moves back below
    `c.close()`, press comes back None and this fails."""
    from gazbot7 import web
    # net = +55 - 40 = +15 over volume 150 (neutral counts in VOLUME, never in net) = +10.0%
    cap = _cap_db(tmp_path, [(10_000, 55.0, "buy"), (20_000, 40.0, "sell"),
                             (30_000, 55.0, "neutral")])
    out = web.cvd_meter(cap)
    assert out["press"] is not None, (
        "press came back None through the real call path — the symptom of the 2026-10-02 bug. "
        "Check the query still runs BEFORE c.close().")
    assert out["press"] == pytest.approx(10.0, abs=0.1), out["press"]
    assert out["press_vol"] == 150, "neutral size belongs in VOLUME even though it is not in net"
    # and the SERVER did the normalising: (10 + 20) / 40 = 0.75
    assert out["press_pos"] == pytest.approx(0.75, abs=0.01)


def test_an_off_scale_reading_CLAMPS_instead_of_running_off_the_track(tmp_path, _open_venue):
    """±20% is the 99th percentile, so real readings do exceed it. The dot must sit AT the end,
    never past it — a marker rendered outside its own track is the gauge misstating its scale."""
    from gazbot7 import web
    cap = _cap_db(tmp_path, [(10_000, 90.0, "buy"), (20_000, 10.0, "sell")])   # +80% of volume
    out = web.cvd_meter(cap)
    assert out["press"] == pytest.approx(80.0, abs=0.1)
    assert out["press_pos"] == 1.0, "must clamp to the end of the track, not overshoot it"


def test_an_empty_window_is_zero_volume_NOT_a_failed_read(tmp_path, _open_venue):
    """The None/0 discrimination is load-bearing: `press_vol: None` means the READ BROKE,
    `press_vol: 0` means it read fine and nobody traded. That distinction is what identified
    the closed-connection bug from the live payload alone."""
    from gazbot7 import web
    cap = _cap_db(tmp_path, [(9_000_000, 40.0, "buy")])    # 2.5h old — outside the 5-min window
    out = web.cvd_meter(cap)
    assert out["press"] is None
    assert out["press_vol"] == 0, "a quiet window must report 0 volume, never a None read-failure"
