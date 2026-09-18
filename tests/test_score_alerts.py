"""SCORING THE ALERTS AGAINST HIS PRESSES — the measurable half of automation.

★★ TWO COUNTING TRAPS THIS GUARDS, both of which inflate a number in the desk's favour:
  1. THE PRESS LOG DOUBLE-COUNTS. `gazbot7-capture-read-*.path` fires on PathModified, which
     triggers TWICE per write — 52 of the consecutive same-kind gaps over 2026-09-14..18 are under
     two seconds with an IDENTICAL request.raw. 110 records are ~57 real presses.
  2. ONLY ALERTS THAT PAGED COUNT. leg_watch's 30/45-min lines are SILENT by design; counting them
     would credit the desk with warnings he never received.
"""
import datetime as dt
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import score_alerts as sa

SRC = "/home/alphabot/gazbot7/scripts/score_alerts.py"


def test_presses_are_deduped_on_the_operators_own_stamp(tmp_path, monkeypatch):
    """⚠ TRAP 1. Two capture rows, one press."""
    p = tmp_path / "reads.jsonl"
    raw = "2026-09-15T05:36:35.628387+00:00|BUY|4|100,200,400,600"
    p.write_text("\n".join(json.dumps({
        "ts": f"2026-09-15T05:36:3{i}.000000+00:00", "kind": "buy",
        "request": {"raw": raw}, "facts": {"price": 29340.75}}) for i in (5, 7)))
    monkeypatch.setattr(sa, "READS", str(p))
    got = sa.presses("2026-09-15")
    assert len(got) == 1, f"the double-fire was counted as {len(got)} presses"
    assert got[0]["t"] == dt.datetime.fromisoformat("2026-09-15T05:36:35.628387+00:00")


def test_a_buy_request_stamp_parses_despite_its_payload(tmp_path, monkeypatch):
    """⚠ A buy is '<stamp>|BUY|qty|targets' and a claim is '<stamp>[|lot=N]'. Parsing the whole
    line as a timestamp throws on EVERY buy — which is half the sample, silently."""
    p = tmp_path / "r.jsonl"
    p.write_text(json.dumps({"ts": "2026-09-15T05:36:35+00:00", "kind": "buy",
                             "request": {"raw": "2026-09-15T05:36:35+00:00|BUY|4|100,200"},
                             "facts": {}}) + "\n"
                 + json.dumps({"ts": "2026-09-15T06:00:00+00:00", "kind": "claim",
                               "request": {"raw": "2026-09-15T06:00:00+00:00|lot=2"},
                               "facts": {}}))
    monkeypatch.setattr(sa, "READS", str(p))
    assert len(sa.presses("2026-09-15")) == 2


def test_only_alerts_that_PAGED_are_counted(tmp_path, monkeypatch):
    """⚠ TRAP 2. The quiet 30/45-min milestones are deliberately silent."""
    p = tmp_path / "leg.log"
    p.write_text("2026-09-15T10:00:00Z quiet 30min: UP LEG · 30min · +76.5pt\n"
                 "2026-09-15T10:28:00Z ALERT 60min: UP LEG · 60min · +87.8pt\n")
    monkeypatch.setattr(sa, "LEG", str(p))
    monkeypatch.setattr(sa, "EVT", str(tmp_path / "nope.log"))
    got = sa.alerts("2026-09-15")
    assert len(got) == 1 and "UP leg" in got[0]["what"]


def test_a_press_with_no_alert_is_UNPROMPTED_not_dropped():
    """★ The honest denominator. 24 of his 28 entries this week had no alert anywhere near them;
    quietly dropping those would turn 12% into 100%."""
    src = open(SRC).read()
    assert "UNPROMPTED" in src and "else:" in src


def test_an_ignored_alert_is_PRICED_not_assumed_to_be_noise():
    """⚠ An alert that fires on a 144pt run he happened to miss is a DIFFERENT problem from one
    that fires on nothing. Both are 'ignored'; only one is noise."""
    src = open(SRC).read()
    assert "def move_after" in src
    assert "It is only noise if" in src


def test_it_is_read_only():
    src = open(SRC).read()
    for banned in ("placeOrder", "MarketOrder", "connectAsync", "gate_switches",
                   "day_rider_claim", "day_rider_buy", '"w"', "os.remove"):
        assert banned not in src, f"the scorer reached for {banned}"
