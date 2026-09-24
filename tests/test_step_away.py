"""STEP AWAY — "I'm in a meeting, look after this."

★★★ THE MEASURED CASE FOR ARM-WHEN-AWAY, over his last 49 entries (MAE from the 5s tape):
      armed ALWAYS        49 entries · 20 fire · net +$3,352
      armed while WATCHING 37 · 11 fire · net    +$95   <- worthless, AND it costs two big winners
      armed while AWAY     12 ·  9 fire · net +$3,257   <- effectively all of the value
Always-on would have turned his +$819 of 09-16 and +$623 of 09-15 into -$200 apiece. The value is
entirely in trades nobody was watching — the same finding as the hold-time table (over-8h holds:
0 winners from 4, -$6,612).
"""
import datetime as dt
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import step_away as sa
from gazbot7 import web

SRC = "/home/alphabot/gazbot7/scripts/step_away.py"


def _assert_flattens_all(raw, monkeypatch, tmp_path):
    """Feed the written claim to the RIDER'S OWN parser and require 'all'.

    ⚠ This is the invariant, not the byte format: a spec the rider resolved to `lot=N` would close
    ONE lot and leave the rest naked while the guard disarmed itself. Testing the text would have
    to be rewritten every time the format gains a field; testing the parser never does."""
    import gazbot7.day_rider as dr
    f = tmp_path / "parse_claim.txt"
    f.write_text(raw)
    monkeypatch.setattr(dr, "CLAIM_FILE", str(f))
    assert dr.claim_requested() == "all", f"the rider reads {raw!r} as something other than ALL"


def _sandbox(tmp_path, monkeypatch, **state):
    monkeypatch.setattr(sa, "STATE", str(tmp_path / "step_away.json"))
    monkeypatch.setattr(sa, "CLAIM", str(tmp_path / "day_rider_claim.txt"))
    monkeypatch.setattr(sa, "LOG", str(tmp_path / "s.log"))
    sa.write_state(state)
    return tmp_path


def test_it_holds_no_order_path_at_all():
    """★★★ THE SAFETY PROPERTY. It writes the claim file his own button writes; the RIDER executes
    it through its own ownership check. A button that reached the broker directly is how 2026-08-06
    happened — a flatten fired without checking whose position it was."""
    src = open(SRC).read()
    for banned in ("placeOrder", "MarketOrder", "LimitOrder", "connectAsync", "IB()",
                   "qualifyContracts", "gate_switches"):
        assert banned not in src, f"step_away reached for {banned}"


def test_firing_writes_a_BARE_stamp_meaning_flatten_all(tmp_path, monkeypatch):
    """⚠ claim_requested() treats a bare ISO stamp as ALL and `<stamp>|lot=N` as one lot. A stray
    suffix here would close ONE lot and leave the rest naked while the guard disarmed itself."""
    _sandbox(tmp_path, monkeypatch, armed=True, limit_usd=200)
    sa.fire("loss limit", -240.0, {"limit_usd": 200})
    raw = (tmp_path / "day_rider_claim.txt").read_text().strip()
    # ★2026-09-24 ASSERT AGAINST THE REAL PARSER, NOT THE BYTES. The claim now carries
    # `|src=step_away:...` so the booked trade can record that the GUARD closed the position rather
    # than his hand — so "no pipe" is no longer the invariant. THE INVARIANT IS THAT IT STILL
    # FLATTENS EVERYTHING: a spec the rider read as `lot=N` would close ONE lot and leave the rest
    # naked while the guard disarmed itself.
    _assert_flattens_all(raw, monkeypatch, tmp_path)


def test_it_DISARMS_the_instant_it_fires(tmp_path, monkeypatch):
    """⚠ A killer left armed fires again against the NEXT position — flattening a fresh trade
    seconds after it opens."""
    _sandbox(tmp_path, monkeypatch, armed=True, limit_usd=200)
    sa.fire("loss limit", -240.0, {"limit_usd": 200})
    assert sa.read_state()["armed"] is False


