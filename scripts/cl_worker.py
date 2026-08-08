#!/usr/bin/env python3
"""CL WORKER — the ROOT half of the CL sims. Verifies queued signals and books the PASSes.

WHY THIS EXISTS AS A SEPARATE PROCESS. The shadow service runs as `alphabot`; /root is 0700, there is
no system-wide `claude`, and alphabot has no sudo. The first version called the model from inside the
shadow loop and every single verdict came back `FileNotFoundError: 'claude'` at 0ms — the sims would
have shown zero trades and looked disciplined rather than broken. So verification lives here, as root,
exactly like scripts/router_tick_durable.py which has worked for days for the same reason.

WHAT IT DOES, per queued signal (cl_signals rows with a NULL verdict):
  1. call claude with the context the shadow loop captured AT FIRE TIME (no reconstruction — the
     context is stored, so there is no provenance gap and no hindsight)
  2. write the verdict, confidence, reason, primary_factor and latency
  3. on PASS: price the entry at the tape as of the VERDICT moment, replay forward on 250ms ticks to
     the twin's own exit (same target_r / stop_atr_mult), and write a shadow_trades + shadow_real row
     under the CL- name so it lands on the shadow board beside every other sim

★ THE SIM IS CHARGED THE FULL DELAY. Entry is the price at verdict time, never the signal price. If a
signal's edge does not survive waiting for an answer, this will say so, correctly.

★ HONESTY LIMIT OF THE SPLIT. The entry price is the tape as the WORKER prices it rather than read
live off the loop. The worker runs every minute, so it is close, but it is a reconstruction — and the
delay charged is real (signal -> verdict), not zero.

Fail-safe: any error on one signal marks it no_verdict and moves on. A dead worker means the CL sims
simply stop trading; nothing else on the desk notices.

  PYTHONPATH=src ./.venv/bin/python scripts/cl_worker.py [--limit 20] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

import duckdb  # noqa: E402

from gazbot7.cl_sims import CL_GATES, _call, ensure_schema  # noqa: E402

GB = "/home/alphabot/gazbot7"
VPP, FEE_RT = 2.0, 1.50
MAX_HOLD_S = 120 * 60


def price_at(con, ts_ms: int) -> float | None:
    """Last tick at or before ts_ms — what the tape showed when the verdict landed."""
    r = con.execute(f"""SELECT price FROM c.ticks WHERE symbol='MNQ' AND ts_ms <= {ts_ms}
                        ORDER BY ts_ms DESC LIMIT 1""").fetchone()
    return float(r[0]) if r else None


def replay_exit(con, side: str, entry: float, atr: float, t0_ms: int,
                target_r: float, stop_mult: float):
    """Race the twin's own target against its own stop on 250ms ticks. First touch wins — never MFE.
    Reading a peak as if it implied ordering has produced five wrong answers on this desk this week."""
    rows = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
                           AND ts_ms >= {t0_ms} AND ts_ms <= {t0_ms + MAX_HOLD_S*1000}
                           ORDER BY ts_ms""").fetchall()
    if not rows:
        return None
    tgt = target_r * atr
    stp = stop_mult * atr
    for ts, px in rows:
        fav = (px - entry) if side == "LONG" else (entry - px)
        if -fav >= stp:
            return ts, entry - stp * (1 if side == "LONG" else -1), "STOP"
        if fav >= tgt:
            return ts, entry + tgt * (1 if side == "LONG" else -1), "TARGET"
    ts, px = rows[-1]
    return ts, px, "MAX_HOLD"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = all queued")
    ap.add_argument("--dry-run", action="store_true", help="do not call the model or write trades")
    a = ap.parse_args()

    sh = sqlite3.connect(f"{GB}/data/shadow.db")
    ensure_schema(sh)
    from gazbot7.slot_strategy import scaleout_slots
    spec = {s.tag.replace("_A", ""): s for s in scaleout_slots() if s.tag.endswith("_A")}

    q = ("SELECT id, sim, gate, side, signal_ts_ms, signal_price, context FROM cl_signals "
         "WHERE verdict IS NULL ORDER BY id")
    if a.limit:
        q += f" LIMIT {a.limit}"
    todo = sh.execute(q).fetchall()
    print(f"{len(todo)} queued signal(s)")
    if not todo:
        return 0

    cap = duckdb.connect()
    cap.execute(f"ATTACH '{GB}/data/capture.db' AS c (READ_ONLY)")

    for sid, sim, gate, side, ts_ms, sig_px, ctx_json in todo:
        if a.dry_run:
            print(f"  #{sid} {sim:<22} {side:<6} would verify")
            continue
        ctx = json.loads(ctx_json or "{}")
        res, ms = _call(ctx)
        import time
        v_ms = int(time.time() * 1000)
        entry = price_at(cap, v_ms) if res["verdict"] == "PASS" else None
        sh.execute("UPDATE cl_signals SET verdict=?,confidence=?,reason=?,primary_factor=?,"
                   "latency_ms=?,verdict_ts_ms=?,entry_price=? WHERE id=?",
                   (res["verdict"], res["confidence"], res["reason"], res["primary_factor"],
                    ms, v_ms, entry, sid))
        sh.commit()

        booked = ""
        if res["verdict"] == "PASS" and entry is not None:
            sp = spec.get(gate)
            atr = (ctx.get("volatility") or {}).get("atr_pt") or 0.0
            if sp and atr > 0:
                ex = replay_exit(cap, side, entry, atr, v_ms, sp.target_r, sp.stop_atr_mult)
                if ex:
                    x_ts, x_px, reason = ex
                    d = 1 if side == "LONG" else -1
                    pnl = (x_px - entry) * d * VPP - FEE_RT
                    from gazbot7.store import record_shadow_real, record_shadow_trade
                    tid = record_shadow_trade(
                        sh, strategy=sim, symbol="MNQ", side=side, qty=1.0,
                        entry_ts=v_ms // 1000, entry_price=entry, entry_atr=atr,
                        target_r=sp.target_r, stop_atr_mult=sp.stop_atr_mult,
                        exit_ts=x_ts // 1000, exit_price=x_px, exit_reason=reason, ceiling_pnl=pnl)
                    try:
                        from datetime import UTC, datetime
                        record_shadow_real(sh, trade_id=tid, strategy=sim, symbol="MNQ",
                                           real_pnl=pnl, fill_status="filled",
                                           repriced_at=datetime.now(UTC).isoformat(timespec="seconds"))
                    except Exception as e:
                        print(f"      (shadow_real write skipped: {e})")
                    booked = f"  -> booked {reason} ${pnl:+.2f}"
                else:
                    booked = "  -> no ticks yet, will not book (signal too recent)"
        print(f"  #{sid} {sim:<22} {side:<6} {res['verdict']:<10} {ms:>6}ms"
              f"  {(res['primary_factor'] or '')[:44]}{booked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
