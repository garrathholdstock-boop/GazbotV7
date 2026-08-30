"""CL-VERIFY — record what Claude WOULD have said about each live gate signal. Gates nothing.

Spec: docs/CL_VERIFICATION_SHADOW_SCOPE.md. Operator, 2026-08-03.

★ ARCHITECTURE: OFFLINE RECONSTRUCTION, NOT A HOT-PATH HOOK.
The desk's decision loop runs every second. A ~6s verification call inside it would stall the desk
outright, so this never touches `slot_strategy.decide`. Instead it reads signals AFTER the fact from
the trade ledger, reconstructs the context as it stood AT SIGNAL TIME, asks, and records. Zero live
risk, no new failure surface on the trading path, and it answers the actual question — is the
JUDGEMENT any good — which is independent of whether the plumbing is real-time. Build the live path
only if the judgement earns it.

★ WHY NO PERSISTENCE PRE-FILTER (the operator's "15 cycles in a row", which he flagged as arbitrary).
Two measurements killed it:
  * `MinuteBars.bars()` exposes only COMPLETED minutes, so every gate feature is bar-quantised and a
    gate's condition is CONSTANT within the minute. A count of 1s cycles is therefore either ~60 or
    0 — it measures nothing.
  * A bar-level filter (N>=2 bars) costs 60+ seconds of lag, on a desk measured at a median +7.58 min
    into a run already. That is the worst place on the desk to spend delay.
And no throttle is needed: 33 signals/day mean, 78 peak, ~6s per call = ~3 min of compute a day.
So: verify EVERY signal. The call is its own filter and it is 10x cheaper in lag than one extra bar.

★ HINDSIGHT IS THE ONE THING THAT INVALIDATES THIS. Every field in the context must be computable
from data at or before the signal timestamp. One forward-looking value silently turns the whole
experiment into a lookahead study that will score brilliantly and mean nothing. `build_context`
takes ts_ms and slices strictly `< ts_ms`; tests assert it.
"""
from __future__ import annotations

import json
import os
import sqlite3

# ★★2026-08-19 HEADLESS CONTEXT ISOLATION — the prompt must be the ONLY instruction.
# Claude Code auto-loads a CLAUDE.md from the cwd chain AND the per-project auto-memory index.
# Must be OUTSIDE the repo: Claude Code walks UP to the repo root, so a dir inside gazbot7
# still loads gazbot7's memory. See ops/ROUTER_CONTEXT_ISOLATION.md.
CL_CTX = "/var/lib/gazbot7/router_ctx"

import subprocess
import time
from dataclasses import asdict, dataclass

GB = "/home/alphabot/gazbot7"
CL_PREFIX = "CL-"          # operator wants these instantly recognisable in the sim list
CALL_TIMEOUT_S = 25        # ★ widened from 15 after the first live run: observed 7.6-15.0s with one
                           # timeout at the 15s ceiling (a 6.7% no_verdict rate is too high to leave).
                           # Slower than the durable router's 5-7s because each call rebuilds context
                           # from scratch rather than reusing the tick's already-assembled state.
VPP = 2.0


SCHEMA = """
CREATE TABLE IF NOT EXISTS cl_verdicts (
    signal_ts   INTEGER NOT NULL,       -- epoch ms of the live signal
    sim         TEXT    NOT NULL,       -- 'CL-<gate>'
    gate        TEXT    NOT NULL,
    side        TEXT    NOT NULL,
    entry_price REAL,
    verdict     TEXT,                   -- PASS | VETO | no_verdict
    confidence  INTEGER,
    reason      TEXT,
    primary_factor TEXT,                -- REQUIRED: makes the calls auditable in aggregate
    latency_ms  INTEGER,
    context     TEXT,                   -- the exact JSON shown to the model, for audit
    live_pnl    REAL,                   -- what the desk actually banked on this signal
    PRIMARY KEY (signal_ts, sim)
);
"""


@dataclass
class Signal:
    ts_ms: int
    gate: str
    side: str
    entry_price: float
    live_pnl: float


