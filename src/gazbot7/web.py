"""GAZBOT V7 — the watch page server.

Serves the V5 MNQ cockpit (copied verbatim: web_static/app.{html,css,js}) and the
four endpoints its JS consumes, computed from V7's store + capture DB + core's
status.json:

* /api/futures/bars/MNQ?count=N  — 1-minute price bars for the hero chart (the tf
  buttons set N); aggregated from the 5s capture bars.
* /api/futures/us-terminal       — holdings (from core's live position) + activity
  (last/VWAP/ATR/net-ATR for the ribbon + chart) + regime/margin (empty in V7).
* /api/futures/mnq               — header P&L, rolling, blotter, curve, gate perf,
  leaderboard (from the trades store; cleanup trades excluded).
* /api/futures/execution         — signal→fill through-rate from the funnel.

Read-only, stdlib only — never touches the trading path. Clean-room.
"""

from __future__ import annotations

import http.server
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from . import pnl

_STATIC = os.path.join(os.path.dirname(__file__), "web_static")
_CT = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript",
       ".pdf": "application/pdf"}
_PARIS = ZoneInfo("Europe/Paris")
_VPP, _FEE = 2.0, 1.5
_CLEANUP = pnl._CLEANUP_REASONS  # ADOPT_FLATTEN etc. — not strategy trades


def _dq(c) -> str:
    """``" AND data_quality IS NULL"`` when the column exists, else ``""``.

    ★★2026-08-13 — ONE PLACE, because six copies is how this drifted in the first place. The flag
    was added on 08-05 and fixed only in `pnl.py`; its own comment warned that "a field was added
    and the CONSUMERS were not audited", and then the same thing happened again here — SIX separate
    queries in this file read the trades table and NONE of them filtered. So the operator saw a
    correct P&L sitting above a blotter, an equity curve, a per-gate table, a router panel and a
    cube that all still contained four phantom day-rider trades worth $1,551 that never happened.
    A wrong number is bad; a right number next to a wrong one is worse, because nothing says which
    to believe.
    ⚠ Conditional on the column existing, for the same reason pnl.py is: fixtures and older
    databases build `trades` without it, and a view that throws is worse than one that over-counts.
    """
    try:
        if any(r[1] == "data_quality" for r in c.execute("PRAGMA table_info(trades)").fetchall()):
            return " AND data_quality IS NULL"
    except Exception:
        pass
    return ""


