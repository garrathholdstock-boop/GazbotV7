#!/usr/bin/env python3
"""ROUTER WATCH — event detector for the EVENT-DRIVEN router (Option B, 2026-07-31 trial).

Runs continuously under the Monitor tool (persistent). Polls the live desk every ~15s,
holds state between polls, and prints ONE stdout line per wake-worthy EVENT (debounced).
Each printed line becomes a Monitor notification that WAKES Claude to make a real call
(Claude then runs desk_view.py + recent_trades.py and decides). No Telegram from here —
the operator only gets texted when Claude actually acts or on a critical exception.

COVERAGE (silence is not success — health problems ALSO emit, never mask a dead desk):
  BREAK↑/↓        new session high/low beyond pad
  REGIME→TREND    ER climbed above ER_TREND (sustained)
  REGIME→CHOP     ER fell below ER_CHOP (sustained)
  WALL-OF-STOP    >=STOP_WALL_N STOP exits on one gate within STOP_WALL_MIN
  BLEED           day P&L dropped >=DD_ALARM from its session peak
  ⚠HALT / ⚠NAKED / ⚠FEED-STALE / ⚠AUDIT-STALE   health exceptions (critical)

Read-only. Debounced per event-type (cooldown) so it never spams. Thresholds are tunable.
"""
import sqlite3, json, time, os, sys
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
    _PARIS = ZoneInfo("Europe/Paris")
except Exception:
    _PARIS = None


def paris_day_start_utc():
    """Start of the current Paris trading day (Paris midnight), as a UTC datetime.
    The desk's 'day' resets at Paris midnight, so P&L drawdown must be measured within it."""
    if _PARIS is None:
        # fallback: Paris midnight ~= 22:00 UTC in summer / 23:00 in winter; use 22:00 UTC
        now = datetime.now(timezone.utc)
        anchor = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if now.hour < 22:
            from datetime import timedelta as _td
            anchor -= _td(days=1)
        return anchor
    now_p = datetime.now(_PARIS)
    start_p = now_p.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_p.astimezone(timezone.utc)

DATA = "/home/alphabot/gazbot7/data"
CAP = f"{DATA}/capture.db"
DB = f"{DATA}/gazbot7.db"
HEALTH = f"{DATA}/core_health.json"
STATUS = f"{DATA}/router_watch_status.json"   # liveness heartbeat (file, not an event)
SYM = "MNQ"
POLL_S = 15

# ── thresholds (tunable) ──
# regime uses HYSTERESIS (separate enter/exit) so ER wobble near a boundary doesn't re-fire.
ER_TREND_ENTER = 0.25  # enter TREND
ER_TREND_EXIT  = 0.20  # leave trend -> mixed
ER_CHOP_ENTER  = 0.08  # enter CHOP
ER_CHOP_EXIT   = 0.13  # leave chop -> mixed
REGIME_DWELL_S = 600   # min seconds between regime-change emits (10min — was too twitchy at 5)
ER_WIN_MIN   = 30      # ER window (minutes) — 30 smooths single chop-swings (20 flashed false trends)
ATR_TREND_MIN = 18     # REGIME→TREND + BREAK require ATR>=this (a real trend/break has vol; a LOW-vol drift-high isn't tradeable; 16 let a marginal non-trend through)
ATR_WIN_MIN  = 14      # window for the ATR vol proxy (minutes)
BREAK_PAD    = 5       # pts beyond running hi/lo to call a break
BREAK_COOL_S = 180     # min seconds between break emits (same direction)
STOP_WALL_N  = 2       # >=N STOP exits on a gate ...
STOP_WALL_MIN= 6       # ... within this many minutes -> wall
DD_ALARM     = 200.0   # $ drawdown from session peak -> bleed
FEED_STALE_S = 30      # tick age (s) while market OPEN -> feed break (30: a real gateway drop stays stale minutes; thin overnight gaps resolve in seconds — 8 false-fired on sparse overnight ticks)
FEED_COOL_S  = 300     # min seconds between feed-stale emits
AUDIT_STALE_S= 30      # core_health audit age -> auditor stale
# CME index-futures daily maintenance halt = 21:00-22:00 UTC (16:00-17:00 CT): no ticks is NORMAL then.
MAINT_HOUR_UTC = 21


