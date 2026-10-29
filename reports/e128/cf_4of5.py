"""Counterfactual 2026-10-29 with a 4/5 vote: the 02:40Z short is refused; replay Claude on the real tape from 02:45Z, desk flat,
the 02:00Z win banked. Same prompt builder as the live robot (desk_prompt), book replaced by the counterfactual one. Log only."""
import sys, json, datetime as dt
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import hybrid_robot as H, leg_robot as L, hybrid_near_misses as N
UTC = dt.timezone.utc
OUT = "/home/alphabot/gazbot7/reports/e128/cf_2026-10-29_4of5.jsonl"
import os; os.makedirs(os.path.dirname(OUT), exist_ok=True)
key = "2026-10-29"; d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
NEED = 4
bars_all = N.ML.minute_bars(key)
series_all = L.series_for(dt.date.fromisoformat(key))
o1, c1 = "2026-10-29T02:00:36.745649+00:00", sys.argv[1]
done = [{"side": "SHORT", "opened": o1, "closed": c1, "held_min": 30.0, "points": 32.0, "pnl_usd": 256.0, "peak_pt": 32.0, "entry": 29539.5, "exit": 29507.5}]
trades = [{"t": "02:00", "side": "SHORT", "entry": 29539.5, "status": "CLAIMED +256 USD"}]
state = {"realised": 256.0, "busy": 0}
H.live_book = lambda key_, px, now_ts: (None, list(done), list(trades))
H.day_equity = lambda key_, now_ts: {"now": state["realised"]}
f = open(OUT, "w")
for m in range(2 * 60 + 45, 13 * 60 + 30, 5):
    op = d0 + m * 60; now_ts = op + 20
    if state["realised"] >= H.LOCK_USD:
        f.write(json.dumps({"t": f"{m//60:02d}:{m%60:02d}", "event": "LOCKED"}) + "\n"); break
    if op < state["busy"]:
        continue
    upto = [b for b in H.live_bars(key, now_ts) if b[0] + 60 <= op]; px = upto[-1][3]
    turns = L.confirmed_turns([b for b in series_all if b[0] + 60 <= now_ts - L.SETTLE_S])
    prompt, _, _ = H.desk_prompt(key, op, upto, px, now_ts, turns)
    d = H.S.ask(prompt); act = d.get("action", "WAIT"); dd = H.det_dir(turns, op - 60)
    rec = {"t": f"{m//60:02d}:{m%60:02d}", "px": px, "action": act, "reason": (d.get("reason") or "")[:220], "error": d.get("error"), "mil": dd}
    if act in ("ENTER_LONG", "ENTER_SHORT") and (1 if act == "ENTER_LONG" else -1) == dd:
        more = H.ask_ballots(prompt, 4, timeout=150)
        agree = sum(1 for b in [d] + more if b.get("action") == act and not b.get("error"))
        rec["votes"] = agree; rec["ballots"] = [act] + [b.get("action") for b in more]
        if agree >= NEED:
            o = N.outcome(bars_all, op, dd, d0)
            rec["entered"] = o
            state["realised"] += o["pnl"]
            state["busy"] = op + o["mins"] * 60 if o["hit"] else 10 ** 12
            closed = dt.datetime.fromtimestamp(state["busy"] if o["hit"] else d0 + 20 * 3600 + 2400, UTC).isoformat()
            side = "LONG" if dd > 0 else "SHORT"
            done.append({"side": side, "opened": dt.datetime.fromtimestamp(op, UTC).isoformat(), "closed": closed, "held_min": o["mins"] or 0,
                         "points": 37.5 if o["hit"] else 0, "pnl_usd": o["pnl"], "peak_pt": 37.5, "entry": o["fill"], "exit": o["fill"] + dd * 37.5})
            trades.append({"t": rec["t"], "side": side, "entry": o["fill"], "status": f"CLAIMED {o['pnl']:+,.0f} USD"})
    f.write(json.dumps(rec) + "\n"); f.flush()
f.write(json.dumps({"event": "END", "realised": state["realised"]}) + "\n")
