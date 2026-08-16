"""CL- SIMS — eight shadow variants that mirror the live gates but only take trades Claude PASSES.

Operator, 2026-08-04: "I want 8 new sims. Same as current live. But the trades only happen if you
pass them."

WHY THIS SHAPE IS BETTER THAN WHAT I BUILT FIRST. My first attempt logged a verdict alongside each
live trade and scored the two verdict-sets against each other. This is a direct A/B instead:
`CL-grind_long` takes the same signals as live `grind_long`, minus the ones I veto, with the same
exits. So the comparison is one number against one number — CL-X versus live X — and there is no
verdict-set arithmetic to get wrong.

★ THE HONESTY REQUIREMENT: THE SIM ENTERS AT THE VERDICT PRICE, NOT THE SIGNAL PRICE.
The verdict takes ~8-15s to come back. If the sim entered at the signal price it would receive the
filtering for free with no latency cost, and it would beat the live gate on an advantage that cannot
exist in reality. So the wait is CHARGED to it: entry is the tape price at the moment the verdict
lands. If a signal's edge does not survive 15s of delay, this design will say so — correctly.

★ THE PROMPT DOES NOT NAME THE KNOWN-HOSTILE CONDITIONS.
The first run's prompt listed "violent whipsaw (ATR>=19 with ER30<0.25) is unsurvivable", and then I
reported as a finding that 61 of 113 vetoes cited violent whipsaw. That was a result about the prompt,
not about judgement. Here the model gets the raw numbers and must reach its own conclusion. If it
independently derives the whipsaw rule, that is a finding; if it is told, it is a parrot.

★ SPLIT ARCHITECTURE (rewritten 2026-08-04 after the first version could not work at all).
The first cut fired the model call from inside gazbot7-shadow. That service runs as `alphabot`, /root is
0700, there is no system-wide `claude` and alphabot has no sudo — so all 9 of its first verdicts were
`FileNotFoundError: 'claude'` at 0ms. The sims would have sat at zero trades looking disciplined while
being entirely broken, which is the exact failure this file's own scoreboard has a counter for.

So it is split, following the durable-router pattern that already works:
  * THIS half runs in gazbot7-shadow (alphabot): detect fires, journal them, and ENQUEUE a row in
    cl_signals with a NULL verdict. No model call, no network, no async — cheap and unbreakable.
  * scripts/cl_worker.py runs as ROOT on a timer: picks up NULL-verdict rows, calls claude, writes the
    verdict, and on PASS replays the trade forward on ticks to produce a real shadow_trades row.

Honesty cost of the split, stated rather than hidden: the entry price is the tape at the moment the
WORKER prices it, not read live off the shadow loop. The worker runs within a minute, so it is close,
but it is a reconstruction and the sim is still charged the full delay from signal to verdict.

Fail-safe throughout: no verdict, timeout, parse error or crash => the CL sim simply does not take
that trade, and nothing else on the desk notices.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass

CL_PREFIX = "CL-"
# ★2026-08-05 raised 25 -> 45. The 25s ceiling was NOT a neutral dropout: it was CORRELATED WITH THE
# VERDICT and therefore biased the book. Measured over the first 275 signals, PASS calls averaged
# 21.4s and VETO calls 16.8s, with the observed max (24.7s) censored right at the 25s wall — so the
# ceiling preferentially truncated the SLOW, PASS-leaning calls, i.e. exactly the ones that produce a
# shadow_trades row. 27 of 44 lost verdicts were timeouts. The CL book consequently read as more
# "disciplined" (3% take rate) than the model's actual judgement, which is the same selection effect
# as [[mfe-is-not-a-win-rate]] wearing different clothes: the dropout is not random w.r.t. the outcome.
# 45s clears the observed PASS mean with headroom. Batch safety: cl_worker drains all queued rows
# sequentially on a 2-min timer with TimeoutStartSec=900, and timeouts run ~9% of signals, so a 20-row
# backlog worst-cases well inside 900s. Revert: CALL_TIMEOUT_S = 25.
CALL_TIMEOUT_S = 45

# the eight live-roster gates, mirrored 1:1
CL_GATES: dict[str, str] = {
    "CL-grind_long": "grind_long",
    "CL-capitulation_long": "capitulation_long",
    "CL-abs_veto_long": "abs_veto_long",
    "CL-abs_veto_short": "abs_veto_short",
    "CL-exhaustion_short": "exhaustion_short",
    "CL-rgv_short": "rgv_short",
    "CL-nipc_long": "nipc_long",
    "CL-nipc_short": "nipc_short",
}

SCHEMA = """
-- ★2026-08-04 SIGNAL JOURNAL (operator: "keep a log of all buy signals and stamp those buy signals
-- with the conditions at the time so we can run analysis").
--
-- EVERY gate fire is logged with the conditions AS THEY STOOD AT THAT INSTANT — whether or not the
-- trade was taken. This is the single most useful thing in this file, and it is independent of the CL
-- experiment. It permanently removes the need to RECONSTRUCT context after the fact, which is where
-- this desk keeps going wrong: the NIPC replay diverged from live partly on provenance, and my first
-- CL run rebuilt ATR/ER from a fresh DuckDB pull rather than the deque the gate actually read. A
-- stamped-at-fire-time record cannot drift from what the gate saw, because it IS what the gate saw.
--
-- Columns are EXPLICIT, not a JSON blob, so this is directly queryable/groupable for analysis —
-- "what conditions precede a winner" becomes a GROUP BY instead of a parsing job.
--
-- Includes fires that were NOT taken (gate benched, slot already busy, floors blocked). Those are the
-- control group and they are currently invisible everywhere else on the desk — the trades table only
-- knows about signals that became positions.
CREATE TABLE IF NOT EXISTS signal_journal (
    ts_ms        INTEGER NOT NULL,
    gate         TEXT    NOT NULL,
    side         TEXT    NOT NULL,
    price        REAL,
    -- volatility / regime, exactly as the gate read them
    atr_pt       REAL,
    atr_pct      REAL,
    er30         REAL,
    er15         REAL,
    range_30m_pt REAL,
    net_30m_pt   REAL,
    -- gate-relevant geometry
    ext_atr      REAL,      -- extension from VWAP in ATRs
    vwap_slope   REAL,
    vwap_slope_fast REAL,
    net_atr_2    REAL,      -- the 120s impulse
    net_atr_5    REAL,      -- the 300s impulse thrust actually fires on
    -- tape
    tape_net     INTEGER,   -- net aggressor contracts
    -- context that is not a feature
    taken        INTEGER,   -- 1 if a live position resulted, 0 if suppressed, NULL if unknown yet
    suppressed_by TEXT,     -- 'switch_off' | 'slot_busy' | 'er_floor' | 'atr_floor' | 'veto' | NULL
    tradeability REAL,      -- the 0-10 gauge at fire time
    extra        TEXT,      -- JSON escape hatch for anything added later without a migration
    PRIMARY KEY (ts_ms, gate, side)
);
CREATE INDEX IF NOT EXISTS ix_sj_gate_ts ON signal_journal(gate, ts_ms);

CREATE TABLE IF NOT EXISTS cl_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim TEXT NOT NULL, gate TEXT NOT NULL, side TEXT NOT NULL,
    signal_ts_ms INTEGER NOT NULL,      -- when the gate fired
    signal_price REAL NOT NULL,         -- price then (recorded, NOT used as the entry)
    verdict_ts_ms INTEGER,              -- when the answer came back
    entry_price REAL,                   -- ★ price at verdict_ts_ms — what the sim actually pays
    verdict TEXT, confidence INTEGER, reason TEXT, primary_factor TEXT,
    latency_ms INTEGER, context TEXT
);
"""


@dataclass
class Pending:
    sim: str
    gate: str
    side: str
    ts_ms: int
    price: float
    ctx: dict


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.commit()


PROMPT = """You are deciding whether to take ONE trade on an MNQ futures desk. Reply PASS or VETO.

