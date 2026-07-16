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
_CT = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript"}
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
    """last / vwap / atr_pct / net_atr for the ribbon + chart axes."""
    try:
        from .deciders import Bar, compute_features
        c = _conn(cap_path)
        rows = list(reversed(c.execute(
            "SELECT bar_ts, open, high, low, close, volume FROM bars "
            "WHERE symbol='MNQ' AND timeframe='5s' ORDER BY bar_ts DESC LIMIT 120"
        ).fetchall()))
        c.close()
        if len(rows) < 6:
            return None
        f = compute_features([Bar(r["bar_ts"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows])
        return {"last": rows[-1]["close"], "vwap": round(f.vwap, 2),
                "atr_pct": round(f.atr_pct * 100, 3), "net_atr": round(f.net_atr_5, 2)}
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
        "net_atr": f.get("net_atr"), "gates": [],
    }
    holdings = []
    pos = st.get("position")
    if pos and not pos.get("flat"):
        last = f.get("last") or pos.get("entry")
        sign = 1 if pos.get("side") == "LONG" else -1
        qty = pos.get("qty") or 1
        pnl_usd = round(sign * ((last or pos["entry"]) - pos["entry"]) * _VPP * qty, 2)
        holdings = [{
            "label": "MNQ", "symbol": "MNQ", "side": pos.get("side"), "qty": qty,
            "avg": pos.get("entry"), "stop": pos.get("stop"), "last": last,
            "multiplier": _VPP, "pnl_usd": pnl_usd,
            "pnl_pct": round(sign * ((last or pos["entry"]) - pos["entry"]) / pos["entry"] * 100, 3) if pos.get("entry") else None,
            "entry_gate": "thrust", "opened_at": pos.get("opened_at"),
        }]
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
        k = ((r["gate"] or "thrust"), r["side"])
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
            out["blotter"].append({"time": r["closed_at"], "side": r["side"], "gate": r["gate"] or "thrust",
                                   "exit": r["exit_reason"], "pnl_usd": round(r["pnl_usd"], 2), "pnl_pct": ppct})
        gp = _gate_groups(today_rows)
        out["gate_perf"] = gp
        out["leaderboard"] = {"top": gp[:5], "bottom": list(reversed(gp[-5:])) if len(gp) > 5 else []}
        c.close()
    except Exception:
        pass
    return out


# ── /api/futures/execution — signal→fill funnel ───────────────────────────────
def execution_json(store_path):
    try:
        from .monitor import execution_health
        c = _conn(store_path)
        since = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        v = execution_health(c, since_iso=since)
        blocks = {r["block_reason"]: r["n"] for r in c.execute(
            "SELECT block_reason, COUNT(*) n FROM signals WHERE outcome='blocked' AND ts>=? "
            "GROUP BY block_reason", (since,)).fetchall() if r["block_reason"]}
        c.close()
        events = v.submitted + v.rejects
        through = v.fills
        return {"current": {"pct": (round(100 * through / events) if events else 0),
                            "events": events, "through": through, "level": v.status,
                            "slip_ticks": None, "slip_usd": None, "blocks": blocks},
                "baseline_pct": 51, "trend": []}
    except Exception:
        return {"current": None, "baseline_pct": 51, "trend": []}


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
    from .shadow import default_slate
    day_start, day_end = _paris_day_bounds(date)
    wk_start = day_end - 7 * 86400
    fleet = [v.name for v in default_slate()]  # the registered fleet (shown even if idle)
    try:
        c = _conn(shadow_path)
        rows = c.execute(
            "SELECT st.strategy s, st.symbol sym, st.exit_ts ts, sr.real_pnl pnl "
            "FROM shadow_trades st JOIN shadow_real sr ON sr.trade_id=st.id "
            "WHERE sr.fill_status='filled'").fetchall()
        c.close()
    except Exception:
        rows = []
    names = fleet + sorted({r["s"] for r in rows} - set(fleet))
    agg = {s: {"today": [], "week": [], "all": [], "by_symbol": {}, "min_ts": None} for s in names}
    for r in rows:
        a = agg.setdefault(r["s"], {"today": [], "week": [], "all": [], "by_symbol": {}, "min_ts": None})
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


def serve(port, store_path, cap_path, data_dir, shadow_path):
    class H(http.server.BaseHTTPRequestHandler):
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

    http.server.HTTPServer(("0.0.0.0", port), H).serve_forever()


def main():
    port = int(os.environ.get("GAZBOT7_WEB_PORT", "8087"))
    store = os.environ.get("GAZBOT7_STORE", "data/gazbot7.db")
    cap = os.environ.get("GAZBOT7_CAPTURE", "data/capture.db")
    data_dir = os.path.dirname(store) or "."
    shadow = os.environ.get("GAZBOT7_SHADOW", os.path.join(data_dir, "shadow.db"))
    serve(port, store, cap, data_dir, shadow)


if __name__ == "__main__":
    main()
