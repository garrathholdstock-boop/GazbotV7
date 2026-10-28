"""THE DESK BRIEF (E119) is gospel: what Claude reads must be exactly what the live robot does. These tests fail the moment the robot's
constants or switches and the brief disagree, a hand-written layer hard-codes a number that belongs to the code, or a versioned layer
loses its version/date/citation discipline."""
from __future__ import annotations

import datetime as dt
import re
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")
import hybrid_robot as H  # noqa: E402
from gazbot7 import day_rider as R  # noqa: E402
from gazbot7 import desk_brief as DB  # noqa: E402

KEY = "2026-10-27"


def test_mechanics_are_generated_from_the_robot():
    m = DB.mechanics_from_robot(H, KEY)
    tgt = float(H.TARGETS.split(",")[0]) / H.PV
    assert (m["target_pts"], m["lots"], m["lock_usd"]) == (tgt, H.QTY, H.LOCK_USD)
    assert m["flat_utc"] == f"{R.FLAT_UTC_MIN // 60:02d}:{R.FLAT_UTC_MIN % 60:02d}Z"
    assert m["exit_live"] == H.L.read_switch(H.SWITCH, "hybrid_exit_live")
    text = DB.mechanics(m)
    assert f"+{tgt:g} points" in text and f"{H.QTY} MNQ" in text and f"${H.LOCK_USD:,.0f}" in text and m["flat_utc"] in text
    assert ("does NOT close the real position" in text) == (not m["exit_live"])
    assert not re.search(r"\d(st|nd|rd|th) claim", text)


def test_the_cap_line_follows_the_release_switch(tmp_path, monkeypatch):
    sw = tmp_path / "h.env"; monkeypatch.setattr(H, "SWITCH", str(sw))
    sw.write_text("hybrid_robot=on\n")
    assert DB.mechanics_from_robot(H, KEY)["mil_cap"] == H.MIL_CAP
    assert f"At most {H.MIL_CAP} claims" in DB.mechanics(DB.mechanics_from_robot(H, KEY))
    sw.write_text(f"hybrid_robot=on\nhybrid_milcap_off_for={KEY}\n")
    m = DB.mechanics_from_robot(H, KEY)
    assert m["mil_cap"] is None and "released the per-leg claim cap" in DB.mechanics(m)


def test_the_veto_is_stated_in_utc_for_that_date(tmp_path, monkeypatch):
    (tmp_path / "env").write_text("hybrid_robot=on\n")                 # the live switch file may lift the veto (v1.06) - not read here
    monkeypatch.setattr(H, "SWITCH", str(tmp_path / "env"))
    for key in ("2026-07-15", "2026-11-12"):                   # summer (CEST) and winter (CET)
        d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
        want = dt.datetime.fromtimestamp(H.L.veto_cutoff(d0 + 12 * 3600), dt.timezone.utc).strftime("%H:%MZ")
        assert DB.mechanics_from_robot(H, key)["veto_utc"] == want
    assert DB.mechanics_from_robot(H, "2026-07-15")["veto_utc"] == "03:00Z" and DB.mechanics_from_robot(H, "2026-11-12")["veto_utc"] == "04:00Z"


def test_hand_written_layers_never_hard_code_numbers_that_belong_to_the_code():
    s = DB._read("strategy.md")
    assert s.count("37.5") == 1 and "at a +37.5 target" in s          # the one cited measurement; everything else is templated
    assert "294" not in s and "{WIN_USD}" in s
    assert "lock" not in s.lower() and "touches +" not in s and "claims per" not in s.lower() and "20:40" not in s
    for bad in ("flattened at 13:30", "erases five to fifteen", "never wrong", "biggest and fastest", "room to go", "stretched",
                "END of a leg", "protects most of"):
        assert bad not in s and bad not in DB._read("experience.md"), bad


def test_every_layer_is_versioned_and_experience_lines_are_dated_and_cited():
    assert re.fullmatch(r"D\d+", DB.version())
    for ln in DB._read("experience.md").splitlines():
        if ln.startswith("- "):
            assert re.match(r"- 20\d\d-\d\d-\d\d \(E\d+", ln), ln