def _status(data_dir):
    try:
        with open(os.path.join(data_dir, "status.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def _conn(path):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


# ── /api/futures/bars/MNQ — 1m bars aggregated from 5s capture ────────────────
def bars_json(cap_path, count):
    out = []
    try:
        c = _conn(cap_path)
        rows = c.execute(
            "SELECT bar_ts, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
            "ORDER BY bar_ts DESC LIMIT ?", (count * 12 + 24,),
        ).fetchall()
        c.close()
        by_min = {}
        for r in rows:  # desc → first close seen for a minute is its latest 5s close
            m = (r["bar_ts"] // 60) * 60
            by_min.setdefault(m, r["close"])
        for m in sorted(by_min)[-count:]:
            out.append({"ts": datetime.fromtimestamp(m, UTC).isoformat(), "close": by_min[m]})
    except Exception:
        pass
    return {"bars": out}


def _features(cap_path):
    """last / vwap / atr_pct / net_atr + the chart-read numbers (ATR in pts+$, its violence
    bucket, and the ~30-min efficiency ratio + trend/chop label) — so the cockpit shows AT A
    GLANCE how big (ATR) and how clean (ER) the tape is."""
    try:
        from .deciders import Bar, compute_features
        c = _conn(cap_path)
        rows = list(reversed(c.execute(
            "SELECT bar_ts, open, high, low, close, volume FROM bars "
            "WHERE symbol='MNQ' AND timeframe='5s' ORDER BY bar_ts DESC LIMIT 360"   # 30 min
        ).fetchall()))
        c.close()
        if len(rows) < 6:
            return None
        # Aggregate the 5s bars → 1-MINUTE OHLC — the SAME basis the gates + hour_watch use, so the
        # ribbon's ATR + violence match the ATR floors and the Telegram (2026-07-23). A 5s-bar ATR
        # reads ~4x smaller (~2.9 vs the ~12-23 the gate sees), which made a floor like 20 look
        # impossible on the chart. ER already used 1-min closes and is unchanged.
        agg: dict = {}
        for r in rows:
            m = (r["bar_ts"] // 60) * 60
            a = agg.get(m)
            if a is None:
                agg[m] = [r["open"], r["high"], r["low"], r["close"], r["volume"]]
            else:
                a[1] = max(a[1], r["high"])
                a[2] = min(a[2], r["low"])
                a[3] = r["close"]
                a[4] += r["volume"]
        bars = [Bar(m, *agg[m]) for m in sorted(agg)]
        if len(bars) < 6:
            return None
        f = compute_features(bars)   # 1-min ATR/VWAP — matches the live gate + hour_watch
        atr_pts = round(f.atr, 1)
        # ER over the 30-min 1-min closes (net progress / total distance walked) — unchanged, correct
        cl = [b.close for b in bars]
        er = day_type = None
        if len(cl) >= 6:
            total = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1
            er = round(abs(cl[-1] - cl[0]) / total, 2)
            day_type = "trend" if er >= 0.18 else "chop" if er < 0.08 else "mixed"
        violence = ("asleep" if atr_pts < 3 else "calm" if atr_pts < 8 else "normal"
                    if atr_pts < 16 else "elevated" if atr_pts < 28 else "violent")
        return {"last": rows[-1]["close"], "vwap": round(f.vwap, 2),
                "atr_pct": round(f.atr_pct * 100, 3), "net_atr": round(f.net_atr_5, 2),
                "atr_pts": atr_pts, "atr_usd": round(atr_pts * _VPP), "violence": violence,
                "er": er, "day_type": day_type}
    except Exception:
        return None


# ── /api/futures/us-terminal — holdings + activity ────────────────────────────
def us_terminal_json(cap_path, data_dir):
    from . import session
    st = _status(data_dir)
    f = _features(cap_path) or {}
    now = datetime.now(UTC)
    activity = {
        "symbol": "MNQ", "label": "MNQ", "is_known": bool(f),
        "session_active": session.is_open(now),
        "state": "live" if session.is_open(now) else "closed",
        "last": f.get("last"), "vwap": f.get("vwap"), "atr_pct": f.get("atr_pct"),
        "net_atr": f.get("net_atr"), "atr_pts": f.get("atr_pts"), "atr_usd": f.get("atr_usd"),
        "violence": f.get("violence"), "er": f.get("er"), "day_type": f.get("day_type"), "gates": [],
    }
    # position is now the multi-slot tournament shape — a LIST of open slots (one per gate).
    # Tolerate the legacy single-position dict too (so a revert to core+strategy still renders).
    raw = st.get("position")
    if isinstance(raw, list):
        slots = raw
    elif isinstance(raw, dict) and not raw.get("flat"):
        slots = [raw]
    else:
        slots = []
    prot_by_gate = {s.get("gate"): s for s in ((st.get("protection") or {}).get("slots") or [])}
    last_px = f.get("last")
    holdings = []
    for s in slots:
        entry = s.get("entry_price") or s.get("entry") or s.get("avg")
        if entry is None:
            continue
        side = s.get("side") or ("SHORT" if (s.get("qty") or 0) < 0 else "LONG")
        qty = abs(s.get("qty") or 1)
        last = last_px or entry
        sign = 1 if side == "LONG" else -1
        gate = s.get("gate", "—")
        held_s = None
        if s.get("opened_at"):
            try:
                held_s = (now - datetime.fromisoformat(s["opened_at"])).total_seconds()
            except (ValueError, TypeError):
                held_s = None
        holdings.append({
            "label": "MNQ", "symbol": "MNQ", "side": side, "qty": qty,
            "avg": entry, "stop": s.get("stop_price") or s.get("stop"), "last": last,
            "multiplier": _VPP, "pnl_usd": round(sign * (last - entry) * _VPP * qty, 2),
            "pnl_pct": round(sign * (last - entry) / entry * 100, 3) if entry else None,
            "entry_gate": gate, "opened_at": s.get("opened_at"), "held_seconds": held_s,
            "protected": bool(prot_by_gate.get(gate, s).get("stop_coid")),
        })
    # ★★2026-08-07 THE DAY RIDER IS A SECOND DESK AND WAS INVISIBLE HERE.
    # This window is built from the TOURNAMENT's status.json, so a day-rider position — its own
    # service, its own clientId 4, same account and same symbol — rendered nowhere at all. On 08-07
    # it held SHORT 2 @ 29567.25, ~150pt offside, while every screen the operator had showed "flat".
    # A live position with no surface is exactly how the 08-06 incident stayed invisible for hours.
    # It reports under gate `day_rider`. Fail-soft: on any error the window renders the tournament
    # rows exactly as before, so a bad state file can never blank the holdings panel.
    try:
        with open(os.path.join(data_dir, "day_rider_state.json")) as fh:
            dr = json.load(fh)
        if dr.get("entered") and not dr.get("closed"):
            entry = float(dr.get("entry") or 0.0)
            qty = abs(float(dr.get("qty") or 0.0))
            direction = int(dr.get("direction") or 0)
            if entry > 0 and qty > 0 and direction in (-1, 1):
                last = last_px or entry
                # the ARMED trail is the live protection; the 600pt venue stop is last-resort only
                stop = dr.get("trail") or dr.get("venue_stop")
                holdings.append({
                    "label": "MNQ", "symbol": "MNQ",
                    "side": "LONG" if direction > 0 else "SHORT", "qty": qty,
                    "avg": entry, "stop": stop, "last": last, "multiplier": _VPP,
                    "pnl_usd": round(direction * (last - entry) * _VPP * qty, 2),
                    "pnl_pct": round(direction * (last - entry) / entry * 100, 3),
                    "entry_gate": "day_rider",
                    "opened_at": None, "held_seconds": None,
                    # an UNARMED trail is not protection — say so honestly rather than let the
                    # 600pt insurance stop render as if it were a working protective stop.
                    "protected": bool(dr.get("trail")),
                })
    except Exception:
        pass

    return {"holdings": holdings, "activity": [activity], "regime_groups": {},
            "margin_deployed_usd": None, "nlv_usd": None}


# ── /api/futures/mnq — header / rolling / blotter / curve / gates ──────────────
def _strategy_trades(c, since_iso=None):
    """Today's real trades. Feeds the BLOTTER, the equity CURVE and the per-GATE table.

    ★★2026-08-13 — EXCLUDE data_quality-flagged rows HERE TOO. `pnl.py` learned this on 08-05 and
    its own comment names the trap: "a field was added and the CONSUMERS were not audited". The fix
    went into the P&L source and stopped there, so this function — a completely separate query —
    kept returning flagged rows. Operator, the same day the rider booked four phantom trades:
    "the trades list is still showing those erroneous day trade trades."
    He was reading a correct P&L above a blotter full of trades that never happened, which is worse
    than either being wrong alone: the numbers disagree and neither says why.
    It is not only the blotter — `curve` and `gate_perf` are built from these rows, so the equity
    line and every per-gate stat carried the $1,551 of fictitious profit as well.
    ⚠ Tolerates the column being absent, for exactly the reason pnl.py does: adding the clause
    unconditionally broke 8 tests whose fixtures build `trades` without it, and would equally break
    a fresh deployment or an older database. A view that throws is worse than one that over-counts.
    """
    ph = ",".join("?" * len(_CLEANUP))
    q = (f"SELECT closed_at, side, gate, exit_reason, pnl_usd, entry_price, exit_price, qty "
         f"FROM trades WHERE symbol='MNQ' AND exit_reason NOT IN ({ph})")
    q += _dq(c)
    args = list(_CLEANUP)
    if since_iso:
        q += " AND closed_at>=?"
        args.append(since_iso)
    q += " ORDER BY closed_at"
    return c.execute(q, args).fetchall()


def _gate_groups(rows):
    g = {}
    for r in rows:
        k = ((r["gate"] or "—"), r["side"])
        d = g.setdefault(k, {"gate": k[0], "side": k[1], "n": 0, "w": 0, "gw": 0.0, "gl": 0.0, "net": 0.0})
        d["n"] += 1
        d["net"] += r["pnl_usd"]
        if r["pnl_usd"] > 0:
            d["w"] += 1; d["gw"] += r["pnl_usd"]
        else:
            d["gl"] += -r["pnl_usd"]
    out = []
    for d in g.values():
        out.append({"gate": d["gate"], "side": d["side"], "n": d["n"],
                    "win_pct": round(100 * d["w"] / d["n"]) if d["n"] else None,
                    "pf": round(d["gw"] / d["gl"], 2) if d["gl"] > 1e-9 else None,
                    "net": round(d["net"], 2)})
    out.sort(key=lambda x: x["net"], reverse=True)
    return out


def mnq_json(store_path):
    now = datetime.now(UTC)
    out = {"expiry": "SEP26", "fee_per_rt": _FEE, "header": {}, "rolling": {},
           "blotter": [], "curve": [], "gate_perf": [], "leaderboard": {"top": [], "bottom": []},
           "long_short": [], "loss_buckets": [], "drill": {}, "ratchet": None,
           "contracts_cap_aggregate": None}
    try:
        c = _conn(store_path)
        # ★2026-08-11 desk="tournament" so this header keeps the meaning it has always had.
        # The day rider started writing trade rows today; folding them in would silently change
        # the number the operator reads as "the desk's day" without him asking for it. The
        # rider's own position and P&L surface separately in HOLDINGS.
        today, n_today, wins = pnl.day(c, "MNQ", now, desk="tournament")
        # ★★2026-08-13 (operator): "we watch the day rider holding but then it doesnt show in any
        # daily p&l. there should be a tourn p&l, day rider p&l and a total desk p&l."
        # He is right, and the strip was worse than merely incomplete — it was INCONSISTENT:
        # `today` was tournament-only (deliberately, 08-11) while `yest`/`d7`/`d30` were and remain
        # UNFILTERED, i.e. both desks. So TODAY and 7D silently measured different things and the
        # comparison across the strip was meaningless.
        # Fixed by publishing the split explicitly instead of picking one meaning. `today` KEEPS its
        # tournament-only meaning so no existing consumer shifts under it (the P&L strip parse is
        # pinned in memory as header.today); the UI reads the new fields.
        # The week that prompted this: tournament −$438, day-rider +$1,183.50 — one number could
        # not have told him the desk was losing while the rider carried it.
        today_rider, n_rider, _ = pnl.day(c, "MNQ", now, desk="day_rider")
        today_total = round(today + today_rider, 2)
        d7, _, _ = pnl.realized(c, "MNQ", since_iso=(now - timedelta(days=7)).isoformat())
        d30, _, _ = pnl.realized(c, "MNQ", since_iso=(now - timedelta(days=30)).isoformat())
        y0 = pnl.paris_day_start_utc(now - timedelta(days=1))
        t0 = pnl.paris_day_start_utc(now)
        yest = round(sum(r["pnl_usd"] for r in c.execute(
            "SELECT pnl_usd FROM trades WHERE symbol='MNQ' AND closed_at>=? AND closed_at<? "
            "AND exit_reason NOT IN (" + ",".join("?" * len(_CLEANUP)) + ")" + _dq(c),
            (y0, t0, *_CLEANUP)).fetchall()), 2)
        out["header"] = {"today": today, "yest": yest, "d2": None, "d7": d7, "d30": d30,
                         "win_today": (round(100 * wins / n_today) if n_today else None),
                         "trades_today": n_today,
                         # The explicit three-way split. `today_tournament` is the same number as
                         # `today` — named, so a reader never has to know which desk the bare
                         # `today` meant. `yest`/`d7`/`d30` are already BOTH desks, so the strip is
                         # internally consistent once the UI shows `today_total`.
                         "today_tournament": today, "today_rider": today_rider,
                         "today_total": today_total,
                         "trades_tournament": n_today, "trades_rider": n_rider}
        # rolling
        def _roll(days):
            p, n, w = pnl.realized(c, "MNQ", since_iso=(now - timedelta(days=days)).isoformat())
            return {"pnl": p, "trades": n, "win": (round(100 * w / n) if n else None), "pf": None, "maxdd": None}
        out["rolling"] = {"1D": {"pnl": today, "trades": n_today,
                                 "win": (round(100 * wins / n_today) if n_today else None), "pf": None, "maxdd": None},
                          "7D": _roll(7), "30D": _roll(30)}
        # today's strategy trades → blotter (newest first) + curve + gate perf
        today_rows = _strategy_trades(c, since_iso=t0)
        cum = 0.0
        for r in today_rows:
            cum += r["pnl_usd"]
            out["curve"].append({"cum": round(cum, 2)})
        for r in reversed(today_rows):
            sign = 1 if r["side"] == "LONG" else -1
            ppct = (round(sign * (r["exit_price"] - r["entry_price"]) / r["entry_price"] * 100, 3)
                    if r["entry_price"] else None)
            out["blotter"].append({"time": r["closed_at"], "side": r["side"], "gate": r["gate"] or "—",
                                   "exit": r["exit_reason"], "pnl_usd": round(r["pnl_usd"], 2), "pnl_pct": ppct})
        gp = _gate_groups(today_rows)
        out["gate_perf"] = gp
        out["leaderboard"] = {"top": gp[:5], "bottom": list(reversed(gp[-5:])) if len(gp) > 5 else []}
        # losses by exit reason (data was always here — just never wired)
        losses: dict = {}
        for r in today_rows:
            if r["pnl_usd"] < 0:
                b = losses.setdefault(r["exit_reason"], {"n": 0, "usd": 0.0})
                b["n"] += 1
                b["usd"] += r["pnl_usd"]
        out["loss_buckets"] = sorted(
            [{"cause": k, "n": v["n"], "usd": round(v["usd"], 2)} for k, v in losses.items()],
            key=lambda x: x["usd"])
        c.close()
    except Exception:
        pass
    return out


def _disabled_gates(data_dir):
    """Gates switched OFF in ``gate_switches.env`` — the live intraday on/off the tournament
    re-reads. Mirrors ``tournament.parse_switches`` (kept in sync by
    tests/test_web.py::test_disabled_gates_matches_tournament_parser); reimplemented here so
    the stdlib-only web server never imports the trading stack. Missing/bad file → none off."""
    off = set()
    try:
        with open(os.path.join(data_dir, "gate_switches.env")) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if v.strip().lower() in ("off", "0", "no", "false", "disable", "disabled"):
                    off.add(k.strip())
    except OSError:
        pass
    return off


# ── /api/futures/tournament — the per-gate scoreboard (roster × trades × live) ─
def tournament_json(store_path, data_dir, cap_path):
    """The tournament scoreboard: the full 6-gate roster (from ``tournament_slots()`` so
    0-trade gates still show), each gate's today-realized (from ``trades``) + open-unrealized
    (from the live ``status.json`` slots × last price), ranked by total, bottom-2 flagged for
    relegation. Plus a desk-level safety block for the header pill. Read-only."""
    from .slot_strategy import grind_long_short_slots, scaleout_slots, tournament_slots
    # ★2026-07-29: roster follows the LIVE slate (GAZBOT7_TOURNAMENT_SLATE), so the dual-slot _A/_B
    # sub-slots show. Was hardcoded tournament_slots() → the scaleout slate's _A/_B trades were invisible
    # and the scoreboard didn't add up (abs_veto_short showed only pre-deploy −135, the +768 win hidden).
    _slate_fn = {"tournament": tournament_slots, "grind2": grind_long_short_slots,
                 "scaleout": scaleout_slots}.get(os.environ.get("GAZBOT7_TOURNAMENT_SLATE", "tournament"), tournament_slots)
    roster = [(s.tag, s.side) for s in _slate_fn()]
    disabled = _disabled_gates(data_dir)   # live intraday on/off (gate_switches.env)
    st = _status(data_dir)
    last = (_features(cap_path) or {}).get("last")
    raw = st.get("position")
    live = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) and not raw.get("flat") else [])
    slot_by_gate = {s.get("gate"): s for s in live if s.get("gate")}

    stats: dict = {}
    wstats: dict = {}   # week-to-date, for the avg-winner/avg-loser/delta/expectancy block
    try:
        now = datetime.now(UTC)
        c = _conn(store_path)
        for r in _strategy_trades(c, since_iso=pnl.paris_day_start_utc(now)):
            d = stats.setdefault(r["gate"] or "?",
                                 {"realized": 0.0, "n": 0, "wins": 0, "gw": 0.0, "gl": 0.0, "exits": {}, "side": r["side"]})
            d["realized"] += r["pnl_usd"]
            d["n"] += 1
            if r["pnl_usd"] > 0:
                d["wins"] += 1
                d["gw"] += r["pnl_usd"]
            else:
                d["gl"] += -r["pnl_usd"]
            d["exits"][r["exit_reason"]] = d["exits"].get(r["exit_reason"], 0) + 1
        for r in _strategy_trades(c, since_iso=pnl.paris_week_start_utc(now)):
            d = wstats.setdefault(r["gate"] or "?", {"n": 0, "wins": 0, "gw": 0.0, "gl": 0.0})
            d["n"] += 1
            if r["pnl_usd"] > 0:
                d["wins"] += 1
                d["gw"] += r["pnl_usd"]
            else:
                d["gl"] += -r["pnl_usd"]
        c.close()
    except Exception:
        pass

    # ★ union: any gate that ACTUALLY traded today but isn't in the live-slate roster (e.g. pre-deploy
    # base-gate trades, or a web-vs-desk slate mismatch) still shows — so the scoreboard reflects reality
    # and always adds up, regardless of the web service's env.
    _rtags = {t for t, _ in roster}
    for _g, _dd in stats.items():
        if _g not in _rtags:
            roster.append((_g, _dd.get("side", "SHORT")))

    rows = []
    for gate, side in roster:
        d = stats.get(gate, {})
        slot = slot_by_gate.get(gate)
        entry = slot.get("entry_price") if slot else None
        qty = abs(slot.get("qty") or 0) if slot else 0.0
        open_unreal = 0.0
        if slot and entry and last:
            open_unreal = round((1 if side == "LONG" else -1) * (last - entry) * _VPP * qty, 2)
        realized = round(d.get("realized", 0.0), 2)
        n = d.get("n", 0)
        # week-to-date winner/loser expectancy: with W winners and L losers the desk
        # nets W·avg_win − L·avg_loss, so this is where a low-win-rate/big-winner gate
        # (grind chandelier) shows whether the fat winners outweigh the many small losers.
        wd = wstats.get(gate, {})
        w_n = wd.get("n", 0)
        w_wins = wd.get("wins", 0)
        w_losses = w_n - w_wins
        avg_win = round(wd["gw"] / w_wins) if w_wins else None
        avg_loss = round(wd["gl"] / w_losses) if w_losses else None
        rows.append({
            "gate": gate, "side": side, "live": slot is not None,
            "enabled": gate not in disabled,   # armed to take NEW entries (gate_switches.env)
            "qty": qty, "entry": entry, "stop": (slot.get("stop_price") if slot else None),
            "protected": (bool(slot.get("stop_coid")) if slot else None),
            "open_unreal": open_unreal, "realized": realized, "total": round(realized + open_unreal, 2),
            "n": n, "win_pct": (round(100 * d.get("wins", 0) / n) if n else None),
            "pf": (round(d["gw"] / d["gl"], 2) if d.get("gl", 0) > 1e-9 else None),
            "exits": d.get("exits", {}),
            "wk_n": w_n, "wk_wins": w_wins, "wk_losses": w_losses,
            "wk_avg_win": avg_win, "wk_avg_loss": avg_loss,
            "wk_delta": (avg_win - avg_loss) if (avg_win is not None and avg_loss is not None) else None,
            "wk_exp": (round((wd["gw"] - wd["gl"]) / w_n, 1) if w_n else None),
        })
    rows.sort(key=lambda x: x["total"], reverse=True)
    active = [r for r in rows if r["n"] > 0 or r["live"]]
    releg = {r["gate"] for r in sorted(active, key=lambda x: x["total"])[:2]} if len(active) >= 2 else set()
    for r in rows:
        r["relegate"] = r["gate"] in releg

    any_naked = any(not s.get("stop_coid") for s in live)
    unverified = (st.get("protection") or {}).get("unverified_cycles", 0)
    halted = bool(st.get("halted"))
    level = "red" if (halted or any_naked) else ("amber" if unverified else "green")
    return {
        "gates": rows,
        "desk": {
            "realized_today": round(sum(r["realized"] for r in rows), 2),
            "open_unreal": round(sum(r["open_unreal"] for r in rows), 2),
            "live_count": sum(1 for r in rows if r["live"]), "roster_count": len(rows),
            "enabled_count": sum(1 for r in rows if r["enabled"]),
            "benched": sorted(g for g, _ in roster if g in disabled),
            "halted": halted, "any_naked": any_naked, "unverified_cycles": unverified,
            "flat": not live, "safety": level, "last": last,
        },
    }


# ── /api/futures/promotion — the shadow feeder → promotion candidates ─────────
_SHADOW_FAMILY = [
    ("grind", ("grind",)),
    ("thrust", ("thrust", "cb_thrust", "abs_veto", "chand")),
    ("reversal_grab", ("rg_long", "rg_short", "rg_")),
    ("capitulation", ("capit",)),
    ("exhaustion", ("exhaust",)),
]


def _shadow_family(name):
    n = (name or "").lower()
    for fam, keys in _SHADOW_FAMILY:
        if any(n.startswith(k) or k in n for k in keys):
            return fam
    return "other"


def promotion_json(shadow_path):
    """The shadow board as the promotion FEEDER: each variant's honest real_pnl (all-time +
    today), its gate family, and whether that family is already live in the tournament. Ranked
    by net; a ``candidate`` = net-positive with a real track record (n≥20). ⚠ shadow is the
    OPTIMISTIC feeder — it ignores the single-position constraint and enters at hindsight
    bar-closes, so it OVERSTATES; it NOMINATES, the paper tournament JUDGES. Never auto-promote."""
    from .slot_strategy import tournament_slots
    live_families = {s.kind for s in tournament_slots()}
    out = {"candidates": [], "live_families": sorted(live_families),
           "note": "shadow overstates (feeder) — nominate, don't auto-promote; paper is the judge"}
    try:
        c = _conn(shadow_path)
        t0 = datetime.fromisoformat(pnl.paris_day_start_utc(datetime.now(UTC))).timestamp()
        rows = c.execute(
            "SELECT st.strategy s, COUNT(*) n, SUM(sr.real_pnl) net, "
            "SUM(CASE WHEN sr.real_pnl>0 THEN 1 ELSE 0 END) w, "
            "SUM(CASE WHEN st.entry_ts>=? THEN sr.real_pnl ELSE 0 END) today, "
            "SUM(CASE WHEN st.entry_ts>=? THEN 1 ELSE 0 END) today_n "
            "FROM shadow_trades st JOIN shadow_real sr ON sr.trade_id=st.id "
            "WHERE sr.fill_status='filled' AND sr.real_pnl IS NOT NULL GROUP BY st.strategy",
            (t0, t0)).fetchall()
        c.close()
        cands = []
        for r in rows:
            n = r["n"] or 0
            fam = _shadow_family(r["s"])
            net = round(r["net"] or 0, 1)
            cands.append({
                "variant": r["s"], "family": fam, "family_live": fam in live_families,
                "n": n, "net": net, "win": (round(100 * (r["w"] or 0) / n) if n else None),
                "today": round(r["today"] or 0, 1), "today_n": r["today_n"] or 0,
                "candidate": (net > 0 and n >= 20)})
        cands.sort(key=lambda x: -x["net"])
        out["candidates"] = cands
    except Exception:
        pass
    return out


# ── /api/futures/execution — the entry funnel: SAY-to-buy vs ACTUALLY-buy ─────
def execution_json(store_path):
    """The full signal→fill funnel for the tournament, today (Paris day). Every entry
    logs a ``submitted`` (we tried) then a ``filled`` (we got it) or a ``nofill`` (IOC
    cancelled — said buy, got nothing) / ``rejected``. Reports the through-rate, the
    per-entry SLIPPAGE (fill vs the intended ref), the failure reasons, an hourly trend,
    and a per-gate breakdown — so you see exactly what we said vs bought, and why misses."""
    from collections import defaultdict, deque

    from .ticks import tick_for
    out = {"current": None, "baseline_pct": None, "trend": [], "funnel": {}, "per_gate": [],
           "slippage": {"avg_ticks": None, "avg_usd": None, "n": 0}, "window": "today"}
    try:
        c = _conn(store_path)
        t0 = pnl.paris_day_start_utc(datetime.now(UTC))
        rows = c.execute(
            "SELECT ts, gate, side, outcome, intended_price FROM signals "
            "WHERE ts>=? AND outcome IN ('submitted','filled','nofill','rejected') ORDER BY ts",
            (t0,)).fetchall()
        c.close()
        tick = tick_for("MNQ") or 0.25
        g = defaultdict(lambda: {"submitted": 0, "filled": 0, "nofill": 0, "rejected": 0,
                                 "side": None, "slip": []})
        refq: dict = defaultdict(deque)          # per-gate FIFO of submitted refs → matched on fill
        hourly: dict = defaultdict(lambda: {"submitted": 0, "filled": 0})
        for r in rows:
            gate, oc, side = (r["gate"] or "?"), r["outcome"], r["side"]
            d = g[gate]; d["side"] = side
            d[oc] = d.get(oc, 0) + 1
            hr = (r["ts"] or "")[:13]
            if oc == "submitted":
                refq[gate].append(r["intended_price"]); hourly[hr]["submitted"] += 1
            elif oc == "filled":
                hourly[hr]["filled"] += 1
                ref = refq[gate].popleft() if refq[gate] else None
                if ref and r["intended_price"]:  # slippage = adverse move ref→fill, per side
                    adv = (r["intended_price"] - ref) if side == "LONG" else (ref - r["intended_price"])
                    d["slip"].append(adv)
        sub = sum(d["submitted"] for d in g.values())
        fil = sum(d["filled"] for d in g.values())
        nof = sum(d["nofill"] for d in g.values())
        rej = sum(d["rejected"] for d in g.values())
        allslip = [s for d in g.values() for s in d["slip"]]
        avg_pts = (sum(allslip) / len(allslip)) if allslip else None
        blocks = {}
        if nof:
            blocks["nofill (IOC cancelled)"] = nof
        if rej:
            blocks["rejected"] = rej
        out["funnel"] = {"submitted": sub, "filled": fil, "nofill": nof, "rejected": rej}
        out["current"] = {
            "pct": (round(100 * fil / sub) if sub else None), "events": sub, "through": fil,
            "level": ("CRIT" if (sub >= 3 and fil == 0) else "OK"),
            "slip_ticks": (round(avg_pts / tick, 1) if avg_pts is not None else None),
            "slip_usd": (round(avg_pts * _VPP, 2) if avg_pts is not None else None),
            "blocks": blocks}
        out["slippage"] = {"avg_ticks": (round(avg_pts / tick, 1) if avg_pts is not None else None),
                           "avg_usd": (round(avg_pts * _VPP, 2) if avg_pts is not None else None),
                           "n": len(allslip)}
        out["per_gate"] = sorted(
            [{"gate": gate, "side": d["side"], "submitted": d["submitted"], "filled": d["filled"],
              "nofill": d["nofill"],
              "through": (round(100 * d["filled"] / d["submitted"]) if d["submitted"] else None),
              "slip_ticks": (round(sum(d["slip"]) / len(d["slip"]) / tick, 1) if d["slip"] else None)}
             for gate, d in g.items()], key=lambda x: -x["submitted"])
        out["trend"] = [
            {"pct": (round(100 * v["filled"] / v["submitted"]) if v["submitted"] else 0),
             "events": v["submitted"], "level": ("CRIT" if (v["submitted"] >= 3 and v["filled"] == 0) else "OK")}
            for _, v in sorted(hourly.items())]
    except Exception:
        pass
    return out


# ── /api/futures/router — the intelligent-router panel (regime + gates + stream) ─
_ROUTER_META = {  # gate → (family, mechanism, side)
    "grind_long": ("momentum", "continuation", "LONG"),
    "abs_veto_long": ("momentum", "thrust", "LONG"),
    "capitulation_long": ("reversion", "flush-fade", "LONG"),
    "exhaustion_short": ("reversion", "reversal", "SHORT"),
    "abs_veto_short": ("momentum", "thrust", "SHORT"),
    "rgv_short": ("fade", "turnback", "SHORT"),
    # ★2026-08-05 nipc was MISSING here since it shipped 08-01, so the board silently showed 6 of 8
    # gates for four days. A dashboard that omits a gate is worse than one that shows it benched —
    # you cannot notice the state of something you are never shown. Same failure as the truncated
    # shadow block that hid a 9-of-9 green thrust family from the router.
    # This map is the ONLY place gates are enumerated for the panel, so it must track the live roster.
    "nipc_long": ("news", "impulse-pullback", "LONG"),
    "nipc_short": ("news", "impulse-pullback", "SHORT"),
}


def _router_reason(on, fam, side, is_chop, bias):
    """Derive WHY a gate is on/off from its mechanism + the live regime — so it stays true
    as the regime changes, rather than a hardcoded string that goes stale."""
    if on:
        if fam == "news":
            return "armed — news-impulse window"
        if fam in ("reversion", "fade"):
            return "armed — reversion fits a rotation"
        return "armed — aligned momentum"
    # ★2026-08-05 nipc is not benched by REGIME — it is PINNED OFF in the router and held out of the
    # 22:00 reactivation pending the live/replay divergence diagnosis. Showing it as "benched —
    # momentum bleeds in the rotation" would imply the router might re-arm it on a regime change,
    # which is exactly wrong and the sort of misleading label that gets acted on.
    if fam == "news":
        return "PINNED OFF — failed acceptance replay; held from the nightly re-arm"
    if side == "SHORT" and bias == "UP":
        return "benched — counter to the up-day"
    if side == "LONG" and bias == "DOWN":
        return "benched — counter to the down-day"
    if fam == "momentum" and is_chop:
        return "benched — momentum bleeds in the rotation"
    if fam == "fade" and side == "SHORT":
        return "benched — needs an over-extension above VWAP; no setup"
    return "benched"


def router_json(store_path, cap_path, data_dir):
    """The ROUTER watch panel: multi-clock regime read (why a 0.3 ER can still be chop),
    per-gate on/off + reason + live P&L, the shadow-family cross-check, the timestamped
    activity stream (from router_trial_log.txt), and the <=2 open slots. Read-only; every
    section is independently guarded so one bad read never blanks the page."""
    now = datetime.now(UTC)
    out = {"ts": now.astimezone(_PARIS).strftime("%Y-%m-%d %H:%M:%S"), "tz": "Paris",
           "regime": {}, "gates": [], "shadow": {}, "activity": [], "holdings": [],
           "chandeliers": [], "day": {}, "untradeable": {}, "leaning": {}}
    cl = []
    try:
        s = pnl.paris_day_start_utc(now)
        ds_dt = datetime.fromisoformat(s) if isinstance(s, str) else s
        ds_ep = int(ds_dt.timestamp())
        ds_iso = ds_dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        ds_ep = int(now.timestamp()) - now.hour * 3600
        ds_iso = now.strftime("%Y-%m-%dT00:00:00")

    try:   # UNTRADEABLE-DAY METER (stay-out evidence) — guarded, never blanks the page
        from .untradeable import compute as _untradeable_compute
        out["untradeable"] = _untradeable_compute(cap_path, store_path, ds_ep, int(now.timestamp()))
    except Exception:
        out["untradeable"] = {}

    # ★2026-08-05 DAY LEANING — operator: "dashboard needs a way to indicate to me the way the day is
    # leaning. so i know. then when its confirmed we buy 2 lots."
    # It calls the SAME gazbot7.drift.read() the live service calls, so the panel can never show one
    # thing while the desk acts on another (pnl.py's one-source-of-truth rule, applied to a signal).
    # The `*_needed` fields are surfaced on purpose: the operator wants to watch it BUILD toward
    # confirmation, not just be told the instant it fires.
    try:
        from .drift import ER_MIN as _ERM, RT_MIN as _RTM, read as _drift_read
        _d = _drift_read(cap_path, now=now)
        out["leaning"] = {
            "ok": _d.ok, "direction": _d.direction, "confirmed": _d.confirmed,
            "minutes": _d.minutes, "net_pt": round(_d.net_pt, 1), "range_pt": round(_d.range_pt, 1),
            "efficiency": round(_d.efficiency, 3), "roundtrip": round(_d.roundtrip, 3),
            "er_min": _ERM, "rt_min": _RTM,
            "er_needed": round(_d.er_needed, 3), "rt_needed": round(_d.rt_needed, 3),
            "blockers": _d.blockers, "detail": _d.detail,
        }
    except Exception:
        out["leaning"] = {}

    day_bias, day_net, day_er, day_hi, day_lo = "FLAT", 0.0, None, None, None
    try:
        c = _conn(cap_path)
        rows = c.execute(
            "SELECT bar_ts, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
            "AND bar_ts>=? AND bar_ts<=? ORDER BY bar_ts", (ds_ep, int(now.timestamp()))).fetchall()
        c.close()
        mins = {}  # last close per minute → same 1-min basis as desk_view, so day-ER matches
        for r in rows:
            mins[r["bar_ts"] // 60] = r["close"]
        cl = [mins[k] for k in sorted(mins)]
        if len(cl) >= 6:
            day_net = cl[-1] - cl[0]
            path = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1.0
            day_er = round(abs(cl[-1] - cl[0]) / path, 3)
            day_hi, day_lo = max(cl), min(cl)
            day_bias = "DOWN" if day_net < -40 else ("UP" if day_net > 40 else "FLAT")
    except Exception:
        pass
    f = _features(cap_path) or {}
    last = f.get("last") or (cl[-1] if cl else None)
    r_lo, r_hi = day_lo, day_hi
    try:
        c = _conn(cap_path)
        rr = c.execute("SELECT MIN(low) lo, MAX(high) hi FROM bars WHERE symbol='MNQ' "
                       "AND timeframe='5s' AND bar_ts>=?", (int(now.timestamp()) - 3 * 3600,)).fetchone()
        c.close()
        if rr and rr["lo"] is not None:
            r_lo, r_hi = rr["lo"], rr["hi"]
    except Exception:
        pass
    er30 = f.get("er")
    is_chop = (day_er is not None and day_er < 0.12)
    verdict = ("TREND " + day_bias if (day_er or 0) >= 0.20
               else "RANGE-ROTATION" if is_chop else "MIXED")
    posn = None
    if last is not None and r_hi is not None and r_hi > (r_lo or 0):
        posn = round(max(0.0, min(1.0, (last - r_lo) / (r_hi - r_lo))) * 100)
    out["regime"] = {
        "verdict": verdict, "day_bias": day_bias, "day_net": round(day_net),
        "day_er": day_er, "er_30min": round(er30, 2) if er30 is not None else None,
        "atr_pts": f.get("atr_pts"), "violence": f.get("violence"), "last": last,
        "range_lo": r_lo, "range_hi": r_hi, "range_pos": posn,
        "day_hi": day_hi, "day_lo": day_lo,
    }

    live = {}
    try:
        c = _conn(store_path)
        for r in c.execute("SELECT gate, ROUND(SUM(pnl_usd),1) p, COUNT(*) n FROM trades "
                           "WHERE closed_at>=?" + _dq(c) + " GROUP BY gate", (ds_iso,)).fetchall():
            g = r["gate"] or ""
            base = g.rsplit("_", 1)[0] if g.rsplit("_", 1)[-1] in ("A", "B") else g
            d = live.setdefault(base, [0.0, 0])
            d[0] += r["p"] or 0.0
            d[1] += r["n"]
        c.close()
    except Exception:
        pass
    switches = {}
    try:
        for ln in open(os.path.join(data_dir, "gate_switches.env")):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                switches[k.strip()] = v.strip().lower() == "on"
    except Exception:
        pass
    for name, (fam, sub, side) in _ROUTER_META.items():
        on = switches.get(name, True)
        lv = live.get(name)
        out["gates"].append({
            "name": name, "family": fam, "mech": sub, "side": side, "on": on,
            "reason": _router_reason(on, fam, side, is_chop, day_bias),
            "live_pnl": round(lv[0], 1) if lv else None, "trades": lv[1] if lv else 0,
        })

    try:
        c = _conn(os.path.join(data_dir, "shadow.db"))
        fam_map = {"momentum-long": ("grind_fast", "thrust_aligned", "thrust_loose", "thrust_fast", "chand_k25", "chand_k20"),
                   "momentum-short": ("thrust_short_raw", "thrust_short_absveto55"),
                   "reversion": ("capit_loose", "capit_mid", "rg_long_fast", "rg_long_fast_v")}
        for fam, strats in fam_map.items():
            q = ",".join("?" * len(strats))
            r = c.execute(f"SELECT ROUND(SUM(ceiling_pnl),1) p, COUNT(*) n FROM shadow_trades "
                          f"WHERE CAST(entry_ts AS BIGINT)>=? AND exit_price IS NOT NULL AND strategy IN ({q})",
                          (ds_ep, *strats)).fetchone()
            out["shadow"][fam] = {"pnl": r["p"], "n": r["n"]} if r and r["p"] is not None else {"pnl": None, "n": 0}
        c.close()
    except Exception:
        pass

    try:
        lines = open(os.path.join(data_dir, "router_trial_log.txt")).read().splitlines()
        for ln in reversed(lines[-24:]):
            parts = [p.strip() for p in ln.split(" | ")]
            if len(parts) < 3:
                continue
            try:
                t = datetime.fromisoformat(parts[0].replace("Z", "+00:00")).astimezone(_PARIS).strftime("%H:%M")
            except (ValueError, TypeError):
                t = parts[0][11:16] if len(parts[0]) >= 16 else parts[0]
            kind = parts[1] if len(parts) > 1 else ""
            changed, gist = "", ""
            for p in parts:
                if p.startswith("changed:"):
                    changed = p[8:].strip()
                if p.startswith("HOLISTIC:") or p.startswith("KEY:") or "VINDICAT" in p or "★" in p:
                    gist = p.split(":", 1)[-1].strip() if ":" in p else p
            if not gist:
                gist = parts[2]
            is_change = bool(changed) and changed.lower() not in ("none", "none (hold)")
            tag = "EXTEND" if kind == "EXTEND" else ("CHG" if is_change else "hold")
            out["activity"].append({"t": t, "tag": tag, "changed": changed,
                                    "text": gist[:180], "is_change": is_change})
    except Exception:
        pass

    try:
        c = _conn(store_path)
        rr = c.execute("SELECT pnl_usd FROM trades WHERE closed_at>=?" + _dq(c)
                       + " ORDER BY closed_at", (ds_iso,)).fetchall()
        c.close()
        run, peak = 0.0, 0.0
        for r in rr:
            run += r["pnl_usd"] or 0.0
            peak = max(peak, run)
        out["day"] = {"pnl": round(run, 1), "peak": round(peak, 1), "trades": len(rr)}
    except Exception:
        out["day"] = {}
    try:
        st = _status(data_dir)
        out["day"]["flat"] = bool(st.get("flat", not st.get("position")))
        out["day"]["healthy"] = st.get("healthy")
        out["day"]["halted"] = st.get("halted")
        raw = st.get("position")
        slots = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) and not raw.get("flat") else [])
        for s in slots:
            entry = s.get("entry_price") or s.get("entry")
            if entry is None:
                continue
            side = s.get("side") or ("SHORT" if (s.get("qty") or 0) < 0 else "LONG")
            sign = 1 if side == "LONG" else -1
            lastp = last or entry
            held = None
            if s.get("opened_at"):
                try:
                    held = int((now - datetime.fromisoformat(s["opened_at"])).total_seconds())
                except (ValueError, TypeError):
                    held = None
            out["holdings"].append({
                "gate": s.get("gate", "—"), "side": side, "qty": abs(s.get("qty") or 1),
                "entry": entry, "stop": s.get("stop_price") or s.get("stop"),
                "pnl_usd": round(sign * (lastp - entry) * _VPP * abs(s.get("qty") or 1), 1),
                "held_s": held, "protected": bool(s.get("stop_coid")),
            })
        # ── Lot B chandelier tail metrics — the give-back-exit visibility ──
        # peak_favorable isn't stored, so reconstruct it from capture bars since entry.
        # BIG-RUN gates use exit_chandelier_lock (wide 3.5xATR trail → LOCK to 0.5xATR at
        # lock_r=6R); FADERS use the continuously-tightening exit_chandelier (start 1.5).
        CH = {"grind_long": ("lock", 3.5, 6.0, 0.5), "abs_veto_long": ("lock", 3.5, 6.0, 0.5),
              "abs_veto_short": ("lock", 3.5, 6.0, 0.5), "exhaustion_short": ("lock", 3.5, 6.0, 0.5),
              "rgv_short": ("trail", 1.5, 0.5, 0.75), "capitulation_long": ("trail", 1.5, 0.5, 0.75)}
        for s in slots:
            g = s.get("gate", "")
            base = g[:-2] if g.endswith(("_A", "_B")) else g
            if not g.endswith("_B") or base not in CH:
                continue
            entry = s.get("entry_price") or s.get("entry")
            atr = s.get("entry_atr") or 0
            if not entry or atr <= 0:
                continue
            side = s.get("side") or "LONG"
            qty = abs(s.get("qty") or 1)
            lastp = last or entry
            peakfav = 0.0
            try:
                op = int(datetime.fromisoformat(s["opened_at"]).timestamp())
                c2 = _conn(cap_path)
                rr = c2.execute("SELECT MAX(high) hi, MIN(low) lo FROM bars WHERE symbol='MNQ' "
                                "AND timeframe='5s' AND bar_ts>=?", (op,)).fetchone()
                c2.close()
                if rr and rr["hi"] is not None:
                    peakfav = (rr["hi"] - entry) if side == "LONG" else (entry - rr["lo"])
            except Exception:
                pass
            peakfav = max(peakfav, (lastp - entry) if side == "LONG" else (entry - lastp), 0.0)
            peak_r = peakfav / atr
            cur_r = ((lastp - entry) if side == "LONG" else (entry - lastp)) / atr
            ctype, start_k, p2, p3 = CH[base]
            if ctype == "lock":
                active = peak_r >= p2
                k = p3 if active else start_k
                r_to_go = None if active else round(max(0.0, p2 - peak_r), 2)
                lock_r = p2
            else:
                k = max(p2, start_k - p3 * peak_r)
                active = peakfav > 0
                r_to_go = None
                lock_r = None
            giveback_pts = k * atr
            exit_fav = peakfav - giveback_pts   # fav level that fires CHANDELIER
            exit_price = entry + exit_fav if side == "LONG" else entry - exit_fav
            r_usd = atr * _VPP * qty            # 1R in dollars (stop distance × $2/pt × qty)
            out["chandeliers"].append({
                "gate": g, "side": side, "type": ctype, "armed": peakfav > 0, "active": bool(active),
                "cur_r": round(cur_r, 2), "peak_r": round(peak_r, 2), "lock_r": lock_r,
                "r_to_activate": r_to_go, "k": round(k, 2),
                "r_usd": round(r_usd), "cur_usd": round(cur_r * r_usd), "peak_usd": round(peak_r * r_usd),
                "lock_usd": (round(lock_r * r_usd) if lock_r else None),
                "to_activate_usd": (round(r_to_go * r_usd) if r_to_go else None),
                "giveback_pts": round(giveback_pts, 1), "giveback_usd": round(giveback_pts * _VPP * qty),
                "exit_price": round(exit_price, 1),
                "peak_price": round(entry + peakfav if side == "LONG" else entry - peakfav, 1),
                "locked_usd": round(max(0.0, exit_fav) * _VPP * qty),
            })
    except Exception:
        pass
    return out


# ── POST /api/control/claim — operator "Claim profit" per-slot flatten ─────────
def claim_post(body, data_dir):
    """PIN-guarded per-slot flatten REQUEST. Verifies {pin} against data/claim_pin.txt
    (server-side), then appends {gate} to data/claim_requests.txt for the tournament to
    consume on its next manage cycle via the desk's OWN safe _flatten_slot. This web layer
    NEVER touches positions/broker — zero ledger risk from here; the trading core owns the
    actual flatten. Fat-finger guard, not real auth (fine for PAPER; not for real money)."""
    try:
        req = json.loads(body or b"{}")
    except Exception:
        return {"ok": False, "error": "bad request"}
    gate = str(req.get("gate", "")).strip()
    pin = str(req.get("pin", "")).strip()
    if not gate:
        return {"ok": False, "error": "no gate given"}
    try:
        want = open(os.path.join(data_dir, "claim_pin.txt")).read().strip()
    except Exception:
        return {"ok": False, "error": "claim PIN not set on server"}
    if not want or pin != want:
        return {"ok": False, "error": "wrong PIN"}
    try:
        with open(os.path.join(data_dir, "claim_requests.txt"), "a") as f:
            f.write(gate + "\n")
    except Exception as e:
        return {"ok": False, "error": f"write failed: {e}"}
    return {"ok": True, "gate": gate, "msg": f"claim requested — {gate} flattens on the next cycle"}


# ── POST /api/control/dayrider-claim — operator "Claim profit" on the day rider ─
def dayrider_claim_post(body, data_dir):
    """PIN-guarded REQUEST to bank the day rider's open position.

    Same shape as claim_post above and for the same reason: this layer writes a
    file and returns, and the DAY RIDER does the flatten on its own cycle through
    own_flatten_verdict. The web process never touches the broker. A button that
    reached the broker directly is how 2026-08-06 happened — a flatten fired
    without checking whose position it was and took the tournament's with it.

    ⚠ Not instant. The day rider ticks every minute, so the fill is up to ~60s
    after the press and the price will have moved. The response says so rather
    than letting the operator believe he banked the number he was looking at.
    ⚠ It ENDS the session: the `closed` latch means no re-entry today.
    """
    try:
        req = json.loads(body or b"{}")
    except Exception:
        return {"ok": False, "error": "bad request"}
    pin = str(req.get("pin", "")).strip()
    try:
        want = open(os.path.join(data_dir, "claim_pin.txt")).read().strip()
    except Exception:
        return {"ok": False, "error": "claim PIN not set on server"}
    if not want or pin != want:
        return {"ok": False, "error": "wrong PIN"}
    # Refuse when there is nothing to claim, so the button cannot leave a stale
    # request file lying in wait to fire against tomorrow's position.
    try:
        st = json.load(open(os.path.join(data_dir, "day_rider_state.json")))
    except Exception:
        st = {}
    if not st.get("entered") or st.get("closed"):
        return {"ok": False, "error": "nothing to claim — the day rider is not in a position"}
    try:
        with open(os.path.join(data_dir, "day_rider_claim.txt"), "w") as f:
            f.write(datetime.now(UTC).isoformat() + "\n")
    except Exception as e:
        return {"ok": False, "error": f"write failed: {e}"}
    return {"ok": True, "msg": "claim requested — the day rider flattens on its next tick (up to ~60s). "
                               "This ends its session; it will not re-enter today."}


# ── /api/shadow/* — the shadow desk (V5 shadow_desk.html verbatim; V7 data) ────
def _shadow_block(vals):
    """The {n, real_pnl, win} block the shadow UI reads — honest net, win% or null."""
    n = len(vals)
    if n == 0:
        return {"n": 0, "real_pnl": 0, "win": None}
    return {"n": n, "real_pnl": round(sum(vals), 2),
            "win": round(100 * sum(1 for v in vals if v > 0) / n)}


def _paris_day_bounds(date_str):
    """(day_start, day_end) unix-seconds for the viewed Paris day (default: today)."""
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_PARIS)
    else:
        d = datetime.now(_PARIS)
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = start.timestamp()
    return day_start, day_start + 86400


