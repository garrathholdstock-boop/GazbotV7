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
  DAY-RIDER ENTERED/CLOSED   the SECOND desk took or left a position
  DAY-RIDER BLEED            the rider's OWN unrealised drawdown (never the account net)
  ⚠DAY-RIDER STALE-FLAT      rider not ticking while flat — its watchdog says "ok flat" forever
  DAY-RIDER NO-DETECT        past its 15:00Z cutoff with no entry this session
  ⚠DESK-MISMATCH             venue net != tournament claim + rider claim (the 08-06 detector)

Read-only. Debounced per event-type (cooldown) so it never spams. Thresholds are tunable.
"""
import sqlite3, json, time, os, sys
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
    _PARIS = ZoneInfo("Europe/Paris")
except Exception:
    _PARIS = None


def desk_book():
    """Who owns what, per DESK, plus the shared-account reconciliation.

    Returns a dict or None. Every position number is attributed to the desk that owns it,
    because the two desks net into ONE IBKR number and treating that number as anybody's in
    particular is precisely the 2026-08-06 failure.

    `mismatch` is the interesting field: venue_net minus (tournament + rider) claims. Non-zero
    means the account holds something no desk admits to — an orphan stop that fired with no
    slot behind it, a fill one desk never received, or one desk acting on the other's lots.

    ⚠ venue_net is read from the RIDER's state file, so it is only as fresh as the rider's
    heartbeat. A stale rider makes venue_net stale, and a stale number must never be
    reconciled against live claims — so this returns venue_net=None once the heartbeat is old,
    and the caller must not report a mismatch it cannot actually see.
    """
    try:
        with open(DR_STATE) as fh:
            dr = json.load(fh)
    except Exception:
        return None
    now = datetime.now(timezone.utc)
    hb_age = None
    try:
        hb_age = (now - datetime.fromisoformat(dr["heartbeat"])).total_seconds()
    except Exception:
        pass

    rider_qty = 0.0
    if dr.get("entered") and not dr.get("closed"):
        try:
            rider_qty = abs(float(dr.get("qty") or 0)) * int(dr.get("direction") or 0)
        except Exception:
            rider_qty = 0.0

    tour_qty, tour_known = 0.0, False
    try:
        with open(HEALTH) as fh:
            h = json.load(fh)
        prot = h.get("protection") if isinstance(h.get("protection"), dict) else {}
        for sl in (prot.get("slots") or []):
            q = abs(float(sl.get("qty") or 0))
            tour_qty += -q if str(sl.get("side", "")).upper() == "SHORT" else q
        tour_known = True
    except Exception:
        pass

    # ⚠ venue_net has its OWN timestamp and the heartbeat must not stand in for it. Until
    # 2026-08-11 venue_net was refreshed only while the rider held a position, so a closed
    # rider kept a fresh heartbeat beside a frozen venue number — and this detector read the
    # two as one, firing a critical false DESK-MISMATCH. If venue_net_ts is absent (a rider on
    # older code, or a tick that never reached the broker) the venue read is UNKNOWN, and an
    # unknown must not be reconciled: no number is better than a stale one.
    venue = None
    try:
        v_age = (now - datetime.fromisoformat(dr["venue_net_ts"])).total_seconds()
        if v_age <= DR_HB_STALE_S:
            venue = float(dr["venue_net"])
    except Exception:
        venue = None

    mismatch = None
    if venue is not None and tour_known:
        mismatch = venue - (tour_qty + rider_qty)

    return {"rider": dr, "rider_qty": rider_qty, "tour_qty": tour_qty,
            "tour_known": tour_known, "venue_net": venue, "mismatch": mismatch,
            "hb_age": hb_age, "venue_ts": dr.get("venue_net_ts")}


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

# ── DAY RIDER (2026-08-11, operator: "does the day rider have a watcher too?") ──────────────
# It did not. It has a flatten-only WATCHDOG for the catastrophic case — venue holds a
# position nobody is managing — and nothing else. That watchdog returns "ok flat" whenever the
# venue is flat NO MATTER HOW STALE the heartbeat is, so a rider that died at 09:00 and never
# entered pages nobody and looks fine all day. Silent non-participation.
DR_STATE = f"{DATA}/day_rider_state.json"
DR_HB_STALE_S   = 300      # heartbeat age -> the rider is not ticking (it ticks every 60s)
DR_BLEED_USD    = 200.0    # unrealised drawdown on the RIDER alone -> bleed (mirrors DD_ALARM)
DR_BLEED_COOL_S = 900      # it holds for hours; one bleed alert per 15min, not per poll
DR_NO_DETECT_UTC_MIN = 15 * 60      # its own entry cutoff — after this, no entry can happen
DR_VPP = 2.0               # MNQ $/point

# ★★ THE TWO DESKS SHARE ONE IBKR ACCOUNT (DUQ191770) AND IBKR NETS THEM INTO ONE NUMBER.
# That is the whole 2026-08-06 incident: the day-rider flattened the ACCOUNT net without
# checking whose position it was, took the tournament's 2 lots with it, and the tournament sat
# 11 minutes halted with its safety block skipped. So every position number here is labelled
# with the desk that OWNS it, and they are reconciled rather than assumed:
#     venue_net  ==  tournament claim  +  day-rider claim
# venue_net is the whole-account net the RIDER's client already reports (day_rider_state.json),
# the tournament's claim comes from core_health.json, and the rider's claim from its own state.
# No new IB connection is opened to do this — a watcher that grabbed its own clientId to check
# for confusion between clients would be adding another one.
DESK_MISMATCH_COOL_S = 600


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
        # DAY RIDER (a SEPARATE desk — never fold its numbers into the tournament's)
        "dr_in": False, "dr_peak": None, "last_dr_bleed": 0.0,
        "dr_stale_flat": False, "dr_no_detect": False, "last_mismatch": 0.0,
        "mismatch_seen": (None, None),
    }

    px, tms = last_tick()
    er = er_recent(tms or now_ms0)
    # ★2026-08-11 the label said "ER(20m)" while ER_WIN_MIN has been 30 — it printed the
    # 30-min ER under a 20-min name. On the US-open reversal that read 0.09 ("dead tape")
    # while the actual 20-min leg was 0.55, i.e. the label hid the entire move. Derive the
    # label from the constant so the two can never drift apart again, and round it: the raw
    # float printed 17 significant digits.
    emit(f"WATCH START — px {px} hi {hi} lo {lo} ER({ER_WIN_MIN}m) {er:.3f} — "
         f"event-driven router watch live, "
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
            # ★★2026-08-07 SESSION-AWARE. FEED_STALE_S is documented as "while market OPEN" but the guard
            # only knew about the DAILY 21:00-22:00 maintenance halt — not the WEEKEND. CME equity futures
            # close Friday 21:00Z and do not reopen until Sunday 22:00Z, so from 22:00 Friday this fired
            # every ~5 min for ~48h: ~576 false alarms, which is exactly how a real alert gets ignored.
            # Observed live 2026-08-07 22:00/22:05/22:10Z with both feed services healthy and sweep
            # reporting "MARKET CLOSED". A stale tick with the market shut is not a feed break.
            try:
                from gazbot7 import session as _sess
                market_open = _sess.is_open(datetime.now(timezone.utc))
            except Exception:
                market_open = True          # fail LOUD: if we cannot tell, keep alarming
            if tick_age > FEED_STALE_S and not in_maint and market_open and (wall_time - st["last_feed"]) > FEED_COOL_S:
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

            # ── DAY RIDER — a SECOND DESK, watched separately and labelled as such ──────
            # Everything below says "DAY-RIDER" in the event text on purpose. The two desks
            # net into ONE IBKR number and the 08-06 cascade began with a flatten that did
            # not check whose position it was; an alert that does not name the desk invites
            # exactly that confusion at exactly the wrong moment.
            book = desk_book()
            if book:
                drs = book["rider"]
                in_pos = bool(drs.get("entered") and not drs.get("closed"))
                hb_age = book["hb_age"]
                mins_utc = time.gmtime().tm_hour * 60 + time.gmtime().tm_min

                # (1) ENTERED — it took a position. Informational, once per entry.
                if in_pos and not st["dr_in"]:
                    side = "SHORT" if book["rider_qty"] < 0 else "LONG"
                    emit(f"DAY-RIDER ENTERED — {side} {abs(book['rider_qty']):g} @ "
                         f"{drs.get('entry')} (its own desk; tournament claim "
                         f"{book['tour_qty']:+g})")
                    st["dr_peak"] = 0.0
                elif not in_pos and st["dr_in"]:
                    emit(f"DAY-RIDER CLOSED — {drs.get('note') or 'flat'}")
                    st["dr_peak"] = None
                st["dr_in"] = in_pos

                # (2) BLEED on the RIDER'S OWN unrealised P&L, never the account net.
                if in_pos:
                    try:
                        ahead = float(drs.get("ahead_pt"))
                        upnl = ahead * abs(book["rider_qty"]) * DR_VPP
                    except Exception:
                        upnl = None
                    if upnl is not None:
                        if st["dr_peak"] is None or upnl > st["dr_peak"]:
                            st["dr_peak"] = upnl
                        dd = st["dr_peak"] - upnl
                        if dd >= DR_BLEED_USD and (wall_time - st["last_dr_bleed"]) > DR_BLEED_COOL_S:
                            emit(f"DAY-RIDER BLEED — unrealised ${upnl:.0f} on ITS OWN 2 lots, "
                                 f"down ${dd:.0f} from its peak ${st['dr_peak']:.0f}; trail "
                                 f"{'ARMED @ ' + str(drs.get('trail')) if drs.get('trail') else 'NOT ARMED'}, "
                                 f"hard flat 20:40Z (tournament P&L is separate)")
                            st["last_dr_bleed"] = wall_time

                # (3) STALE-FLAT — closes the hole in day_rider_watchdog.py: it returns
                # "ok flat" whenever the venue is flat however dead the strategy is, so a
                # rider that died before entering pages nobody and looks fine all day.
                stale_flat = (not in_pos and hb_age is not None and hb_age > DR_HB_STALE_S
                              and market_open)
                if stale_flat and not st["dr_stale_flat"]:
                    emit(f"⚠DAY-RIDER STALE-FLAT — heartbeat {hb_age:.0f}s old and it holds "
                         f"nothing, so the flatten-watchdog will report 'ok flat' forever. "
                         f"The rider may be DEAD and simply not trading (check "
                         f"gazbot7-day-rider.timer)")
                st["dr_stale_flat"] = stale_flat      # latch on rise, clear when it recovers

                # (4) NO-DETECT — past its own 15:00Z entry cutoff with no entry all session.
                if (mins_utc >= DR_NO_DETECT_UTC_MIN and not st["dr_no_detect"]
                        and market_open and not in_pos and not drs.get("entered")):
                    emit(f"DAY-RIDER NO-DETECT — past its 15:00Z entry cutoff with no entry "
                         f"this session (drift never cleared eff>=0.15 & rt>=0.45). Not a "
                         f"fault; it means the desk is tournament-only today")
                    st["dr_no_detect"] = True

                # (5) ★★ DESK MISMATCH — the 08-06 detector. The account holds something no
                # desk admits to: an orphan stop that fired with no slot behind it, a fill one
                # desk never received, or one desk moving the other's lots. Only checked when
                # venue_net is FRESH — desk_book() returns None for it once the rider's
                # heartbeat is stale, and reconciling live claims against a stale number would
                # manufacture phantom mismatches.
                # ★2026-08-12 REQUIRE TWO INDEPENDENT VENUE READS TO AGREE.
                # The claims and the venue snapshot are sampled at DIFFERENT INSTANTS: venue_net
                # comes from the rider's 60s tick, the tournament's claim from core_health written
                # on its own cycle. So any position change by either desk opens a window where they
                # legitimately disagree. It false-fired twice — 16:09:13 nine seconds after the
                # tournament opened 2 shorts, and again when it stopped out at 16:11:56, 35s AFTER
                # the venue read that still counted them.
                # A real orphan persists across venue reads; a race does not. So a mismatch must be
                # seen on TWO SEPARATE venue snapshots (different venue_net_ts) before it alerts —
                # the same two-tick confirmation the direction rule uses, for the same reason.
                mm = book["mismatch"]
                v_ts = book.get("venue_ts")
                confirmed = False
                if mm is not None and abs(mm) >= 1:
                    prev_mm, prev_ts = st["mismatch_seen"]
                    if prev_mm is not None and abs(prev_mm - mm) < 0.5 and prev_ts != v_ts:
                        confirmed = True          # same imbalance, a genuinely newer venue read
                    st["mismatch_seen"] = (mm, v_ts)
                    if not confirmed:
                        # ★2026-08-13 FIX: this called an undefined `log()`. The NameError raised on
                        # EVERY unconfirmed-mismatch cycle and aborted the rest of the block — the
                        # `if confirmed` DESK-MISMATCH alert below AND the liveness heartbeat write
                        # were both skipped. It surfaced the moment the day-rider opened 2 lots
                        # (13:38:29Z): the 08-06 shared-account detector broke exactly when a second
                        # desk took a position, which is the one case it exists to watch.
                        # Deliberately stderr, not emit(): this is the "seen once, awaiting a second
                        # read" note, which the comment above calls NOT an event. emit() would page
                        # every 15s through every ordinary position change.
                        print(f"  -> DESK-MISMATCH {mm:+g} seen, awaiting a second venue read "
                              f"(transient during a position change looks exactly like this)",
                              file=sys.stderr, flush=True)
                else:
                    st["mismatch_seen"] = (None, None)
                if (confirmed
                        and (wall_time - st["last_mismatch"]) > DESK_MISMATCH_COOL_S):
                    emit(f"⚠DESK-MISMATCH — venue net {book['venue_net']:+g} but tournament "
                         f"claims {book['tour_qty']:+g} and day-rider claims "
                         f"{book['rider_qty']:+g} (unaccounted {mm:+g}). Shared account "
                         f"DUQ191770 — this is the 08-06 shape: CHECK TWS for working stops "
                         f"with no position behind them")
                    st["last_mismatch"] = wall_time

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
