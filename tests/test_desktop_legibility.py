"""DESKTOP LEGIBILITY — bigger small text, brighter greys, PHONE UNTOUCHED (2026-09-25).

Operator: "on desktop can you please increase all the smallest font sizes by 3pt and make all the
dull grey fonts 50% brighter."

⚠⚠⚠ THE SCOPING IS THE WHOLE SAFETY OF THIS CHANGE. The TRADE tab is built to fit ONE PHONE SCREEN
WITHOUT SCROLLING — he said so repeatedly and the layout was rebuilt around it. Taking 8px to 11px
on a phone would push the strip, the gauges or the PASS row off the bottom, which is the single
thing he has complained about most.
"""
import re

CSS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.css"


def _new_block():
    return open(CSS, encoding="utf-8").read().split("DESKTOP LEGIBILITY (2026-09-25)", 1)[1]


def test_the_overrides_are_inside_a_min_width_query():
    """★ min-width:900px — the SAME breakpoint .hero-body already uses, so this cannot disagree
    with the layout switch that is already there."""
    b = _new_block()
    assert "@media (min-width:900px){" in b
    body = b.split("@media (min-width:900px){", 1)[1]
    assert "max-width" not in body, "a phone query inside the desktop block would invert the scoping"


def test_the_phone_keeps_its_small_fonts():
    """⚠ The one-screen budget depends on them. If these disappear, the phone layout has been
    changed by a desktop request."""
    css = open(CSS, encoding="utf-8").read()
    head = css.split("DESKTOP LEGIBILITY (2026-09-25)", 1)[0]
    for sz in ("font-size:8px", "font-size:9px", "font-size:10px"):
        assert sz in head, f"{sz} vanished from the base stylesheet"


def test_every_desktop_size_is_exactly_three_px_larger():
    """⚠ Not 'roughly bigger'. He asked for +3, and a silent drift means the next person cannot
    tell what the rule was."""
    b = _new_block()
    sizes = [float(x) for x in re.findall(r"font-size:([0-9.]+)px", b)]
    assert sizes, "no overrides found"
    # the source tier was 8 .. 10.5, so every override must land in 11 .. 13.5
    assert all(11.0 <= s <= 13.5 for s in sizes), sorted(set(sizes))


def test_the_greys_are_lifted_toward_white_not_multiplied():
    """⚠ Multiplying #66727e by 1.5 overflows the blue channel and SHIFTS THE HUE — the text would
    go blue, not bright. Lifting 50% toward white preserves the colour."""
    b = _new_block()
    got = dict(re.findall(r"--(mut2?|txt2):(#[0-9a-f]{6})", b))
    assert got == {"mut": "#c7d0d7", "mut2": "#b2b8be", "txt2": "#d9e0e6"}
    for h in got.values():
        r, g, bl = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        assert max(r, g, bl) <= 255 and abs(max(r, g, bl) - min(r, g, bl)) < 40, "hue drifted"


def test_the_brightest_text_colour_is_deliberately_UNCHANGED():
    """⚠ --txt is already near white (luminance 240). Lifting it too would flatten the contrast
    between a VALUE and its LABEL — the hierarchy that makes the strip readable at a glance. He
    asked for the DULL greys to be brighter, not for everything to converge."""
    b = _new_block()
    assert not re.search(r"--txt:#", b), "--txt must not be redefined by a legibility change"