def test_the_build_fills_the_target_and_stamps_a_static_sha_that_ignores_the_live_state():
    m = DB.mechanics_from_robot(H, KEY)
    a, sa = DB.build(m, {"now_utc": "05:00Z", "mins_to_us_open": 510, "mil_dir": 1, "mil_claims": 0, "mil_cap": 2})
    b, sb = DB.build(m, {"now_utc": "09:00Z", "mins_to_us_open": 270, "mil_dir": -1, "mil_claims": 1, "mil_cap": 2})
    assert sa == sb and a != b and sa["version"] == DB.version()
    assert '"action":"ENTER_LONG|ENTER_SHORT|EXIT|HOLD|WAIT"' in a
    assert "no entry can be traded now" in DB.state_block({"now_utc": "05:00Z", "mins_to_us_open": 1, "mil_dir": None})


def test_live_state_shows_the_real_book_and_realised_plus_open():
    s = DB.state_block({"now_utc": "08:00Z", "mins_to_us_open": 330, "mil_dir": 1, "mil_claims": 1, "mil_cap": 2,
                        "trades": [{"t": "04:25", "side": "LONG", "entry": 100.0, "status": "CLAIMED +294 USD"},
                                   {"t": "05:05", "side": "LONG", "entry": 120.0, "status": "OPEN", "mark_pts": -12.0, "to_target_pts": 49.5}],
                        "day_usd": 198.0, "lock_usd": 1000})
    assert "CLAIMED +294 USD" in s and "OPEN, now -12.0 pt" in s and "(realised + open): +198" in s


def test_live_state_never_frames_claims_as_a_quota_and_says_when_nothing_can_be_traded():
    base = {"now_utc": "03:30Z", "mins_to_us_open": 600, "mil_dir": 1, "mil_since": "01:17Z", "mil_cap": 2}
    s0 = DB.state_block(base | {"mil_claims": 0})
    assert "MIL: UP since 01:17Z" in s0 and "claim" not in s0.lower()
    assert "1 claim already taken on this MIL; the robot stops trading it after 2" in DB.state_block(base | {"mil_claims": 1})
    assert "Cap reached on this MIL (2 claims): no entry can be traded" in DB.state_block(base | {"mil_claims": 2})
    assert "Before 04:00Z: no entry can be traded now" in DB.state_block(base | {"before_veto": "04:00Z"})


def _replay(monkeypatch):
    """import the replay engine without leaking its patched minute-bar loader into other tests"""
    import mil_labels as ML
    monkeypatch.setattr(ML, "minute_bars", ML.minute_bars)                 # restored after the test, whatever replay sets
    sys.path.insert(0, "/home/alphabot/gazbot7/reports/recursive_loop/E112_code")
    import replay as RP
    return RP


def test_the_replay_page_agrees_with_live_state_about_the_open_trade(monkeypatch):
    RP = _replay(monkeypatch)
    import sim_week_recursive as S
    day = "2025-11-13"; d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp()); op = d0 + 5 * 3600
    bars = RP.day_bars(day); px = [b for b in bars if b[0] + 60 <= op][-1][3]
    rider = {"dir": -1, "fill": px + 5, "opened_iso": dt.datetime.fromtimestamp(op - 1800, dt.timezone.utc).isoformat(), "target": 37.5}
    pos, done, trades = RP.real_book({"presses": []}, rider, op, bars, px)
    page = S.context([b for b in RP.S.load_day(day)[0] if b[0] + 60 <= op], op, pos, "", done, True, band=False, leg_list=False, mil=False,
                     card=False, window_note="w", header="h", open_note="OPEN: SHORT from 04:30Z - see YOUR POSITION")
    assert "YOUR POSITION: SHORT" in page and "OPEN: SHORT" in page and "no trades yet today" not in page
    assert trades[0]["status"] == "OPEN" and abs(trades[0]["mark_pts"] - 5.0) < 1e-9


def test_the_facts_only_arm_has_no_false_old_lines_and_says_mechanics_win(monkeypatch):
    RP = _replay(monkeypatch)
    f = RP.v2_facts()
    assert "flattened at 13:30Z" not in f and "YOU ARE THE EXIT" not in f and "SIMULATOR" not in f
    assert "where anything above disagrees with them, they win" in RP.PRECEDENCE
