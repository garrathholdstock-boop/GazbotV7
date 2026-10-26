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


def test_the_veto_is_stated_in_utc_for_that_date():
    for key in ("2026-07-15", "2026-11-12"):                   # summer (CEST) and winter (CET)
        d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
        want = dt.datetime.fromtimestamp(H.L.veto_cutoff(d0 + 12 * 3600), dt.timezone.utc).strftime("%H:%MZ")
        assert DB.mechanics_from_robot(H, key)["veto_utc"] == want
    assert DB.mechanics_from_robot(H, "2026-07-15")["veto_utc"] == "03:00Z" and DB.mechanics_from_robot(H, "2026-11-12")["veto_utc"] == "04:00Z"


def test_hand_written_layers_never_hard_code_numbers_that_belong_to_the_code():
    s = DB._read("strategy.md")
    assert "37.5" not in s and "294" not in s and "{TARGET_PTS}" in s and "{WIN_USD}" in s
    assert "lock" not in s.lower() and "touches +" not in s and "claims per" not in s.lower() and "20:40" not in s
    for bad in ("flattened at 13:30", "erases five to fifteen", "never wrong", "biggest and fastest"):
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
    assert f"+{m['target_pts']:g} points" in a.split("\nDESK MECHANICS (generated")[0]
    assert '"action":"ENTER_LONG|ENTER_SHORT|EXIT|HOLD|WAIT"' in a
    assert "no entry can be traded now" in DB.state_block({"now_utc": "05:00Z", "mins_to_us_open": 1, "mil_dir": None})


def test_live_state_shows_the_real_book_and_realised_plus_open():
    s = DB.state_block({"now_utc": "08:00Z", "mins_to_us_open": 330, "mil_dir": 1, "mil_claims": 1, "mil_cap": 2,
                        "trades": [{"t": "04:25", "side": "LONG", "entry": 100.0, "status": "CLAIMED +294 USD"},
                                   {"t": "05:05", "side": "LONG", "entry": 120.0, "status": "OPEN", "mark_pts": -12.0, "to_target_pts": 49.5}],
                        "day_usd": 198.0, "lock_usd": 1000})
    assert "CLAIMED +294 USD" in s and "OPEN, now -12.0 pt" in s and "(realised + open): +198" in s
