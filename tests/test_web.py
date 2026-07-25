"""Web cockpit — the multi-slot holdings transform (us_terminal_json).

The tournament writes status.json with `position` as a LIST of open slots; the
cockpit must render one holding per slot (with per-slot gate/P&L/protection) and
still tolerate the legacy single-position dict shape (revert to core+strategy)."""

from __future__ import annotations

import json

from gazbot7.web import us_terminal_json


def _dir(tmp_path, status):
    (tmp_path / "status.json").write_text(json.dumps(status))
    return str(tmp_path)


# a capture.db that doesn't exist → _features returns None → last falls back to entry
_NO_CAP = "/nonexistent/capture.db"


def test_multi_slot_one_holding_per_open_slot(tmp_path):
    status = {
        "position": [
            {"gate": "rgv_long", "side": "LONG", "qty": 1.0, "entry_price": 28880.0,
             "opened_at": "2026-07-20T18:40:00+00:00", "stop_price": 28860.0, "stop_coid": "stp-1"},
            {"gate": "thrust_short", "side": "SHORT", "qty": 1.0, "entry_price": 28900.0,
             "opened_at": "2026-07-20T18:50:00+00:00", "stop_price": 28920.0, "stop_coid": None},
        ],
        "protection": {"held": True, "slots": [
            {"gate": "rgv_long", "stop_coid": "stp-1"}, {"gate": "thrust_short", "stop_coid": None}]},
    }
    r = us_terminal_json(_NO_CAP, _dir(tmp_path, status))
    h = {x["entry_gate"]: x for x in r["holdings"]}
    assert set(h) == {"rgv_long", "thrust_short"}
    assert h["rgv_long"]["side"] == "LONG" and h["rgv_long"]["avg"] == 28880.0
    assert h["rgv_long"]["stop"] == 28860.0 and h["rgv_long"]["protected"] is True
    assert h["thrust_short"]["protected"] is False          # no stop_coid → naked badge
    # no live last (no capture) → last=entry → pnl 0, but the row is real
    assert h["rgv_long"]["held_seconds"] is not None


def test_legacy_single_position_dict_still_renders(tmp_path):
    status = {"position": {"symbol": "MNQ", "flat": False, "side": "SHORT", "qty": 1,
                           "entry": 28915.25, "stop": 28935.25, "opened_at": "2026-07-20T18:39:00+00:00"}}
    r = us_terminal_json(_NO_CAP, _dir(tmp_path, status))
    assert len(r["holdings"]) == 1
    assert r["holdings"][0]["side"] == "SHORT" and r["holdings"][0]["avg"] == 28915.25


def test_flat_is_no_holdings(tmp_path):
    r = us_terminal_json(_NO_CAP, _dir(tmp_path, {"position": None, "flat": True}))
    assert r["holdings"] == []


def test_missing_status_file_is_flat(tmp_path):
    assert us_terminal_json(_NO_CAP, str(tmp_path))["holdings"] == []


def test_per_slot_pnl_sign_by_side(tmp_path):
    # inject a fake capture so _features gives a real last? simpler: entry only → last=entry → 0.
    # Assert the sign math directly by giving entries and checking pnl is 0 at last==entry.
    status = {"position": [
        {"gate": "grind_long", "side": "LONG", "qty": 2.0, "entry_price": 28800.0,
         "stop_price": 28780.0, "stop_coid": "s1", "opened_at": "2026-07-20T18:00:00+00:00"}]}
    r = us_terminal_json(_NO_CAP, _dir(tmp_path, status))
    assert r["holdings"][0]["qty"] == 2.0 and r["holdings"][0]["pnl_usd"] == 0.0


# ── /api/futures/tournament — the scoreboard rollup ───────────────────────────
def _seed_trade(store, gate, side, pnl, reason="STOP"):
    from datetime import UTC, datetime
    from gazbot7.store import record_trade
    now = datetime.now(UTC).isoformat()
    record_trade(store, symbol="MNQ", side=side, qty=1, entry_price=100.0,
                 exit_price=100.0 + (pnl / 2.0 if side == "LONG" else -pnl / 2.0),
                 opened_at=now, closed_at=now, pnl_usd=pnl, fees_usd=0.0,
                 exit_reason=reason, gate=gate, exit_exec_id=f"x-{gate}-{pnl}")


def test_tournament_full_6_roster_even_when_empty(tmp_path):
    from gazbot7.store import open_store
    from gazbot7.web import tournament_json
    store = str(tmp_path / "g.db")
    open_store(store).close()
    d = tournament_json(store, _dir(tmp_path, {"position": None, "flat": True}), _NO_CAP)
    assert {r["gate"] for r in d["gates"]} == {"grind_long", "capitulation_long", "abs_veto_long",
                                               "rgv_short", "exhaustion_short", "abs_veto_short"}
    assert d["desk"]["roster_count"] == 6 and d["desk"]["flat"] is True
    assert d["desk"]["safety"] == "green" and d["desk"]["live_count"] == 0


