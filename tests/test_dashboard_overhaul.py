"""THE DASHBOARD, REBUILT AROUND HIS TRADING (2026-09-18).

Operator: "i want to overhaul the dashboard and make it simpler... the tournament section isnt
needed. the chart is essential. current holdings is needed. trades is needed. execution is broken
it doesnt load. neither does cube. remove." Plus a 14-day clickable history, and:
*"make sure all changes are desktop and iphone. i live on the iphone app all day!!!!!"*

★ EXECUTION WAS NOT BROKEN. It returned 200 with TWO non-empty values in the whole payload — it
measures the TOURNAMENT's order flow and the tournament no longer trades. Six panels of nothing.
"""
import json
import re
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

HTML = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.html"
JS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.js"
CSS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.css"
WEB = "/home/alphabot/gazbot7/src/gazbot7/web.py"


def test_every_id_the_js_touches_exists_in_the_page():
    """★★★ THE ONE THAT MATTERS. $() returns null for a missing element, so ONE stale id inside the
    render loop throws on every tick and takes the WHOLE dashboard with it — a removed panel turns
    into a blank page with no error the operator can see."""
    js, html = open(JS).read(), open(HTML).read()
    ids = set(re.findall(r'\$\("([a-zA-Z0-9_-]+)"\)', js))
    have = set(re.findall(r'id="([a-zA-Z0-9_-]+)"', html))
    # hold-svg is guarded; lb-* belong to renderGates, dead code that PREDATES this overhaul and is
    # never called. Anything NEW appearing here is a real break.
    known = {"hold-svg", "lb-top", "lb-bottom"}
    assert (ids - have) <= known, f"unguarded missing ids: {sorted(ids - have - known)}"


def test_tabs_and_panels_pair_exactly():
    """⚠ A tab with no panel is a dead button; a panel with no tab is unreachable ON THE PHONE,
    where panels are shown one at a time — and he lives on the phone."""
    h = open(HTML).read()
    btn = set(re.findall(r'<button class="tab[^"]*" data-tab="([a-z]+)"', h))
    pan = set(re.findall(r'<section class="panel[^"]*" id="p-[a-z]+" data-tab="([a-z]+)"', h))
    assert btn == pan, f"unpaired: {btn ^ pan}"
    assert btn == {"desk", "days", "chart", "hold", "trades"}, f"tab set drifted: {sorted(btn)}"


def test_the_retired_panels_and_their_fetches_are_both_gone():
    """⚠ Removing a panel but leaving its fetch keeps paying for a payload nobody renders; leaving
    its RENDERER is what throws. Both halves have to go."""
    js, h = open(JS).read(), open(HTML).read()
    for dead in ("p-tourn", "p-exec"):
        assert dead not in h, f"{dead} panel survived"
    for ep in ("api/futures/tournament", "api/futures/execution", "api/futures/promotion"):
        assert ep not in js, f"{ep} is still fetched by a page that renders none of it"
    for fn in ("renderTournament(", "renderExec(", "renderPromotion("):
        assert fn not in js, f"{fn} still called against DOM that no longer exists"


def test_the_safety_chip_still_has_a_live_feed():
    """★★★ THE REGRESSION THIS OVERHAUL NEARLY SHIPPED. renderSafety read STATE.tour; retiring the
    tournament PANEL also retired its fetch, so the chip that says HALTED / NAKED / UNVERIFIED
    would have sat at "SAFETY —" forever. It is GUARDED, so nothing throws and nothing complains —
    a safety indicator failing silently to a neutral face."""
    js = open(JS).read()
    i = js.index("function renderSafety()")
    body = js[i:i + 400]
    assert "STATE.ctx" in body, "the safety chip lost its feed"
    assert "STATE.tour" not in body, "the safety chip still reads the retired tournament payload"
    assert '"desk"' in open(WEB).read(), "context_json no longer carries the desk/safety block"


