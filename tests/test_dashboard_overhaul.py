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
    # ⚠ guarded-but-absent: these are read through setTxt/setHtml, which no-op on a missing id.
    # 2026-09-24 the TRADE merge removed their elements; the WRITES are all guarded (there is a
    # separate test for that) so a READ is harmless.
    known = {"hold-svg", "ctx-breadth", "hold-meta", "symnote"}
    assert (ids - have) <= known, f"unguarded missing ids: {sorted(ids - have - known)}"


def test_tabs_and_panels_pair_exactly():
    """⚠ A tab with no panel is a dead button; a panel with no tab is unreachable ON THE PHONE,
    where panels are shown one at a time — and he lives on the phone."""
    h = open(HTML).read()
    btn = set(re.findall(r'<button class="tab[^"]*" data-tab="([a-z]+)"', h))
    pan = set(re.findall(r'<section class="panel[^"]*" id="p-[a-z]+" data-tab="([a-z]+)"', h))
    assert btn == pan, f"unpaired: {btn ^ pan}"
    assert btn == {"trade", "days", "trades"}, f"tab set drifted: {sorted(btn)}"


def test_the_retired_panels_and_their_fetches_are_both_gone():
    """⚠ Removing a panel but leaving its fetch keeps paying for a payload nobody renders; leaving
    its RENDERER is what throws. Both halves have to go."""
    js, h = open(JS).read(), open(HTML).read()
    for dead in ("p-tourn", "p-exec", "p-desk", "p-chart", "p-hold"):
        assert dead not in h, f"{dead} panel survived"
    for ep in ("api/futures/tournament", "api/futures/execution", "api/futures/promotion"):
        assert ep not in js, f"{ep} is still fetched by a page that renders none of it"
    for fn in ("renderTournament(", "renderExec(", "renderPromotion(", "renderDesk(", "renderGates("):
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
    # ★2026-09-24 four, not ten — he kept ATR/ER/RVOL and POS AGE was added because it is the only
    # one with a measured price attached (-$7,023 across 22 holds over 3h).
    for k in ("ctx-atr", "ctx-er", "ctx-rvol", "ctx-posage"):
        assert f'id="{k}"' in h, f"metric {k} missing from the strip"


def test_the_removed_metrics_are_gone_from_the_strip():
    """★2026-09-24 leg, tunnel, session H/L, VWAP stretch, breadth and next-event were dropped on
    his instruction ("delete all other stuff"). ⚠ The direction-naming guard they carried has NOT
    been lost — it lives in tests/test_leg_watch.py, on the message that actually shows the number.
    A DOWN leg reading '+32pt' is a number that reads as its own negation, and that is still
    asserted where it matters."""
    h = open(HTML).read()
    for gone in ("ctx-leg", "ctx-tunnel", "ctx-range", "ctx-vwap", "ctx-event"):
        assert f'id="{gone}"' not in h, f"{gone} survived a deletion he asked for"

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
    # ⚠ There is more than one phone breakpoint now (the TRADE tab added its own), so `rindex` no
    # longer finds "the" one — check EVERY 899px block collectively.
    blocks = "".join(css.split("@media(max-width:899px)")[1:])
    assert "#days-tbl" in blocks, "no phone breakpoint adjusts the day table"
    assert ".orb" in blocks, "no phone breakpoint sizes the action buttons"


def test_the_desktop_grid_matches_the_phone_structure():
    """★2026-09-24 Desktop rebuilt to the same three panels. Two layouts that diverge is how bugs
    hide in the gap between them — which is exactly what happened with the tournament panel."""
    css = open(CSS).read()
    assert "#p-trade{grid-column:1;grid-row:1 / span 2}" in css
    for dead in ("#p-exec{", "#p-tourn{", "#p-chart{", "#p-hold{", "#p-desk{"):
        assert dead not in css, f"{dead} rule survived its panel"


def test_the_trade_count_badge_no_longer_reads_the_tournament_only_field():
    """★★ It showed '0 trades' beside '+$1,630' on a FIFTEEN-trade day. `trades_today` is
    tournament-only — the same bug fixed for the P&L in August and never fixed for the count."""
    js = open(JS).read()
    i = js.index('$("tb-trades")')
    assert "trades_rider" in js[max(0, i - 700):i + 120], "the count badge still reads tournament-only"



def _drill_block(js: str) -> str:
    """The drill-row builder, sliced at a STRUCTURAL boundary.

    ⚠ This used a fixed character window (js[i:i+1800]) and broke the moment a comment was added
    above the return — the FIFTH time on this desk a fixed-width slice has failed for reasons
    unrelated to the invariant it was guarding. Slice to the end of the .map(...).join("") instead:
    that boundary moves with the code.
    """
    i = js.index("const sub = (r.trades || []).map")
    j = js.index('.join("");', i)
    return js[i:j]


