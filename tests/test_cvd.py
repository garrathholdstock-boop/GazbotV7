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
    # ★2026-09-25 rewritten for the rolling window. The INVARIANT is unchanged — the extremes must
    # be of the RUNNING TOTAL — but it is now expressed over the per-minute series rather than a
    # pair of incrementally-updated fields. ⚠ The first version of this test asserted the OLD
    # MECHANISM and failed on a correct change; assert the invariant, never the implementation.
    assert 'st["series"].append([mm, st["cvd"]])' in c, "each point must be the RUNNING total"
    assert 'vals = [x[1] for x in st["series"]]' in c
    assert "max(vals)" in c and "min(vals)" in c


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


# ── THE RANGE GAUGES — a percentage needs its endpoints (2026-09-24) ─────────────────────────────
# Operator, the moment he understood PX·CVD % is a POSITION and not a share of a quantity: "can you
# put the high and low of both price and that somewhere for me?"
# ⚠ A percentage without its endpoints is a number he must TAKE ON TRUST. With them he can do the
# arithmetic himself — the difference between an instrument he checks and an oracle he ignores.

def test_both_ranges_show_their_endpoints():
    html = open(HTML, encoding="utf-8").read()
    for i in ("rg-px-lo", "rg-px-hi", "rg-cv-lo", "rg-cv-hi", "rg-px-dot", "rg-cv-dot"):
        assert i in html, f"{i} missing from the range strip"


def test_the_dot_reuses_the_flags_own_positions():
    """⚠⚠ NEVER RECOMPUTE THE POSITION HERE. If the gauge derived its own, the gauge and the
    divergence flag could disagree and nothing on the page would say which was right — two
    surfaces answering one question differently is this desk's $330 lesson."""
    js = open(JS, encoding="utf-8").read()
    fn = js.split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "cv.px_pos" in fn and "cv.cvd_pos" in fn
    # ⚠ SCOPE THE BAN TO THE MARKER PLACEMENT. The first version of this test forbade ALL division
    # in the function, and then failed on the ZERO TICK — a genuinely different quantity (where 0
    # falls on the scale) that the server does not send and which MUST be derived here. A test that
    # bans a technique rather than naming the invariant blocks correct work; the invariant is that
    # the DOT's position is the server's, so the gauge and the flag can never disagree.
    put = fn.split("const put =", 1)[1].split("};", 1)[0]
    assert "/ (" not in put, "the dot position is being recomputed instead of reusing the server's"


def test_the_dot_is_clamped():
    """⚠ px_pos is computed server-side from bars while `last` comes from a possibly newer bar, so
    a value fractionally outside 0..1 is reachable — and would park the marker outside its track."""
    fn = open(JS, encoding="utf-8").read().split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "Math.max(0, Math.min(1," in fn


def test_the_marker_is_centred_on_its_value():
    """⚠ Without translateX(-50%) every reading sits half a marker high — the kind of quiet offset
    nobody goes looking for because the display still looks correct."""
    css = open("/home/alphabot/gazbot7/src/gazbot7/web_static/app.css", encoding="utf-8").read()
    rule = css.split(".rg .tk em{", 1)[1].split("}", 1)[0]
    assert "translateX(-50%)" in rule


def test_the_strip_cannot_push_the_page_into_a_scroll():
    """⚠ The whole TRADE tab is built to fit one phone screen. A growing strip would undo that;
    fixed height means the elastic chart above gives up the space instead."""
    css = open("/home/alphabot/gazbot7/src/gazbot7/web_static/app.css", encoding="utf-8").read()
    rule = css.split(".ranges{", 1)[1].split("}", 1)[0]
    assert "flex:0 0 auto" in rule


def test_the_cvd_gauge_marks_where_zero_falls():
    """★★★ Operator, reading 43%: "so does 43% mean its back on the sellers side?" — NO, and the
    gauge could not tell him. The scale is anchored to TODAY'S EXTREMES, so zero is NOT the
    midpoint: against a −8,072/+12,469 range it sat at 39%. Without the tick, anything under 50%
    reads as "sellers ahead" when it can mean "still above flat". He made that exact misreading
    within a minute, which is the design inviting it rather than him misreading it."""
    html = open(HTML, encoding="utf-8").read()
    assert 'id="rg-cv-zero"' in html
    fn = open(JS, encoding="utf-8").read().split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "(0 - lo) / (hi - lo)" in fn


def test_the_zero_tick_hides_when_zero_is_off_the_scale():
    """⚠ A one-sided session (CVD never crosses zero) would otherwise pin the tick to an end and
    imply a neutral point that is not on the scale at all."""
    fn = open(JS, encoding="utf-8").read().split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "lo <= 0 && hi >= 0" in fn and "z.hidden" in fn


def test_the_cvd_track_is_heat_coded_by_SIDE_not_by_position():
    """★ Operator: "heat map code them to show buy or sell? the cvd one at least."
    ⚠⚠ THE SPLIT IS AT ZERO, NOT AT THE MIDPOINT. Colouring the left half red and the right half
    green would repeat the exact error that made him ask "does 43% mean its back on the sellers
    side?" — zero sat at 39% of the range that day, so the midpoint is not neutral."""
    fn = open(JS, encoding="utf-8").read().split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "linear-gradient(to right" in fn
    assert "(0 - lo) / (hi - lo)" in fn, "the split must be computed at zero"
    assert "50%" not in fn.split("linear-gradient", 1)[1][:200], "the split is hard-coded to mid"