def shadow_overview_json(shadow_path, date=None):
    """Per-variant honest P&L (real_pnl, filled trades) over today/week/all, plus
    by-symbol — the shape shadow_desk.html renders. real_available always True in
    V7 (the repricer writes real_pnl; no ceiling-mirage fallback)."""
    from .cb import CB_STRATEGIES
    from .shadow import default_slate
    day_start, day_end = _paris_day_bounds(date)
    wk_start = day_end - 7 * 86400
    # registered fleet (shown even if idle) = the variant slate + the circuit-breaker legs
    # ★2026-08-04: + the CL- sims. They are driven by cl_sims.ClSims / scripts/cl_worker.py rather
    # than default_slate(), so building the fleet from the slate alone made them INVISIBLE on the
    # shadow board — they would not have appeared even once they started trading. Registered here so
    # they show (at zero) from the outset, which also means "CL sim not trading" is visible rather
    # than indistinguishable from "CL sim does not exist".
    from .cl_sims import CL_GATES
    fleet = [v.name for v in default_slate()] + list(CB_STRATEGIES) + list(CL_GATES)
    try:
        c = _conn(shadow_path)
        rows = c.execute(
            "SELECT st.strategy s, st.symbol sym, st.exit_ts ts, sr.real_pnl pnl "
            "FROM shadow_trades st JOIN shadow_real sr ON sr.trade_id=st.id "
            "WHERE sr.fill_status='filled'").fetchall()
        c.close()
    except Exception:
        rows = []
    # the board shows the REGISTERED fleet only — a variant culled from the slate
    # vanishes from the dashboard (its history stays in shadow.db for analysis).
    names = fleet
    fleet_set = set(fleet)
    agg = {s: {"today": [], "week": [], "all": [], "by_symbol": {}, "min_ts": None} for s in names}
    for r in rows:
        if r["s"] not in fleet_set:  # culled variant — excluded from the board + totals
            continue
        a = agg[r["s"]]
        ts, p = r["ts"], r["pnl"]
        if ts >= day_end:  # future relative to the viewed day
            continue
        bs = a["by_symbol"].setdefault(r["sym"], {"today": [], "week": [], "all": []})
        a["all"].append(p); bs["all"].append(p)
        a["min_ts"] = ts if a["min_ts"] is None else min(a["min_ts"], ts)
        if ts >= wk_start:
            a["week"].append(p); bs["week"].append(p)
        if day_start <= ts < day_end:
            a["today"].append(p); bs["today"].append(p)
    strategies = []
    for s in names:
        a = agg[s]
        strategies.append({
            "strategy": s, "armed": True,
            "days_live": None if a["min_ts"] is None else max(0, round((day_end - a["min_ts"]) / 86400)),
            "today": _shadow_block(a["today"]), "week": _shadow_block(a["week"]), "all": _shadow_block(a["all"]),
            "by_symbol": {sym: {"today": _shadow_block(b["today"]), "week": _shadow_block(b["week"]),
                                "all": _shadow_block(b["all"])} for sym, b in a["by_symbol"].items()},
        })
    return {
        "today_total": round(sum(sum(a["today"]) for a in agg.values()), 2),
        "week_total": round(sum(sum(a["week"]) for a in agg.values()), 2),
        "all_total": round(sum(sum(a["all"]) for a in agg.values()), 2),
        "n_strategies": len(names), "as_of": (date or datetime.now(_PARIS).strftime("%Y-%m-%d")),
        "real_available": True, "strategies": strategies,
    }


