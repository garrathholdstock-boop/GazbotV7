"""The hero chart's bars endpoint, per symbol.

★2026-09-02. Operator: *"can you add mgc to the charts tab with all the same time toggles? i want
to watch if it behaves the same way over a few days. tunnel. run. tunnel. run."*

The reader was hard-wired to `symbol='MNQ'` while `capture.db` carried both contracts. These tests
EXECUTE the reader against a real two-symbol database — the whole failure this guards against is a
gold request quietly returning index bars, which no source-grep can see and which is the desk's
documented multi-symbol bug (MGC folded into an MNQ deque once read ATR 1848 against a true 15).
"""

from __future__ import annotations

import sqlite3

from gazbot7.web import BAR_SYMBOLS, bars_json


def _cap(tmp_path):
    """A capture.db with BOTH symbols on the SAME minutes, at unmistakably different prices."""
    p = tmp_path / "capture.db"
    c = sqlite3.connect(str(p))
    c.execute("CREATE TABLE bars (symbol TEXT, timeframe TEXT, bar_ts INT, close REAL)")
    t0 = 1_788_300_000 // 60 * 60
    rows = []
    for i in range(60):                       # 5 minutes of 5s bars for each
        rows.append(("MNQ", "5s", t0 + i * 5, 29000.0 + i))
        rows.append(("MGC", "5s", t0 + i * 5, 4400.0 + i / 10.0))
        rows.append(("MNQ", "1m", t0 + i * 5, 1.0))       # wrong timeframe — must be ignored
    c.executemany("INSERT INTO bars VALUES (?,?,?,?)", rows)
    c.commit(); c.close()
    return str(p)


def test_mnq_still_returns_mnq(tmp_path):
    out = bars_json(_cap(tmp_path), 10)
    assert out["symbol"] == "MNQ"
    assert out["bars"] and all(b["close"] >= 29000.0 for b in out["bars"])


def test_mgc_returns_gold_not_the_index(tmp_path):
    out = bars_json(_cap(tmp_path), 10, "MGC")
    assert out["symbol"] == "MGC"
    assert out["bars"], "gold bars are in the db — an empty result is the bug"
    assert all(4400.0 <= b["close"] < 4500.0 for b in out["bars"]), out["bars"][:3]


def test_the_two_symbols_do_not_bleed_into_each_other(tmp_path):
    cap = _cap(tmp_path)
    mnq = [b["close"] for b in bars_json(cap, 10)["bars"]]
    mgc = [b["close"] for b in bars_json(cap, 10, "MGC")["bars"]]
    assert len(mnq) == len(mgc) == 5                     # same minutes, one close each
    assert not (set(mnq) & set(mgc))


def test_unknown_symbol_falls_back_to_mnq_and_never_reaches_the_query(tmp_path):
    """A URL segment must not be able to name a table, an injection, or an empty chart."""
    cap = _cap(tmp_path)
    for bad in ("MGC; DROP TABLE bars", "'; DELETE FROM bars --", "ES", "", None, 7):
        out = bars_json(cap, 10, bad)
        assert out["symbol"] == "MNQ", bad
        assert out["bars"], bad
    # the table is still there and still holds every row
    c = sqlite3.connect(cap)
    assert c.execute("SELECT COUNT(*) FROM bars").fetchone()[0] == 180
    c.close()


def test_lowercase_symbol_is_accepted(tmp_path):
    assert bars_json(_cap(tmp_path), 10, "mgc")["symbol"] == "MGC"


def test_roster_is_the_two_captured_contracts(tmp_path):
    assert BAR_SYMBOLS == ("MNQ", "MGC")


def test_count_caps_the_minutes_returned(tmp_path):
    assert len(bars_json(_cap(tmp_path), 2, "MGC")["bars"]) == 2


def test_missing_db_is_an_empty_chart_not_a_crash(tmp_path):
    out = bars_json("/nonexistent/capture.db", 10, "MGC")
    assert out == {"symbol": "MGC", "bars": []}


# ── the ROUTE, not just the reader ───────────────────────────────────────────
# ★ The dispatch pulls the symbol out of the URL with `path.rsplit("/", 1)[-1]`, and the client
#   always sends a query string ("?timeframe=1m&count=120"). If that ever reached the whitelist
#   attached to the symbol it would fail closed to MNQ — a GOLD toggle silently drawing the INDEX,
#   which is the one outcome worth a test of its own. So this starts the real server and asks it.
def _serve(tmp_path):
    import threading
    import json as _json
    import socket
    from urllib.request import urlopen
    from gazbot7.web import serve

    cap = _cap(tmp_path)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    t = threading.Thread(target=serve, args=(port, cap, cap, str(tmp_path), cap), daemon=True)
    t.start()
    for _ in range(100):
        try:
            urlopen(f"http://127.0.0.1:{port}/api/futures/bars/MNQ?count=2", timeout=1).read()
            break
        except Exception:
            import time as _t; _t.sleep(0.05)
    def get(url):
        return _json.loads(urlopen(f"http://127.0.0.1:{port}{url}", timeout=5).read())
    return get


def test_route_keeps_the_symbol_apart_from_the_query_string(tmp_path):
    get = _serve(tmp_path)
    mnq = get("/api/futures/bars/MNQ?timeframe=1m&count=3")
    mgc = get("/api/futures/bars/MGC?timeframe=1m&count=3")
    assert mnq["symbol"] == "MNQ" and mgc["symbol"] == "MGC"
    assert all(b["close"] >= 29000.0 for b in mnq["bars"])
    assert all(b["close"] < 4500.0 for b in mgc["bars"]), "the gold toggle served index bars"


def test_route_falls_back_to_mnq_for_an_uncaptured_symbol(tmp_path):
    get = _serve(tmp_path)
    assert get("/api/futures/bars/ES?count=2")["symbol"] == "MNQ"