def emit(msg):
    ts = time.strftime('%H:%M:%SZ', time.gmtime())
    print(f"{ts} {msg}", flush=True)


def q(dbpath, sql, args=()):
    try:
        c = sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True, timeout=2)
        c.row_factory = sqlite3.Row
        rows = c.execute(sql, args).fetchall()
        c.close()
        return rows
    except Exception:
        return None


def last_tick():
    r = q(CAP, "SELECT price, ts_ms FROM ticks WHERE symbol=? ORDER BY ts_ms DESC LIMIT 1", (SYM,))
    if not r:
        return None, None
    return r[0]["price"], r[0]["ts_ms"]


def er_recent(now_ms):
    start = now_ms - ER_WIN_MIN * 60 * 1000
    rows = q(CAP, "SELECT CAST(ts_ms/60000 AS INTEGER) m, price FROM ticks "
                  "WHERE symbol=? AND ts_ms>=? ORDER BY ts_ms", (SYM, start))
    if not rows:
        return None
    closes = {}
    for row in rows:
        closes[row["m"]] = row["price"]
    seq = [closes[k] for k in sorted(closes)]
    if len(seq) < 3:
        return None
    net = abs(seq[-1] - seq[0])
    path = sum(abs(seq[i] - seq[i-1]) for i in range(1, len(seq)))
    return (net / path) if path else 0.0


def atr_recent(now_ms):
    """Simple vol proxy: mean per-minute (high-low) range over the recent window ≈ ATR."""
    start = now_ms - ATR_WIN_MIN * 60 * 1000
    rows = q(CAP, "SELECT CAST(ts_ms/60000 AS INTEGER) m, max(price) hi, min(price) lo FROM ticks "
                  "WHERE symbol=? AND ts_ms>=? GROUP BY m", (SYM, start))
    if not rows or len(rows) < 3:
        return None
    ranges = [r["hi"] - r["lo"] for r in rows]
    return sum(ranges) / len(ranges)


def day_pnl():
    # sum closed trades since the PARIS day start (matches the desk's day; avoids the UTC-rollover artifact)
    rows = q(DB, "SELECT pnl_usd, closed_at FROM trades WHERE closed_at IS NOT NULL "
                 "ORDER BY closed_at DESC LIMIT 400")
    if rows is None:
        return None
    anchor = paris_day_start_utc()
    tot = 0.0
    for r in rows:
        try:
            ts = datetime.fromisoformat(str(r["closed_at"]))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if ts >= anchor:
            tot += (r["pnl_usd"] or 0.0)
    return tot


def stop_walls():
    rows = q(DB, "SELECT gate, exit_reason, closed_at FROM trades WHERE closed_at IS NOT NULL "
                 "ORDER BY closed_at DESC LIMIT 120")
    if rows is None:
        return {}
    cut = time.time() - STOP_WALL_MIN * 60
    tally = {}
    for r in rows:
        try:
            ts = datetime.fromisoformat(str(r["closed_at"])).timestamp()
        except Exception:
            continue
        if ts < cut:
            continue
        if r["exit_reason"] == "STOP":
            tally[r["gate"]] = tally.get(r["gate"], 0) + 1
    return {g: n for g, n in tally.items() if n >= STOP_WALL_N}


def health():
    try:
        d = json.load(open(HEALTH))
        prot = d.get("protection") or {}
        return {
            "halted": bool(d.get("halted")),
            "healthy": bool(d.get("healthy")),
            "held": bool(prot.get("held")),
            "unverified": int(prot.get("unverified_cycles") or 0),
            "audit_age": None,  # derive from ts below
            "ts": d.get("ts"),
        }
    except Exception:
        return None


