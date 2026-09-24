"""CUMULATIVE DELTA AND THE DIVERGENCE FLAG (2026-09-24).

Operator, on FLOW: "its essentially 30 seconds delayed? so the tape has already done the
corresponding move? if so its useless."

He was WRONG about the delay — a 30s WINDOW ends NOW and its newest trade is ~0.3s old — and RIGHT
about the uselessness, for a better reason. MEASURED over 6h of tape: an episode of |flow|>=0.20
has a MEDIAN LIFE OF 3 SECONDS (75th pct 9s; only 7% outlast 30s; NONE outlast 60s). The thing
being averaged lives three seconds and the average is thirty seconds long. Not stale DATA — a
stale QUESTION, and a shorter window would only flicker on 3-second noise.

CVD answers the question he actually asked: an average forgets, a running total does not.
"""
WEB = "/home/alphabot/gazbot7/src/gazbot7/web.py"
JS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.js"
HTML = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.html"


def _code(src):
    b = src.split('"""', 2)
    src = b[2] if len(b) > 2 else src
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def _fn(path, name):
    return open(path, encoding="utf-8").read().split(f"def {name}(", 1)[1].split("\ndef ", 1)[0]


def test_it_is_incremental_because_a_full_scan_is_too_slow_to_poll():
    """⚠⚠⚠ PERFORMANCE IS CORRECTNESS HERE. A full-session scan is ~994,000 ticks and MEASURED
    112-154ms, growing all session, against a page that polls every ONE SECOND. Incremental brings
    it to 4-5ms. If someone 'simplifies' this back to a single SUM, the dashboard starts burning a
    seventh of a core continuously."""
    c = _code(_fn(WEB, "cvd_meter"))
    assert 'ts_ms>?' in c, "it must read only ticks NEWER than the last it saw"
    assert 'st["last"]' in c


def test_the_increment_is_locked():
    """⚠ ThreadingHTTPServer — one thread per request. Two concurrent polls would BOTH apply the
    same increment to the running total without the lock, and the error is permanent for the
    session because the total never recomputes."""
    w = open(WEB, encoding="utf-8").read()
    assert "_CVD_LOCK = threading.Lock()" in w
    assert "with _CVD_LOCK:" in _code(_fn(WEB, "cvd_meter"))


def test_neutral_contributes_nothing():
    """⚠ 13% of the tape, and nobody crossed the spread for it. Counting it either way invents
    pressure that did not exist."""
    c = _code(_fn(WEB, "cvd_meter"))
    assert 'a == "buy"' in c and 'a == "sell"' in c and "continue" in c


def test_extremes_track_the_running_total_not_the_increments():
    """⚠ max(deltas) would be the largest single TRADE — a different and useless number. The
    divergence compares where CVD sits in ITS OWN session range, so the range must be the range of
    the cumulative line."""
    c = _code(_fn(WEB, "cvd_meter"))
    assert 'st["cvd"] > st["hi"]' in c and 'st["cvd"] < st["lo"]' in c


def test_the_session_anchor_matches_the_rest_of_the_page():
    """⚠ A SECOND definition of "today" on one dashboard is how the header and the day table came
    to disagree by $330 and cost him an evening doubting a book that reconciles to the cent."""
    c = _code(_fn(WEB, "cvd_meter"))
    assert "hour=22" in c and "timedelta(days=(0 if now.hour >= 22 else 1))" in c


def test_the_cache_is_cleared_when_the_session_rolls():
    """⚠ Accumulating across the 22:00Z roll would carry yesterday's pressure into today forever."""
    assert "_CVD.clear()" in _code(_fn(WEB, "cvd_meter"))


def test_divergence_compares_two_scale_free_positions():
    """★ Both sides are 0..1 positions within their own session range, so the rule needs no tuned
    point threshold and cannot drift with volatility."""
    c = _code(_fn(WEB, "cvd_meter"))
    assert "px_pos" in c and "cvd_pos" in c
    assert "pr >= 0.85 and cr <= 0.50" in c and "pr <= 0.15 and cr >= 0.50" in c


def test_a_shut_venue_reports_absent_not_zero():
    c = _code(_fn(WEB, "cvd_meter"))
    assert "is_open" in c and 'out["open"] = False' in c


def test_the_divergence_cell_is_amber_never_a_direction():
    """⚠⚠ A divergence is NOT a side. Colouring it green or red would be the page asserting an edge
    that has not been measured — and on this desk every direction study of a disagreement has come
    back a coin."""
    js = open(JS, encoding="utf-8").read()
    blk = js.split("CVD AND THE DIVERGENCE FLAG", 1)[1].split("POSITION AGE IS A GUARD", 1)[0]
    assert 'dvEl.className = cv.divergence ? "warn" : ""' in blk
    assert '"pos"' not in blk.split("if (dvEl)", 1)[1]


def test_the_tooltip_says_the_correlation_is_not_the_point():
    """⚠⚠ CVD tracking the session move (+0.98 over 5 sessions) is near-TAUTOLOGICAL — aggressive
    buying is largely what moves price. If he reads that agreement as confirmation, the cell has
    actively misled him."""
    html = open(HTML, encoding="utf-8").read()
    seg = html.split('id="ctx-cvd"', 1)[0][-900:]
    assert "TAUTOLOGICAL" in seg.upper()


# ── THE INPUTS MUST BE VISIBLE, NOT ONLY THE VERDICT (2026-09-24) ────────────────────────────────
# ★★★ Operator: "how do u know from what youve given me about price being at the top of the session
# or not? and aggression has drained away. how do i see that" — and the answer was that he COULD
# NOT. px_pos/cvd_pos lived only in a `title` tooltip, and he is on the iPhone ~96% of the time
# where there is no hover. A flag had been built whose INPUTS were invisible, and his open position
# was then explained to him using them.

def test_the_two_positions_are_rendered_not_only_in_a_tooltip():
    """⚠⚠ A DERIVED VERDICT WHOSE INPUTS CANNOT BE SEEN IS UNAUDITABLE. "in line" is something he
    can neither check nor disagree with nor learn to read. The pair lets him watch a divergence
    APPROACH instead of only hearing it arrive.
    ⚠ There is NO HOVER ON A PHONE — a `title` is not a display, it is a desktop footnote."""
    js = open(JS, encoding="utf-8").read()
    blk = js.split("if (dvEl)", 1)[1].split("\n    }", 1)[0]
    body = blk.split("dvEl.title", 1)[0]          # what is actually WRITTEN INTO THE CELL
    assert "px_pos" in blk and "cvd_pos" in blk
    assert "textContent" in body and "Math.round(pp * 100)" in body and "Math.round(cp * 100)" in body


def test_the_label_says_which_number_is_which():
    """⚠ A bare '81·43' is two unexplained numbers. The label has to carry the order."""
    html = open(HTML, encoding="utf-8").read()
    seg = html.split('id="ctx-div"', 1)[0][-200:]
    assert "PX" in seg and "CVD" in seg


def test_the_verdict_word_is_not_what_gets_displayed():
    """★ The COLOUR carries the verdict; the CELL carries the evidence. Showing the word instead
    would throw away the numbers at exactly the moment they matter most."""
    js = open(JS, encoding="utf-8").read()
    body = js.split("if (dvEl)", 1)[1].split("dvEl.title", 1)[0]
    assert "toUpperCase()" not in body, "the verdict word is back in the cell, hiding the inputs"