def test_the_dot_colour_follows_the_SIGN_of_cvd():
    """⚠ Sign and range-position DISAGREE whenever the range is lopsided — on 2026-09-24 CVD was
    +1,137 (buyers ahead) while sitting at 45% of its range. He asked which SIDE we are on, and
    that is the sign."""
    fn = open(JS, encoding="utf-8").read().split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "cv.cvd > 0" in fn and "cv.cvd < 0" in fn


def test_a_one_sided_session_colours_the_whole_track():
    """⚠ Drawing a split at a zero that is not on the scale would be a lie about where neutral is."""
    fn = open(JS, encoding="utf-8").read().split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "lo > 0 ?" in fn


def test_the_price_track_is_tinted_at_VWAP_not_at_the_midpoint():
    """★ "High in the range" carries no inherent side; ABOVE OR BELOW THE DAY'S AVERAGE PRICE does.
    ⚠ VWAP is rarely the midpoint, so "above half" and "above VWAP" are different statements — the
    split must be computed, and the tick drawn, exactly as the CVD gauge's zero is."""
    fn = open(JS, encoding="utf-8").read().split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "(vw - plo) / (phi - plo)" in fn
    assert 'id="rg-px-vwap"' in open(HTML, encoding="utf-8").read()


def test_the_price_dot_colour_follows_side_of_vwap_not_range_position():
    fn = open(JS, encoding="utf-8").read().split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "se.last > vw" in fn and "se.last < vw" in fn


def test_vwap_outside_the_range_leaves_the_track_plain():
    """⚠ VWAP can sit outside the session range after a gap. A tick pinned to an end would assert
    a boundary that is not on the scale — the same fault the CVD zero tick guards against."""
    fn = open(JS, encoding="utf-8").read().split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "vw >= plo && vw <= phi" in fn and 'ptk.style.background = "var(--line2)"' in fn


# ── THE RANGE ROLLS (2026-09-25) ─────────────────────────────────────────────────────────────────
# Operator: "are the bottom and top range numbers on the cvd horizontal chart changing? theyve been
# the same since i woke up this morning." They were CHANGING CORRECTLY — the CVD high was set at
# 00:26Z and the low at 05:25Z, and he read them at 09:46Z. The behaviour was right and the ANCHOR
# was wrong: a session range spans up to 24h, so by the US open he reads position against overnight
# ASIA extremes; and IT ONLY EVER GROWS, so the gauge gets duller as the day ages.

def test_the_range_is_a_rolling_window_not_the_session():
    w = open(WEB, encoding="utf-8").read()
    assert 'CVD_WINDOW_MIN = int(os.environ.get("CVD_WINDOW_MIN", "180"))' in w
    c = _code(_fn(WEB, "cvd_meter"))
    assert "cut = (int(now.timestamp()) // 60) - CVD_WINDOW_MIN" in c


def test_the_price_range_uses_the_SAME_window():
    """⚠⚠ Two scales measured over different spans cannot be compared — and comparing them IS the
    divergence. A rolling CVD against a session price range would be a silent category error."""
    c = _code(_fn(WEB, "cvd_meter"))
    assert "win0 = int(now.timestamp()) - CVD_WINDOW_MIN * 60" in c
    assert "(win0, win0)" in c, "the price query must use the rolling window, not the session open"


def test_the_cvd_LEVEL_stays_session_cumulative():
    """⚠ The NUMBER means "net aggression since 22:00Z" and he has learned it that way. Only the
    SCALE rolls. Rolling the level too would silently redefine the number under him."""
    c = _code(_fn(WEB, "cvd_meter"))
    # the running total is still seeded at the session open and never reset by the window
    assert 'st = {"last": op - 1, "cvd": 0.0, "series": []}' in c
    assert "st[\"cvd\"] = 0" not in c.split("for r in rows")[1], "the level must not reset"


def test_the_series_is_one_point_per_minute_not_per_tick():
    """⚠ Per-tick would hold ~1M points in memory for a 3h window on a busy session."""
    c = _code(_fn(WEB, "cvd_meter"))
    assert 'r["ts_ms"] // 60000' in c and 'st["series"][-1][0] == mm' in c


def test_trimming_happens_after_appending():
    """⚠ A cold start replays the WHOLE session to rebuild the running total. Without a trim after
    that replay, the series would carry a 24h curve forever and the window would be a fiction."""
    c = _code(_fn(WEB, "cvd_meter"))
    assert c.index('st["series"] = [x for x in st["series"] if x[0] >= cut]') > c.index('st["series"].append')


def test_the_gauge_labels_the_WINDOW_not_the_session():
    """⚠⚠⚠2026-09-25 IT DID NOT. cvd_meter computed the window's price extremes and THREW THEM AWAY,
    so the gauge fell back to session.low/high — printing SESSION endpoints beneath a dot positioned
    on the 3-HOUR scale. Measured: labels 30680.00 → 30998.50 against a real window of
    30838.25 → 30952.50, px_pos 43% where the printed numbers imply 65%.
    ⚠ THE EARLIER TEST PASSED BECAUSE IT CHECKED THE QUERY, NOT THE DISPLAY. `(win0, win0)` was
    correct all along. Assert what the PAGE shows, not what the server computes."""
    c = _code(_fn(WEB, "cvd_meter"))
    assert 'out["px_lo"], out["px_hi"] = px["lo"], px["hi"]' in c, "the window endpoints must ship"
    js = open(JS, encoding="utf-8").read()
    fn = js.split("function ranges()", 1)[1].split("})();", 1)[0]
    assert "cv.px_lo != null ? cv.px_lo : se.low" in fn, "the gauge must prefer the window"
    # and the dot's scale and the printed labels must come from the same place
    assert fn.index("cv.px_lo") < fn.index("cv.px_pos"), "labels and marker must share one scale"
