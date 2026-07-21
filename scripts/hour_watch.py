#!/usr/bin/env python3
"""GAZBOT V7 — hourly tape/gate WATCH engine (the deterministic feeder for the adaptive sweep).

The hourly sweep runs this to decide whether the last hour was ROUTINE (a one-liner) or
NOTABLE (escalate → dissect → ATTENTION GAZ Telegram). It computes the facts — tape character +
violence (and whether it's expanding), per-gate participation (who caught the move, who FOUGHT
it and bled), disabled gates, safety events — and the trigger flags. The narrative dissection +
advice is authored by the sweep on top of this; this just makes the escalate/don't decision
reliable and reproducible. Read-only.

    cd /home/alphabot/gazbot7 && .venv/bin/python scripts/hour_watch.py --json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import pnl  # noqa: E402

_DATA = "/home/alphabot/gazbot7/data"
_CLEANUP = ("ADOPT_FLATTEN", "RECONCILED_CLOSE")
# tunable escalation thresholds
_HEAVY_TRADES = 12       # ≥ this many round-trips in the hour = heaps of action
_VIOLENT_ATR = 28.0      # 1-min ATR ≥ this = violent tape
_BLEED_1H = -80.0        # a gate ≤ this in the hour = bleeding
_BIG_DAY_MOVE = 150.0    # |desk net this hour| ≥ this = a real swing
_DRASTIC_EXITS = ("STOP_UNFILLED", "NAKED_FLATTEN", "MAX_HOLD")   # a bad-class exit in the hour


def _tape(cap_path, now, lookback_s):
    c = sqlite3.connect(cap_path)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT bar_ts,high,low,close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
        "AND bar_ts>=? AND bar_ts<? ORDER BY bar_ts",
        (now.timestamp() - lookback_s, now.timestamp())).fetchall()
    c.close()
    mins = {}
    for r in rows:
        m = (r["bar_ts"] // 60) * 60
        b = mins.setdefault(m, {"h": r["high"], "l": r["low"], "c": r["close"]})
        b["h"] = max(b["h"], r["high"])
        b["l"] = min(b["l"], r["low"])
        b["c"] = r["close"]
    mk = sorted(mins)
    if len(mk) < 6:
        return None
    cl = [mins[m]["c"] for m in mk]
    sa = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1
    er = abs(cl[-1] - cl[0]) / sa
    trs = []
    for i, m in enumerate(mk):
        pc = mins[mk[i - 1]]["c"] if i else mins[m]["c"]
        trs.append(max(mins[m]["h"] - mins[m]["l"], abs(mins[m]["h"] - pc), abs(mins[m]["l"] - pc)))
    atr = sum(trs) / len(trs)
    net = cl[-1] - cl[0]
    rng = max(b["h"] for b in mins.values()) - min(b["l"] for b in mins.values())
    return {"net": round(net, 1), "range": round(rng, 1), "atr": round(atr, 1), "er": round(er, 2),
            "day_type": "trend" if er >= 0.18 else "chop" if er < 0.08 else "mixed",
            "violence": "CALM" if atr < 8 else "NORMAL" if atr < 16 else "ELEVATED" if atr < 28 else "VIOLENT",
            "dir": "up" if net > 0 else "down" if net < 0 else "flat"}


_SIDE = {"rgv_long": "LONG", "grind_long": "LONG", "capitulation_long": "LONG",
         "thrust_short": "SHORT", "rgv_short": "SHORT", "exhaustion_short": "SHORT"}
_STYLE = {"rgv_long": "reversion", "rgv_short": "reversion", "capitulation_long": "reversion",
          "grind_long": "momentum", "thrust_short": "momentum", "exhaustion_short": "reversion"}


def run(now=None):
    now = now or dt.datetime.now(dt.UTC)
    tape = _tape(f"{_DATA}/capture.db", now, 3600)
    prior = _tape(f"{_DATA}/capture.db", now - dt.timedelta(hours=1), 3600)
    expanding = bool(tape and prior and (tape["atr"] > prior["atr"] * 1.3 or tape["range"] > prior["range"] * 1.3))

    g = sqlite3.connect(f"{_DATA}/gazbot7.db")
    g.row_factory = sqlite3.Row
    t0 = pnl.paris_day_start_utc(now)
    hr_iso = (now - dt.timedelta(hours=1)).isoformat()
    ph = ",".join("?" * len(_CLEANUP))
    rows = g.execute(
        f"SELECT gate, ROUND(SUM(pnl_usd),1) day, "
        f"ROUND(SUM(CASE WHEN closed_at>=? THEN pnl_usd ELSE 0 END),1) h, "
        f"SUM(CASE WHEN closed_at>=? THEN 1 ELSE 0 END) hn "
        f"FROM trades WHERE symbol='MNQ' AND closed_at>=? AND exit_reason NOT IN ({ph}) GROUP BY gate",
        (hr_iso, hr_iso, t0, *_CLEANUP)).fetchall()
    # exit-mix + drastic-exit scan for the hour
    hr_exits = g.execute(
        f"SELECT gate, exit_reason, COUNT(*) n FROM trades WHERE symbol='MNQ' AND closed_at>=? "
        f"AND exit_reason NOT IN ({ph}) GROUP BY gate, exit_reason", (hr_iso, *_CLEANUP)).fetchall()
    g.close()
    exits_by_gate = {}
    drastic_hits = []
    for r in hr_exits:
        exits_by_gate.setdefault(r["gate"], {})[r["exit_reason"]] = r["n"]
        if r["exit_reason"] in _DRASTIC_EXITS:
            drastic_hits.append(f"{r['gate']}:{r['exit_reason']}×{r['n']}")

    try:
        with open(f"{_DATA}/gate_switches.env") as f:
            from gazbot7.tournament import parse_switches
            disabled = parse_switches(f.read())
    except Exception:
        disabled = set()
    try:
        health = json.loads(open(f"{_DATA}/core_health.json").read())
    except Exception:
        health = {}

    gates = []
    for r in rows:
        gate = r["gate"]
        side, style = _SIDE.get(gate, "?"), _STYLE.get(gate, "?")
        aligned = None
        if tape and tape["dir"] != "flat" and side in ("LONG", "SHORT"):
            aligned = (side == "LONG" and tape["dir"] == "up") or (side == "SHORT" and tape["dir"] == "down")
        fighting = (aligned is False) and (r["h"] or 0) < 0     # against the tape AND losing
        gates.append({"gate": gate, "side": side, "style": style, "day": r["day"], "h": r["h"] or 0.0,
                      "hn": r["hn"] or 0, "exits": exits_by_gate.get(gate, {}),
                      "aligned": aligned, "fighting": bool(fighting), "disabled": gate in disabled})
    gates.sort(key=lambda x: x["h"])
    total_hn = sum(x["hn"] for x in gates)
    active_hn = sum(x["hn"] for x in gates if not x["disabled"])   # a disabled gate's churn is handled
    day_net = round(sum((x["day"] or 0) for x in gates), 1)

    # ── triggers (a gate we've already DISABLED no longer counts — it's handled) ──
    heavy = active_hn >= _HEAVY_TRADES
    violent = bool(tape and tape["atr"] >= _VIOLENT_ATR)
    bleeders = [x["gate"] for x in gates if x["h"] <= _BLEED_1H and not x["disabled"]]
    big_swing = bool(tape and abs(tape["net"]) >= _BIG_DAY_MOVE) or bool(bleeders)
    halted = bool(health.get("halted"))
    any_naked = any(not s.get("stop_coid") for s in (health.get("protection", {}) or {}).get("slots", []))
    drastic = halted or any_naked or bool(drastic_hits)
    fighters = [x["gate"] for x in gates if x["fighting"] and not x["disabled"]]
    escalate = heavy or violent or big_swing or drastic

    return {
        "ts": now.isoformat(), "tape": tape, "expanding": expanding, "day_net": day_net,
        "hour_trades": total_hn, "active_trades": active_hn, "gates": gates, "disabled": sorted(disabled),
        "bleeders": bleeders, "fighters": fighters, "drastic_hits": drastic_hits,
        "safety": {"halted": halted, "any_naked": any_naked,
                   "unverified": (health.get("protection", {}) or {}).get("unverified_cycles", 0)},
        "triggers": {"heavy_action": heavy, "violent": violent, "big_swing": big_swing, "drastic": drastic},
        "escalate": escalate,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = run()
    if a.json:
        print(json.dumps(r, indent=2))
        return
    t = r["tape"] or {}
    print(f"TAPE(1h): {t.get('day_type','?').upper()} net {t.get('net',0):+}pt range {t.get('range',0)}pt "
          f"| VIOLENCE {t.get('violence','?')} ATR~{t.get('atr',0)}pt {'(EXPANDING)' if r['expanding'] else ''}")
    print(f"hour trades: {r['hour_trades']} | day net ${r['day_net']} | disabled: {r['disabled'] or 'none'}")
    for x in r["gates"]:
        tag = " (disabled)" if x["disabled"] else (" 🩸FIGHTING" if x["fighting"] else "")
        print(f"  {x['gate']:16} {x['side']:5} {x['style']:9} 1h ${x['h']:>7} ({x['hn']}tr) day ${x['day']}{tag}")
    print(f"TRIGGERS: {[k for k,v in r['triggers'].items() if v] or 'none'} → "
          f"{'*** ESCALATE — dissect + ATTENTION GAZ ***' if r['escalate'] else 'routine one-liner'}")


if __name__ == "__main__":
    main()