def open_db(path: str = f"{GB}/data/shadow.db") -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def unverified(store_path: str, con: sqlite3.Connection, since: str) -> list[Signal]:
    """Live signals not yet verified. One row per (timestamp, base gate) — the _A/_B sub-slots are
    two lots of ONE decision, so they get one verdict, not two."""
    sq = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    # ★ Bucket to 5s before grouping. The _A and _B lots of ONE decision get venue timestamps a
    # second or two apart (13:34:52 / 13:34:53), so grouping on the raw opened_at splits every
    # signal in two and would double-count the whole experiment.
    rows = sq.execute(
        "SELECT MIN(opened_at), REPLACE(REPLACE(gate,'_A',''),'_B','') g, MIN(side), AVG(entry_price), "
        "       SUM(pnl_usd) "
        "FROM trades WHERE opened_at >= ? AND closed_at IS NOT NULL "
        "GROUP BY CAST(strftime('%s', opened_at) AS INTEGER)/5, g "
        "ORDER BY 1", (since,)).fetchall()
    sq.close()
    done = {(t, s) for t, s in con.execute("SELECT signal_ts, sim FROM cl_verdicts")}
    out = []
    for opened, gate, side, px, pnl in rows:
        from datetime import datetime
        ts = int(datetime.fromisoformat(opened).timestamp() * 1000)
        base = gate.replace("_A", "").replace("_B", "")
        if (ts, CL_PREFIX + base) in done:
            continue
        out.append(Signal(ts, base, side, float(px or 0), float(pnl or 0)))
    return out


def build_context(cap_path: str, store_path: str, sig: Signal) -> dict:
    """Everything the model sees. STRICTLY `< sig.ts_ms` — see the hindsight warning above.

    Deliberately EXCLUDES the L2 book. MNQ's whole visible 10-deep book is ~86 contracts against
    ~2,664 contracts/min of flow — about 6x below the depth at which absorption means anything, a
    finding credited with explaining four separate dead ends. Asking the model to read buyer
    absorption off that is asking it to report noise with confidence. Tape FLOW is real and included;
    the BOOK is not, on this instrument."""
    import duckdb

    from .deciders import Bar, _atr
    from .sizing import efficiency_ratio
    from .tradeability import score as tscore

    t_s = sig.ts_ms // 1000
    con = duckdb.connect()
    con.execute(f"ATTACH '{cap_path}' AS c (READ_ONLY)")
    rows = con.execute(f"""
        SELECT m, h, l, cl FROM (
          SELECT CAST(bar_ts/60 AS BIGINT)*60 m, MAX(high) h, MIN(low) l, ARG_MAX(close, bar_ts) cl
          FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts < {t_s}
          GROUP BY 1 ORDER BY 1 DESC LIMIT 60) ORDER BY m""").fetchall()
    if len(rows) < 31:
        con.close()
        return {}
    b = [Bar(ts=m, open=cl, high=h, low=l, close=cl, volume=1.0) for m, h, l, cl in rows]
    er, atr = efficiency_ratio(b, 30), _atr(b)
    w = b[-30:]
    rng = max(x.high for x in w) - min(x.low for x in w)
    net = w[-1].close - w[0].close
    cls = [x.close for x in w]
    fav = max(max(cls) - cls[0], cls[0] - min(cls))
    gb = 0.0 if fav <= 0 else max(0.0, min(1.0, 1 - abs(cls[-1] - cls[0]) / fav))

    def flow(sec):
        r = con.execute(f"""SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size
                            WHEN aggressor='sell' THEN -size END),0) FROM c.ticks
                            WHERE symbol='MNQ' AND ts_ms < {sig.ts_ms}
                            AND ts_ms >= {sig.ts_ms - sec*1000}""").fetchone()
        return int(r[0] or 0)

    ctx = {
        "signal": {"gate": sig.gate, "side": sig.side, "price": sig.entry_price},
        "regime": {"atr_pt": round(atr, 1), "er30": round(er, 3),
                   "range_30m_pt": round(rng, 1), "net_30m_pt": round(net, 1),
                   "tradeability_0_10": tscore(er, atr, gb).score,
                   "tradeability_label": tscore(er, atr, gb).label},
        "tape_flow_net_contracts": {"30s": flow(30), "60s": flow(60), "5m": flow(300)},
        "note_no_l2": "L2 book deliberately excluded — not measurable on MNQ (86 contracts vs 2,664/min flow)",
    }
    sq = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    from datetime import datetime, timezone
    iso = datetime.fromtimestamp(t_s, timezone.utc).isoformat()
    prev = sq.execute("SELECT gate, exit_reason, pnl_usd FROM trades WHERE closed_at < ? "
                      "ORDER BY closed_at DESC LIMIT 5", (iso,)).fetchall()
    sq.close()
    con.close()
    ctx["last_5_closed"] = [{"gate": g, "exit": r, "pnl": p} for g, r, p in prev]
    ctx["stop_wall"] = sum(1 for _, r, _ in prev if (r or "").startswith("STOP")) >= 4
    return ctx