def test_an_arming_NEVER_survives_the_2200Z_reopen(tmp_path, monkeypatch):
    """⚠ An arming forgotten on Friday must not flatten Monday's position seconds after it opens —
    the CLAIM_MAX_AGE_S lesson, which exists because exactly this shape of bug was reasoned about."""
    _sandbox(tmp_path, monkeypatch, armed=True, limit_usd=200, session="1999-01-01")
    assert sa.read_state()["armed"] is False


def test_the_session_boundary_is_the_reopen_not_midnight():
    """★ A midnight key would roll over MID-SESSION, the one moment it must not."""
    assert sa.session_key(dt.datetime(2026, 9, 18, 23, 0, tzinfo=dt.UTC)) == "2026-09-18"
    assert sa.session_key(dt.datetime(2026, 9, 19, 2, 0, tzinfo=dt.UTC)) == "2026-09-18"
    assert sa.session_key(dt.datetime(2026, 9, 19, 21, 0, tzinfo=dt.UTC)) == "2026-09-18"


def test_a_stale_price_must_not_trigger():
    """⚠⚠ Acting on a dead feed is how a guard becomes the hazard — and a shut venue and a broken
    feed produce the same silence."""
    src = open(SRC).read()
    assert "STALE_PX_S" in src and "age > STALE_PX_S" in src
    assert sa.STALE_PX_S <= 120, "the staleness bound is too loose to be a bound"


def test_pnl_uses_the_riders_own_convention():
    """★ Imported from rider_peak_watch, verified there against a booked trade. Two implementations
    of one P&L is how numbers on this desk drift apart."""
    assert sa.open_pnl.__module__ == "rider_peak_watch"
    # LONG 4 lots, 25pt against = -$200 gross, minus fees
    assert -212 < sa.open_pnl(29975.0, 30000.0, 1, 4) < -200


def test_arming_needs_no_pin_but_disarming_does(tmp_path):
    """★★ The PIN guards actions that ADD risk. Arming REDUCES it, and friction at the moment he is
    walking into a meeting is friction that costs money."""
    out = web.step_away_post(json.dumps({"armed": True, "limit_usd": 300}).encode(), str(tmp_path))
    assert out["ok"] is True and out["armed"] is True
    bad = web.step_away_post(json.dumps({"armed": False}).encode(), str(tmp_path))
    assert bad["ok"] is False and "PIN" in bad["error"]
    assert json.load(open(tmp_path / "step_away.json"))["armed"] is True, "it disarmed without a PIN"


def test_a_negative_or_silly_limit_cannot_be_armed(tmp_path):
    """⚠ A limit of 0 or -50 would flatten instantly on the first tick."""
    out = web.step_away_post(json.dumps({"armed": True, "limit_usd": -50}).encode(), str(tmp_path))
    assert out["limit_usd"] == 50.0, "a negative limit was not normalised"
    out2 = web.step_away_post(json.dumps({"armed": True}).encode(), str(tmp_path))
    assert out2["limit_usd"] == 200.0, "the default limit changed"


def test_the_armed_state_is_visible_on_the_dashboard():
    """⚠ A guard he cannot see is one he cannot trust — and one he forgets he armed."""
    assert '"step_away"' in open("/home/alphabot/gazbot7/src/gazbot7/web.py").read()
    js = open("/home/alphabot/gazbot7/src/gazbot7/web_static/app.js").read()
    assert "sa-state" in js and "ARMED" in js


def test_the_take_profit_branch_actually_fires(tmp_path, monkeypatch):
    """★★2026-09-24 THE TP WAS ACCEPTED BY THE BACKEND FROM DAY ONE AND NEVER SENT BY THE PAGE.
    Six days armed-capable, zero arms, and the operator reasonably concluded it had not been built.
    A control that exists only in the API does not exist — and an untested branch is not a feature."""
    _sandbox(tmp_path, monkeypatch, armed=True, limit_usd=200, take_profit_usd=300)
    sa.fire("take profit", 340.0, {"limit_usd": 200, "take_profit_usd": 300})
    assert sa.read_state()["armed"] is False
    assert sa.read_state()["reason"] == "take profit"
    raw = (tmp_path / "day_rider_claim.txt").read_text().strip()
    _assert_flattens_all(raw, monkeypatch, tmp_path)
    assert "src=step_away:take_profit" in raw, "the guard no longer stamps its own claims"


