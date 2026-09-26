"""ENTRIES TODAY — a discipline mirror on the line he already reads (2026-09-26).

★★★ Operator, reviewing his own week: "i think i got tempted to trade into lots of little runs all
day... my original successes were trading more macro moves not just little runs. but need to be
disciplined to not get excited and trade chop."

MEASURED, and he was right:
    09-16   8 entries   55m median   +$1,477.50
    09-17  15 entries   50m median   +$1,546.50
    09-20   7 entries   98m median   +$1,464.00
    09-23  33 entries   14m median     -$613.50
    09-24  36 entries    5m median      +$55.50
By hold band, everything he has made sits in the MIDDLE: under-15m -$2,257 / 68 entries · 30-60m
+$5,828 / 33 · 1-3h +$4,276 / 31 · over-3h -$7,313 / 24.

⚠ Hold time is partly an OUTCOME (a winner gets held, a loser gets cut), which inflates that middle
band. ENTRY COUNT is a pure DECISION — which is why the count, not the hold, is what goes on screen.
"""
WEB = "/home/alphabot/gazbot7/src/gazbot7/web.py"
JS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.js"


def _code(src):
    b = src.split('"""', 2)
    src = b[2] if len(b) > 2 else src
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def _fn(path, name):
    return open(path, encoding="utf-8").read().split(f"def {name}(", 1)[1].split("\ndef ", 1)[0]


def test_it_counts_ENTRIES_not_exit_rows():
    """⚠⚠ The rows in `trades` are scale-out EXITS of one decision. Counting them would have shown
    him 41 "entries" on a 36-entry day — useless in the one direction that matters."""
    c = _code(_fn(WEB, "entries_today"))
    assert 'r["opened_at"][:15]' in c and 'entry_price' in c
    assert "len(ents)" in c


def test_it_counts_from_opened_at_on_the_22Z_session():
    """⚠ From OPENED, so the position he is in RIGHT NOW counts — a count that excluded the open
    trade would always be one behind the decision he just made.
    ⚠ And the 22:00Z anchor, like every other "today" on this page. A second definition of today is
    how the header and the day table came to disagree by $330."""
    c = _code(_fn(WEB, "entries_today"))
    assert "opened_at >= ?" in c and "hour=22" in c


def test_it_is_a_MIRROR_and_can_never_block_or_page():
    """⚠⚠⚠ His good sessions ran 7-15 entries on NINE sessions of evidence — nowhere near enough to
    gate a decision on. The colour exists to be NOTICED, not obeyed."""
    c = _code(_fn(WEB, "entries_today"))
    for forbidden in ("notify", "gate_switches", "day_rider_claim", "off"):
        assert forbidden not in c, f"entries_today references {forbidden}"


def test_the_bands_are_labelled_descriptive_not_fitted():
    src = open(WEB, encoding="utf-8").read().split("def entries_today(", 1)[1].split("\ndef ", 1)[0]
    assert "DESCRIPTIVE BANDS" in src and "not a fitted threshold" in src


def test_it_costs_no_vertical_space():
    """⚠ It goes into `hold-meta`, a line that already exists. The TRADE tab's one-screen budget is
    not negotiable and a new row would have been the wrong trade."""
    js = open(JS, encoding="utf-8").read()
    assert 'setHtml("hold-meta", "flat" + entriesTag())' in js
    assert "entriesTag" in js
    assert 'id="entries-row"' not in open(
        "/home/alphabot/gazbot7/src/gazbot7/web_static/app.html", encoding="utf-8").read()


def test_the_coloured_markup_is_written_with_setHtml_not_setTxt():
    """⚠ entriesTag() returns a coloured <b>. setTxt sets textContent and would have printed
    `<b class="warn">12</b>` on screen as literal text."""
    js = open(JS, encoding="utf-8").read()
    assert 'setTxt("hold-meta"' not in js, "hold-meta must use setHtml now that it carries markup"