PROMPT = """You are verifying ONE live gate signal on the GAZBOT V7 MNQ desk. PAPER. You are NOT
placing a trade — your verdict is recorded and scored, it gates nothing.

Say VETO only if the context gives a concrete reason this specific signal is likely to lose. The
mechanical gate has already passed it, and the desk's standing asymmetry is that wrongly-benched is
cheap (a missed trade) while wrongly-armed is expensive (churn) — but a veto that merely restates the
gate's own logic adds nothing, so do not veto on generic caution.

Known-hostile conditions from this desk's own measurements:
 - VIOLENT WHIPSAW (ATR >= 19pt with ER30 < 0.25): unsurvivable at every exit cell and every R from
   0.5 to 6.0. No exit rescues it; only not trading it does.
 - DEAD tape (ATR < 8pt): nothing survives spread + $1.50/RT fee.
 - A day handing back most of its move, or 4+ of the last 5 trades stopping (a stop wall).
 - A fader (exhaustion/capitulation/rgv) firing INTO a strong aligned move.

Reply with STRICT JSON only:
{"verdict":"PASS"|"VETO","confidence":0-100,"reason":"<one line>","primary_factor":"<the single thing that decided it>"}

primary_factor is required and must name ONE thing. If your vetoes all cite the same factor, that
factor is a mechanical rule and should be coded rather than asked — so be precise.

CONTEXT:
"""


def verify(ctx: dict, *, timeout_s: int = CALL_TIMEOUT_S) -> tuple[dict, int]:
    """Ask headless Claude. FAIL-SAFE: any error/timeout/parse failure returns no_verdict. This layer
    can never block or break anything — a dead verifier is simply invisible."""
    t0 = time.time()
    try:
        os.makedirs(CL_CTX, exist_ok=True)
        p = subprocess.run(["claude", "-p", PROMPT + json.dumps(ctx, indent=1)],
                           capture_output=True, text=True, timeout=timeout_s, cwd=CL_CTX)
        import re
        m = re.search(r"\{.*\}", p.stdout, re.S)
        d = json.loads(m.group(0)) if m else {}
        v = d.get("verdict")
        if v not in ("PASS", "VETO"):
            raise ValueError(f"bad verdict {v!r}")
        return ({"verdict": v, "confidence": int(d.get("confidence", 0)),
                 "reason": str(d.get("reason", ""))[:300],
                 "primary_factor": str(d.get("primary_factor", ""))[:120]},
                int((time.time() - t0) * 1000))
    except Exception as e:
        return ({"verdict": "no_verdict", "confidence": 0, "reason": f"{type(e).__name__}: {e}"[:300],
                 "primary_factor": ""}, int((time.time() - t0) * 1000))


def record(con: sqlite3.Connection, sig: Signal, ctx: dict, res: dict, latency_ms: int) -> None:
    con.execute("INSERT OR REPLACE INTO cl_verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (sig.ts_ms, CL_PREFIX + sig.gate, sig.gate, sig.side, sig.entry_price,
                 res["verdict"], res["confidence"], res["reason"], res["primary_factor"],
                 latency_ms, json.dumps(ctx), sig.live_pnl))
    con.commit()


def score(con: sqlite3.Connection) -> dict:
    """The experiment. Because nothing was gated, we see the outcome of BOTH arms with no selection
    bias — that is the whole reason for doing it in shadow."""
    out: dict = {}
    for v in ("PASS", "VETO", "no_verdict"):
        r = con.execute("SELECT COUNT(*), COALESCE(SUM(live_pnl),0), COALESCE(AVG(live_pnl),0) "
                        "FROM cl_verdicts WHERE verdict=?", (v,)).fetchone()
        out[v] = {"n": r[0], "total": round(r[1], 2), "per_signal": round(r[2], 2)}
    p, vt = out["PASS"], out["VETO"]
    out["separation_per_signal"] = round(p["per_signal"] - vt["per_signal"], 2)
    # ★ Both arms must be populated before this means ANYTHING. The first live run had 5 VETOs and
    # ZERO PASSes and still printed "the judgement separates" — separation against an empty set is
    # arithmetic, not evidence. Refuse to claim a result until there is something to compare against.
    if p["n"] < 10 or vt["n"] < 10:
        out["verdict"] = (f"NO CLAIM — need >=10 in each arm to compare "
                          f"(PASS n={p['n']}, VETO n={vt['n']})")
    elif vt["per_signal"] < p["per_signal"]:
        out["verdict"] = "VETO signals lose more than PASS — the judgement separates"
    else:
        out["verdict"] = "NO separation — the judgement is not adding anything"
    out["primary_factors"] = dict(con.execute(
        "SELECT primary_factor, COUNT(*) FROM cl_verdicts WHERE verdict='VETO' "
        "GROUP BY 1 ORDER BY 2 DESC").fetchall())
    out["latency_ms_p50"] = con.execute(
        "SELECT latency_ms FROM cl_verdicts WHERE verdict!='no_verdict' "
        "ORDER BY latency_ms LIMIT 1 OFFSET (SELECT COUNT(*)/2 FROM cl_verdicts "
        "WHERE verdict!='no_verdict')").fetchone()
    return out
