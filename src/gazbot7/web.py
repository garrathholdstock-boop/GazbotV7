"""GAZBOT V7 — the watch page server.

Serves the /mnq-style cockpit (web_static/) + /api/status computed live from the
V7 store + capture DB + the runner's status.json. Read-only, stdlib only — a
watch surface, never touches the trading path.
"""

from __future__ import annotations

import http.server
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_STATIC = Path(__file__).parent / "web_static"
_CT = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript"}
_PARIS = ZoneInfo("Europe/Paris")


def _paris_hms(iso: str) -> str:
    """ISO-UTC timestamp → Paris HH:MM:SS for display."""
    try:
        return datetime.fromisoformat(iso).astimezone(_PARIS).strftime("%H:%M:%S")
    except Exception:
        return (iso or "")[11:19] or "—"


def _q1(conn, sql, args=(), default=None):
    try:
        r = conn.execute(sql, args).fetchone()
        return r[0] if r and r[0] is not None else default
    except Exception:
        return default


def _status_json(data_dir: str) -> dict:
    try:
        with open(os.path.join(data_dir, "status.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def build_status(store_path: str, cap_path: str, data_dir: str) -> dict:
    from . import pnl as pnlmod

    st = _status_json(data_dir)
    now = datetime.now(UTC)
    # "today" = trades since PARIS midnight (the desk's day convention) — one source
    day_start = pnlmod.paris_day_start_utc(now)
    d7 = (now - timedelta(days=7)).isoformat()
    d30 = (now - timedelta(days=30)).isoformat()
    out = {
        "conn": st.get("conn", "—"), "healthy": st.get("healthy", False),
        "live": st.get("place_live", False), "position": st.get("position"),
        "kpi": {}, "trades": [], "shadow": [], "exec": {}, "gates": [], "fills": [],
        "bars": [], "price": None, "vwap": None, "atr_pct": None, "backfills": 0,
    }
    try:
        c = sqlite3.connect(store_path)
        c.row_factory = sqlite3.Row
        # all realized-P&L numbers come from the single pnl source (S7)
        today_pnl, n_t, wins = pnlmod.realized(c, "MNQ", since_iso=day_start)
        d7_pnl, _n7, _w7 = pnlmod.realized(c, "MNQ", since_iso=d7)
        d30_pnl, _n30, _w30 = pnlmod.realized(c, "MNQ", since_iso=d30)
        out["kpi"] = {
            "today": today_pnl, "d7": d7_pnl, "d30": d30_pnl,
            "trades": n_t,
            "win": round(100 * wins / n_t) if n_t else None,
        }
        out["trades"] = [
            {"t": _paris_hms(r["closed_at"]), "side": r["side"], "gate": r["gate"] or "thrust",
             "exit": r["exit_reason"], "pnl": round(r["pnl"], 2)}
            for r in c.execute(
                "SELECT closed_at, side, gate, exit_reason, pnl_usd pnl FROM trades "
                "WHERE symbol='MNQ' AND closed_at>=? ORDER BY closed_at DESC LIMIT 20", (day_start,)
            ).fetchall()
        ]
        out["shadow"] = [
            {"strategy": r["strategy"], "n": r["n"], "pnl": round(r["pnl"] or 0, 0), "win": round(r["win"] or 0)}
            for r in c.execute(
                "SELECT s.strategy, COUNT(*) n, SUM(r.real_pnl) pnl, "
                "100.0*SUM(CASE WHEN r.real_pnl>0 THEN 1 ELSE 0 END)/COUNT(*) win "
                "FROM shadow_trades s JOIN shadow_real r ON r.trade_id=s.id WHERE r.fill_status='filled' "
                "GROUP BY s.strategy ORDER BY pnl DESC"
            ).fetchall()
        ]
        subm = _q1(c, "SELECT COUNT(*) FROM orders WHERE created_at>=?", (day_start,), 0)
        nf = _q1(c, "SELECT COUNT(*) FROM fills WHERE ingested_at>=?", (day_start,), 0)
        out["exec"] = {"submitted": subm, "fills": nf,
                       "through": round(100 * nf / subm) if subm else None}
        out["backfills"] = _q1(c, "SELECT COUNT(*) FROM trades WHERE symbol='MNQ' AND exit_reason='RECONSTRUCTED_BACKFILL'", (), 0)
        # fills for the chart markers (today's entries/exits)
        out["fills"] = [
            {"side": r["side"], "entry": r["entry_price"], "exit": r["exit_price"],
             "opened_at": r["opened_at"], "closed_at": r["closed_at"]}
            for r in c.execute(
                "SELECT side, entry_price, exit_price, opened_at, closed_at FROM trades "
                "WHERE symbol='MNQ' AND closed_at>=? ORDER BY closed_at", (day_start,)
            ).fetchall()
        ]
        # gate leaderboard (gate x side)
        out["gates"] = [
            {"gate": r["gate"] or "thrust", "side": r["side"], "n": r["n"],
             "win": round(100 * r["w"] / r["n"]) if r["n"] else 0, "net": round(r["net"] or 0, 1)}
            for r in c.execute(
                "SELECT COALESCE(gate,'thrust') gate, side, COUNT(*) n, SUM(pnl_usd>0) w, SUM(pnl_usd) net "
                "FROM trades WHERE symbol='MNQ' AND closed_at>=? GROUP BY gate, side ORDER BY net DESC",
                (day_start,)
            ).fetchall()
        ]
        c.close()
    except Exception:
        pass
    try:
        from .deciders import Bar, compute_features
        cap = sqlite3.connect(cap_path)
        cap.row_factory = sqlite3.Row
        rows = list(reversed(cap.execute(
            "SELECT bar_ts, open, high, low, close, volume FROM bars "
            "WHERE symbol='MNQ' AND timeframe='5s' ORDER BY bar_ts DESC LIMIT 240"
        ).fetchall()))
        out["bars"] = [[r["bar_ts"], r["close"]] for r in rows]
        if rows:
            out["price"] = rows[-1]["close"]
            if len(rows) >= 6:
                f = compute_features([Bar(r["bar_ts"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows])
                out["vwap"] = round(f.vwap, 2)
                out["atr_pct"] = round(f.atr_pct, 5)
        cap.close()
    except Exception:
        pass
    return out


def serve(port: int, store_path: str, cap_path: str, data_dir: str) -> None:
    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, body: bytes, ct: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                if self.path == "/" or self.path.startswith("/index"):
                    self._send((_STATIC / "app.html").read_bytes(), _CT[".html"])
                elif self.path.startswith("/static/"):
                    f = _STATIC / os.path.basename(self.path)
                    self._send(f.read_bytes(), _CT.get(f.suffix, "text/plain"))
                elif self.path.startswith("/api/status"):
                    body = json.dumps(build_status(store_path, cap_path, data_dir)).encode()
                    self._send(body, "application/json")
                else:
                    self._send(b"not found", "text/plain", 404)
            except Exception as e:
                self._send(f"error: {e}".encode(), "text/plain", 500)

        def log_message(self, *a):
            pass

    http.server.HTTPServer(("0.0.0.0", port), H).serve_forever()


def main() -> None:
    port = int(os.environ.get("GAZBOT7_WEB_PORT", "8087"))
    store = os.environ.get("GAZBOT7_STORE", "data/gazbot7.db")
    cap = os.environ.get("GAZBOT7_CAPTURE", "data/capture.db")
    serve(port, store, cap, os.path.dirname(store) or ".")


if __name__ == "__main__":
    main()