def test_a_zero_take_profit_means_NONE_not_zero():
    """⚠ A take-profit of 0 would fire the instant the position was green by a cent."""
    js = open("/home/alphabot/gazbot7/src/gazbot7/web_static/app.js").read()
    i = js.index('$("sa-btn")')
    block = js[i:i + 1800]
    assert "tp && tp > 0" in block, "a blank or zero take-profit is no longer treated as 'none'"


def test_the_ui_exposes_BOTH_legs():
    h = open("/home/alphabot/gazbot7/src/gazbot7/web_static/app.html").read()
    assert 'id="sa-loss"' in h and 'id="sa-tp"' in h, "the take-profit has no control on the page"
    js = open("/home/alphabot/gazbot7/src/gazbot7/web_static/app.js").read()
    assert "take_profit_usd" in js, "the page still never sends a take-profit"


def test_arming_reports_whether_it_will_fire_immediately(tmp_path):
    """★★★ Arming a −$200 stop while the position is already −$250 flattens it on the next
    2-second tick. That may be exactly what he wants, but it must never be a SURPRISE — and the
    reply is the only place he sees it.
    ⚠ Not hypothetical: arming against a live position without first reading its open P&L is
    precisely the mistake that prompted this."""
    import json as _j
    # no position -> no claim about P&L
    (tmp_path / "day_rider_state.json").write_text(_j.dumps({"qty": 0, "closed": True}))
    out = web.step_away_post(_j.dumps({"armed": True, "limit_usd": 200}).encode(), str(tmp_path))
    assert out["ok"] and out["fires_immediately"] is False and out["open_pnl"] is None
    src = open("/home/alphabot/gazbot7/src/gazbot7/web.py").read()
    i = src.index("SAY WHAT WILL HAPPEN THE INSTANT IT IS ARMED")
    assert "ALREADY PAST YOUR LEVEL" in src[i:i + 3000]


def test_the_watcher_and_the_web_run_as_the_SAME_user():
    """★★★ 2026-09-24 THE ARM BUTTON RETURNED "error 13, permission denied".

    gazbot7-web runs as `alphabot`; gazbot7-step-away was written as `root`. They SHARE
    data/step_away.json — and whichever wrote last OWNED it. So the moment the watcher (root)
    expired an arming, the web process (alphabot) could no longer write the file and the button
    died. Two services writing one file under two users is the bug; matching the user is the fix.
    ⚠ A file-permission failure is invisible until someone presses the button, which is why this
    is asserted against the UNIT rather than left to be found in production again."""
    import os as _os

    def user_of(path):
        try:
            return [l.split("=", 1)[1].strip() for l in open(path).read().splitlines()
                    if l.startswith("User=") and not l.strip().startswith("#")][0]
        except Exception:
            return None

    away = user_of("/home/alphabot/gazbot7/ops/systemd/gazbot7-step-away.service")
    assert away, "step-away declares no User at all"
    # ⚠ The web unit lives only in /etc/systemd/system (it is not in the repo), so compare against
    # it when present and fall back to the invariant that actually matters: the watcher must run as
    # whoever OWNS the data directory, because that is who the web process is.
    web = user_of("/etc/systemd/system/gazbot7-web.service")
    if web:
        assert away == web, (f"step-away runs as {away} but the web runs as {web} — they share "
                             f"data/step_away.json and the ARM button will return error 13")
    owner = __import__("pwd").getpwuid(_os.stat("/home/alphabot/gazbot7/data").st_uid).pw_name
    assert away == owner, (f"step-away runs as {away} but data/ is owned by {owner} — it will "
                           f"leave root-owned files the web process cannot rewrite")