def shadow_activity_json(shadow_path, limit=50):
    """Most-recent filled shadow trades, honest net — the Activity tab feed."""
    try:
        c = _conn(shadow_path)
        rows = c.execute(
            "SELECT st.strategy, st.symbol, st.side, st.exit_ts, st.exit_reason, sr.real_pnl "
            "FROM shadow_trades st JOIN shadow_real sr ON sr.trade_id=st.id "
            "WHERE sr.fill_status='filled' ORDER BY st.exit_ts DESC, st.id DESC LIMIT ?",
            (limit,)).fetchall()
        c.close()
    except Exception:
        rows = []
    return {"trades": [{"exit_ts": r["exit_ts"], "strategy": r["strategy"], "symbol": r["symbol"],
                        "side": r["side"], "exit_reason": r["exit_reason"],
                        "pnl": round(r["real_pnl"], 2)} for r in rows]}


def tradeability_json(cap_path):
    """★2026-08-03 — the live 0-10 tape gauge (operator: "show me what we are currently sitting in").

    A GUIDE, not a gate: nothing arms or benches off this. Rolling, not day-cumulative, because the
    existing untradeable meter is cumulative and on 08-03 still read 37/TRADEABLE at 19:36 when ATR
    had collapsed to 9pt. Validated against the shadow book (the honest counterfactual for what the
    desk's mechanisms would have made): correlation +0.50 over 16 days, low-score days averaging
    -$1,904 of shadow P&L against +$612 for high-score days. Two known misses, 07-30 and 07-31 — both
    scored ~4.2 and lost >$3,000, so a good score is NOT permission to size up."""
    try:
        from .tradeability import live
        r = live(cap_path)
        return {"score": r.score, "label": r.label, "detail": r.detail,
                "er30": r.er30, "atr": r.atr,
                "components": {"efficiency": r.efficiency, "room": r.room,
                               "persistence": r.persistence}}
    except Exception as e:
        # a gauge that silently shows a stale number is worse than one that admits it cannot see
        return {"score": None, "label": "unavailable", "detail": str(e)}


