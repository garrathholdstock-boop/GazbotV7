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
    st = _status_json(data_dir)
    now = datetime.now(UTC)
    # "today" = trades since PARIS midnight (the desk's day convention), in UTC terms
    day_start = datetime.now(_PARIS).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).isoformat()
    d7 = (now - timedelta(days=7)).isoformat()
    d30 = (now - timedelta(days=30)).isoformat()
    out = {
        "conn": st.get("conn", "—"), "healthy": st.get("healthy", False),
        "live": st.get("place_live", False), "position": st.get("position"),
        "kpi": {}, "trades": [], "shadow": [], "exec": {}, "bars": [], "price": None,
    }
    try:
        c = sqlite3.connect(store_path)
        c.row_factory = sqlite3.Row
        n_t = _q1(c, "SELECT COUNT(*) FROM trades WHERE symbol='MNQ' AND closed_at>=?", (day_start,), 0)
        wins = _q1(c, "SELECT COUNT(*) FROM trades WHERE symbol='MNQ' AND closed_at>=? AND pnl_usd>0", (day_start,), 0)
        out["kpi"] = {
            "today": _q1(c, "SELECT ROUND(SUM(pnl_usd),2) FROM trades WHERE symbol='MNQ' AND closed_at>=?", (day_start,), 0.0),
            "d7": _q1(c, "SELECT ROUND(SUM(pnl_usd),2) FROM trades WHERE symbol='MNQ' AND closed_at>=?", (d7,), 0.0),
            "d30": _q1(c, "SELECT ROUND(SUM(pnl_usd),2) FROM trades WHERE symbol='MNQ' AND closed_at>=?", (d30,), 0.0),
            "trades": n_t,
            "win": round(100 * wins / n_t) if n_t else None,
        }
        out["trades"] = [
            {"t": _paris_hms(r["closed_at"]), "side": r["side"], "exit": r["exit_reason"], "pnl": round(r["pnl"], 2)}
            for r in c.execute(
                "SELECT closed_at, side, exit_reason, pnl_usd pnl FROM trades "
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
        fills = _q1(c, "SELECT COUNT(*) FROM fills WHERE ingested_at>=?", (day_start,), 0)
        out["exec"] = {"submitted": subm, "fills": fills,
                       "through": round(100 * fills / subm) if subm else None}
        c.close()
    except Exception:
        pass
    try:
        cap = sqlite3.connect(cap_path)
        cap.row_factory = sqlite3.Row
        rows = cap.execute(
            "SELECT bar_ts, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' ORDER BY bar_ts DESC LIMIT 240"
        ).fetchall()
        out["bars"] = [[r["bar_ts"], r["close"]] for r in reversed(rows)]
        if out["bars"]:
            out["price"] = out["bars"][-1][1]
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
