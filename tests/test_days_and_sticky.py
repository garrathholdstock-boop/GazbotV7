"""THE DAYS TAB: 20 TRADING SESSIONS, A LIVE BAR STRIP, AND LIMITS THAT STICK (2026-09-24).

Operator: "it only shows 11 days. can we show the last 20? so a rolling 4 weeks?" · "at the top can
we have that graph that you made on the reports tab are we getting better... big green bars for big
winning days and inverse red for losing" · "can we make the step away limits stick between arms?"
"""
import re

WEB = "/home/alphabot/gazbot7/src/gazbot7/web.py"
JS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.js"
HTML = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.html"


def _code(src):
    body = src.split('"""', 2)
    src = body[2] if len(body) > 2 else src
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def _fn(path, name):
    return open(path, encoding="utf-8").read().split(f"def {name}(", 1)[1].split("\ndef ", 1)[0]


def test_n_means_trading_sessions_not_calendar_days():
    """★ THE BUG HE HIT. `date('now','-14 days')` spans two WEEKENDS, so a request for 14 returned
    11. How many calendar days hold N trading days is unknowable in advance — it depends on
    holidays — so the SQL looks back generously and the slice happens after grouping."""
    c = _code(_fn(WEB, "days_json"))
    assert "n * 2 + 14" in c, "the lookback must over-reach, not equal n"
    assert "reverse=True)[:n]" in c, "the slice to n SESSIONS must happen after grouping by day"


def test_the_page_asks_for_twenty():
    assert "api/futures/days?n=20" in open(JS, encoding="utf-8").read()


def test_the_bar_strip_shares_one_scale_for_up_and_down():
    """⚠⚠ THE SINGLE MOST MISLEADING THING A P&L CHART CAN DO is scale the up and down sides
    separately — a -$2,222 day would draw the same height as a +$857 one. One max, one zero line
    in the middle."""
    js = open(JS, encoding="utf-8").read()
    fn = js.split("function renderDayBars(", 1)[1].split("\n  }", 1)[0]
    assert "Math.abs(r.pnl || 0)" in fn and "MID = H / 2" in fn
    assert fn.count("mx") >= 2, "both directions must divide by the same maximum"


def test_the_bar_strip_runs_oldest_left():
    """⚠ days_json returns NEWEST FIRST. Reading a time axis backwards is a mistake you only notice
    after you have already drawn a conclusion from it."""
    fn = open(JS, encoding="utf-8").read().split("function renderDayBars(", 1)[1]
    assert "rows.slice().reverse()" in fn


def test_the_strip_reports_green_count_and_pnl_separately():
    """⚠ They are different questions: one big red day can outweigh nine green ones, which IS this
    desk's loss profile (the five worst days are 52% of all loss)."""
    fn = open(JS, encoding="utf-8").read().split("function renderDayBars(", 1)[1]
    assert "green" in fn and "worst" in fn and "best" in fn


def test_step_away_limits_come_from_the_server_not_localstorage():
    """★ step_away.json keeps limit_usd/take_profit_usd after firing, so the values follow him to
    any device and survive a browser wipe — and the GUARD and the PAGE then agree by construction
    rather than by coincidence."""
    js = open(JS, encoding="utf-8").read()
    fn = js.split("function stickyLimits()", 1)[1].split("})();", 1)[0]
    assert "sa.limit_usd" in fn and "sa.take_profit_usd" in fn
    assert "localStorage" not in fn


def test_sticky_limits_never_overwrite_a_field_being_typed_in():
    """⚠ A poll lands every second and would eat the keystroke he is halfway through."""
    fn = open(JS, encoding="utf-8").read().split("function stickyLimits()", 1)[1].split("})();", 1)[0]
    assert "document.activeElement" in fn


def test_the_heading_matches_what_is_fetched():
    """⚠ A panel headed 'LAST 14 SESSIONS' over 20 rows is the kind of quiet disagreement that
    makes him doubt a number that is actually right."""
    html = open(HTML, encoding="utf-8").read()
    n = int(re.search(r"days\?n=(\d+)", open(JS, encoding="utf-8").read()).group(1))
    assert f"LAST {n} SESSIONS" in html


# ── THE STICKY LIMITS WERE OVERWRITING HIM ONCE A SECOND (2026-09-25) ────────────────────────────
# ★★★ Operator: "the dashboard doesnt let me adjust the prices in the step away. i change the $500
# TP to lower and it just changes itself back to $500."
# ⚠⚠⚠ A SAFETY BUG, NOT A UI ANNOYANCE. He could type 300, look away, and arm a guard set to the
# 500 he had just REJECTED — a stop or a target he never chose, on a live position, with the page
# showing a number he did not pick.
# THE FAULT: `document.activeElement` protects the field only WHILE HE IS TYPING. The moment he taps
# Done it blurs, and the next poll — within one second — wrote the stored value back over his edit.
# On a phone every edit ends in a blur, so on a phone the feature was unusable by construction.


def _sticky():
    js = open(JS, encoding="utf-8").read()
    return js.split("function stickyLimits()", 1)[1].split("})();", 1)[0]


def test_a_stored_value_is_delivered_ONCE_not_re_imposed_every_poll():
    """★ THE FIX. Once we have delivered a given stored value, the box belongs to HIM until the
    SERVER's number changes — which happens when he arms, and arming is the act that commits it."""
    b = _sticky()
    assert "AL.saSeen[id] === want" in b, "it must remember what it already delivered"
    assert "AL.saSeen[id] = want" in b


def test_it_still_never_fights_a_keystroke_in_flight():
    """⚠ The activeElement guard was not WRONG, it was INSUFFICIENT. It stays."""
    assert "document.activeElement" in _sticky()


def test_the_seen_map_is_initialised():
    """⚠ An undefined lookup would compare undefined === want, deliver every poll, and restore the
    exact bug while the guard above looked present."""
    js = open(JS, encoding="utf-8").read()
    assert "saSeen: {}" in js


def test_the_old_unconditional_write_is_gone():
    """⚠ `if (el.value !== want) el.value = want` on every poll IS the bug. If it returns, the
    field fights him again and nothing else in this file would notice."""
    b = _sticky()
    assert "if (el.value !== want) el.value = want" not in b