def reports_json(static_dir):
    """List the weekly_<date>.html reports in web_static, newest first, with the
    <title> pulled from each file. The reports index reads this to render its cards."""
    import re
    out = []
    for fn in sorted(os.listdir(static_dir)):
        m = re.match(r"(?:weekly|v7_big_runs|gates)_(\d{4}-\d{2}-\d{2})\.html$", fn)
        if not m:
            continue
        title = fn
        try:
            head = open(os.path.join(static_dir, fn), encoding="utf-8").read(2000)
            tm = re.search(r"<title>(.*?)</title>", head, re.S)
            if tm:
                title = tm.group(1).strip()
        except OSError:
            pass
        pdf = fn[:-5] + ".pdf"  # weekly_<date>.pdf sibling, if a PDF was rendered
        has_pdf = os.path.exists(os.path.join(static_dir, pdf))
        play = "monday_" + m.group(1) + ".html"  # the Monday playbook for this week, if built
        has_play = os.path.exists(os.path.join(static_dir, play))
        out.append({"date": m.group(1), "file": fn, "title": title,
                    "pdf": pdf if has_pdf else None, "play": play if has_play else None})
    out.sort(key=lambda r: r["date"], reverse=True)
    return {"reports": out}


# ── /api/cube/* — the daily-capture X-ray (market × session-phase grid) ────────
# Faithful V7 port of the retired V5 Cube: each cell = what the tape did (regime / flow
# from capture.db) + what we traded (P&L / gates from the store), sliced by session phase.
# Descriptive, NOT edge — a rough per-minute heuristic, not the courtroom verdict.
_CUBE_MARKETS = ["US"]
_CUBE_PHASES = ["overnight", "eu_session", "us_open", "us_midday", "us_pm"]