def test_drill_points_are_DIRECTION_CORRECTED():
    """★★★ A SHORT THAT FALLS IS A WINNER. Rendering exit-minus-entry raw would print every
    profitable short as a negative number — a value reading as its own negation, the same defect
    fixed in leg_watch's own messages on 2026-09-15. Verified against the live book: the 08:11
    SHORT on 2026-09-18 ran 29913.00 -> 29890.25 for +$176, and must read +22.8pt."""
    block = _drill_block(open(JS).read())
    assert 't.side === "SHORT" ? -1 : 1' in block, "points are no longer direction-corrected"
    assert "(t.exit - t.entry) * sgn" in block


def test_the_drill_shows_what_he_asked_for():
    """Operator: "i want time of day. points. p&l green or red." """
    block = _drill_block(open(JS).read())
    assert 'class="tm"' in block, "time of day missing"
    assert 'class="pt ' in block, "points column missing"
    assert 'class="pl ' in block, "P&L column missing"
    # both the points and the P&L must carry the sign colour, not just the P&L
    assert block.count("${cls}") >= 2, "points and P&L are not both colour-coded"


def test_the_green_palette_variable_is_the_real_one():
    """⚠ It is --grn, NOT --green. The first cut wrote var(--green,#3fbf7f): the variable does not
    exist, so every positive number silently rendered in an off-palette fallback while negatives
    used the real --red. A colour that is nearly right is harder to spot than one obviously wrong."""
    css = open(CSS).read()
    rules = [ln for ln in css.splitlines() if not ln.strip().startswith("/*") and "--green" in ln]
    assert not rules, f"an undefined --green survives in a rule: {rules}"
    assert ".pos{color:var(--grn)}" in css


def test_a_winner_and_a_loser_are_separable_without_reading_a_digit():
    """★ Phone-first: a left accent bar coloured by outcome, so the row reads at a glance."""
    css = open(CSS).read()
    assert "tr.dt.w > td:first-child{border-left-color:var(--grn)}" in css
    assert "tr.dt.l > td:first-child{border-left-color:var(--red)}" in css


def test_the_drill_degrades_rather_than_wraps_on_a_narrow_phone():
    """⚠ Seven columns will not fit a phone. Dropping the two least important beats a wrapped row
    or a sideways scroll — he reads this one-handed."""
    css = open(CSS).read()
    i = css.rindex("@media(max-width:560px)")
    assert "td.px{display:none}" in css[i:]


def test_prices_are_fixed_to_two_decimals():
    """★★ WHY 2026-09-15 "opened very strangely". Its BADFILL row is an AVERAGE of fabricated fills
    and carries FOUR decimals (29306.625 -> 29269.3125) where every other row is clean 2dp, so that
    one row re-flowed the whole table. MNQ ticks in 0.25, so 2dp is exact for any real price; an
    averaged one rounds, and that row is struck through anyway."""
    block = _drill_block(open(JS).read())
    assert "Number(v).toFixed(2)" in block, "prices are no longer width-stable"
    assert "${px(t.entry)}" in block and "${px(t.exit)}" in block


def test_the_sub_table_has_fixed_column_widths():
    """⚠ Formatting alone is not enough — a rogue value must be CLIPPED, not allowed to shove every
    other column sideways."""
    css = open(CSS).read()
    assert "#days-tbl table.sub{table-layout:fixed}" in css
    for w in ("td.tm{", "td.pt{", "td.pl{"):
        assert w in css, f"{w} lost its pinned width"


def test_quantity_renders_as_an_integer():
    """⚠ The DB stores qty as a float, so it rendered "4.0" on every single row."""
    assert "Math.round(t.qty)" in _drill_block(open(JS).read())


def test_long_holds_render_as_hours():
    """⚠ 2026-09-15's last trade ran 421 minutes to the 20:40 flat and sat beside 16m neighbours as
    a raw "421m". It is also the ABANDONMENT pattern — over-8h holds are 0 winners from 4 — so it
    should read as what it is."""
    block = _drill_block(open(JS).read())
    assert "held < 120" in block and 'padStart(2, "0")' in block
    assert '"20:40 flat"' in block, "CLOCK_FLAT no longer reads as the hard flat"


def test_the_day_table_counts_by_CLOSED_at_like_the_header():
    """★★★ 2026-09-23: the header said $857.50 and this table said $527.50 — a $330 gap caused by a
    SINGLE carry-in trade (id 986: opened 09-22 14:33, closed 09-23 06:59). Both were defensible
    answers to DIFFERENT questions, which is worse than one wrong number: nothing on the page told
    him which to believe, and he spent an evening doubting a book that reconciles to IBKR to the
    cent. Every surface must answer the SAME question."""
    w = open(WEB).read()
    i = w.index("def days_json(")
    body = w[i:i + 3600]
    assert "date(closed_at) >= date('now', ?)" in body, "the day table is back on opened_at"
    assert 'r["closed_at"][:10]' in body, "days are keyed on the wrong timestamp"
    assert '"basis": "closed_at"' in body, "the basis is no longer declared in the payload"