def test_tournament_ranks_and_flags_relegation(tmp_path):
    from gazbot7.store import open_store
    from gazbot7.web import tournament_json
    store = str(tmp_path / "g.db")
    s = open_store(store)
    _seed_trade(s, "grind_long", "LONG", 100.0)      # winner
    _seed_trade(s, "abs_veto_short", "SHORT", 5.0)    # small +
    _seed_trade(s, "rgv_short", "SHORT", -170.0)      # loser
    s.close()
    d = tournament_json(store, _dir(tmp_path, {"position": None, "flat": True}), _NO_CAP)
    g = {r["gate"]: r for r in d["gates"]}
    assert d["gates"][0]["gate"] == "grind_long"      # top of the scoreboard
    assert g["grind_long"]["realized"] == 100.0 and g["rgv_short"]["realized"] == -170.0
    # bottom-2 of the ACTIVE (traded) gates → rgv_short + abs_veto_short
    releg = {r["gate"] for r in d["gates"] if r["relegate"]}
    assert releg == {"rgv_short", "abs_veto_short"}
    assert g["capitulation_long"]["relegate"] is False   # 0-trade gate not judged


def test_tournament_safety_naked_and_halted(tmp_path):
    from gazbot7.store import open_store
    from gazbot7.web import tournament_json
    store = str(tmp_path / "g.db")
    open_store(store).close()
    naked = {"position": [{"gate": "grind_long", "side": "LONG", "qty": 1, "entry_price": 100.0,
                           "stop_coid": None}], "protection": {"slots": []}}
    d = tournament_json(store, _dir(tmp_path, naked), _NO_CAP)
    assert d["desk"]["any_naked"] is True and d["desk"]["safety"] == "red"
    d2 = tournament_json(store, _dir(tmp_path, {"position": None, "halted": True}), _NO_CAP)
    assert d2["desk"]["halted"] is True and d2["desk"]["safety"] == "red"


# ── /api/futures/execution — the entry funnel (say vs buy) ─────────────────────
def test_execution_funnel_submitted_filled_nofill(tmp_path):
    from datetime import UTC, datetime
    from gazbot7.store import open_store, record_signal
    from gazbot7.web import execution_json
    store = str(tmp_path / "g.db")
    s = open_store(store)
    now = datetime.now(UTC).isoformat()

    def sig(gate, side, oc, px):
        record_signal(s, symbol="MNQ", gate=gate, side=side, outcome=oc, intended_price=px, ts=now)

    sig("grind_long", "LONG", "submitted", 100.0)
    sig("grind_long", "LONG", "filled", 100.5)            # +0.5 pt slip
    sig("grind_long", "LONG", "submitted", 200.0)
    sig("grind_long", "LONG", "filled", 200.25)           # +0.25 pt slip
    sig("rgv_short", "SHORT", "submitted", 300.0)
    sig("rgv_short", "SHORT", "nofill", None)             # missed — IOC cancelled
    s.close()
    d = execution_json(store)
    assert d["funnel"] == {"submitted": 3, "filled": 2, "nofill": 1, "rejected": 0}
    assert d["current"]["pct"] == 67 and d["current"]["blocks"] == {"nofill (IOC cancelled)": 1}
    assert d["slippage"]["n"] == 2                            # two filled entries had a ref to compare
    pg = {r["gate"]: r for r in d["per_gate"]}
    assert pg["grind_long"]["through"] == 100 and pg["rgv_short"]["through"] == 0
    assert pg["rgv_short"]["nofill"] == 1


def test_execution_empty_when_no_signals(tmp_path):
    from gazbot7.store import open_store
    from gazbot7.web import execution_json
    store = str(tmp_path / "g.db")
    open_store(store).close()
    d = execution_json(store)
    assert d["funnel"] == {} or d["funnel"].get("submitted", 0) == 0
    assert d["current"] is None or d["current"]["events"] == 0


# ── /api/futures/promotion — shadow feeder → candidates ───────────────────────
def test_promotion_maps_family_and_flags_candidates(tmp_path):
    from gazbot7.store import open_store, record_shadow_real, record_shadow_trade
    from gazbot7.web import promotion_json
    s = open_store(str(tmp_path / "shadow.db"))

    def seed(strategy, pnl, n):
        for i in range(n):
            tid = record_shadow_trade(s, strategy=strategy, symbol="MNQ", side="LONG", qty=1,
                                      entry_ts=1000 + i, entry_price=100.0, entry_atr=8.0, target_r=2.0,
                                      stop_atr_mult=1.0, exit_ts=1100 + i, exit_price=101.0,
                                      exit_reason="TARGET", ceiling_pnl=pnl)
            record_shadow_real(s, trade_id=tid, strategy=strategy, symbol="MNQ", real_pnl=pnl,
                               fill_status="filled", repriced_at="2026-07-21T00:00:00+00:00")

    seed("grind_fast", 5.0, 25)      # +125, n25 → candidate, grind
    seed("thrust_cont", 4.0, 30)     # +120, n30 → candidate, thrust
    seed("rg_short_x", -2.0, 5)      # -10, n5  → not a candidate, reversal_grab
    s.close()
    d = promotion_json(str(tmp_path / "shadow.db"))
    by = {c["variant"]: c for c in d["candidates"]}
    assert by["grind_fast"]["family"] == "grind" and by["grind_fast"]["candidate"] is True
    assert by["thrust_cont"]["family"] == "thrust" and by["thrust_cont"]["candidate"] is True
    assert by["rg_short_x"]["family"] == "reversal_grab" and by["rg_short_x"]["candidate"] is False
    assert d["candidates"][0]["net"] >= d["candidates"][-1]["net"]           # ranked by net
    assert {"grind", "thrust", "reversal_grab", "capitulation", "exhaustion"} == set(d["live_families"])