def _cube_iso_epoch(iso):
    """ISO-8601 text → epoch seconds (UTC-anchored; naive treated as UTC)."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _cube_paris_date(iso):
    """The Paris calendar date (YYYY-MM-DD) an ISO-8601 UTC instant falls on."""
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(_PARIS).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _session_phase(ts_epoch):
    """UTC session phase for an epoch timestamp (seconds; ms auto-normalised). Ported
    verbatim from V5 intelligence/session_phase.py — same UTC boundaries so the grid's
    time buckets match the desk's capture convention."""
    ts = float(ts_epoch)
    if ts > 1e12:  # milliseconds
        ts /= 1000.0
    dt = datetime.fromtimestamp(ts, tz=UTC)
    h = dt.hour + dt.minute / 60.0
    if h < 7.0 or h >= 22.0:
        return "overnight"
    if h < 13.5:
        return "eu_session"
    if h < 15.5:
        return "us_open"
    if h < 19.0:
        return "us_midday"
    return "us_pm"


def _paris_day_utc_bounds(date_str):
    """(start, end) UTC datetimes bracketing the Paris day ``date_str`` — DST-correct
    (each midnight localised independently, so a 23h/25h DST day is exact)."""
    d0 = datetime.strptime(date_str, "%Y-%m-%d")
    start = d0.replace(tzinfo=_PARIS).astimezone(UTC)
    end = (d0 + timedelta(days=1)).replace(tzinfo=_PARIS).astimezone(UTC)
    return start, end