def test_a_carried_trade_is_MARKED_in_the_drill():
    """⚠ A trade that opened on an earlier day shows only a TIME in the drill. Unmarked, that time
    implies it started today — the column would simply lie."""
    w, js = open(WEB).read(), open(JS).read()
    assert '"carried": x["opened_at"][:10] != x["closed_at"][:10]' in w
    assert "t.carried" in js and "opened " in js, "the drill does not mark or explain a carry-in"


# ── 2026-09-24: the TRADE tab ─────────────────────────────────────────────────────────────────

def test_no_renderer_writes_to_an_element_that_no_longer_exists():
    """★★★ THE ONE THAT MATTERS, AGAIN. Merging DESK/CHART/HOLD into TRADE removed EIGHT elements
    that renderers still wrote to. $() returns null for a missing id, so ONE unguarded write throws
    inside the render loop and the WHOLE dashboard goes blank with no error he can see. That
    failure nearly shipped in the 09-18 rebuild too — this is the test that catches it."""
    import re as _re
    js, html = open(JS).read(), open(HTML).read()
    have = set(_re.findall(r'id="([a-zA-Z0-9_-]+)"', html))
    bad = [m.group(0) for m in _re.finditer(
        r'\$\("([a-zA-Z0-9_-]+)"\)\.(textContent|innerHTML|style|onclick|disabled|className|value)', js)
        if m.group(1) not in have]
    assert not bad, f"unguarded writes to removed elements: {bad}"


def test_the_four_actions_exist_and_are_circular():
    h, css = open(HTML).read(), open(CSS).read()
    for k in ("buy-long", "buy-short", "flat-all", "sa-btn"):
        assert f'id="{k}"' in h, f"action {k} missing"
    assert ".orb{" in css and "border-radius:50%" in css, "the actions are not circular"
    assert "aspect-ratio:1/1" in css


def test_flatten_takes_no_PIN_but_buy_and_sell_do():
    """★ His instruction: FLATTEN only ever REDUCES risk and friction on a kill switch costs money.
    BUY/SELL place an order and keep the PIN."""
    js = open(JS).read()
    i = js.index('const fl = $("flat-all")')
    flat = js[i:js.index("/* ── STEP AWAY", i)]
    assert "window.prompt" not in flat, "FLATTEN asks for a PIN"
    assert "window.confirm" in flat, "FLATTEN lost its confirm — a circular target is easy to mis-hit"
    j = js.index("const send = (side) =>")
    buy = js[j:js.index('const bl = $("buy-long")', j)]
    assert 'window.prompt("PIN")' in buy, "BUY/SELL no longer ask for a PIN"


def test_buy_size_is_fixed_at_four():
    js = open(JS).read()
    assert "const BUY_LOTS = 4;" in js
    assert "qty: BUY_LOTS" in js, "the order no longer sends the fixed size"


def test_step_away_looks_different_when_armed():
    """⚠ A guard that looks identical armed and disarmed is one he will forget he set."""
    js, css = open(JS).read(), open(CSS).read()
    assert '"orb away" + (sa.armed ? " armed" : "")' in js
    assert ".orb.away.armed{" in css, "the armed state has no distinct styling"
    assert ".orb.away{" in css and "#16326e" in css, "STEP AWAY is not the dark blue he asked for"


def test_only_two_take_profit_tiers():
    """★ "i only need the first 2. after that i usually flatten everything." """
    js = open(JS).read()
    assert "RIDER_USD.slice(0, 2)" in js, "the holding card still offers more than two tiers"


def test_position_age_is_banded_by_the_measured_buckets():
    """⚠ Not decoration: over-8h holds are 0 winners from 4 at -$6,612."""
    js = open(JS).read()
    i = js.index('const po = c.position, pa = $("ctx-posage")')
    block = js[i:i + 600]
    assert "ABANDONED" in block and "warn" in block


def test_pass_survived_the_merge():
    """⚠ PASS is build-queue item 1 and the blocker for ever automating his reads. It lived on the
    DESK panel; if it had not moved to TRADE the negative-example dataset would stay empty for
    ever."""
    h, js = open(HTML).read(), open(JS).read()
    assert 'id="pass-btn"' in h and 'id="pass-note"' in h
    assert 'fetch("api/control/pass"' in js


def test_buy_and_sell_are_DISABLED_while_holding():
    """★2026-09-24 The rider refuses a second entry ("already in a position — flatten before buying
    again"), which is CORRECT. But arriving as an alert after he has pressed AND typed a PIN makes a
    correct refusal feel like a broken button — he reported it as an error. Show the state instead
    of reporting it."""
    js = open(JS).read()
    assert "b.disabled = !!open" in js, "BUY/SELL are pressable while a position is open"
    i = js.index("b.disabled = !!open")
    assert "Already in a position" in js[i:i + 300], "the disabled button does not say why"