def main():
    now_ms0 = last_tick()[1] or int(time.time() * 1000)
    hi = lo = None
    # seed hi/lo from last 3h of ticks
    seed = q(CAP, "SELECT max(price) hi, min(price) lo FROM ticks WHERE symbol=? AND ts_ms>=?",
             (SYM, now_ms0 - 3 * 3600 * 1000))
    if seed and seed[0]["hi"] is not None:
        hi, lo = seed[0]["hi"], seed[0]["lo"]

    st = {
        "regime": None,        # 'trend' | 'chop' | 'mixed'
        "last_regime": 0.0,
        "last_break_up": 0.0,
        "last_break_dn": 0.0,
        "last_feed": 0.0,
        "peak_pnl": None,
        "bleed_armed": True,
        "day_anchor": paris_day_start_utc(),
        "walls": set(),
        "halt": False, "naked": False, "audit": False,
    }

    px, tms = last_tick()
    er = er_recent(tms or now_ms0)
    emit(f"WATCH START — px {px} hi {hi} lo {lo} ER(20m) {er} — event-driven router watch live, "
         f"thresholds ER_TREND {ER_TREND_ENTER}/ER_CHOP {ER_CHOP_ENTER} break±{BREAK_PAD} DD ${DD_ALARM:.0f}")

    while True:
        try:
            wall_time = time.time()
            px, tms = last_tick()
            if px is None:
                time.sleep(POLL_S); continue

            # ── FEED STALE (suppressed during the CME daily maintenance halt; cooldown so it never spams) ──
            tick_age = (time.time() * 1000 - tms) / 1000.0 if tms else 999
            in_maint = time.gmtime().tm_hour == MAINT_HOUR_UTC
            if tick_age > FEED_STALE_S and not in_maint and (wall_time - st["last_feed"]) > FEED_COOL_S:
                emit(f"⚠FEED-STALE — last MNQ tick {tick_age:.0f}s ago (feed break? check gateway)")
                st["last_feed"] = wall_time
            if in_maint:
                # market closed for maintenance — skip trading-signal detection this poll
                try:
                    json.dump({"ts": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                               "px": px, "regime": st["regime"], "note": "CME maint halt"}, open(STATUS, "w"))
                except Exception:
                    pass
                time.sleep(POLL_S); continue

            # ── HEALTH exceptions ──
            h = health()
            if h:
                if h["halted"] and not st["halt"]:
                    emit("⚠HALT — desk core reports HALTED (check /positions, flatten if needed)")
                st["halt"] = h["halted"]
                naked = h["held"] and h["unverified"] > 0
                if naked and not st["naked"]:
                    emit(f"⚠NAKED — held position unverified {h['unverified']} cycles (possible stopless — CHECK IBKR)")
                st["naked"] = naked
                # audit age
                try:
                    ats = datetime.fromisoformat(str(h["ts"])).timestamp()
                    audit_age = time.time() - ats
                except Exception:
                    audit_age = 0
                audit_bad = audit_age > AUDIT_STALE_S
                if audit_bad and not st["audit"]:
                    emit(f"⚠AUDIT-STALE — core_health {audit_age:.0f}s old (auditor hung?)")
                st["audit"] = audit_bad

            # ── NEW PARIS DAY rollover: reset P&L-peak + session hi/lo for a clean new-day range ──
            cur_anchor = paris_day_start_utc()
            if cur_anchor != st["day_anchor"]:
                st["day_anchor"] = cur_anchor
                st["peak_pnl"] = None
                st["bleed_armed"] = True
                hi = lo = px
                emit(f"NEW-DAY — Paris day rolled over: reset P&L-peak + session hi/lo (px {px:.0f})")

            # ── BREAKS (vol-gated: a tradeable break has vol; a low-vol drift-high isn't actionable) ──
            if hi is None:
                hi = lo = px
            atr_now = atr_recent(tms)
            # ★2026-08-04 was `atr_now is None or atr_now >= ATR_TREND_MIN` — FAIL-OPEN. atr_recent()
            # returns None when there are INSUFFICIENT BARS, which is precisely the state at a session
            # reopen, so every trivial first-tick high/low fired a BREAK with "ATR 0". The 22:00 Globex
            # reopen emitted BREAK↑ and BREAK↓ 60 seconds apart, in opposite directions, both noise.
            # "I cannot measure volatility" is not "volatility is fine" — an unmeasurable read must
            # SUPPRESS the alert, not pass it. Alert fatigue on the one channel meant for real
            # exceptions (naked position, wall-of-STOP) is the actual cost.
            volok = (atr_now is not None and atr_now >= ATR_TREND_MIN)
            if px > hi + BREAK_PAD and volok and (wall_time - st["last_break_up"]) > BREAK_COOL_S:
                emit(f"BREAK↑ — new session high {px:.0f} (prev {hi:.0f}, +{px-hi:.0f}, ATR {atr_now or 0:.0f})")
                st["last_break_up"] = wall_time
            if px < lo - BREAK_PAD and volok and (wall_time - st["last_break_dn"]) > BREAK_COOL_S:
                emit(f"BREAK↓ — new session low {px:.0f} (prev {lo:.0f}, {px-lo:.0f}, ATR {atr_now or 0:.0f})")
                st["last_break_dn"] = wall_time
            hi = max(hi, px); lo = min(lo, px)  # track session range even when a low-vol break is suppressed

            # ── REGIME (hysteresis + a VOL gate: a real TREND needs ATR; an efficient LOW-vol drift is not tradeable) ──
            er = er_recent(tms)
            atr = atr_recent(tms)
            if er is not None:
                cur = st["regime"]
                new = cur
                if cur == "trend":
                    if er < ER_TREND_EXIT: new = "mixed"
                elif cur == "chop":
                    if er > ER_CHOP_EXIT: new = "mixed"
                else:  # mixed or None
                    if er >= ER_TREND_ENTER and atr is not None and atr >= ATR_TREND_MIN: new = "trend"   # ★ same fail-open fixed: unmeasurable ATR must not confirm a trend
                    elif er < ER_CHOP_ENTER: new = "chop"
                if new != cur:
                    # worth a wake: a TREND starting (vol-gated upstream), or a real TREND→CHOP (trend ended).
                    # NOT mixed→chop (just settling into the chop we're already positioned for = pure noise).
                    is_worth = (new == "trend") or (new == "chop" and cur == "trend")
                    if cur is not None and is_worth and (wall_time - st["last_regime"]) > REGIME_DWELL_S:
                        emit(f"REGIME→{new.upper()} — ER({ER_WIN_MIN}m) {er:.2f} ATR {atr or 0:.0f} (was {cur}), px {px:.0f}")
                        st["last_regime"] = wall_time
                        st["regime"] = new
                    elif cur is None or not is_worth:
                        st["regime"] = new  # silent (startup, settle to mixed, or mixed→chop non-event)

            # ── WALL-OF-STOP ──
            walls = stop_walls()
            for g, n in walls.items():
                if g not in st["walls"]:
                    emit(f"WALL-OF-STOP {g} — {n} stops in {STOP_WALL_MIN}min (getting chopped — bench?)")
            st["walls"] = set(walls.keys())

            # ── BLEED (drawdown from session peak) ──
            dp = day_pnl()
            if dp is not None:
                if st["peak_pnl"] is None or dp > st["peak_pnl"]:
                    st["peak_pnl"] = dp
                    st["bleed_armed"] = True
                dd = st["peak_pnl"] - dp
                if dd >= DD_ALARM and st["bleed_armed"]:
                    emit(f"BLEED — day P&L ${dp:.0f}, down ${dd:.0f} from session peak ${st['peak_pnl']:.0f}")
                    st["bleed_armed"] = False  # re-arms when a new peak is made

            # liveness heartbeat to file (NOT an event)
            try:
                json.dump({"ts": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                           "px": px, "er": er, "regime": st["regime"],
                           "day_pnl": dp, "peak": st["peak_pnl"], "hi": hi, "lo": lo},
                          open(STATUS, "w"))
            except Exception:
                pass

            time.sleep(POLL_S)
        except KeyboardInterrupt:
            break
        except Exception as e:
            # never let a transient error kill the watch
            emit(f"⚠WATCH-ERROR {type(e).__name__}: {e} (continuing)")
            time.sleep(POLL_S)


if __name__ == "__main__":
    main()