def _cube_classify(bars):
    """Regime read for a phase's 5s bars: aggregate to 1-min windows, classify each window
    (dead / shock / trending / chop) by its range + own efficiency, return the dominant, the
    mix (pct), the window count (cycles) and mean net-move-in-ATR. Rough by design — MVP."""
    if not bars:
        return {"cycles": 0, "dominant_regime": None, "regime_mix": {}, "avg_net_atr": None}
    agg: dict = {}
    for b in bars:
        m = (b["bar_ts"] // 60) * 60
        a = agg.get(m)
        if a is None:
            agg[m] = [b["open"], b["high"], b["low"], b["close"]]
        else:
            a[1] = max(a[1], b["high"])
            a[2] = min(a[2], b["low"])
            a[3] = b["close"]
    windows = [agg[m] for m in sorted(agg)]
    cycles = len(windows)
    ranges = [w[1] - w[2] for w in windows]
    atr = (sum(ranges) / len(ranges)) if ranges else 0.0
    counts = {"trending": 0, "chop": 0, "shock": 0, "dead": 0}
    net_atrs = []
    for o, h, low, cl in windows:
        rng = h - low
        net = cl - o
        er = abs(net) / rng if rng > 1e-9 else 0.0
        # cutoffs calibrated to MNQ 1-min range percentiles (p10≈7pt, median≈13pt, p90≈29pt):
        # dead = the quietest ~decile, shock = the most violent ~decile, the rest split by efficiency.
        if rng < 6.0:
            reg = "dead"
        elif rng > 30.0:
            reg = "shock"
        elif er >= 0.5:
            reg = "trending"
        else:
            reg = "chop"
        counts[reg] += 1
        if atr > 1e-9:
            net_atrs.append(net / atr)
    dom = max(counts, key=lambda k: counts[k]) if cycles else None
    if dom and counts[dom] == 0:
        dom = None
    mix = {k: round(100.0 * v / cycles, 1) for k, v in counts.items() if v > 0} if cycles else {}
    avg_net_atr = round(sum(net_atrs) / len(net_atrs), 2) if net_atrs else None
    return {"cycles": cycles, "dominant_regime": dom, "regime_mix": mix, "avg_net_atr": avg_net_atr}


def cube_days_json(store_path):
    """Distinct Paris-days present in the trades store (by ``closed_at``), newest first —
    the day picker's option list."""
    days = set()
    try:
        c = _conn(store_path)
        rows = c.execute(
            "SELECT DISTINCT closed_at FROM trades WHERE symbol='MNQ' AND exit_reason NOT IN ("
            + ",".join("?" * len(_CLEANUP)) + ")" + _dq(c), tuple(_CLEANUP)).fetchall()
        c.close()
        for r in rows:
            d = _cube_paris_date(r["closed_at"])
            if d:
                days.add(d)
    except Exception:
        pass
    return {"days": sorted(days, reverse=True)}


def cube_json(store_path, cap_path, day):
    """The X-ray for one Paris day (or ``latest``): a dense market×phase grid + per-contract
    drill. Cells fuse the trades store (P&L / trades / win% / gates, phase-bucketed by
    ``opened_at``) with capture.db (regime + cycles from 5s ``bars``; signed-aggressor OFI
    from ``ticks``). ``themes`` is always null in V7 (no desk_analysis) — the UI degrades."""
    now = datetime.now(UTC)
    avail = cube_days_json(store_path)["days"]
    if day == "latest" or not day:
        day = avail[0] if avail else now.astimezone(_PARIS).strftime("%Y-%m-%d")
    try:
        start, end = _paris_day_utc_bounds(day)
    except Exception:
        day = now.astimezone(_PARIS).strftime("%Y-%m-%d")
        start, end = _paris_day_utc_bounds(day)

    phases = _CUBE_PHASES
    # --- what we traded: P&L / trades / wins / gates per phase (from the store) ---
    pnl_by_phase = {ph: {"pnl": 0.0, "n": 0, "w": 0, "gates": {}} for ph in phases}
    try:
        c = _conn(store_path)
        trows = c.execute(
            "SELECT opened_at, closed_at, pnl_usd, gate FROM trades WHERE symbol='MNQ' "
            "AND exit_reason NOT IN (" + ",".join("?" * len(_CLEANUP)) + ")" + _dq(c),
            tuple(_CLEANUP)).fetchall()
        c.close()
        for r in trows:
            if _cube_paris_date(r["closed_at"]) != day:  # same day-convention as available-days
                continue
            ph = _session_phase(_cube_iso_epoch(r["opened_at"]))
            b = pnl_by_phase[ph]
            b["pnl"] += r["pnl_usd"]
            b["n"] += 1
            if r["pnl_usd"] > 0:
                b["w"] += 1
            g = r["gate"] or "—"
            b["gates"][g] = b["gates"].get(g, 0) + 1
    except Exception:
        pass

    # --- what the tape did: FLOW (signed-aggressor OFI) per phase, aggregated in SQL ---
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    ofi_by_phase: dict = {}
    try:
        c = _conn(cap_path)
        hx = ("(CAST(strftime('%H', ts_ms/1000, 'unixepoch') AS REAL)"
              " + CAST(strftime('%M', ts_ms/1000, 'unixepoch') AS REAL)/60.0)")
        rows = c.execute(
            f"SELECT CASE WHEN {hx}<7.0 OR {hx}>=22.0 THEN 'overnight' "
            f"WHEN {hx}<13.5 THEN 'eu_session' WHEN {hx}<15.5 THEN 'us_open' "
            f"WHEN {hx}<19.0 THEN 'us_midday' ELSE 'us_pm' END phase, "
            f"SUM(CASE aggressor WHEN 'buy' THEN size WHEN 'sell' THEN -size ELSE 0 END) signed, "
            f"COUNT(*) n FROM ticks WHERE symbol='MNQ' AND ts_ms>=? AND ts_ms<? GROUP BY phase",
            (start_ms, end_ms)).fetchall()
        c.close()
        for r in rows:
            n = r["n"] or 0
            ofi_by_phase[r["phase"]] = (r["signed"] / n) if n else None
    except Exception:
        pass

    # --- what the tape did: REGIME + cycles + net-ATR per phase (from 5s bars) ---
    regime_by_phase = {ph: _cube_classify([]) for ph in phases}
    try:
        c = _conn(cap_path)
        brows = c.execute(
            "SELECT bar_ts, open, high, low, close FROM bars WHERE symbol='MNQ' "
            "AND timeframe='5s' AND bar_ts>=? AND bar_ts<? ORDER BY bar_ts",
            (int(start.timestamp()), int(end.timestamp()))).fetchall()
        c.close()
        buckets = {ph: [] for ph in phases}
        for b in brows:
            buckets[_session_phase(b["bar_ts"])].append(b)
        for ph, bars in buckets.items():
            regime_by_phase[ph] = _cube_classify(bars)
    except Exception:
        pass

    # --- assemble the dense grid + per-contract drill ---
    grid: dict = {"US": {}}
    drill: dict = {"US": {}}
    for ph in phases:
        reg = regime_by_phase[ph]
        pb = pnl_by_phase[ph]
        ofi = ofi_by_phase.get(ph)
        ofi = round(ofi, 2) if ofi is not None else None
        n = pb["n"]
        wr = (pb["w"] / n) if n else None
        grid["US"][ph] = {
            "cycles": reg["cycles"], "dominant_regime": reg["dominant_regime"],
            "regime_mix": reg["regime_mix"], "pnl": round(pb["pnl"], 2), "trades": n,
            "win_rate": wr, "avg_ofi": ofi,
        }
        if reg["cycles"] or n:
            drill["US"][ph] = [{
                "symbol": "MNQ", "dominant_regime": reg["dominant_regime"], "avg_ofi": ofi,
                "avg_net_atr": reg["avg_net_atr"], "cycles": reg["cycles"], "trades": n,
                "win_rate": wr, "pnl": round(pb["pnl"], 2), "gates": pb["gates"],
            }]
        else:
            drill["US"][ph] = []

    return {
        "day": day, "markets": _CUBE_MARKETS, "phases": phases, "grid": grid, "drill": drill,
        "themes": None,  # V7 has no desk_analysis — the frontend shows the "generate nightly" note
        "note": "Descriptive X-ray from capture + trades. Regime is a rough per-minute heuristic "
                "(range + efficiency), not the courtroom verdict.",
    }


def serve(port, store_path, cap_path, data_dir, shadow_path):
    class H(http.server.BaseHTTPRequestHandler):
        # 2026-07-22: drop a slow/dead client after this long so its thread is freed (a client that
        # gave up mid-response left a BrokenPipe + tied up the single thread → the whole page froze).
        timeout = 30

        def _send(self, body, ct, code=200):
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj):
            self._send(json.dumps(obj).encode(), "application/json")

        def do_POST(self):
            try:
                path = urlparse(self.path).path
                n = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(n) if n else b""
                if path == "/api/control/claim":
                    self._json(claim_post(body, data_dir))
                elif path == "/api/control/dayrider-claim":
                    self._json(dayrider_claim_post(body, data_dir))
                else:
                    self._send(b"not found", "text/plain", 404)
            except Exception as e:
                self._send(f"error: {e}".encode(), "text/plain", 500)

        def do_GET(self):
            try:
                p = urlparse(self.path)
                path, qs = p.path, parse_qs(p.query)
                if path == "/" or path.startswith("/index"):
                    self._send(open(os.path.join(_STATIC, "app.html"), "rb").read(), _CT[".html"])
                elif path == "/shadow" or path == "/shadow/":
                    self._send(open(os.path.join(_STATIC, "shadow.html"), "rb").read(), _CT[".html"])
                elif path == "/reports" or path == "/reports/":
                    self._send(open(os.path.join(_STATIC, "reports.html"), "rb").read(), _CT[".html"])
                elif path == "/cube" or path == "/cube/":
                    self._send(open(os.path.join(_STATIC, "cube.html"), "rb").read(), _CT[".html"])
                elif path == "/router" or path == "/router/":
                    self._send(open(os.path.join(_STATIC, "router.html"), "rb").read(), _CT[".html"])
                elif path.startswith("/api/futures/router"):
                    self._json(router_json(store_path, cap_path, data_dir))
                elif path.startswith("/api/tradeability"):
                    self._json(tradeability_json(cap_path))
                elif path.startswith("/api/reports"):
                    self._json(reports_json(_STATIC))
                elif path.startswith("/api/cube/available-days"):
                    self._json(cube_days_json(store_path))
                elif path.startswith("/api/cube/"):
                    self._json(cube_json(store_path, cap_path, path.rsplit("/", 1)[-1]))
                elif path.startswith("/static/"):
                    fp = os.path.join(_STATIC, os.path.basename(path))
                    self._send(open(fp, "rb").read(), _CT.get(os.path.splitext(fp)[1], "text/plain"))
                elif path.startswith("/api/shadow/overview"):
                    self._json(shadow_overview_json(shadow_path, (qs.get("date", [None])[0])))
                elif path.startswith("/api/shadow/activity"):
                    self._json(shadow_activity_json(shadow_path, min(200, int(qs.get("limit", ["50"])[0]))))
                elif path.startswith("/api/futures/bars/MNQ"):
                    self._json(bars_json(cap_path, min(600, int(qs.get("count", ["120"])[0]))))
                elif path.startswith("/api/futures/us-terminal"):
                    self._json(us_terminal_json(cap_path, data_dir))
                elif path.startswith("/api/futures/tournament"):
                    self._json(tournament_json(store_path, data_dir, cap_path))
                elif path.startswith("/api/futures/promotion"):
                    self._json(promotion_json(shadow_path))
                elif path.startswith("/api/futures/mnq"):
                    self._json(mnq_json(store_path))
                elif path.startswith("/api/futures/execution"):
                    self._json(execution_json(store_path))
                else:
                    self._send(b"not found", "text/plain", 404)
            except Exception as e:
                self._send(f"error: {e}".encode(), "text/plain", 500)

        def log_message(self, *a):
            pass

    # THREADING: one request per thread so a slow query (e.g. a scan over a large capture.db) can't
    # block every other request and freeze the dashboard (2026-07-22). Each handler opens its own DB
    # connections per call (functions take paths, not shared conns) → thread-safe. daemon threads so
    # a stuck request can't block shutdown.
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), H)
    srv.daemon_threads = True
    srv.serve_forever()


def main():
    port = int(os.environ.get("GAZBOT7_WEB_PORT", "8087"))
    store = os.environ.get("GAZBOT7_STORE", "data/gazbot7.db")
    cap = os.environ.get("GAZBOT7_CAPTURE", "data/capture.db")
    data_dir = os.path.dirname(store) or "."
    shadow = os.environ.get("GAZBOT7_SHADOW", os.path.join(data_dir, "shadow.db"))
    serve(port, store, cap, data_dir, shadow)


if __name__ == "__main__":
    main()