def test_the_metric_strip_carries_everything_he_asked_for():
    h = open(HTML).read()
    for k in ("ctx-er", "ctx-atr", "ctx-rvol", "ctx-range", "ctx-vwap",
              "ctx-leg", "ctx-tunnel", "ctx-posage", "ctx-event"):
        assert f'id="{k}"' in h, f"metric {k} missing from the strip"


def test_the_leg_readout_names_its_direction():
    """⚠ A DOWN leg rendered as a bare '+32pt' is a number that reads as its own negation — the
    exact defect fixed in leg_watch's own messages on 2026-09-15."""
    js = open(JS).read()
    i = js.index('set("ctx-leg"')
    assert "lg.dir" in js[i:i + 240], "the leg readout no longer names UP/DOWN"


def test_rvol_carries_its_contract_blind_caveat():
    """⚠ capture.db.bars has NO contract column, so a window spanning a roll compares two different
    instruments. The number must not imply a precision it does not have."""
    assert "rvol_caveat" in open(WEB).read()
    assert "rvol_caveat" in open(JS).read(), "the caveat never reaches the page"


def test_the_day_table_counts_ENTRIES_not_exit_rows():
    """⚠⚠ The rows in `trades` are scale-out EXITS of one decision — 20 rows over 2026-09-14/15 are
    9 entries. A per-row count overstates his activity ~2.5x."""
    w = open(WEB).read()
    i = w.index("def days_json(")
    body = w[i:i + 3000]
    assert "entries" in body and 'x["opened_at"], x["entry_price"], x["side"]' in body


def test_profit_factor_is_null_when_undefined_never_infinite():
    """⚠ A day with no losing trade has an UNDEFINED profit factor. Rendering it as ∞ or as a huge
    number would make a one-trade day look like the best session on record."""
    w = open(WEB).read()
    i = w.index("def days_json(")
    assert 'if gross_l > 0 else None' in w[i:i + 3000]


def test_flagged_trades_are_shown_but_not_counted():
    """⚠ BADFILL: a real trade whose PRICE came from a fabricated fill. He must SEE it; it must
    never reach a P&L — the 08-21 lesson, where an EXCLUDE: row vanished and he could not find a
    trade he had watched happen."""
    w, js = open(WEB).read(), open(JS).read()
    i = w.index("def days_json(")
    assert 'data_quality' in w[i:i + 3000] and '"flagged"' in w[i:i + 3000]
    assert "flagged" in js and "never counted" in js


def test_the_phone_layout_is_explicitly_handled():
    """★ "i live on the iphone app all day!!!!!" — the day rows must be touch targets, not hover
    affordances, and the strip must wrap rather than scroll sideways."""
    css = open(CSS).read()
    assert "#days-tbl tr.dayrow" in css
    assert "min-height:44px" in css or "min-height:48px" in css, "day rows are not touch-sized"
    i = css.rindex("@media(max-width:899px)")
    assert "#days-tbl" in css[i:], "the phone breakpoint does not adjust the day table"


def test_the_desktop_grid_gives_the_chart_three_of_four_columns():
    """★ "the chart could be bigger." And a floor on row 1, because a chart box measuring ZERO with
    no error anywhere once went unnoticed for nine days."""
    css = open(CSS).read()
    assert "#p-chart{grid-column:1 / span 3;grid-row:1}" in css
    assert "minmax(360px,1.4fr)" in css, "row 1 lost its height floor"
    for dead in ("#p-exec{", "#p-tourn{"):
        assert dead not in css, f"{dead} rule survived its panel"


def test_the_trade_count_badge_no_longer_reads_the_tournament_only_field():
    """★★ It showed '0 trades' beside '+$1,630' on a FIFTEEN-trade day. `trades_today` is
    tournament-only — the same bug fixed for the P&L in August and never fixed for the count."""
    js = open(JS).read()
    i = js.index('$("tb-trades")')
    assert "trades_rider" in js[max(0, i - 700):i + 120], "the count badge still reads tournament-only"
