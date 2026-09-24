"""THE ON-PAGE ALERT — it must agree with the phone, and it must never overstate itself.

★★★2026-09-24. Operator: "the telegram sometimes comes 10 seconds after the event. any way of
speeding it up? or thats life?" Measured that day: tape->detection <=1.00s (MD_STREAM publishes MNQ
at exactly 1Hz), python spawn 0.039s, Telegram API POST 0.043s — desk-side total under 1.1s. The
rest is Telegram -> Apple push -> handset and there is no lever on it. The dashboard is already
connected and already polling at 1Hz, so it can fire in ~1s while the tab is in front of him.

⚠⚠⚠ IT IS AN ADDITION TO TELEGRAM, NEVER A REPLACEMENT — it lives only while the tab is open and
foregrounded. These tests exist to stop it becoming a second, disagreeing alarm channel.
"""
import re

APP_JS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.js"
APP_HTML = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.html"
APP_CSS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.css"
PEAK = "/home/alphabot/gazbot7/scripts/rider_peak_watch.py"


def _js():
    return open(APP_JS, encoding="utf-8").read()


def test_the_page_ladder_matches_the_phone_ladder():
    """★★★ THE ONE THAT MATTERS. Two surfaces alerting on two different definitions of "worth
    looking at" would teach him that one of them is lying, and he would then trust neither.

    Read from BOTH sources and compare — never assert a literal in both places, which is how a pair
    of constants drifts while every test still passes.
    """
    js = _js()
    page = {k: int(re.search(rf"AL_{k}\s*=\s*(\d+)", js).group(1))
            for k in ("ARM", "STEP", "GIVEBACK")}
    src = open(PEAK, encoding="utf-8").read()
    phone = {k: int(float(re.search(rf'PEAK_{k}_USD",\s*"([\d.]+)"', src).group(1)))
             for k in ("ARM", "STEP", "GIVEBACK")}
    assert page == phone, (
        f"the dashboard alerts on {page} but the Telegram alerts on {phone} — "
        f"two alarm channels disagreeing about what is worth his attention")


def test_the_alert_has_no_order_path():
    """⚠⚠⚠ It is a BEEP. It may not claim, buy, sell or flatten. The one thing on this page that
    fires by itself must be the one thing that cannot place an order."""
    js = _js()
    block = js.split("THE ON-PAGE ALERT", 1)[1].split("function renderHolding", 1)[0]
    for forbidden in ("fetch(", "api/control", "XMLHttpRequest", "dayrider", "claim"):
        assert forbidden not in block, f"the alert module references {forbidden!r}"


def test_it_never_claims_to_work_when_it_cannot_make_a_sound():
    """⚠ iOS will not play audio no gesture asked for. A label reading ON while the page is silent
    is this desk's signature failure — an instrument reporting healthy about what it never checked.
    So there are THREE states, not two, and "tap" is the honest middle one."""
    js = _js()
    assert '"ALERTS tap"' in js and '"ALERTS off"' in js and '"ALERTS on"' in js
    assert "AL.unlocked ?" in js, "the label must branch on unlocked, not merely on the preference"


def test_the_visual_half_does_not_depend_on_audio():
    """⚠ The flash and the title change are what still work on a muted handset, with audio never
    unlocked, or with the tab behind something. alFire() must do them BEFORE it reaches the beep."""
    js = _js()
    fire = js.split("function alFire(", 1)[1].split("\n  }", 1)[0]
    assert fire.index("al-flash") < fire.index("alBeep")
    assert fire.index("document.title") < fire.index("alBeep")


def test_vibrate_is_guarded():
    """⚠ iOS Safari has NO Vibration API. An unguarded call throws, and one throw inside a render
    pass kills every write after it — the exact failure that blanked this dashboard on 2026-09-24."""
    js = _js()
    assert "if (navigator.vibrate)" in js


def test_the_flash_cannot_push_the_one_screen_layout_out_of_shape():
    """⚠ The whole TRADE tab is built to fit one phone screen without scrolling. An alert banner in
    the document flow would undo that every time it fired."""
    css = open(APP_CSS, encoding="utf-8").read()
    rule = css.split(".alflash{", 1)[1].split("}", 1)[0]
    assert "position:fixed" in rule
    assert "pointer-events:none" in rule, "it must never sit over the FLATTEN button as a target"


def test_audio_is_a_media_element_not_webaudio():
    """⚠ On iPhone a WebAudio tone is silenced by the hardware ringer switch; a media element is
    not. He is on the phone nearly all the time, so the channel that survives a muted handset is
    the only one worth having."""
    html = open(APP_HTML, encoding="utf-8").read()
    assert '<audio id="al-snd"' in html and "playsinline" in html
    assert "AudioContext" not in _js(), "WebAudio is inaudible on a muted iPhone"
