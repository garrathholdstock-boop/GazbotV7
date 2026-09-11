"""The hero chart must have HEIGHT, and it must not depend on where it sits among its siblings.

*** THE 2026-09-11 BLANK DESKTOP CHART. `.hero-body` was a grid declaring SIX rows by ORDER -
ribbon, chart(1fr), tfbar, legend, sec, dtt - and sizing only the second. On 2026-09-02 the MGC
hero-chart work (6af09e0) added `.mstrip` and `#symbar`, making EIGHT children. CSS grid assigns
rows POSITIONALLY, so `.mstrip` took the one sized row and `.chart-host` slid into an `auto` row.

Its only child `#price-svg` is `position:absolute`, so it contributes NO height: the box measured
ZERO. renderHero() opens with `if (host.clientHeight === 0 ...) return;` - a guard written to skip
the HIDDEN phone tab - so it returned on every tick and drew nothing for NINE DAYS.

!! NOTHING REPORTED A FAULT. The API returned 200, the bars were 1.1 min fresh, the JS threw no
   error, the service had not restarted. Every instrument was green about something none of them
   measured - this desk's most common failure shape. The only symptom was an empty rectangle, and
   only on desktop: the phone media query sets an explicit `.chart-host` height.

WHAT THESE TESTS PIN, and deliberately not more: they cannot render a page, so they do not prove
the chart is visible. They prove the two structural properties whose absence caused this - the
chart is sized BY CLASS rather than by position, and it keeps a floor it cannot be squeezed below.
A test that merely counted children against rows would have passed the day before the break and
failed the day after for the right reason, but it would also have to be edited by anyone adding a
child - so the fix removes the coupling instead, and this pins the fix.
"""
import re

CSS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.css"
HTML = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.html"
JS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.js"


def _css():
    with open(CSS, encoding="utf-8") as fh:
        return fh.read()


def _desktop_css():
    """The CSS OUTSIDE any max-width media query - i.e. what a desktop browser applies.

    The phone rules must be excluded or this tests the wrong layout: the whole reason the bug was
    desktop-only is that `@media (max-width:899px)` sets an explicit `.chart-host{height:300px}`.
    """
    s = _css()
    out, i = [], 0
    for m in re.finditer(r"@media[^{]*max-width[^{]*\{", s):
        out.append(s[i:m.start()])
        depth, j = 1, m.end()
        while depth and j < len(s):                      # walk to the matching close brace
            depth += (s[j] == "{") - (s[j] == "}")
            j += 1
        i = j
    out.append(s[i:])
    return "".join(out)


def test_the_chart_is_sized_by_class_not_by_position():
    """THE REGRESSION CASE. A rule must target `.chart-host` itself.

    The broken layout named no chart rule at all: the chart got its height purely by being the 2nd
    child. Any such rule is invisible to someone inserting a sibling, which is how this broke.
    """
    css = _desktop_css()
    assert re.search(r"\.hero-body\s*>\s*\.chart-host\s*\{", css), (
        "no desktop rule targets .chart-host by class - its height is positional again, which is "
        "exactly the 2026-09-11 bug")


def test_the_chart_can_grow_and_has_a_floor_it_cannot_be_squeezed_below():
    """It must ABSORB leftover space (or it is a thin strip) and REFUSE to shrink to nothing.

    The floor replaces the old `minmax(170px,1fr)`, whose second job was stopping the chart being
    squeezed to the bottom when the ribbon and DTT populate at the first data tick.
    """
    css = _desktop_css()
    m = re.search(r"\.hero-body\s*>\s*\.chart-host\s*\{([^}]*)\}", css)
    assert m, "no .chart-host rule at all"
    decl = m.group(1)
    assert re.search(r"flex\s*:\s*1", decl), f"the chart cannot grow into the panel: {decl!r}"
    fl = re.search(r"min-height\s*:\s*(\d+)px", decl)
    assert fl and int(fl.group(1)) >= 170, (
        f"the chart has no >=170px floor, so the ribbon/DTT can squeeze it flat again: {decl!r}")


def test_the_layout_does_not_size_rows_by_order():
    """A grid-template-rows on .hero-body is the defect itself, whatever its row count.

    Re-introducing one would re-create the silent break the moment a child is added, so this fails
    on the MECHANISM rather than on a count that would need editing forever.
    """
    css = _desktop_css()
    m = re.search(r"\.hero-body\s*\{([^}]*)\}", css)
    assert m, ".hero-body rule vanished"
    assert "grid-template-rows" not in m.group(1), (
        "hero-body sizes its rows POSITIONALLY again - adding any child silently unsizes the chart")


def test_the_svg_still_contributes_no_height_which_is_why_the_floor_matters():
    """Pins the PREMISE, so this suite keeps making sense if the SVG is ever laid out normally.

    `.chart-host svg{position:absolute}` is why an unsized `.chart-host` measures zero rather than
    collapsing to something visible. If that ever changes, the reasoning above needs revisiting -
    so assert it rather than leave it as an unstated assumption.
    """
    assert re.search(r"\.chart-host\s+svg\s*\{[^}]*position\s*:\s*absolute", _css()), (
        "the hero SVG is no longer absolutely positioned - re-check whether .chart-host still "
        "needs an explicit height at all")


def test_the_zero_height_guard_is_still_the_thing_that_hides_a_layout_fault():
    """renderHero() returns silently on a zero-height host. That guard is CORRECT (it skips the
    hidden phone tab) and is deliberately left in place - but it is also why a layout fault shows
    up as a blank rectangle instead of an error. Pinned so the coupling stays documented: if this
    guard is ever removed, a future zero-height regression becomes noisy instead of silent, and
    the CSS tests above are then belt-and-braces rather than the only net.
    """
    with open(JS, encoding="utf-8") as fh:
        js = fh.read()
    assert "clientHeight === 0" in js, (
        "renderHero's zero-height guard is gone - if that was deliberate, update this test; a "
        "blank chart should now surface differently")


def test_the_chart_host_is_present_in_the_page_the_js_draws_into():
    """Cheap wiring check: the CSS above is meaningless if the element or the SVG id moved."""
    with open(HTML, encoding="utf-8") as fh:
        html = fh.read()
    assert 'class="chart-host"' in html, ".chart-host is gone from app.html"
    assert 'id="price-svg"' in html, "#price-svg is gone - renderHero() targets it by id"