A mechanical gate has already fired — its own entry conditions are met. Your job is to judge, from the
market context below, whether THIS instance is likely to lose anyway.

Cost context: $1.50 per round trip, MNQ is $2/point, and the stop is 1x ATR. So a trade needs to clear
roughly a point of friction before it earns anything.

Weigh the evidence in the context yourself. Do not assume a gate firing is sufficient, and do not veto
on generic caution — a veto that merely restates the gate's own logic adds nothing. If the context
gives no concrete reason to expect this one to fail, PASS it.

The context includes `l2_book`: the resting 10-deep order book at the moment the gate fired, with sizes
on each side. Read it if it tells you something the price series does not; ignore it if it does not.
Note its `age_ms` and `stale` flag — a stale book describes the past, not the moment of entry.

Reply with STRICT JSON only:
{"verdict":"PASS"|"VETO","confidence":0-100,"reason":"<one line>","primary_factor":"<the single thing that decided it>"}

CONTEXT:
"""


def _call(ctx: dict) -> tuple[dict, int]:
    """Blocking model call. Run via asyncio.to_thread so the shadow loop never waits on it."""
    t0 = time.time()
    try:
        p = subprocess.run(["claude", "-p", PROMPT + json.dumps(ctx, indent=1)],
                           capture_output=True, text=True, timeout=CALL_TIMEOUT_S)
        import re
        m = re.search(r"\{.*\}", p.stdout, re.S)
        d = json.loads(m.group(0)) if m else {}
        if d.get("verdict") not in ("PASS", "VETO"):
            raise ValueError(f"bad verdict {d.get('verdict')!r}")
        return ({"verdict": d["verdict"], "confidence": int(d.get("confidence", 0)),
                 "reason": str(d.get("reason", ""))[:300],
                 "primary_factor": str(d.get("primary_factor", ""))[:120]},
                int((time.time() - t0) * 1000))
    except Exception as e:
        return ({"verdict": "no_verdict", "confidence": 0,
                 "reason": f"{type(e).__name__}: {e}"[:300], "primary_factor": ""},
                int((time.time() - t0) * 1000))


_SWITCH_PATH = "/home/alphabot/gazbot7/data/gate_switches.env"
_SW_CACHE: dict = {"mtime": -1.0, "off": frozenset()}

# ★★2026-08-16 BUILD #6 — `suppressed_by` WAS A DEAD COLUMN: NULL in every row, because the one
# caller passed neither it nor `taken`. Any claim of the form "the gate fired but we did not take it,
# because X" was unanswerable from the journal — which is the entire reason the journal exists.
#
# ⚠⚠ WHAT THIS LOOP CAN AND CANNOT SEE. Read this before trusting the column.
# ClSims is a SHADOW MIRROR of the gates: it re-evaluates entries from bars, it is not the desk, and
# it has no view of live slot state. Of the five declared reasons it can determine three, and two it
# cannot:
#     switch_off  YES — straight from gate_switches.env, the router's own file
#     atr_floor   YES — deciders.ATR_FLOOR against this fire's ATR
#     er_floor    YES — deciders.ER_FLOOR (currently {}, so it never fires; wired for when it is not)
#     slot_busy   NO  — needs the live SlotBook
#     veto        NO  — the 55s absorption veto lives in tournament.run()
#
# ★ A BLIND SPOT WRITTEN AS NULL WOULD READ EXACTLY LIKE "NOTHING SUPPRESSED IT" — the same failure
# one level down. So an unsuppressed fire is written as the explicit sentinel 'none_visible', never
# NULL, and `taken` is left NULL because this loop genuinely does not know whether a position
# resulted. Reading the column afterwards:
#     NULL           = written before 2026-08-16, or by a caller that passed nothing
#     'none_visible' = checked; nothing THIS LOOP can see suppressed it (the desk still might have)
#     anything else  = the reason, and it is authoritative
NOT_VISIBLE = "none_visible"
# ★2026-08-16 (audit) A THIRD STATE, because two were not enough. _switches_off() fails OPEN — a
# read failure returns an empty set, which is right (inventing suppressions would be worse) but it
# meant a benched gate was written as 'none_visible': the exact wrong story this column was built to
# stop telling, and now written PERMANENTLY into signal_journal rather than transiently into a
# report. 'unknown_switch_unreadable' is indistinguishable from nothing only if you do not look.
SWITCH_UNREADABLE = "unknown_switch_unreadable"


def _switches_off() -> frozenset:
    """Gates currently switched OFF, cached on mtime.

    A read failure returns an EMPTY set — fail OPEN. Claiming a gate is off because the file could
    not be read would invent suppressions that never happened, and this column exists to be trusted.
    """
    try:
        m = os.path.getmtime(_SWITCH_PATH)
        if m != _SW_CACHE["mtime"]:
            from .tournament import parse_switches
            with open(_SWITCH_PATH) as fh:
                _SW_CACHE["off"] = frozenset(parse_switches(fh.read()))
            _SW_CACHE["mtime"] = m
    except Exception:
        return None            # ⚠ None = "could not tell", NOT "nothing is off"
    return _SW_CACHE["off"]


def suppression_reason(gate: str, f, er30: float | None = None) -> str:
    """Why the LIVE desk would have declined this fire, as far as this loop can tell.

    ★ ORDER MIRRORS tournament.step() DELIBERATELY: the switch is tested first, because a benched
    gate never reaches its floors. Reporting 'atr_floor' for a benched gate would be a true
    statement about a test the desk never ran — precise, and misleading.
    """
    from .deciders import ATR_FLOOR, ER_FLOOR

    off = _switches_off()
    if off is None:
        # Cannot read the switch file. Saying 'none_visible' here would assert that nothing
        # suppressed a fire we genuinely know nothing about — and unlike a report, this is written
        # to the journal forever.
        return SWITCH_UNREADABLE
    if gate in off:
        return "switch_off"
    floor = ATR_FLOOR.get(gate)
    if floor is not None and f.atr < floor:
        return "atr_floor"
    er_floor = ER_FLOOR.get(gate)
    if er_floor is not None and er30 is not None and er30 < er_floor:
        return "er_floor"
    return NOT_VISIBLE


def journal(con: sqlite3.Connection, *, ts_ms: int, gate: str, side: str, price: float,
            f, bars, tape_net: float, taken: int | None = None,
            suppressed_by: str | None = None, extra: dict | None = None) -> None:
    """Stamp ONE gate fire with the conditions at that instant. Call it for EVERY fire, taken or not.

    Cheap by construction: one INSERT, no network, no query — every value is already in hand because
    the gate just evaluated them. At 33-100 fires/day this is nothing.

    Never raises. A journal that can break the caller is worse than no journal, and this sits in a
    loop that must not stop."""
    try:
        from .sizing import efficiency_ratio
        from .tradeability import score as tscore
        w = bars[-30:] if len(bars) >= 30 else bars
        rng = (max(x.high for x in w) - min(x.low for x in w)) if w else 0.0
        net = (w[-1].close - w[0].close) if w else 0.0
        er30 = efficiency_ratio(bars, 30)
        er15 = efficiency_ratio(bars, 15)
        cls = [x.close for x in w]
        fav = max(max(cls) - cls[0], cls[0] - min(cls)) if cls else 0.0
        gb = 0.0 if fav <= 0 else max(0.0, min(1.0, 1 - abs(cls[-1] - cls[0]) / fav))
        con.execute(
            "INSERT OR IGNORE INTO signal_journal (ts_ms,gate,side,price,atr_pt,atr_pct,er30,er15,"
            "range_30m_pt,net_30m_pt,ext_atr,vwap_slope,vwap_slope_fast,net_atr_2,net_atr_5,"
            "tape_net,taken,suppressed_by,tradeability,extra) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ts_ms, gate, side, round(price, 2), round(f.atr, 2), round(f.atr_pct, 6),
             round(er30, 4), round(er15, 4), round(rng, 1), round(net, 1),
             round(f.ext_atr, 3), round(f.vwap_slope_atr, 4), round(f.vwap_slope_fast, 4),
             round(f.net_atr_2, 3), round(f.net_atr_5, 3), int(tape_net),
             taken, suppressed_by, tscore(er30, f.atr, gb).score,
             json.dumps(extra) if extra else None))
        con.commit()
    except Exception:
        pass   # deliberately silent — see docstring


class ClSims:
    """Shadow-service half: detect fires on the mirrored gates, journal them, enqueue for verification.

    Deliberately does NO model call and manages NO positions — see the split note in the module
    docstring. Everything here is a local INSERT, so it cannot stall the 1s loop and cannot fail in a
    way the shadow desk notices.
    """

    def __init__(self, con: sqlite3.Connection, store, *, value_per_point: float = 2.0,
                 fee_rt: float = 1.50) -> None:
        from .slot_strategy import scaleout_slots
        ensure_schema(con)
        self._con = con
        self._vpp, self._fee = value_per_point, fee_rt
        # mirror the LIVE exits: take each twin's Lot-A spec off the running slate so a CL sim cannot
        # silently drift from the gate it is being compared against.
        self._spec = {s.tag.replace("_A", ""): s for s in scaleout_slots() if s.tag.endswith("_A")}
        self._seen: set = set()

    def _fires(self, f, tape_net, in_rth, cap):
        """Which mirrored gates fire this tick. Reuses the live deciders — no reimplementation."""
        from .deciders import gate_capitulation, gate_grind, gate_reversal_grab, gate_thrust
        out = []
        for sim, gate in CL_GATES.items():
            spec = self._spec.get(gate)
            if spec is None:
                continue
            p = dict(spec.params)
            try:
                if spec.kind == "thrust":
                    e = gate_thrust(f, **p)
                elif spec.kind == "grind":
                    e = gate_grind(f, tape_net=tape_net, **p)
                elif spec.kind == "capitulation":
                    e = gate_capitulation(f, cap_sell=cap.get("sell", 0.0), cap_buy=cap.get("buy", 0.0),
                                          cap_base=cap.get("base", 0.0), cap_dpx=cap.get("dpx", 0.0),
                                          cap_flip=cap.get("flip", False), **p)
                elif spec.kind == "reversal_grab":
                    e = gate_reversal_grab(f, tape_net=tape_net, in_rth=in_rth, **p)
                else:
                    e = None      # nipc is a tick state machine — not driven from this loop
            except Exception:
                e = None
            if e is not None and e.side == spec.side:
                out.append((sim, gate, e.side, spec))
        return out

    def step(self, bars, *, price: float, tape_net: float, now_ms: int, in_rth: bool, cap: dict) -> None:
        from .deciders import compute_features
        f = compute_features(bars)
        for sim, gate, side, spec in self._fires(f, tape_net, in_rth, cap):
            # one fire per gate per minute: features are bar-quantised, so a 1s loop would otherwise
            # enqueue the same decision ~60 times.
            key = (now_ms // 60000, sim)
            if key in self._seen:
                continue
            self._seen.add(key)
            # ★2026-08-16 BUILD #6 — record WHY, not just THAT. `taken` stays None on purpose:
            # this loop cannot see whether a live position resulted, and guessing 1 here would be
            # the dead column replaced by a wrong one.
            from .sizing import efficiency_ratio
            journal(self._con, ts_ms=now_ms, gate=gate, side=side, price=price, f=f, bars=bars,
                    tape_net=tape_net,
                    suppressed_by=suppression_reason(gate, f, efficiency_ratio(bars, 30)))
            self._con.execute(
                "INSERT INTO cl_signals (sim,gate,side,signal_ts_ms,signal_price,context) "
                "VALUES (?,?,?,?,?,?)",
                (sim, gate, side, now_ms, price,
                 json.dumps(build_ctx(f, price, side, gate, bars, tape_net, [], ts_ms=now_ms))))
            self._con.commit()
        if len(self._seen) > 5000:
            self._seen.clear()


# ───────────────────────────────── L2 BOOK (added 2026-08-04) ─────────────────────────────────
# ★ THIS REPLACES A WRONG CLAIM OF MY OWN. The previous build_ctx docstring said the book was
# "deliberately EXCLUDED: ~86 contracts visible against ~2,664 contracts/min of flow, roughly 6x
# below where absorption is measurable." Both numbers were wrong and the conclusion inverted:
# measured over 08-03/08-04, MNQ shows ~162 contracts across the 10 visible levels against ~170
# contracts/MINUTE traded — so the resting book is about 57 SECONDS of flow, not a rounding error.
# Worse, I told the operator we did not persist the book at all. We do: alphabot-depth-capture.service
# has been writing all 10 levels both sides at ~3.7 snaps/sec since 07-15 (4.2M MNQ rows).
#
# SCOPE, per the operator: the book is NOT here to generate triggers — prior studies found it does not
# predict run starts, consistent with [run-catcher NULL]. It is here to CONFIRM OR VETO a trigger that
# already fired. That is a far weaker claim and the one thing the coded rule cannot do: `ext_atr > 1.5
# AND ER30 < 0.25` sees only price, so a stretched price over a stacked bid and the same price over a
# hollow one look identical to it. This is the orthogonal information that could justify a model call.
#
# The prompt is NOT told what to conclude from the ladder — see the anchoring note in the header.
DEPTH_DB = "/home/alphabot/gazbot7/data/depth.db"
# ★ WHY 7s AND NOT 1s. depth_capture.py samples the book every SNAP_S=0.25s but writes in
# FLUSH_S=5.0s BATCHES, and it dedups a static book (`if last_row[sym] == row: continue`). So a read of
# this DB is up to 5s behind reality BY DESIGN, and a gap can mean either "not yet flushed" or "the book
# did not change" — indistinguishable from here. A 3s threshold flagged almost every read as stale and
# would have taught the model to discount a book that was fine. 7s means genuinely nothing arrived.
# The true age is always passed through as age_ms so the verdict can weigh it rather than trust a flag.
BOOK_STALE_MS = 7_000


def book_snapshot(ts_ms: int, symbol: str = "MNQ") -> dict | None:
    """Nearest-prior 10-deep book snapshot to ts_ms, as raw ladder plus aggregates.

    Read-only, indexed on (symbol, ts_ms) so it costs well under a millisecond. Any failure returns
    None and the context simply carries no book — the shadow loop must never die for this (it already
    went down once this week on a logging bug, which is exactly the standard being applied here)."""
    try:
        con = sqlite3.connect(f"file:{DEPTH_DB}?mode=ro", uri=True, timeout=1.0)
        try:
            cols = ["ts_ms"] + [f"{s}{i}{k}" for i in range(1, 11) for s in ("bid", "ask") for k in ("p", "s")]
            row = con.execute(
                f"SELECT {','.join(cols)} FROM depth_snap WHERE symbol=? AND ts_ms<=? "
                "ORDER BY ts_ms DESC LIMIT 1", (symbol, ts_ms)).fetchone()
        finally:
            con.close()
        if not row:
            return None
        d = dict(zip(cols, row))
        age = ts_ms - int(d["ts_ms"])
        ladder, bid_tot, ask_tot, near_b, near_a = [], 0.0, 0.0, 0.0, 0.0
        for i in range(1, 11):
            bp, bs = d[f"bid{i}p"] or 0.0, d[f"bid{i}s"] or 0.0
            ap, as_ = d[f"ask{i}p"] or 0.0, d[f"ask{i}s"] or 0.0
            ladder.append({"lvl": i, "bid": round(bp, 2), "bid_size": int(bs),
                           "ask": round(ap, 2), "ask_size": int(as_)})
            bid_tot += bs
            ask_tot += as_
            if i <= 3:
                near_b += bs
                near_a += as_
        tot = bid_tot + ask_tot
        return {
            "age_ms": age,
            "stale": age > BOOK_STALE_MS,
            "ladder_10_deep": ladder,
            "bid_depth_total": int(bid_tot),
            "ask_depth_total": int(ask_tot),
            "imbalance_all_levels": round((bid_tot - ask_tot) / tot, 3) if tot else None,
            "imbalance_near_3": round((near_b - near_a) / (near_b + near_a), 3) if (near_b + near_a) else None,
            "spread_pt": round((d["ask1p"] or 0) - (d["bid1p"] or 0), 2),
            "scale_note": ("resting depth across these 10 levels is typically ~160 contracts while "
                           "traded flow is ~170 contracts/min, i.e. the visible book is on the order "
                           "of a minute of flow"),
        }
    except Exception:
        return None


def build_ctx(f, price: float, side: str, gate: str, bars, tape_net: float,
              recent: list[tuple[str, str, float]], ts_ms: int | None = None) -> dict:
    """The snapshot, from the SHADOW SERVICE'S OWN LIVE STATE — the same Features and MinuteBars the
    gates just evaluated. Nothing is reconstructed from the database afterwards, so there is no
    provenance gap between what the gate saw and what the model is shown.

    The L2 book IS included as of 2026-08-04 (see the note above the book_snapshot helper); it is read
    at signal time and stored, so the verdict is judged on the book as it was when the gate fired, not
    on a book fetched later."""
    from .sizing import efficiency_ratio
    w = bars[-30:] if len(bars) >= 30 else bars
    rng = (max(x.high for x in w) - min(x.low for x in w)) if w else 0.0
    net = (w[-1].close - w[0].close) if w else 0.0
    ctx = {
        "proposed_trade": {"gate": gate, "side": side, "price": round(price, 2)},
        "volatility": {"atr_pt": round(f.atr, 1), "atr_pct_of_price": round(f.atr_pct, 5)},
        "directional_efficiency_er30": round(efficiency_ratio(bars, 30), 3),
        "last_30_min": {"range_pt": round(rng, 1), "net_move_pt": round(net, 1)},
        "extension_from_vwap_in_atr": round(f.ext_atr, 2),
        "vwap_slope_atr": round(f.vwap_slope_atr, 3),
        "net_move_5bar_in_atr": round(f.net_atr_5, 2),
        "tape_net_flow_contracts": int(tape_net),
        "last_5_closed_trades": [{"gate": g, "exit": r, "pnl": round(p, 2)} for g, r, p in recent],
    }
    bk = book_snapshot(ts_ms) if ts_ms else None
    ctx["l2_book"] = bk if bk else {"unavailable": True}
    return ctx
