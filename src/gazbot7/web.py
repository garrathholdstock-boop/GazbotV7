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
    return {"holdings": holdings, "activity": [activity], "regime_groups": {},
            "margin_deployed_usd": None, "nlv_usd": None}


# ── /api/futures/mnq — header / rolling / blotter / curve / gates ──────────────
def _strategy_trades(c, since_iso=None):
    ph = ",".join("?" * len(_CLEANUP))
    q = (f"SELECT closed_at, side, gate, exit_reason, pnl_usd, entry_price, exit_price, qty "
         f"FROM trades WHERE symbol='MNQ' AND exit_reason NOT IN ({ph})")
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
        today, n_today, wins = pnl.day(c, "MNQ", now)
        d7, _, _ = pnl.realized(c, "MNQ", since_iso=(now - timedelta(days=7)).isoformat())
        d30, _, _ = pnl.realized(c, "MNQ", since_iso=(now - timedelta(days=30)).isoformat())
        y0 = pnl.paris_day_start_utc(now - timedelta(days=1))
        t0 = pnl.paris_day_start_utc(now)
        yest = round(sum(r["pnl_usd"] for r in c.execute(
            "SELECT pnl_usd FROM trades WHERE symbol='MNQ' AND closed_at>=? AND closed_at<? "
            "AND exit_reason NOT IN (" + ",".join("?" * len(_CLEANUP)) + ")",
            (y0, t0, *_CLEANUP)).fetchall()), 2)
        out["header"] = {"today": today, "yest": yest, "d2": None, "d7": d7, "d30": d30,
                         "win_today": (round(100 * wins / n_today) if n_today else None),
                         "trades_today": n_today}
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


# ── /api/futures/tournament — the per-gate scoreboard (roster × trades × live) ─
def tournament_json(store_path, data_dir, cap_path):
    """The tournament scoreboard: the full 6-gate roster (from ``tournament_slots()`` so
    0-trade gates still show), each gate's today-realized (from ``trades``) + open-unrealized
    (from the live ``status.json`` slots × last price), ranked by total, bottom-2 flagged for
    relegation. Plus a desk-level safety block for the header pill. Read-only."""
    from .slot_strategy import tournament_slots

    roster = [(s.tag, s.side) for s in tournament_slots()]
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
                                 {"realized": 0.0, "n": 0, "wins": 0, "gw": 0.0, "gl": 0.0, "exits": {}})
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
    fleet = [v.name for v in default_slate()] + list(CB_STRATEGIES)
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


def reports_json(static_dir):
    """List the weekly_<date>.html reports in web_static, newest first, with the
    <title> pulled from each file. The reports index reads this to render its cards."""
    import re
    out = []
    for fn in sorted(os.listdir(static_dir)):
        m = re.match(r"(?:weekly|v7_big_runs)_(\d{4}-\d{2}-\d{2})\.html$", fn)
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
            + ",".join("?" * len(_CLEANUP)) + ")", tuple(_CLEANUP)).fetchall()
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
            "AND exit_reason NOT IN (" + ",".join("?" * len(_CLEANUP)) + ")", tuple(_CLEANUP)).fetchall()
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
