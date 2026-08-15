"""Validate a from-the-lake reconstruction of the footprint's 20s net signed aggressor
volume against the 431 rows `shadow.db.footprint_signal_net` recorded LIVE at fire time.

If this does not reproduce the recorded number we cannot sweep net_min on the LIVE trades
(which carry no net log of their own), so this runs FIRST and its match rate is quoted in
the report.
"""
from __future__ import annotations

import json
import sqlite3
import sys

from gazbot7.lake import connect

WINDOW_S = 20


def main() -> None:
    sh = sqlite3.connect("data/shadow.db")
    rows = sh.execute(
        "SELECT trade_id, side, entry_ts, net_signed, price_move FROM footprint_signal_net ORDER BY entry_ts"
    ).fetchall()
    print(f"recorded fires: {len(rows)}", file=sys.stderr)

    con = connect()
    con.execute("CREATE OR REPLACE TEMP TABLE probe (tid BIGINT, t0 BIGINT, t1 BIGINT)")
    con.executemany(
        "INSERT INTO probe VALUES (?,?,?)",
        [(int(r[0]), int(r[2]) * 1000 - WINDOW_S * 1000, int(r[2]) * 1000) for r in rows],
    )
    got = con.execute(
        """
        SELECT p.tid,
               sum(CASE WHEN t.aggressor='buy' THEN t.size
                        WHEN t.aggressor='sell' THEN -t.size ELSE 0 END) AS net,
               count(*) AS nt,
               max(t.price) - min(t.price) AS rng
        FROM probe p JOIN ticks t
          ON t.symbol='MNQ' AND t.ts_ms >= p.t0 AND t.ts_ms < p.t1
        GROUP BY 1
        """
    ).fetchall()
    rec = {int(g[0]): (g[1], g[2]) for g in got}

    out, exact, close, miss = [], 0, 0, 0
    for tid, side, ets, net, pm in rows:
        g = rec.get(int(tid))
        if g is None or g[1] == 0:
            miss += 1
            continue
        mine = float(g[0] or 0.0)
        d = abs(mine - float(net))
        rel = d / max(1.0, abs(float(net)))
        if d <= 1e-6:
            exact += 1
        elif rel <= 0.05:
            close += 1
        out.append({"trade_id": int(tid), "side": side, "entry_ts": int(ets),
                    "recorded": float(net), "reconstructed": mine, "rel_err": rel})

    n = len(out)
    print(json.dumps({
        "n_recorded": len(rows), "n_compared": n, "no_tape": miss,
        "exact": exact, "within_5pct": close,
        "exact_pct": round(100.0 * exact / max(1, n), 1),
        "within_5pct_pct": round(100.0 * (exact + close) / max(1, n), 1),
        "median_rel_err": round(sorted(o["rel_err"] for o in out)[n // 2], 4) if n else None,
    }, indent=2))
    with open("reports/friday_v7/sections/exh_net_validate.json", "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
