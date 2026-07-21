"""Telegram command bot — the pure command logic + the on/off file write.

Safe-by-design: only /off /on mutate (the gate switch file the tournament reads live); every
other command is read-only. These tests pin the parsing, the file edit, and the guards."""

from __future__ import annotations

import json

from gazbot7 import telegram_bot as tg


def test_parse_command_strips_slash_and_botname():
    assert tg.parse_command("/off thrust_short") == ("off", "thrust_short")
    assert tg.parse_command("/status@GazbotBot") == ("status", "")
    assert tg.parse_command("/ON rgv_short") == ("on", "rgv_short")
    assert tg.parse_command("hello") == ("", "")          # non-command ignored
    assert tg.parse_command("") == ("", "")


def test_apply_gate_switch_updates_in_place_and_preserves_comments():
    txt = "# header\nrgv_long=on\nthrust_short=on\n"
    out = tg.apply_gate_switch(txt, "thrust_short", "off")
    assert "thrust_short=off" in out and "rgv_long=on" in out and "# header" in out
    assert tg.disabled_from(out) == {"thrust_short"}
    # flip back on
    assert tg.disabled_from(tg.apply_gate_switch(out, "thrust_short", "on")) == set()


def test_apply_gate_switch_appends_when_absent():
    out = tg.apply_gate_switch("# header only\n", "grind_long", "off")
    assert "grind_long=off" in out
    assert tg.disabled_from(out) == {"grind_long"}


def test_handle_off_writes_file_and_confirms(tmp_path):
    sw = str(tmp_path / "gate_switches.env")
    gate = tg.roster()[0]
    r = tg.handle("off", gate, switch_path=sw)
    assert "DISABLED" in r
    assert tg.disabled_from(open(sw).read()) == {gate}
    # /on re-enables
    r2 = tg.handle("on", gate, switch_path=sw)
    assert "RE-ENABLED" in r2 and tg.disabled_from(open(sw).read()) == set()


def test_handle_off_rejects_unknown_gate(tmp_path):
    sw = str(tmp_path / "gate_switches.env")
    r = tg.handle("off", "not_a_gate", switch_path=sw)
    assert "unknown gate" in r
    # nothing written
    import os
    assert not os.path.exists(sw)


def test_handle_off_needs_an_arg(tmp_path):
    r = tg.handle("off", "", switch_path=str(tmp_path / "s.env"))
    assert r.startswith("usage:")


def test_handle_help_and_unknown():
    assert "/off" in tg.handle("help", "")
    assert "/off" in tg.handle("", "")                    # bare / → help
    assert "unknown command" in tg.handle("frobnicate", "")


def test_render_status_flags_naked_and_halted():
    health = {"healthy": True, "halted": False, "place_live": True,
              "protection": {"slots": [{"gate": "rgv_short", "side": "SHORT", "qty": 1, "stop_coid": None}],
                             "unverified_cycles": 0}}
    s = tg.render_status(health, set())
    assert "NAKED" in s
    assert "HALTED" in tg.render_status({"halted": True, "protection": {}}, set())


def test_handle_status_reads_health(tmp_path):
    hp = tmp_path / "core_health.json"
    hp.write_text(json.dumps({"healthy": True, "halted": False, "place_live": True,
                              "protection": {"slots": [], "unverified_cycles": 0}}))
    r = tg.handle("status", "", health_path=str(hp), switch_path=str(tmp_path / "s.env"))
    assert "HEALTHY" in r and "flat" in r


def test_render_gates_marks_disabled():
    out = tg.render_gates({tg.roster()[0]}, {tg.roster()[0]: 100.0})
    assert "🔴" in out and "OFF" in out and "🟢" in out
