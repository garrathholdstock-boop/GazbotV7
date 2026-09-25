"""GAZBOT V7 — the watch page server.

Serves the V5 MNQ cockpit (copied verbatim: web_static/app.{html,css,js}) and the
four endpoints its JS consumes, computed from V7's store + capture DB + core's
status.json:

* /api/futures/bars/<MNQ|MGC>?count=N — 1-minute price bars for the hero chart (the tf
  buttons set N); aggregated from the 5s capture bars.
* /api/futures/us-terminal       — holdings (from core's live position) + activity
  (last/VWAP/ATR/net-ATR for the ribbon + chart) + regime/margin (empty in V7).
* /api/futures/mnq               — header P&L, rolling, blotter, curve, gate perf,
  leaderboard (from the trades store; cleanup trades excluded).
* /api/futures/execution         — signal→fill through-rate from the funnel.

Read-only, stdlib only — never touches the trading path. Clean-room.
"""

from __future__ import annotations

import http.server
import json
import os
import sqlite3
import threading
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from . import pnl

_STATIC = os.path.join(os.path.dirname(__file__), "web_static")
_CT = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript",
       ".pdf": "application/pdf"}
_PARIS = ZoneInfo("Europe/Paris")
_VPP, _FEE = 2.0, 1.5
_CLEANUP = pnl._CLEANUP_REASONS  # ADOPT_FLATTEN etc. — not strategy trades


def _dq(c, show_badfill: bool = False) -> str:
    """``" AND data_quality IS NULL"`` when the column exists, else ``""``.

    ★★2026-08-13 — ONE PLACE, because six copies is how this drifted in the first place. The flag
    was added on 08-05 and fixed only in `pnl.py`; its own comment warned that "a field was added
    and the CONSUMERS were not audited", and then the same thing happened again here — SIX separate
    queries in this file read the trades table and NONE of them filtered. So the operator saw a
    correct P&L sitting above a blotter, an equity curve, a per-gate table, a router panel and a
    cube that all still contained four phantom day-rider trades worth $1,551 that never happened.
    A wrong number is bad; a right number next to a wrong one is worse, because nothing says which
    to believe.
    ⚠ Conditional on the column existing, for the same reason pnl.py is: fixtures and older
    databases build `trades` without it, and a view that throws is worse than one that over-counts.

    ★2026-08-21 TWO KINDS OF FLAG, because hiding a real trade was its own fault. On 08-21 a
    genuine round trip was labelled `EXCLUDE:` (a system-bug loss, per the operator's
    "label, never adjust" rule) and vanished from all six views — the operator watched a trade
    happen on his own account and then could not find it. `EXCLUDE:` still means GONE. `BADFILL:`
    means SHOW IT, DO NOT COUNT IT: the trade is real and the operator must see it, but its price
    came from a broken fill, so it must never reach a P&L, a curve or a gate ranking. Only the
    blotter passes `show_badfill=True`.
    """
    try:
        if any(r[1] == "data_quality" for r in c.execute("PRAGMA table_info(trades)").fetchall()):
            if show_badfill:
                return " AND (data_quality IS NULL OR data_quality LIKE 'BADFILL:%')"
            return " AND data_quality IS NULL"
    except Exception:
        pass
    return ""



def context_json(cap_path, data_dir, store_path):
    """THE METRIC STRIP + THE FOUR THINGS HE ACTUALLY TRADES ON.

    Operator, 2026-09-18: bigger chart, and around it "current rvol. atr. efficiency. session high.
    session low." plus leg state, tunnel age, position age and the next event.

    ★★★ LEG STATE IS READ FROM leg_watch's OWN LOG, NOT RE-DERIVED. The alert and the dashboard must
    never be able to disagree about whether a leg is open — two implementations of one definition is
    how this desk's numbers drift apart (the slate/SlotSpec case, the drift.ok case). The watcher is
    the single source; this reads what it wrote.
    ⚠ 24 of his 26 presses in the week to 09-18 landed INSIDE a live leg, and nothing on the
    dashboard showed it. That is why this exists.

    ⚠⚠ RVOL IS CONTRACT-BLIND AND SAYS SO. capture.db.bars stores symbol='MNQ' with NO contract
    column, so a comparison spanning a roll compares two different instruments. Build-queue item 5.
    The field carries `rvol_caveat` rather than pretending precision it does not have.
    """
    import sqlite3 as _sq
    out = {"ts": datetime.now(UTC).isoformat()}

    # ── session shape: high / low / where price sits / VWAP stretch in ATR ────────────────────
    try:
        c = _sq.connect(cap_path)
        # the CME session opens 22:00Z; anything else mixes yesterday's range into today's
        now = datetime.now(UTC)
        open_ts = int((now.replace(hour=22, minute=0, second=0, microsecond=0)
                       - timedelta(days=(0 if now.hour >= 22 else 1))).timestamp())
        r = c.execute("select min(low), max(high), sum(volume), "
                      "       sum(close*volume), sum(volume) "
                      "from bars where symbol='MNQ' and timeframe='5s' and bar_ts>=?",
                      (open_ts,)).fetchone()
        last = c.execute("select close from bars where symbol='MNQ' and timeframe='5s' "
                         "order by bar_ts desc limit 1").fetchone()
        lo, hi, vol = (r[0], r[1], r[2]) if r else (None, None, None)
        px = last[0] if last else None
        vwap = (r[3] / r[4]) if r and r[4] else None
        out["session"] = {
            "high": hi, "low": lo, "last": px,
            "pos_in_range": (round((px - lo) / (hi - lo), 3) if px and hi and lo and hi > lo else None),
            "vwap": round(vwap, 2) if vwap else None,
        }

        # ── RVOL: this hour SO FAR vs the SAME MINUTES of that hour on previous sessions ──────
        # ★★★2026-09-24 THE `frac` SCALING WAS WRONG AND THE OPERATOR CAUGHT IT FROM THE TAPE:
        # "its the us open first 15 minutes and the desk is reading between .80 and .99 during the
        # big thrusts. cant be right?" It could not, and he was right.
        #
        # The old line compared a PARTIAL hour against `base * frac` — the full-hour average scaled
        # by the fraction of the hour elapsed. That assumes volume accrues LINEARLY through the
        # hour, and the 13:00Z hour is the one hour of the day where that is most false: the cash
        # open lands at 13:30, so the hour is violently back-loaded.
        #
        # MEASURED on 51 sessions of our own 5s bars, MEDIAN cumulative share of the 13:00Z hour:
        #     13:15  actual  6.2%  · linear  26.7%  -> a NORMAL day reads 0.23x
        #     13:35  actual 37.0%  · linear  60.0%  -> a NORMAL day reads 0.62x
        #     13:40  actual 52.5%  · linear  68.3%  -> a NORMAL day reads 0.77x
        #     13:45  actual 65.6%  · linear  76.7%  -> a NORMAL day reads 0.86x
        #     13:55  actual 91.9%  · linear  93.3%  -> a NORMAL day reads 0.98x
        # So his 0.80-0.99 through the first 15 minutes of the open was a PERFECTLY ORDINARY open,
        # possibly a slightly busy one, reported as a quiet one. The meter could not have said
        # "busy" at 13:40 without the day being ~30% above normal, and it read its worst exactly
        # when he most needs it.
        #
        # ★ THE FIX REMOVES THE ASSUMPTION RATHER THAN CORRECTING IT. Compare this hour's elapsed
        # window against THE SAME ELAPSED WINDOW on previous sessions — 13:00-13:42 against
        # 13:00-13:42 — so the intraday volume shape cancels instead of being modelled. A curve
        # fitted to the shape would need re-fitting per hour, per contract and after every roll;
        # like-for-like needs nothing and cannot drift.
        # ⚠ MEDIAN, not mean: one FOMC or NFP in the 10-day baseline drags a mean upward and would
        # make every ordinary day afterwards read quiet.
        hr0 = int(now.replace(minute=0, second=0, microsecond=0).timestamp())
        elapsed = max(1, int(now.timestamp()) - hr0)
        cur = c.execute("select sum(volume) from bars where symbol='MNQ' and timeframe='5s' "
                        "and bar_ts>=?", (hr0,)).fetchone()[0] or 0
        hist = []
        for d in range(1, 11):
            a = hr0 - d * 86400
            row = c.execute("select sum(volume), count(*) from bars where symbol='MNQ' and "
                            "timeframe='5s' and bar_ts>=? and bar_ts<?", (a, a + elapsed)).fetchone()
            # ⚠ A weekend or holiday window is EMPTY, not quiet. Averaging a zero in would halve
            # the baseline every Monday and report a flat tape as a volume surge.
            if row and row[0] and row[1] >= max(1, elapsed // 5 // 2):
                hist.append(row[0])
        base = sorted(hist)[len(hist) // 2] if hist else None
        out["rvol"] = round(cur / base, 2) if base else None
        out["rvol_n_days"] = len(hist)
        out["surge"] = surge_meters(cap_path)
        out["cvd"] = cvd_meter(cap_path)
        out["rvol_caveat"] = ("this hour so far vs the SAME minutes of that hour on the last "
                              "10 sessions (median) — no linear-accrual assumption. ⚠ bars carry "
                              "no contract column, so a window spanning a roll compares two "
                              "different instruments")
        c.close()
    except Exception as e:
        out["session_error"] = f"{type(e).__name__}: {e}"

    # ── ER + ATR: reuse the EXISTING meter rather than compute a second one ───────────────────
    try:
        t = tradeability_json(cap_path)
        out["er30"] = t.get("er30")
        out["atr"] = t.get("atr")
        out["tradeability"] = {"score": t.get("score"), "label": t.get("label")}
        if out.get("session", {}).get("vwap") and out.get("session", {}).get("last") and t.get("atr"):
            out["session"]["vwap_stretch_atr"] = round(
                (out["session"]["last"] - out["session"]["vwap"]) / t["atr"], 2)
    except Exception as e:
        out["tradeability_error"] = f"{type(e).__name__}: {e}"

    # ── LEG STATE + TUNNEL AGE, from the watcher's own log ───────────────────────────────────
    try:
        import re as _re
        open_t = None; direction = None; px0 = None; last_end = None
        with open(os.path.join(data_dir, "leg_watch.log")) as fh:
            for ln in fh:
                m = _re.search(r"^(\S+) leg OPEN (UP|DOWN) from ([\d.]+)", ln)
                if m:
                    open_t = m.group(1); direction = m.group(2); px0 = float(m.group(3)); continue
                if " leg OVER" in ln:
                    last_end = ln.split(" ", 1)[0]; open_t = None
        nowt = datetime.now(UTC)
        def _age(stamp):
            return round((nowt - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() / 60)
        if open_t:
            px = out.get("session", {}).get("last")
            out["leg"] = {"open": True, "dir": direction, "age_min": _age(open_t), "from": px0,
                          "travel_pt": (round((px - px0) * (1 if direction == "UP" else -1), 1)
                                        if px else None)}
            out["tunnel_min"] = 0
        else:
            out["leg"] = {"open": False}
            out["tunnel_min"] = _age(last_end) if last_end else None
    except Exception as e:
        out["leg_error"] = f"{type(e).__name__}: {e}"

    # ── POSITION AGE. Over-8h holds are 0 winners from 4 at -$6,612 — the clock IS the guard ──
    try:
        with open(os.path.join(data_dir, "day_rider_state.json")) as fh:
            st = json.load(fh)
        if st.get("qty") and not st.get("closed") and st.get("entered_at"):
            age = (datetime.now(UTC) - datetime.fromisoformat(st["entered_at"])).total_seconds() / 60
            out["position"] = {
                "qty": st.get("qty"), "entry": st.get("entry"),
                "dir": "LONG" if (st.get("direction") or 0) > 0 else "SHORT",
                "age_min": round(age),
                # the measured buckets, so the colour means something rather than looking pretty
                "band": ("ok" if age < 180 else "long" if age < 480 else "ABANDONED"),
            }
        else:
            out["position"] = None
    except Exception as e:
        out["position_error"] = f"{type(e).__name__}: {e}"

    # ── THE SAFETY CHIP. ★★★ IT MUST NEVER GO DARK. Removing the tournament PANEL also removed
    # its fetch, and renderSafety() read STATE.tour — so the chip that says HALTED / NAKED /
    # UNVERIFIED would have sat at "SAFETY —" forever. It is GUARDED, so nothing would have thrown
    # and nothing would have complained: a safety indicator failing silently to a neutral face is
    # precisely the instrument-reports-healthy failure this desk keeps meeting. The fields move
    # here so the chip lives on the one fetch the page still makes.
    try:
        out["desk"] = (tournament_json(store_path, data_dir, cap_path) or {}).get("desk")
    except Exception as e:
        out["desk_error"] = f"{type(e).__name__}: {e}"

    # ★ LIVE BREADTH — US cash hours only. Pre-registered (data/prereg_breadth.json); it is a
    # READING, not a signal, and it reports UNAVAILABLE rather than inventing one from a stale close.
    try:
        with open(os.path.join(data_dir, "breadth.json")) as fh:
            out["breadth"] = json.load(fh)
    except Exception:
        out["breadth"] = {"available": False, "why": "no reading"}

    # ★ THE ARMED STATE MUST BE VISIBLE. A guard he cannot see is one he cannot trust, and one he
    # forgets he armed. It rides on the same fetch as everything else in the strip.
    try:
        with open(os.path.join(data_dir, "step_away.json")) as fh:
            out["step_away"] = json.load(fh)
    except Exception:
        out["step_away"] = {"armed": False}

    # ── NEXT SCHEDULED EVENT ─────────────────────────────────────────────────────────────────
    try:
        with open(os.path.join(data_dir, "event_calendar.json")) as fh:
            cal = json.load(fh)
        from zoneinfo import ZoneInfo as _Z
        nxt = None
        for e in cal.get("events", []):
            d = date.fromisoformat(e["date"])
            hh, mm = (int(x) for x in e["et_time"].split(":"))
            t = datetime(d.year, d.month, d.day, hh, mm,
                         tzinfo=_Z("America/New_York")).astimezone(UTC)
            if t > datetime.now(UTC) and (nxt is None or t < nxt[0]):
                nxt = (t, e)
        if nxt:
            out["next_event"] = {
                "name": nxt[1]["name"], "kind": nxt[1]["kind"],
                "in_hours": round((nxt[0] - datetime.now(UTC)).total_seconds() / 3600, 1),
                "utc": nxt[0].isoformat(),
                "paris": nxt[0].astimezone(_Z("Europe/Paris")).strftime("%a %d %b %H:%M"),
            }
    except Exception as e:
        out["event_error"] = f"{type(e).__name__}: {e}"
    return out


def days_json(store_path, n=14):
    """LAST N SESSIONS, LINE BY LINE — trades, profit factor, and a red/green number he can click.

    ⚠⚠ GROUPED BY ENTRY, NOT BY TRADE ROW. The rows in `trades` are scale-out EXITS of one decision
    — 20 rows over 2026-09-14/15 are 9 entries — so a per-row count overstates his activity ~2.5x.
    The drill-down shows the individual exits; the headline count is DECISIONS.
    ⚠ data_quality filtered: EXCLUDE: rows are gone, BADFILL: rows are shown in the drill and never
    counted (a real trade whose PRICE came from a fabricated fill).
    """
    import sqlite3 as _sq
    c = _sq.connect(store_path)
    c.row_factory = _sq.Row
    # ★★2026-09-23 BY closed_at, NOT opened_at — the header and this table disagreed by $330 on a
    # single carry-in trade (id 986: opened 09-22 14:33, closed 09-23 06:59, +$330), so the
    # dashboard showed 857.50 in one place and 527.50 in another. Both were defensible answers to
    # DIFFERENT questions, which is worse than one wrong number: nothing told the operator which to
    # believe, and he spent an evening doubting a book that reconciles to IBKR to the cent.
    # "Money realised on this day" is the question he is actually asking, and it is the one the
    # header already answered — so this moves to match it rather than the other way round.
    # ⚠ A trade can therefore appear under a day it was not OPENED on; the drill marks those.
    # ★★2026-09-24 `n` NOW MEANS TRADING DAYS, NOT CALENDAR DAYS. Operator: "it only shows 11
    # days. can we show the last 20? so a rolling 4 weeks?" — and he was looking at a request for
    # n=14 that returned 11, because `date('now','-14 days')` spans two WEEKENDS and a fortnight of
    # calendar is about eleven sessions. Asking for "the last 20 sessions" in calendar days is a
    # question nobody can answer in advance: it depends on holidays.
    # ⚠ So look back GENEROUSLY (n*2 days + a fortnight of slack for a holiday run) and keep the
    # most recent n days THAT ACTUALLY HAVE TRADES. The slice happens after grouping, below.
    _lookback = n * 2 + 14
    rows = [dict(r) for r in c.execute(
        "SELECT * FROM trades WHERE closed_at IS NOT NULL "
        "AND date(closed_at) >= date('now', ?) ORDER BY closed_at, id", (f"-{_lookback} days",))]
    c.close()
    by_day = {}
    for r in rows:
        d = r["closed_at"][:10]
        by_day.setdefault(d, []).append(r)
    out = []
    # ⚠ SLICE TO n SESSIONS HERE, after grouping — the SQL cannot know how many calendar days hold
    # n trading days, and guessing there is what produced the 11-for-14.
    for d in sorted(by_day, reverse=True)[:n]:
        rs = by_day[d]
        clean = [x for x in rs if not x.get("data_quality")]
        wins = [x["pnl_usd"] for x in clean if (x["pnl_usd"] or 0) > 0]
        loss = [x["pnl_usd"] for x in clean if (x["pnl_usd"] or 0) <= 0]
        entries = {(x["opened_at"], x["entry_price"], x["side"]) for x in clean}
        gross_w, gross_l = sum(wins), abs(sum(loss))
        out.append({
            "day": d,
            "pnl": round(sum(x["pnl_usd"] or 0 for x in clean), 2),
            "entries": len(entries),
            "exits": len(clean),
            "wins": len(wins), "losses": len(loss),
            "win_rate": round(len(wins) / len(clean), 3) if clean else None,
            # ⚠ PF is UNDEFINED with no losing trade — report null, never a fake infinity.
            "pf": (round(gross_w / gross_l, 2) if gross_l > 0 else None),
            "flagged": len(rs) - len(clean),
            "trades": [{
                "id": x["id"], "side": x["side"], "qty": x["qty"],
                "entry": x["entry_price"], "exit": x["exit_price"],
                "pnl": x["pnl_usd"], "opened": x["opened_at"], "closed": x["closed_at"],
                "reason": x["exit_reason"], "src": x.get("entry_source"),
                "flag": x.get("data_quality"),
                # ⚠ opened on an EARLIER day — the drill must say so or the time column lies
                "carried": x["opened_at"][:10] != x["closed_at"][:10],
            } for x in rs],
        })
    return {"days": out, "n": n, "basis": "closed_at",
            "basis_note": "money REALISED on the day — matches the header. A trade opened on an "
                          "earlier day counts on the day it closed, and is marked in the drill."}


def _status(data_dir):
    try:
        with open(os.path.join(data_dir, "status.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def _conn(path):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


# ── /api/futures/bars/<SYM> — 1m bars aggregated from 5s capture ──────────────
# ★2026-09-02 SYMBOL-AWARE. Operator: "can you add mgc to the charts tab with all the same time
# toggles? i want to watch if it behaves the same way over a few days. tunnel. run. tunnel. run."
# capture.db has carried MGC 5s bars all along (349,470 rows); only this reader was hard-wired.
# ⚠ THE SYMBOL IS WHITELISTED, NOT INTERPOLATED. It arrives from the URL path, and the one thing
#   a URL segment may never do is reach a SQL string. Unknown symbol -> MNQ, never a query.
# ⚠ MD_STREAM/capture.db ARE MULTI-SYMBOL and every consumer must filter — folding MGC into an MNQ
#   reader once made ATR read 1848 against a true 15 and opened live trades with $3,700 stops. The
#   filter here is the `symbol = ?` bind; the FRONT-END half of the same rule (MNQ vwap/fills/ATR
#   must not be drawn over a gold chart) is enforced in app.js renderHero().
BAR_SYMBOLS = ("MNQ", "MGC")


def bars_json(cap_path, count, symbol="MNQ"):
    symbol = symbol.upper() if isinstance(symbol, str) else ""
    if symbol not in BAR_SYMBOLS:
        symbol = "MNQ"
    out = []
    try:
        c = _conn(cap_path)
        rows = c.execute(
            "SELECT bar_ts, close FROM bars WHERE symbol = ? AND timeframe='5s' "
            "ORDER BY bar_ts DESC LIMIT ?", (symbol, count * 12 + 24),
        ).fetchall()
        c.close()
        by_min = {}
        for r in rows:  # desc → first close seen for a minute is its latest 5s close
            m = (r["bar_ts"] // 60) * 60
            by_min.setdefault(m, r["close"])
        for m in sorted(by_min)[-count:]:
            out.append({"ts": datetime.fromtimestamp(m, UTC).isoformat(), "close": by_min[m]})
    except Exception:
        pass
    # `symbol` is echoed so the client can PROVE what it is drawing rather than assume the request
    # it sent is the one it got back — a chart that silently falls back to MNQ while the toggle
    # reads MGC is the worst outcome available here.
    return {"symbol": symbol, "bars": out}


def _mae_table():
    try:
        with open("/home/alphabot/gazbot7/data/mae_percentiles.json") as fh:
            return json.load(fh)
    except Exception:
        return {}


def session_block(now=None) -> dict:
    """Which block are we in, and what has it been worth? Measured, not asserted.

    Numbers are the desk's own shadow book (session.py, n=6,324 MNQ sims) — the unconfounded
    counterfactual, because the shadow fires whether or not a gate is benched.
    """
    now = now or datetime.now(UTC)
    h = now.hour
    if h < 7:
        return {"block": "ASIA", "utc": "00:00-07:00", "edge_per_trade": -3.17, "n": 1840,
                "note": "worst block by a distance — ENTRIES ARE CONFIG-BLOCKED", "tradeable": False}
    if h < 13 or (h == 13 and now.minute < 30):
        return {"block": "LONDON", "utc": "07:00-13:30", "edge_per_trade": 0.70, "n": 1516,
                "note": "the only positive block the desk has", "tradeable": True}
    if h < 21:
        return {"block": "US", "utc": "13:30-21:00", "edge_per_trade": -1.93, "n": 2394,
                "note": "biggest moves and the biggest drawdowns", "tradeable": True}
    return {"block": "POST", "utc": "21:00-24:00", "edge_per_trade": -3.62, "n": 574,
            "note": "halt + thin reopen", "tradeable": False}


def vwap_stretch(cap_path) -> dict:
    """How far price is from VWAP, in points AND in ATR.

    ★ The 2026-08-20 measurement is carried with the number so it cannot drift from its evidence:
    buying MORE THAN 100pt BELOW VWAP with a +25pt target and a ~75pt stop won 90.6-94.5% across
    every block tested. IN-SAMPLE, one instrument, not split by year — context for a discretionary
    entry, never an instruction. Above VWAP is NOT the mirror of that result; it was not measured.
    """
    f = _features(cap_path) or {}
    last, vw = f.get("last"), f.get("vwap")
    if last is None or vw is None:
        return {"ok": False}
    pt = round(last - vw, 2)
    atr = f.get("atr_pts") or 0
    band = ("stretched BELOW" if pt <= -100 else "below" if pt < 0
            else "stretched ABOVE" if pt >= 100 else "above")
    return {"ok": True, "pt": pt, "atr_mult": round(pt / atr, 2) if atr else None,
            "vwap": vw, "band": band,
            "measured": ("below -100pt: +25pt target won 90.6-94.5% (2026-08-20, in-sample)"
                         if pt <= -100 else None)}


def adverse_meter(data_dir, cap_path) -> dict:
    """For an OPEN position: how far against, how long held, and how unusual that is.

    The operator holds naked and manages by hand, so mid-trade the question is never "am I down"
    but "is this NORMAL down or one of the bad ones". Answered against the measured distribution in
    data/mae_percentiles.json, bucketed by MINUTES HELD — an unconditioned distribution calls almost
    every short-trade drawdown normal and is worse than no meter at all.
    """
    try:
        st_ = json.load(open(os.path.join(data_dir, "day_rider_state.json")))
    except Exception:
        return {"ok": False}
    if not st_.get("entered") or st_.get("closed") or not (st_.get("qty") or 0):
        return {"ok": False, "flat": True}
    f = _features(cap_path) or {}
    last, entry = f.get("last"), st_.get("entry")
    d = 1 if (st_.get("direction") or 1) > 0 else -1
    if last is None or not entry:
        return {"ok": False}
    adverse = round(max(0.0, -(last - entry) * d), 1)
    try:
        held = int((datetime.now(UTC)
                    - datetime.fromisoformat(st_["entered_at"])).total_seconds() // 60)
    except Exception:
        held = 0
    blk = session_block()["block"]
    tab = _mae_table().get("blocks", {}).get(blk, {})
    bucket = next((k for k in ("15", "30", "60", "120") if held <= int(k)), "flat")
    ref = tab.get(bucket, {}).get("pt", {})
    pct = None
    if ref:
        pct = 0
        for p in sorted(ref, key=lambda x: int(x)):
            if adverse >= ref[p]:
                pct = int(p)
    return {"ok": True, "adverse_pt": adverse, "adverse_usd": round(adverse * 2.0 * abs(st_["qty"]), 2),
            "held_min": held, "block": blk, "bucket": bucket, "percentile": pct,
            "median": ref.get("50"), "p90": ref.get("90"),
            "n": tab.get(bucket, {}).get("n")}


# ── CUMULATIVE DELTA ─────────────────────────────────────────────────────────────────────────────
# ★★★2026-09-24. Operator, on the 30s FLOW meter: "its essentially 30 seconds delayed? so the tape
# has already done the corresponding move? if so its useless."
# He was wrong about the delay and RIGHT about the uselessness, for a better reason than he gave.
# A 30s WINDOW is not a 30s DELAY — it ends NOW, and its newest trade is ~0.3s old. But MEASURED
# over 6h of tape, an episode of |flow|>=0.20 has a MEDIAN LIFE OF 3 SECONDS (75th pct 9s, only 7%
# last past 30s, NONE past 60s). The thing being averaged lives three seconds and the average is
# thirty seconds long, so by the time a burst fills the window it is over. That is not stale DATA,
# it is a stale QUESTION — and shortening the window would only make it flicker on 3-second noise.
#
# ★ CVD IS THE INSTRUMENT THAT ANSWERS WHAT HE ACTUALLY ASKED. An average FORGETS; a running total
# does not. Sustained pressure shows as a line that climbs all session instead of a burst that
# evaporates in three seconds.
#
# ⚠⚠ AND THE CORRELATION IS NOT THE POINT — IT IS VERY NEARLY A TAUTOLOGY. Aggressive buying is
# largely WHAT MOVES PRICE, so CVD tracking the session's move (+0.98 over 5 sessions) says almost
# nothing. The value is entirely in the DIVERGENCE: 2026-09-18 closed +140.75pt on NEGATIVE
# cumulative delta — price rising while nobody was lifting offers. That is the row worth having.
#
# ⚠⚠⚠ PERFORMANCE IS A CORRECTNESS ISSUE HERE. A full-session scan is 994,537 ticks and MEASURED
# 112-154ms, growing all session, against a page that polls every ONE SECOND. Doing that per
# request would burn a seventh of a core continuously and block the handler that also serves his
# FLATTEN button. So the total is INCREMENTAL: each call sums only the ticks newer than the last
# one it saw, which is typically a single second of tape.
# ⚠ ThreadingHTTPServer — concurrent requests WOULD double-count an increment without the lock.
CVD_WINDOW_MIN = int(os.environ.get("CVD_WINDOW_MIN", "180"))   # rolling 3h — see the note below
_CVD_LOCK = threading.Lock()
_CVD: dict = {}


def cvd_meter(cap_path) -> dict:
    """Session cumulative delta + a divergence flag. Incremental, thread-safe, fail-quiet."""
    out = {"cvd": None, "divergence": None, "open": True}
    try:
        from .session import is_open as _is_open
        now = datetime.now(UTC)
        if not _is_open(now):
            out["open"] = False
            return out
        # ★ SAME session anchor as the session high/low/VWAP already on this page (22:00Z).
        #   A second definition of "today" on one dashboard is how the header and the day table
        #   came to disagree by $330 and cost him an evening of doubting a correct book.
        op = int((now.replace(hour=22, minute=0, second=0, microsecond=0)
                  - timedelta(days=(0 if now.hour >= 22 else 1))).timestamp()) * 1000
        with _CVD_LOCK:
            st = _CVD.get(op)
            if st is None:
                _CVD.clear()                      # a new session; never accumulate across the roll
                # ★★★2026-09-25 THE RANGE IS NOW A ROLLING WINDOW, NOT THE WHOLE SESSION.
                # Operator: "are the bottom and top range numbers on the cvd horizontal chart
                # changing? theyve been the same since i woke up this morning."
                # They were changing correctly — they simply had not been exceeded. The CVD high was
                # set at 00:26Z and the low at 05:25Z, and he was reading them at 09:46Z. TWO REAL
                # FAULTS behind that:
                #   1. a session-anchored range spans up to 24h, so by the US open he would be
                #      measuring position against overnight ASIA extremes that have nothing to do
                #      with the tape in front of him;
                #   2. THE RANGE ONLY EVER GROWS. It never shrinks, so the gauge gets progressively
                #      DULLER through the session — everything compresses toward the middle, and a
                #      meter that quietly loses resolution as the day goes on is worse than one
                #      that is obviously broken.
                # ⚠ THE CVD *LEVEL* STAYS SESSION-CUMULATIVE — that is the meaning he has learned
                #   ("net aggression since 22:00Z"). Only the SCALE it is placed on rolls. Making
                #   the level roll too would silently redefine the number under him.
                st = {"last": op - 1, "cvd": 0.0, "series": []}
                _CVD[op] = st
            c = _conn(cap_path)
            rows = c.execute(
                "SELECT ts_ms, size, aggressor FROM ticks WHERE symbol='MNQ' AND ts_ms>? "
                "AND ts_ms<=? ORDER BY ts_ms", (st["last"], int(now.timestamp() * 1000))).fetchall()
            for r in rows:
                a = r["aggressor"]
                # ⚠ 'neutral' contributes NOTHING — it is 13% of the tape and nobody crossed the
                #   spread for it. Counting it either way invents pressure that did not exist.
                if a == "buy":
                    st["cvd"] += r["size"]
                elif a == "sell":
                    st["cvd"] -= r["size"]
                else:
                    continue
                # ⚠ ONE POINT PER MINUTE ON THE RUNNING TOTAL — not per tick (memory) and not the
                #   increments (max of those is the biggest single trade, a useless number).
                mm = r["ts_ms"] // 60000
                if st["series"] and st["series"][-1][0] == mm:
                    st["series"][-1][1] = st["cvd"]
                else:
                    st["series"].append([mm, st["cvd"]])
            if rows:
                st["last"] = rows[-1]["ts_ms"]
            # ⚠ TRIM AFTER APPENDING, so a cold start that replayed the whole session does not
            #   carry a 24h curve forever. The window is the SCALE, not the memory.
            cut = (int(now.timestamp()) // 60) - CVD_WINDOW_MIN
            st["series"] = [x for x in st["series"] if x[0] >= cut]
            # ⚠ THE PRICE RANGE ROLLS TOO, over the SAME window. Two scales measured over
            #   different spans cannot be compared, and comparing them IS the divergence.
            win0 = int(now.timestamp()) - CVD_WINDOW_MIN * 60
            px = c.execute("SELECT MIN(low) lo, MAX(high) hi, "
                           "(SELECT close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
                           " AND bar_ts>=? ORDER BY bar_ts DESC LIMIT 1) last "
                           "FROM bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>=?",
                           (win0, win0)).fetchone()
            c.close()
            out["cvd"] = int(st["cvd"])
            out["window_min"] = CVD_WINDOW_MIN
            vals = [x[1] for x in st["series"]] or [st["cvd"]]
            out["cvd_hi"], out["cvd_lo"] = int(max(vals)), int(min(vals))
            st["hi"], st["lo"] = max(vals), min(vals)
            # ── THE DIVERGENCE FLAG ──────────────────────────────────────────────────────────
            # ★ Compare WHERE PRICE SITS IN ITS SESSION RANGE against WHERE CVD SITS IN ITS OWN.
            #   Both are 0..1, so the comparison is scale-free and needs no tuned point threshold.
            #   Price near its high on aggression that is NOT near its high = the move is not being
            #   paid for. ⚠ DESCRIPTIVE. It says the two disagree; it does not say which one wins,
            #   and on this desk every direction study of a disagreement has come back a coin.
            if px and px["hi"] is not None and px["lo"] is not None and px["last"] is not None \
                    and px["hi"] > px["lo"] and st["hi"] > st["lo"]:
                pr = (px["last"] - px["lo"]) / (px["hi"] - px["lo"])
                cr = (st["cvd"] - st["lo"]) / (st["hi"] - st["lo"])
                out["px_pos"], out["cvd_pos"] = round(pr, 3), round(cr, 3)
                if pr >= 0.85 and cr <= 0.50:
                    out["divergence"] = "bearish"     # price at highs, buyers not paying for it
                elif pr <= 0.15 and cr >= 0.50:
                    out["divergence"] = "bullish"     # price at lows, sellers not pressing it
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def surge_meters(cap_path) -> dict:
    """PULSE and FLOW — "is the surge in front of me BACKED, and is it REAL?" (2026-09-24)

    Operator, after RVOL was fixed and still read ~1.0 through a thrusty open: "i feel like i need
    1 and 2. shows me if a surge is backed and real."

    ★★★ WHY THESE TWO AND NOT ANOTHER RVOL. RVOL asks "unusual FOR THIS TIME OF DAY", so it sits at
    ~1.0 through every open by construction — the open is the most stereotyped part of the session
    and today's thrusts are being compared with other days' thrusts. It can never answer "is this
    move backed", because that is a question about NOW versus the MINUTES BEFORE IT, not about
    today versus other days.

      PULSE — this minute's volume / the MEDIAN of the previous 15 minutes OF THIS SESSION.
              ★ No cross-day baseline at all, so the Sep->Dec roll that is currently dragging
                RVOL's 10-day median cannot touch it. `bars` has no contract column and this is
                the meter that does not care.
              ⚠ MEDIAN, not mean: one spike minute inside the lookback would raise the bar and
                hide the very expansion the meter exists to show.
      FLOW  — (buy - sell) / (buy + sell) by AGGRESSOR over the last 2 minutes, -1..+1.
              ⚠⚠ `neutral` is 13% of the tape and is EXCLUDED, never split. Assigning it pro-rata
                would manufacture imbalance out of trades nobody lifted or hit.

    ⚠⚠⚠ DESCRIPTIVE, NEVER PREDICTIVE — and the UI says so in its own tooltip. MEASURED on the 5
    sessions of tick data we retain (170 surges at the 90th-percentile 1-min move, 12.5pt):
        BACKED   (pulse>=1.5, flow aligned)  median +5.25pt over the next 5 min, 57.5% extended
        unbacked (pulse<1.5,  flow aligned)  median +0.50pt,                     51.5% extended
        flow OPPOSING the move               median -1.12pt,                     45.5% extended
    That ORDERS correctly, and it is NOT A RESULT: 5 sessions, and minutes inside a session are
    not independent draws. This desk's own history says a 57% hit rate on n=80 clustered in 5 days
    is where direction studies come to die. PROMISING, not proven.

    ⚠ IT CANNOT BE SETTLED RETROSPECTIVELY. `ticks` is pruned at 5 DAYS, so there is no history to
    widen the study with — the readings must be LOGGED FORWARD or the question stays open forever.
    That is what `data/surge_log.jsonl` is for.
    """
    out = {"pulse": None, "flow": None, "flow_n": 0, "pulse_base": None, "open": True}
    try:
        from .session import is_open as _is_open
        now = datetime.now(UTC)
        if not _is_open(now):
            out["open"] = False
            return out
        c = _conn(cap_path)
        t1 = int(now.timestamp())
        # ── PULSE — a ROLLING 60s WINDOW ENDING NOW, not the last completed minute ────────────
        # ★★★2026-09-24, SECOND FIX, and the operator spotted it from the tape again: "flow was -17
        # or so for a while and pulse 1.60 and tape shot south... is it live or will it be delayed?"
        # It was delayed. The first version read the last COMPLETED minute, so between :00 and :59
        # it showed a number that never moved. MEASURED live over 48 seconds:
        #     14:59:59  block 0.95   rolling 0.90
        #     15:00:15  block 0.95   rolling 1.06
        #     15:00:31  block 0.95   rolling 1.29
        #     15:00:39  block 0.95   rolling 1.33
        # Frozen at 0.95 for forty seconds while volume was genuinely expanding — the meter was
        # blind for most of every minute, and worst right after a minute boundary, which is where
        # a surge is most likely to begin.
        # ⚠ THE ORIGINAL REASON FOR THE BLOCK WAS SOUND and must not be lost: a PARTIAL minute
        # compared against a full-minute baseline reads low, which is exactly the linear-accrual
        # error fixed in RVOL this morning. A ROLLING 60s window keeps that property — it is always
        # a full minute of tape — while ending NOW instead of at the last boundary.
        # ⚠ Staleness is now one 5s bar period (~6s measured), not up to 60s. Ticks land ~0.3s
        # behind; 5s bars are only written when the bar closes, and that is the floor here.
        # ⚠⚠ THE LOGGER (surge_log.py) DELIBERATELY KEEPS THE MINUTE-BLOCK FORM. A dataset wants
        # clean, non-overlapping minute boundaries; a meter wants to be current. They agree exactly
        # at a boundary, which is where the logger samples, so the pre-registration is unaffected.
        cur = c.execute("SELECT COALESCE(SUM(volume),0) v FROM bars WHERE symbol='MNQ' AND "
                        "timeframe='5s' AND bar_ts>=? AND bar_ts<?", (t1 - 60, t1)).fetchone()["v"]
        prev = []
        for k in range(1, 16):
            v = c.execute("SELECT COALESCE(SUM(volume),0) v FROM bars WHERE symbol='MNQ' AND "
                          "timeframe='5s' AND bar_ts>=? AND bar_ts<?",
                          (t1 - (k + 1) * 60, t1 - k * 60)).fetchone()["v"]
            if v > 0:
                prev.append(v)
        if len(prev) >= 8:
            base = sorted(prev)[len(prev) // 2]
            if base:
                out["pulse"] = round(cur / base, 2)
                out["pulse_base"] = int(base)
        out["pulse_window"] = "rolling 60s ending now"
        # ── FLOW ─────────────────────────────────────────────────────────────────────────────
        # ★★2026-09-24 WINDOW 120s -> 30s, at the operator's request: "could we do 30 seconds for
        # flow instead of a minute. thats still decent smoothing at that granularity."
        # ⚠ It was 120s, not 60 — so this is a FOUR-fold cut, and on its own it would have made the
        # cell strobe. MEASURED over 6h of tick tape, colour changes per hour at a hard ±0.15:
        #     120s -> 83/hr (one every 43s)   60s -> 156/hr (23s)   30s -> 328/hr (ELEVEN SECONDS)
        # A cell that changes colour every 11 seconds is wallpaper, and wallpaper is how this desk
        # loses an instrument. So the window shortens AND the colour gains HYSTERESIS (enter at
        # ±0.20, leave at ±0.12, applied in app.js where the poll-to-poll state lives):
        #     30s + hysteresis -> 147/hr (25s)     45s + hysteresis -> 83/hr, TODAY'S EXACT RATE
        # He asked for 30s and gets 30s; FLOW_WINDOW_S makes 45 a one-line change if the movement
        # turns out to be more than he wants. The NUMBER is raw and responds at full speed — only
        # the COLOUR is damped, because the colour is the thing that catches the eye from across
        # a room and the number is the thing he reads deliberately.
        _fw = int(os.environ.get("FLOW_WINDOW_S", "30"))
        out["flow_window_s"] = _fw
        r = c.execute("SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size END),0) b, "
                      "COALESCE(SUM(CASE WHEN aggressor='sell' THEN size END),0) s, "
                      "COUNT(*) n FROM ticks WHERE symbol='MNQ' AND ts_ms>=?",
                      ((t1 - _fw) * 1000,)).fetchone()
        tot = (r["b"] or 0) + (r["s"] or 0)
        if tot:
            out["flow"] = round(((r["b"] or 0) - (r["s"] or 0)) / tot, 2)
            out["flow_n"] = int(r["n"])
        c.close()
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def rvol(cap_path, window_min: int = 30, lookback: int = 5) -> dict:
    """RELATIVE VOLUME, normalised BY TIME OF DAY. Operator asked for RVOL back on the dashboard.

    ★ WHY TIME-OF-DAY AND NOT A FLAT AVERAGE. MNQ volume has an enormous intraday shape — the 13:30Z
    cash open is many times any London hour. Divide by the day's mean and the meter reads "hot"
    every single day at 13:30 and "cold" every night, which is a clock, not information. So the
    baseline for the last `window_min` is the SAME clock window on each of the previous sessions,
    and the reading answers the only question worth asking: is there more going on right now than
    there normally is AT THIS TIME OF DAY?

    Returns {rvol, now, baseline, n_days, window_min} — n_days is exposed because a reading built on
    one comparison day is not the same claim as one built on five, and the UI must be able to say so.
    """
    out = {"rvol": None, "now": None, "baseline": None, "n_days": 0,
           "window_min": window_min, "open": True}
    try:
        # ★ A SHUT VENUE IS NOT A QUIET ONE. Without this the meter reads a confident 0.00x all
        # weekend, which looks like a measurement of the tape rather than an absence of tape.
        from .session import is_open as _is_open
        if not _is_open(datetime.now(UTC)):
            out["open"] = False
            return out
        c = _conn(cap_path)
        now = datetime.now(UTC)
        t1 = int(now.timestamp()); t0 = t1 - window_min * 60
        cur = c.execute("SELECT COALESCE(SUM(volume),0) v FROM bars WHERE symbol='MNQ' AND "
                        "timeframe='5s' AND bar_ts>=? AND bar_ts<?", (t0, t1)).fetchone()["v"]
        base = []
        for d in range(1, lookback + 1):
            a, b = t0 - d * 86400, t1 - d * 86400
            v = c.execute("SELECT COALESCE(SUM(volume),0) v, COUNT(*) n FROM bars WHERE "
                          "symbol='MNQ' AND timeframe='5s' AND bar_ts>=? AND bar_ts<?",
                          (a, b)).fetchone()
            # a weekend/holiday window is EMPTY, not quiet — excluded, never averaged in as a zero
            if v["n"] >= window_min * 6 and v["v"] > 0:
                base.append(v["v"])
        c.close()
        if base:
            med = sorted(base)[len(base) // 2]
            out.update(rvol=round(cur / med, 2) if med else None, now=int(cur),
                       baseline=int(med), n_days=len(base))
        else:
            out["now"] = int(cur)
    except Exception:
        pass
    return out


def _features(cap_path):
    """last / vwap / atr_pct / net_atr + the chart-read numbers (ATR in pts+$, its violence
    bucket, and the ~30-min efficiency ratio + trend/chop label) — so the cockpit shows AT A
    GLANCE how big (ATR) and how clean (ER) the tape is."""
    try:
        from .deciders import Bar, compute_features
        c = _conn(cap_path)
        rows = list(reversed(c.execute(
            "SELECT bar_ts, open, high, low, close, volume FROM bars "
            "WHERE symbol='MNQ' AND timeframe='5s' ORDER BY bar_ts DESC LIMIT 360"   # 30 min
        ).fetchall()))
        c.close()
        if len(rows) < 6:
            return None
        # Aggregate the 5s bars → 1-MINUTE OHLC — the SAME basis the gates + hour_watch use, so the
        # ribbon's ATR + violence match the ATR floors and the Telegram (2026-07-23). A 5s-bar ATR
        # reads ~4x smaller (~2.9 vs the ~12-23 the gate sees), which made a floor like 20 look
        # impossible on the chart. ER already used 1-min closes and is unchanged.
        agg: dict = {}
        for r in rows:
            m = (r["bar_ts"] // 60) * 60
            a = agg.get(m)
            if a is None:
                agg[m] = [r["open"], r["high"], r["low"], r["close"], r["volume"]]
            else:
                a[1] = max(a[1], r["high"])
                a[2] = min(a[2], r["low"])
                a[3] = r["close"]
                a[4] += r["volume"]
        bars = [Bar(m, *agg[m]) for m in sorted(agg)]
        if len(bars) < 6:
            return None
        f = compute_features(bars)   # 1-min ATR/VWAP — matches the live gate + hour_watch
        atr_pts = round(f.atr, 1)
        # ER over the 30-min 1-min closes (net progress / total distance walked) — unchanged, correct
        cl = [b.close for b in bars]
        er = day_type = None
        if len(cl) >= 6:
            total = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1
            er = round(abs(cl[-1] - cl[0]) / total, 2)
            day_type = "trend" if er >= 0.18 else "chop" if er < 0.08 else "mixed"
        violence = ("asleep" if atr_pts < 3 else "calm" if atr_pts < 8 else "normal"
                    if atr_pts < 16 else "elevated" if atr_pts < 28 else "violent")
        return {"last": rows[-1]["close"], "vwap": round(f.vwap, 2),
                "atr_pct": round(f.atr_pct * 100, 3), "net_atr": round(f.net_atr_5, 2),
                "atr_pts": atr_pts, "atr_usd": round(atr_pts * _VPP), "violence": violence,
                "er": er, "day_type": day_type}
    except Exception:
        return None


# ── /api/futures/us-terminal — holdings + activity ────────────────────────────
def us_terminal_json(cap_path, data_dir):
    from . import session
    st = _status(data_dir)
    f = _features(cap_path) or {}
    now = datetime.now(UTC)
    activity = {
        "symbol": "MNQ", "label": "MNQ", "is_known": bool(f),
        "session_active": session.is_open(now),
        "state": "live" if session.is_open(now) else "closed",
        "last": f.get("last"), "vwap": f.get("vwap"), "atr_pct": f.get("atr_pct"),
        "net_atr": f.get("net_atr"), "atr_pts": f.get("atr_pts"), "atr_usd": f.get("atr_usd"),
        "violence": f.get("violence"), "er": f.get("er"), "day_type": f.get("day_type"), "gates": [],
    }
    # position is now the multi-slot tournament shape — a LIST of open slots (one per gate).
    # Tolerate the legacy single-position dict too (so a revert to core+strategy still renders).
    raw = st.get("position")
    if isinstance(raw, list):
        slots = raw
    elif isinstance(raw, dict) and not raw.get("flat"):
        slots = [raw]
    else:
        slots = []
    prot_by_gate = {s.get("gate"): s for s in ((st.get("protection") or {}).get("slots") or [])}
    last_px = f.get("last")
    holdings = []
    for s in slots:
        entry = s.get("entry_price") or s.get("entry") or s.get("avg")
        if entry is None:
            continue
        side = s.get("side") or ("SHORT" if (s.get("qty") or 0) < 0 else "LONG")
        qty = abs(s.get("qty") or 1)
        last = last_px or entry
        sign = 1 if side == "LONG" else -1
        gate = s.get("gate", "—")
        held_s = None
        if s.get("opened_at"):
            try:
                held_s = (now - datetime.fromisoformat(s["opened_at"])).total_seconds()
            except (ValueError, TypeError):
                held_s = None
        holdings.append({
            "label": "MNQ", "symbol": "MNQ", "side": side, "qty": qty,
            "avg": entry, "stop": s.get("stop_price") or s.get("stop"), "last": last,
            "multiplier": _VPP, "pnl_usd": round(sign * (last - entry) * _VPP * qty, 2),
            "pnl_pct": round(sign * (last - entry) / entry * 100, 3) if entry else None,
            "entry_gate": gate, "opened_at": s.get("opened_at"), "held_seconds": held_s,
            "protected": bool(prot_by_gate.get(gate, s).get("stop_coid")),
        })
    # ★★2026-08-07 THE DAY RIDER IS A SECOND DESK AND WAS INVISIBLE HERE.
    # This window is built from the TOURNAMENT's status.json, so a day-rider position — its own
    # service, its own clientId 4, same account and same symbol — rendered nowhere at all. On 08-07
    # it held SHORT 2 @ 29567.25, ~150pt offside, while every screen the operator had showed "flat".
    # A live position with no surface is exactly how the 08-06 incident stayed invisible for hours.
    # It reports under gate `day_rider`. Fail-soft: on any error the window renders the tournament
    # rows exactly as before, so a bad state file can never blank the holdings panel.
    try:
        with open(os.path.join(data_dir, "day_rider_state.json")) as fh:
            dr = json.load(fh)
        if dr.get("entered") and not dr.get("closed"):
            entry = float(dr.get("entry") or 0.0)
            qty = abs(float(dr.get("qty") or 0.0))
            direction = int(dr.get("direction") or 0)
            if entry > 0 and qty > 0 and direction in (-1, 1):
                last = last_px or entry
                # the ARMED trail is the live protection; the 600pt venue stop is last-resort only
                stop = dr.get("trail") or dr.get("venue_stop")
                holdings.append({
                    "label": "MNQ", "symbol": "MNQ",
                    "side": "LONG" if direction > 0 else "SHORT", "qty": qty,
                    "avg": entry, "stop": stop, "last": last, "multiplier": _VPP,
                    "pnl_usd": round(direction * (last - entry) * _VPP * qty, 2),
                    "pnl_pct": round(direction * (last - entry) / entry * 100, 3),
                    "entry_gate": "day_rider",
                    "opened_at": None, "held_seconds": None,
                    # an UNARMED trail is not protection — say so honestly rather than let the
                    # 600pt insurance stop render as if it were a working protective stop.
                    "protected": bool(dr.get("trail")),
                    # ★2026-08-20 the DESK ladder panel needs to know which lots are already out,
                    # so a banked rung renders BANKED instead of offering a button that the
                    # endpoint would only reject. Empty list degrades safely: every button shows,
                    # and dayrider_claim_post still refuses a lot that is gone.
                    "targets_done": list(dr.get("targets_done") or []),
                    "lots_open": dr.get("lots_open"),
                })
    except Exception:
        pass

    return {"holdings": holdings, "activity": [activity], "regime_groups": {},
            "stayout": stayout_meters(cap_path), "rvol": rvol(cap_path), "block": session_block(),
            "surge": surge_meters(cap_path), "vwap_stretch": vwap_stretch(cap_path), "adverse": adverse_meter(data_dir, cap_path),
            "margin_deployed_usd": None, "nlv_usd": None}


# ── /api/futures/mnq — header / rolling / blotter / curve / gates ──────────────
def _strategy_trades(c, since_iso=None):
    """Today's real trades. Feeds the BLOTTER, the equity CURVE and the per-GATE table.

    ★★2026-08-13 — EXCLUDE data_quality-flagged rows HERE TOO. `pnl.py` learned this on 08-05 and
    its own comment names the trap: "a field was added and the CONSUMERS were not audited". The fix
    went into the P&L source and stopped there, so this function — a completely separate query —
    kept returning flagged rows. Operator, the same day the rider booked four phantom trades:
    "the trades list is still showing those erroneous day trade trades."
    He was reading a correct P&L above a blotter full of trades that never happened, which is worse
    than either being wrong alone: the numbers disagree and neither says why.
    It is not only the blotter — `curve` and `gate_perf` are built from these rows, so the equity
    line and every per-gate stat carried the $1,551 of fictitious profit as well.
    ⚠ Tolerates the column being absent, for exactly the reason pnl.py does: adding the clause
    unconditionally broke 8 tests whose fixtures build `trades` without it, and would equally break
    a fresh deployment or an older database. A view that throws is worse than one that over-counts.
    """
    ph = ",".join("?" * len(_CLEANUP))
    q = (f"SELECT closed_at, side, gate, exit_reason, pnl_usd, entry_price, exit_price, qty "
         f"FROM trades WHERE symbol='MNQ' AND exit_reason NOT IN ({ph})")
    # ★2026-08-21 STAYS STRICT. These rows feed the curve, the gate table, the leaderboard, the
    # loss buckets and two more panels — a BADFILL row here would re-enter five P&L surfaces at
    # once. The blotter has its own query (`_blotter_rows`) precisely so "show it" cannot leak
    # into "count it".
    q += _dq(c)
    args = list(_CLEANUP)
    if since_iso:
        q += " AND closed_at>=?"
        args.append(since_iso)
    q += " ORDER BY closed_at"
    return c.execute(q, args).fetchall()


def _blotter_rows(c, since_iso=None):
    """Rows for the DISPLAY blotter only — includes `BADFILL:` trades, flagged.

    ★2026-08-21 A trade the operator watched happen must be visible even when its price is
    unusable. `_strategy_trades` stays strict so no P&L surface can ever see these; this is the one
    query that shows them, and it carries `data_quality` so the UI can mark the row as uncounted.
    """
    ph = ",".join("?" * len(_CLEANUP))
    q = (f"SELECT closed_at, side, gate, exit_reason, pnl_usd, entry_price, exit_price, qty, "
         f"data_quality FROM trades WHERE symbol='MNQ' AND exit_reason NOT IN ({ph})")
    q += _dq(c, show_badfill=True)
    args = list(_CLEANUP)
    if since_iso:
        q += " AND closed_at>=?"
        args.append(since_iso)
    q += " ORDER BY closed_at"
    return c.execute(q, args).fetchall()


def _gate_groups(rows):
    g = {}
    for r in rows:
        k = ((r["gate"] or "—"), r["side"])
        d = g.setdefault(k, {"gate": k[0], "side": k[1], "n": 0, "w": 0, "gw": 0.0, "gl": 0.0, "net": 0.0})
        d["n"] += 1
        d["net"] += r["pnl_usd"]
        if r["pnl_usd"] > 0:
            d["w"] += 1; d["gw"] += r["pnl_usd"]
        else:
            d["gl"] += -r["pnl_usd"]
    out = []
    for d in g.values():
        out.append({"gate": d["gate"], "side": d["side"], "n": d["n"],
                    "win_pct": round(100 * d["w"] / d["n"]) if d["n"] else None,
                    "pf": round(d["gw"] / d["gl"], 2) if d["gl"] > 1e-9 else None,
                    "net": round(d["net"], 2)})
    out.sort(key=lambda x: x["net"], reverse=True)
    return out


def mnq_json(store_path):
    now = datetime.now(UTC)
    out = {"expiry": "SEP26", "fee_per_rt": _FEE, "header": {}, "rolling": {},
           "blotter": [], "curve": [], "gate_perf": [], "leaderboard": {"top": [], "bottom": []},
           "long_short": [], "loss_buckets": [], "drill": {}, "ratchet": None,
           "contracts_cap_aggregate": None}
    try:
        c = _conn(store_path)
        # ★2026-08-11 desk="tournament" so this header keeps the meaning it has always had.
        # The day rider started writing trade rows today; folding them in would silently change
        # the number the operator reads as "the desk's day" without him asking for it. The
        # rider's own position and P&L surface separately in HOLDINGS.
        today, n_today, wins = pnl.day(c, "MNQ", now, desk="tournament")
        # ★★2026-08-13 (operator): "we watch the day rider holding but then it doesnt show in any
        # daily p&l. there should be a tourn p&l, day rider p&l and a total desk p&l."
        # He is right, and the strip was worse than merely incomplete — it was INCONSISTENT:
        # `today` was tournament-only (deliberately, 08-11) while `yest`/`d7`/`d30` were and remain
        # UNFILTERED, i.e. both desks. So TODAY and 7D silently measured different things and the
        # comparison across the strip was meaningless.
        # Fixed by publishing the split explicitly instead of picking one meaning. `today` KEEPS its
        # tournament-only meaning so no existing consumer shifts under it (the P&L strip parse is
        # pinned in memory as header.today); the UI reads the new fields.
        # The week that prompted this: tournament −$438, day-rider +$1,183.50 — one number could
        # not have told him the desk was losing while the rider carried it.
        today_rider, n_rider, _ = pnl.day(c, "MNQ", now, desk="day_rider")
        today_total = round(today + today_rider, 2)
        d7, _, _ = pnl.realized(c, "MNQ", since_iso=(now - timedelta(days=7)).isoformat())
        d30, _, _ = pnl.realized(c, "MNQ", since_iso=(now - timedelta(days=30)).isoformat())
        y0 = pnl.paris_day_start_utc(now - timedelta(days=1))
        t0 = pnl.paris_day_start_utc(now)
        yest = round(sum(r["pnl_usd"] for r in c.execute(
            "SELECT pnl_usd FROM trades WHERE symbol='MNQ' AND closed_at>=? AND closed_at<? "
            "AND exit_reason NOT IN (" + ",".join("?" * len(_CLEANUP)) + ")" + _dq(c),
            (y0, t0, *_CLEANUP)).fetchall()), 2)
        out["header"] = {"today": today, "yest": yest, "d2": None, "d7": d7, "d30": d30,
                         "win_today": (round(100 * wins / n_today) if n_today else None),
                         "trades_today": n_today,
                         # The explicit three-way split. `today_tournament` is the same number as
                         # `today` — named, so a reader never has to know which desk the bare
                         # `today` meant. `yest`/`d7`/`d30` are already BOTH desks, so the strip is
                         # internally consistent once the UI shows `today_total`.
                         "today_tournament": today, "today_rider": today_rider,
                         "today_total": today_total,
                         "trades_tournament": n_today, "trades_rider": n_rider}
        # rolling
        def _roll(days):
            p, n, w = pnl.realized(c, "MNQ", since_iso=(now - timedelta(days=days)).isoformat())
            return {"pnl": p, "trades": n, "win": (round(100 * w / n) if n else None), "pf": None, "maxdd": None}
        out["rolling"] = {"1D": {"pnl": today, "trades": n_today,
                                 "win": (round(100 * wins / n_today) if n_today else None), "pf": None, "maxdd": None},
                          "7D": _roll(7), "30D": _roll(30)}
        # today's strategy trades → blotter (newest first) + curve + gate perf
        today_rows = _strategy_trades(c, since_iso=t0)
        cum = 0.0
        for r in today_rows:
            cum += r["pnl_usd"]
            out["curve"].append({"cum": round(cum, 2)})
        for r in reversed(_blotter_rows(c, since_iso=t0)):
            sign = 1 if r["side"] == "LONG" else -1
            ppct = (round(sign * (r["exit_price"] - r["entry_price"]) / r["entry_price"] * 100, 3)
                    if r["entry_price"] else None)
            _flag = r["data_quality"] or ""
            out["blotter"].append({"time": r["closed_at"], "side": r["side"], "gate": r["gate"] or "—",
                                   "exit": r["exit_reason"], "pnl_usd": round(r["pnl_usd"], 2),
                                   "pnl_pct": ppct,
                                   "uncounted": _flag.startswith("BADFILL:"),
                                   "flag": _flag or None})
        gp = _gate_groups(today_rows)
        out["gate_perf"] = gp
        out["leaderboard"] = {"top": gp[:5], "bottom": list(reversed(gp[-5:])) if len(gp) > 5 else []}
        # losses by exit reason (data was always here — just never wired)
        losses: dict = {}
        for r in today_rows:
            if r["pnl_usd"] < 0:
                b = losses.setdefault(r["exit_reason"], {"n": 0, "usd": 0.0})
                b["n"] += 1
                b["usd"] += r["pnl_usd"]
        out["loss_buckets"] = sorted(
            [{"cause": k, "n": v["n"], "usd": round(v["usd"], 2)} for k, v in losses.items()],
            key=lambda x: x["usd"])
        c.close()
    except Exception:
        pass
    return out


def _disabled_gates(data_dir):
    """Gates switched OFF in ``gate_switches.env`` — the live intraday on/off the tournament
    re-reads. Mirrors ``tournament.parse_switches`` (kept in sync by
    tests/test_web.py::test_disabled_gates_matches_tournament_parser); reimplemented here so
    the stdlib-only web server never imports the trading stack. Missing/bad file → none off."""
    off = set()
    try:
        with open(os.path.join(data_dir, "gate_switches.env")) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if v.strip().lower() in ("off", "0", "no", "false", "disable", "disabled"):
                    off.add(k.strip())
    except OSError:
        pass
    return off


# ── /api/futures/tournament — the per-gate scoreboard (roster × trades × live) ─
def tournament_json(store_path, data_dir, cap_path):
    """The tournament scoreboard: the full 6-gate roster (from ``tournament_slots()`` so
    0-trade gates still show), each gate's today-realized (from ``trades``) + open-unrealized
    (from the live ``status.json`` slots × last price), ranked by total, bottom-2 flagged for
    relegation. Plus a desk-level safety block for the header pill. Read-only."""
    from .slot_strategy import grind_long_short_slots, scaleout_slots, tournament_slots
    # ★2026-07-29: roster follows the LIVE slate (GAZBOT7_TOURNAMENT_SLATE), so the dual-slot _A/_B
    # sub-slots show. Was hardcoded tournament_slots() → the scaleout slate's _A/_B trades were invisible
    # and the scoreboard didn't add up (abs_veto_short showed only pre-deploy −135, the +768 win hidden).
    _slate_fn = {"tournament": tournament_slots, "grind2": grind_long_short_slots,
                 "scaleout": scaleout_slots}.get(os.environ.get("GAZBOT7_TOURNAMENT_SLATE", "tournament"), tournament_slots)
    roster = [(s.tag, s.side) for s in _slate_fn()]
    disabled = _disabled_gates(data_dir)   # live intraday on/off (gate_switches.env)
    st = _status(data_dir)
    last = (_features(cap_path) or {}).get("last")
    raw = st.get("position")
    live = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) and not raw.get("flat") else [])
    slot_by_gate = {s.get("gate"): s for s in live if s.get("gate")}

    stats: dict = {}
    wstats: dict = {}   # week-to-date, for the avg-winner/avg-loser/delta/expectancy block
    try:
        now = datetime.now(UTC)
        c = _conn(store_path)
        for r in _strategy_trades(c, since_iso=pnl.paris_day_start_utc(now)):
            d = stats.setdefault(r["gate"] or "?",
                                 {"realized": 0.0, "n": 0, "wins": 0, "gw": 0.0, "gl": 0.0, "exits": {}, "side": r["side"]})
            d["realized"] += r["pnl_usd"]
            d["n"] += 1
            if r["pnl_usd"] > 0:
                d["wins"] += 1
                d["gw"] += r["pnl_usd"]
            else:
                d["gl"] += -r["pnl_usd"]
            d["exits"][r["exit_reason"]] = d["exits"].get(r["exit_reason"], 0) + 1
        for r in _strategy_trades(c, since_iso=pnl.paris_week_start_utc(now)):
            d = wstats.setdefault(r["gate"] or "?", {"n": 0, "wins": 0, "gw": 0.0, "gl": 0.0})
            d["n"] += 1
            if r["pnl_usd"] > 0:
                d["wins"] += 1
                d["gw"] += r["pnl_usd"]
            else:
                d["gl"] += -r["pnl_usd"]
        c.close()
    except Exception:
        pass

    # ★ union: any gate that ACTUALLY traded today but isn't in the live-slate roster (e.g. pre-deploy
    # base-gate trades, or a web-vs-desk slate mismatch) still shows — so the scoreboard reflects reality
    # and always adds up, regardless of the web service's env.
    _rtags = {t for t, _ in roster}
    for _g, _dd in stats.items():
        if _g not in _rtags:
            roster.append((_g, _dd.get("side", "SHORT")))

    rows = []
    for gate, side in roster:
        d = stats.get(gate, {})
        slot = slot_by_gate.get(gate)
        entry = slot.get("entry_price") if slot else None
        qty = abs(slot.get("qty") or 0) if slot else 0.0
        open_unreal = 0.0
        if slot and entry and last:
            open_unreal = round((1 if side == "LONG" else -1) * (last - entry) * _VPP * qty, 2)
        realized = round(d.get("realized", 0.0), 2)
        n = d.get("n", 0)
        # week-to-date winner/loser expectancy: with W winners and L losers the desk
        # nets W·avg_win − L·avg_loss, so this is where a low-win-rate/big-winner gate
        # (grind chandelier) shows whether the fat winners outweigh the many small losers.
        wd = wstats.get(gate, {})
        w_n = wd.get("n", 0)
        w_wins = wd.get("wins", 0)
        w_losses = w_n - w_wins
        avg_win = round(wd["gw"] / w_wins) if w_wins else None
        avg_loss = round(wd["gl"] / w_losses) if w_losses else None
        rows.append({
            "gate": gate, "side": side, "live": slot is not None,
            "enabled": gate not in disabled,   # armed to take NEW entries (gate_switches.env)
            "qty": qty, "entry": entry, "stop": (slot.get("stop_price") if slot else None),
            "protected": (bool(slot.get("stop_coid")) if slot else None),
            "open_unreal": open_unreal, "realized": realized, "total": round(realized + open_unreal, 2),
            "n": n, "win_pct": (round(100 * d.get("wins", 0) / n) if n else None),
            "pf": (round(d["gw"] / d["gl"], 2) if d.get("gl", 0) > 1e-9 else None),
            "exits": d.get("exits", {}),
            "wk_n": w_n, "wk_wins": w_wins, "wk_losses": w_losses,
            "wk_avg_win": avg_win, "wk_avg_loss": avg_loss,
            "wk_delta": (avg_win - avg_loss) if (avg_win is not None and avg_loss is not None) else None,
            "wk_exp": (round((wd["gw"] - wd["gl"]) / w_n, 1) if w_n else None),
        })
    rows.sort(key=lambda x: x["total"], reverse=True)
    active = [r for r in rows if r["n"] > 0 or r["live"]]
    releg = {r["gate"] for r in sorted(active, key=lambda x: x["total"])[:2]} if len(active) >= 2 else set()
    for r in rows:
        r["relegate"] = r["gate"] in releg

    any_naked = any(not s.get("stop_coid") for s in live)
    unverified = (st.get("protection") or {}).get("unverified_cycles", 0)
    halted = bool(st.get("halted"))
    level = "red" if (halted or any_naked) else ("amber" if unverified else "green")
    return {
        "gates": rows,
        "desk": {
            "realized_today": round(sum(r["realized"] for r in rows), 2),
            "open_unreal": round(sum(r["open_unreal"] for r in rows), 2),
            "live_count": sum(1 for r in rows if r["live"]), "roster_count": len(rows),
            "enabled_count": sum(1 for r in rows if r["enabled"]),
            "benched": sorted(g for g, _ in roster if g in disabled),
            "halted": halted, "any_naked": any_naked, "unverified_cycles": unverified,
            "flat": not live, "safety": level, "last": last,
        },
    }


# ── /api/futures/promotion — the shadow feeder → promotion candidates ─────────
_SHADOW_FAMILY = [
    ("grind", ("grind",)),
    ("thrust", ("thrust", "cb_thrust", "abs_veto", "chand")),
    ("reversal_grab", ("rg_long", "rg_short", "rg_")),
    ("capitulation", ("capit",)),
    ("exhaustion", ("exhaust",)),
]


def _shadow_family(name):
    n = (name or "").lower()
    for fam, keys in _SHADOW_FAMILY:
        if any(n.startswith(k) or k in n for k in keys):
            return fam
    return "other"


def promotion_json(shadow_path):
    """The shadow board as the promotion FEEDER: each variant's honest real_pnl (all-time +
    today), its gate family, and whether that family is already live in the tournament. Ranked
    by net; a ``candidate`` = net-positive with a real track record (n≥20). ⚠ shadow is the
    OPTIMISTIC feeder — it ignores the single-position constraint and enters at hindsight
    bar-closes, so it OVERSTATES; it NOMINATES, the paper tournament JUDGES. Never auto-promote."""
    from .slot_strategy import tournament_slots
    live_families = {s.kind for s in tournament_slots()}
    out = {"candidates": [], "live_families": sorted(live_families),
           "note": "shadow overstates (feeder) — nominate, don't auto-promote; paper is the judge"}
    try:
        c = _conn(shadow_path)
        t0 = datetime.fromisoformat(pnl.paris_day_start_utc(datetime.now(UTC))).timestamp()
        rows = c.execute(
            "SELECT st.strategy s, COUNT(*) n, SUM(sr.real_pnl) net, "
            "SUM(CASE WHEN sr.real_pnl>0 THEN 1 ELSE 0 END) w, "
            "SUM(CASE WHEN st.entry_ts>=? THEN sr.real_pnl ELSE 0 END) today, "
            "SUM(CASE WHEN st.entry_ts>=? THEN 1 ELSE 0 END) today_n "
            "FROM shadow_trades st JOIN shadow_real sr ON sr.trade_id=st.id "
            "WHERE sr.fill_status='filled' AND sr.real_pnl IS NOT NULL GROUP BY st.strategy",
            (t0, t0)).fetchall()
        c.close()
        cands = []
        for r in rows:
            n = r["n"] or 0
            fam = _shadow_family(r["s"])
            net = round(r["net"] or 0, 1)
            cands.append({
                "variant": r["s"], "family": fam, "family_live": fam in live_families,
                "n": n, "net": net, "win": (round(100 * (r["w"] or 0) / n) if n else None),
                "today": round(r["today"] or 0, 1), "today_n": r["today_n"] or 0,
                "candidate": (net > 0 and n >= 20)})
        cands.sort(key=lambda x: -x["net"])
        out["candidates"] = cands
    except Exception:
        pass
    return out


# ── /api/futures/execution — the entry funnel: SAY-to-buy vs ACTUALLY-buy ─────
def execution_json(store_path):
    """The full signal→fill funnel for the tournament, today (Paris day). Every entry
    logs a ``submitted`` (we tried) then a ``filled`` (we got it) or a ``nofill`` (IOC
    cancelled — said buy, got nothing) / ``rejected``. Reports the through-rate, the
    per-entry SLIPPAGE (fill vs the intended ref), the failure reasons, an hourly trend,
    and a per-gate breakdown — so you see exactly what we said vs bought, and why misses."""
    from collections import defaultdict, deque

    from .ticks import tick_for
    out = {"current": None, "baseline_pct": None, "trend": [], "funnel": {}, "per_gate": [],
           "slippage": {"avg_ticks": None, "avg_usd": None, "n": 0}, "window": "today"}
    try:
        c = _conn(store_path)
        t0 = pnl.paris_day_start_utc(datetime.now(UTC))
        rows = c.execute(
            "SELECT ts, gate, side, outcome, intended_price FROM signals "
            "WHERE ts>=? AND outcome IN ('submitted','filled','nofill','rejected') ORDER BY ts",
            (t0,)).fetchall()
        c.close()
        tick = tick_for("MNQ") or 0.25
        g = defaultdict(lambda: {"submitted": 0, "filled": 0, "nofill": 0, "rejected": 0,
                                 "side": None, "slip": []})
        refq: dict = defaultdict(deque)          # per-gate FIFO of submitted refs → matched on fill
        hourly: dict = defaultdict(lambda: {"submitted": 0, "filled": 0})
        for r in rows:
            gate, oc, side = (r["gate"] or "?"), r["outcome"], r["side"]
            d = g[gate]; d["side"] = side
            d[oc] = d.get(oc, 0) + 1
            hr = (r["ts"] or "")[:13]
            if oc == "submitted":
                refq[gate].append(r["intended_price"]); hourly[hr]["submitted"] += 1
            elif oc == "filled":
                hourly[hr]["filled"] += 1
                ref = refq[gate].popleft() if refq[gate] else None
                if ref and r["intended_price"]:  # slippage = adverse move ref→fill, per side
                    adv = (r["intended_price"] - ref) if side == "LONG" else (ref - r["intended_price"])
                    d["slip"].append(adv)
        sub = sum(d["submitted"] for d in g.values())
        fil = sum(d["filled"] for d in g.values())
        nof = sum(d["nofill"] for d in g.values())
        rej = sum(d["rejected"] for d in g.values())
        allslip = [s for d in g.values() for s in d["slip"]]
        avg_pts = (sum(allslip) / len(allslip)) if allslip else None
        blocks = {}
        if nof:
            blocks["nofill (IOC cancelled)"] = nof
        if rej:
            blocks["rejected"] = rej
        out["funnel"] = {"submitted": sub, "filled": fil, "nofill": nof, "rejected": rej}
        out["current"] = {
            "pct": (round(100 * fil / sub) if sub else None), "events": sub, "through": fil,
            "level": ("CRIT" if (sub >= 3 and fil == 0) else "OK"),
            "slip_ticks": (round(avg_pts / tick, 1) if avg_pts is not None else None),
            "slip_usd": (round(avg_pts * _VPP, 2) if avg_pts is not None else None),
            "blocks": blocks}
        out["slippage"] = {"avg_ticks": (round(avg_pts / tick, 1) if avg_pts is not None else None),
                           "avg_usd": (round(avg_pts * _VPP, 2) if avg_pts is not None else None),
                           "n": len(allslip)}
        out["per_gate"] = sorted(
            [{"gate": gate, "side": d["side"], "submitted": d["submitted"], "filled": d["filled"],
              "nofill": d["nofill"],
              "through": (round(100 * d["filled"] / d["submitted"]) if d["submitted"] else None),
              "slip_ticks": (round(sum(d["slip"]) / len(d["slip"]) / tick, 1) if d["slip"] else None)}
             for gate, d in g.items()], key=lambda x: -x["submitted"])
        out["trend"] = [
            {"pct": (round(100 * v["filled"] / v["submitted"]) if v["submitted"] else 0),
             "events": v["submitted"], "level": ("CRIT" if (v["submitted"] >= 3 and v["filled"] == 0) else "OK")}
            for _, v in sorted(hourly.items())]
    except Exception:
        pass
    return out


# ── /api/futures/router — the intelligent-router panel (regime + gates + stream) ─
_ROUTER_META = {  # gate → (family, mechanism, side)
    "grind_long": ("momentum", "continuation", "LONG"),
    "abs_veto_long": ("momentum", "thrust", "LONG"),
    "capitulation_long": ("reversion", "flush-fade", "LONG"),
    "exhaustion_short": ("reversion", "reversal", "SHORT"),
    "abs_veto_short": ("momentum", "thrust", "SHORT"),
    "rgv_short": ("fade", "turnback", "SHORT"),
    # ★2026-08-05 nipc was MISSING here since it shipped 08-01, so the board silently showed 6 of 8
    # gates for four days. A dashboard that omits a gate is worse than one that shows it benched —
    # you cannot notice the state of something you are never shown. Same failure as the truncated
    # shadow block that hid a 9-of-9 green thrust family from the router.
    # This map is the ONLY place gates are enumerated for the panel, so it must track the live roster.
    # ★2026-08-15 nipc REMOVED from the panel — retired from the roster (operator). This map is the
    # only place gates are enumerated for the router board, and the 08-05 note above is still the
    # rule: it must TRACK THE LIVE ROSTER. A retired gate shown benched implies the router might
    # re-arm it, which is exactly the misleading label that note warns about.
    # ⚠ This removes it from the BOARD only. Its 49 historical trades (08-03..08-06, -$434.50) are
    # untouched in the ledger and still render in the blotter, which reads gate strings from the
    # trades table and does not consult this map.
}


def _router_reason(on, fam, side, is_chop, bias):
    """Derive WHY a gate is on/off from its mechanism + the live regime — so it stays true
    as the regime changes, rather than a hardcoded string that goes stale."""
    if on:
        if fam == "news":
            return "armed — news-impulse window"
        if fam in ("reversion", "fade"):
            return "armed — reversion fits a rotation"
        return "armed — aligned momentum"
    # ★2026-08-05 nipc is not benched by REGIME — it is PINNED OFF in the router and held out of the
    # 22:00 reactivation pending the live/replay divergence diagnosis. Showing it as "benched —
    # momentum bleeds in the rotation" would imply the router might re-arm it on a regime change,
    # which is exactly wrong and the sort of misleading label that gets acted on.
    if fam == "news":
        return "PINNED OFF — failed acceptance replay; held from the nightly re-arm"
    if side == "SHORT" and bias == "UP":
        return "benched — counter to the up-day"
    if side == "LONG" and bias == "DOWN":
        return "benched — counter to the down-day"
    if fam == "momentum" and is_chop:
        return "benched — momentum bleeds in the rotation"
    if fam == "fade" and side == "SHORT":
        return "benched — needs an over-extension above VWAP; no setup"
    return "benched"


def router_json(store_path, cap_path, data_dir):
    """The ROUTER watch panel: multi-clock regime read (why a 0.3 ER can still be chop),
    per-gate on/off + reason + live P&L, the shadow-family cross-check, the timestamped
    activity stream (from router_trial_log.txt), and the <=2 open slots. Read-only; every
    section is independently guarded so one bad read never blanks the page."""
    now = datetime.now(UTC)
    out = {"ts": now.astimezone(_PARIS).strftime("%Y-%m-%d %H:%M:%S"), "tz": "Paris",
           "regime": {}, "gates": [], "shadow": {}, "activity": [], "holdings": [],
           "chandeliers": [], "day": {}, "untradeable": {}, "leaning": {}}
    cl = []
    try:
        s = pnl.paris_day_start_utc(now)
        ds_dt = datetime.fromisoformat(s) if isinstance(s, str) else s
        ds_ep = int(ds_dt.timestamp())
        ds_iso = ds_dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        ds_ep = int(now.timestamp()) - now.hour * 3600
        ds_iso = now.strftime("%Y-%m-%dT00:00:00")

    try:   # UNTRADEABLE-DAY METER (stay-out evidence) — guarded, never blanks the page
        from .untradeable import compute as _untradeable_compute
        out["untradeable"] = _untradeable_compute(cap_path, store_path, ds_ep, int(now.timestamp()))
    except Exception:
        out["untradeable"] = {}

    # ★2026-08-05 DAY LEANING — operator: "dashboard needs a way to indicate to me the way the day is
    # leaning. so i know. then when its confirmed we buy 2 lots."
    # It calls the SAME gazbot7.drift.read() the live service calls, so the panel can never show one
    # thing while the desk acts on another (pnl.py's one-source-of-truth rule, applied to a signal).
    # The `*_needed` fields are surfaced on purpose: the operator wants to watch it BUILD toward
    # confirmation, not just be told the instant it fires.
    try:
        from .drift import ER_MIN as _ERM, RT_MIN as _RTM, read as _drift_read
        _d = _drift_read(cap_path, now=now)
        out["leaning"] = {
            "ok": _d.ok, "direction": _d.direction, "confirmed": _d.confirmed,
            "minutes": _d.minutes, "net_pt": round(_d.net_pt, 1), "range_pt": round(_d.range_pt, 1),
            "efficiency": round(_d.efficiency, 3), "roundtrip": round(_d.roundtrip, 3),
            "er_min": _ERM, "rt_min": _RTM,
            "er_needed": round(_d.er_needed, 3), "rt_needed": round(_d.rt_needed, 3),
            "blockers": _d.blockers, "detail": _d.detail,
        }
    except Exception:
        out["leaning"] = {}

    day_bias, day_net, day_er, day_hi, day_lo = "FLAT", 0.0, None, None, None
    try:
        c = _conn(cap_path)
        rows = c.execute(
            "SELECT bar_ts, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
            "AND bar_ts>=? AND bar_ts<=? ORDER BY bar_ts", (ds_ep, int(now.timestamp()))).fetchall()
        c.close()
        mins = {}  # last close per minute → same 1-min basis as desk_view, so day-ER matches
        for r in rows:
            mins[r["bar_ts"] // 60] = r["close"]
        cl = [mins[k] for k in sorted(mins)]
        if len(cl) >= 6:
            day_net = cl[-1] - cl[0]
            path = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1.0
            day_er = round(abs(cl[-1] - cl[0]) / path, 3)
            day_hi, day_lo = max(cl), min(cl)
            day_bias = "DOWN" if day_net < -40 else ("UP" if day_net > 40 else "FLAT")
    except Exception:
        pass
    f = _features(cap_path) or {}
    last = f.get("last") or (cl[-1] if cl else None)
    r_lo, r_hi = day_lo, day_hi
    try:
        c = _conn(cap_path)
        rr = c.execute("SELECT MIN(low) lo, MAX(high) hi FROM bars WHERE symbol='MNQ' "
                       "AND timeframe='5s' AND bar_ts>=?", (int(now.timestamp()) - 3 * 3600,)).fetchone()
        c.close()
        if rr and rr["lo"] is not None:
            r_lo, r_hi = rr["lo"], rr["hi"]
    except Exception:
        pass
    er30 = f.get("er")
    is_chop = (day_er is not None and day_er < 0.12)
    verdict = ("TREND " + day_bias if (day_er or 0) >= 0.20
               else "RANGE-ROTATION" if is_chop else "MIXED")
    posn = None
    if last is not None and r_hi is not None and r_hi > (r_lo or 0):
        posn = round(max(0.0, min(1.0, (last - r_lo) / (r_hi - r_lo))) * 100)
    out["regime"] = {
        "verdict": verdict, "day_bias": day_bias, "day_net": round(day_net),
        "day_er": day_er, "er_30min": round(er30, 2) if er30 is not None else None,
        "atr_pts": f.get("atr_pts"), "violence": f.get("violence"), "last": last,
        "range_lo": r_lo, "range_hi": r_hi, "range_pos": posn,
        "day_hi": day_hi, "day_lo": day_lo,
    }

    live = {}
    try:
        c = _conn(store_path)
        for r in c.execute("SELECT gate, ROUND(SUM(pnl_usd),1) p, COUNT(*) n FROM trades "
                           "WHERE closed_at>=?" + _dq(c) + " GROUP BY gate", (ds_iso,)).fetchall():
            g = r["gate"] or ""
            base = g.rsplit("_", 1)[0] if g.rsplit("_", 1)[-1] in ("A", "B") else g
            d = live.setdefault(base, [0.0, 0])
            d[0] += r["p"] or 0.0
            d[1] += r["n"]
        c.close()
    except Exception:
        pass
    switches = {}
    try:
        for ln in open(os.path.join(data_dir, "gate_switches.env")):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                switches[k.strip()] = v.strip().lower() == "on"
    except Exception:
        pass
    for name, (fam, sub, side) in _ROUTER_META.items():
        on = switches.get(name, True)
        lv = live.get(name)
        out["gates"].append({
            "name": name, "family": fam, "mech": sub, "side": side, "on": on,
            "reason": _router_reason(on, fam, side, is_chop, day_bias),
            "live_pnl": round(lv[0], 1) if lv else None, "trades": lv[1] if lv else 0,
        })

    try:
        c = _conn(os.path.join(data_dir, "shadow.db"))
        fam_map = {"momentum-long": ("grind_fast", "thrust_aligned", "thrust_loose", "thrust_fast", "chand_k25", "chand_k20"),
                   "momentum-short": ("thrust_short_raw", "thrust_short_absveto55"),
                   "reversion": ("capit_loose", "capit_mid", "rg_long_fast", "rg_long_fast_v")}
        for fam, strats in fam_map.items():
            q = ",".join("?" * len(strats))
            r = c.execute(f"SELECT ROUND(SUM(ceiling_pnl),1) p, COUNT(*) n FROM shadow_trades "
                          f"WHERE CAST(entry_ts AS BIGINT)>=? AND exit_price IS NOT NULL AND strategy IN ({q})",
                          (ds_ep, *strats)).fetchone()
            out["shadow"][fam] = {"pnl": r["p"], "n": r["n"]} if r and r["p"] is not None else {"pnl": None, "n": 0}
        c.close()
    except Exception:
        pass

    try:
        lines = open(os.path.join(data_dir, "router_trial_log.txt")).read().splitlines()
        for ln in reversed(lines[-24:]):
            parts = [p.strip() for p in ln.split(" | ")]
            if len(parts) < 3:
                continue
            try:
                t = datetime.fromisoformat(parts[0].replace("Z", "+00:00")).astimezone(_PARIS).strftime("%H:%M")
            except (ValueError, TypeError):
                t = parts[0][11:16] if len(parts[0]) >= 16 else parts[0]
            kind = parts[1] if len(parts) > 1 else ""
            changed, gist = "", ""
            for p in parts:
                if p.startswith("changed:"):
                    changed = p[8:].strip()
                if p.startswith("HOLISTIC:") or p.startswith("KEY:") or "VINDICAT" in p or "★" in p:
                    gist = p.split(":", 1)[-1].strip() if ":" in p else p
            if not gist:
                gist = parts[2]
            is_change = bool(changed) and changed.lower() not in ("none", "none (hold)")
            tag = "EXTEND" if kind == "EXTEND" else ("CHG" if is_change else "hold")
            out["activity"].append({"t": t, "tag": tag, "changed": changed,
                                    "text": gist[:180], "is_change": is_change})
    except Exception:
        pass

    try:
        c = _conn(store_path)
        rr = c.execute("SELECT pnl_usd FROM trades WHERE closed_at>=?" + _dq(c)
                       + " ORDER BY closed_at", (ds_iso,)).fetchall()
        c.close()
        run, peak = 0.0, 0.0
        for r in rr:
            run += r["pnl_usd"] or 0.0
            peak = max(peak, run)
        out["day"] = {"pnl": round(run, 1), "peak": round(peak, 1), "trades": len(rr)}
    except Exception:
        out["day"] = {}
    try:
        st = _status(data_dir)
        out["day"]["flat"] = bool(st.get("flat", not st.get("position")))
        out["day"]["healthy"] = st.get("healthy")
        out["day"]["halted"] = st.get("halted")
        raw = st.get("position")
        slots = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) and not raw.get("flat") else [])
        for s in slots:
            entry = s.get("entry_price") or s.get("entry")
            if entry is None:
                continue
            side = s.get("side") or ("SHORT" if (s.get("qty") or 0) < 0 else "LONG")
            sign = 1 if side == "LONG" else -1
            lastp = last or entry
            held = None
            if s.get("opened_at"):
                try:
                    held = int((now - datetime.fromisoformat(s["opened_at"])).total_seconds())
                except (ValueError, TypeError):
                    held = None
            out["holdings"].append({
                "gate": s.get("gate", "—"), "side": side, "qty": abs(s.get("qty") or 1),
                "entry": entry, "stop": s.get("stop_price") or s.get("stop"),
                "pnl_usd": round(sign * (lastp - entry) * _VPP * abs(s.get("qty") or 1), 1),
                "held_s": held, "protected": bool(s.get("stop_coid")),
            })
        # ── Lot B chandelier tail metrics — the give-back-exit visibility ──
        # peak_favorable isn't stored, so reconstruct it from capture bars since entry.
        # BIG-RUN gates use exit_chandelier_lock (wide 3.5xATR trail → LOCK to 0.5xATR at
        # lock_r=6R); FADERS use the continuously-tightening exit_chandelier (start 1.5).
        CH = {"grind_long": ("lock", 3.5, 6.0, 0.5), "abs_veto_long": ("lock", 3.5, 6.0, 0.5),
              "abs_veto_short": ("lock", 3.5, 6.0, 0.5), "exhaustion_short": ("lock", 3.5, 6.0, 0.5),
              "rgv_short": ("trail", 1.5, 0.5, 0.75), "capitulation_long": ("trail", 1.5, 0.5, 0.75)}
        for s in slots:
            g = s.get("gate", "")
            base = g[:-2] if g.endswith(("_A", "_B")) else g
            if not g.endswith("_B") or base not in CH:
                continue
            entry = s.get("entry_price") or s.get("entry")
            atr = s.get("entry_atr") or 0
            if not entry or atr <= 0:
                continue
            side = s.get("side") or "LONG"
            qty = abs(s.get("qty") or 1)
            lastp = last or entry
            peakfav = 0.0
            try:
                op = int(datetime.fromisoformat(s["opened_at"]).timestamp())
                c2 = _conn(cap_path)
                rr = c2.execute("SELECT MAX(high) hi, MIN(low) lo FROM bars WHERE symbol='MNQ' "
                                "AND timeframe='5s' AND bar_ts>=?", (op,)).fetchone()
                c2.close()
                if rr and rr["hi"] is not None:
                    peakfav = (rr["hi"] - entry) if side == "LONG" else (entry - rr["lo"])
            except Exception:
                pass
            peakfav = max(peakfav, (lastp - entry) if side == "LONG" else (entry - lastp), 0.0)
            peak_r = peakfav / atr
            cur_r = ((lastp - entry) if side == "LONG" else (entry - lastp)) / atr
            ctype, start_k, p2, p3 = CH[base]
            if ctype == "lock":
                active = peak_r >= p2
                k = p3 if active else start_k
                r_to_go = None if active else round(max(0.0, p2 - peak_r), 2)
                lock_r = p2
            else:
                k = max(p2, start_k - p3 * peak_r)
                active = peakfav > 0
                r_to_go = None
                lock_r = None
            giveback_pts = k * atr
            exit_fav = peakfav - giveback_pts   # fav level that fires CHANDELIER
            exit_price = entry + exit_fav if side == "LONG" else entry - exit_fav
            r_usd = atr * _VPP * qty            # 1R in dollars (stop distance × $2/pt × qty)
            out["chandeliers"].append({
                "gate": g, "side": side, "type": ctype, "armed": peakfav > 0, "active": bool(active),
                "cur_r": round(cur_r, 2), "peak_r": round(peak_r, 2), "lock_r": lock_r,
                "r_to_activate": r_to_go, "k": round(k, 2),
                "r_usd": round(r_usd), "cur_usd": round(cur_r * r_usd), "peak_usd": round(peak_r * r_usd),
                "lock_usd": (round(lock_r * r_usd) if lock_r else None),
                "to_activate_usd": (round(r_to_go * r_usd) if r_to_go else None),
                "giveback_pts": round(giveback_pts, 1), "giveback_usd": round(giveback_pts * _VPP * qty),
                "exit_price": round(exit_price, 1),
                "peak_price": round(entry + peakfav if side == "LONG" else entry - peakfav, 1),
                "locked_usd": round(max(0.0, exit_fav) * _VPP * qty),
            })
    except Exception:
        pass
    return out


# ── POST /api/control/claim — operator "Claim profit" per-slot flatten ─────────
def claim_post(body, data_dir):
    """PIN-guarded per-slot flatten REQUEST. Verifies {pin} against data/claim_pin.txt
    (server-side), then appends {gate} to data/claim_requests.txt for the tournament to
    consume on its next manage cycle via the desk's OWN safe _flatten_slot. This web layer
    NEVER touches positions/broker — zero ledger risk from here; the trading core owns the
    actual flatten. Fat-finger guard, not real auth (fine for PAPER; not for real money)."""
    try:
        req = json.loads(body or b"{}")
    except Exception:
        return {"ok": False, "error": "bad request"}
    gate = str(req.get("gate", "")).strip()
    pin = str(req.get("pin", "")).strip()
    if not gate:
        return {"ok": False, "error": "no gate given"}
    try:
        want = open(os.path.join(data_dir, "claim_pin.txt")).read().strip()
    except Exception:
        return {"ok": False, "error": "claim PIN not set on server"}
    if not want or pin != want:
        return {"ok": False, "error": "wrong PIN"}
    try:
        with open(os.path.join(data_dir, "claim_requests.txt"), "a") as f:
            f.write(gate + "\n")
    except Exception as e:
        return {"ok": False, "error": f"write failed: {e}"}
    return {"ok": True, "gate": gate, "msg": f"claim requested — {gate} flattens on the next cycle"}


# ── POST /api/control/dayrider-claim — operator "Claim profit" on the day rider ─
def client_error_post(body, data_dir):
    """★★★2026-09-24 THE PAGE REPORTS ITS OWN FAILURES.

    A dashboard that breaks in the browser is INVISIBLE from here: every endpoint returns 200, every
    test passes, and the operator sees a blank panel. That has now happened three times — the
    tournament panel, the day drill, and today's TRADE tab — and each time it cost a round of
    guessing because the only witness was a browser I cannot read.
    ⚠ The render loop's `catch (e) { }` blocks were the worst of it: an exception mid-pass leaves
    everything AFTER it unrendered and says nothing at all.

    Bounded and dumb on purpose: append-only, capped, no parsing of anything the page sends beyond
    truncating it. Nothing here is trusted — it is a browser writing to a log.
    """
    try:
        req = json.loads(body or b"{}")
    except Exception:
        req = {"raw": str(body[:200])}
    rec = {"ts": datetime.now(UTC).isoformat(),
           "where": str(req.get("where", ""))[:80],
           "msg": str(req.get("msg", ""))[:400],
           "stack": str(req.get("stack", ""))[:800],
           "ua": str(req.get("ua", ""))[:120]}
    path = os.path.join(data_dir, "client_errors.jsonl")
    try:
        # ⚠ cap it: a render loop erroring every tick would fill the disk in a day
        if os.path.exists(path) and os.path.getsize(path) > 2_000_000:
            os.replace(path, path + ".1")
        with open(path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    return {"ok": True}


def step_away_post(body, data_dir):
    """ARM / DISARM the step-away guard. Writes a state file; places NO order.

    ★★ ARMING NEEDS NO PIN, AND THAT IS DELIBERATE. The PIN guards actions that ADD risk — an
    order, or DISARMING a guard. Arming one REDUCES risk, and friction at the exact moment he is
    walking into a meeting is friction that costs money. DISARMING asks for the PIN, because that
    is the direction that exposes him.

    ⚠ The watcher (scripts/step_away.py) does the acting, and it acts by writing the claim file his
    own button writes — the web process never touches the broker.
    """
    try:
        req = json.loads(body or b"{}")
    except Exception:
        return {"ok": False, "error": "bad request"}
    arm = bool(req.get("armed"))
    path = os.path.join(data_dir, "step_away.json")
    if not arm:
        pin = str(req.get("pin", "")).strip()
        try:
            want = open(os.path.join(data_dir, "claim_pin.txt")).read().strip()
        except Exception:
            want = ""
        if not want or pin != want:
            return {"ok": False, "error": "wrong PIN — disarming removes a guard"}
        try:
            with open(path, "w") as fh:
                json.dump({"armed": False, "disarmed_at": datetime.now(UTC).isoformat()}, fh)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "armed": False, "msg": "Step-away DISARMED. You are watching it again."}
    try:
        lim = abs(float(req.get("limit_usd") or 200))
    except Exception:
        lim = 200.0
    tp = req.get("take_profit_usd")
    try:
        tp = abs(float(tp)) if tp else None
    except Exception:
        tp = None
    # the session is the 22:00Z reopen — an arming must never survive it
    now = datetime.now(UTC)
    sess = (now.date() if now.hour >= 22 else (now - timedelta(days=1)).date()).isoformat()
    # ★★2026-09-24 SAY WHAT WILL HAPPEN THE INSTANT IT IS ARMED. Arming a −$200 stop while the
    # position is already −$250 flattens it on the next 2-second tick. That may be exactly what he
    # wants, but it must never be a surprise — and the reply is the only place he will see it.
    # ⚠ This is not hypothetical: arming against a LIVE position without first reading its open P&L
    # is precisely the mistake that prompted this guard.
    live = None
    try:
        import sqlite3 as _sq
        with open(os.path.join(data_dir, "day_rider_state.json")) as fh:
            rs = json.load(fh)
        if rs.get("qty") and not rs.get("closed"):
            _c = _sq.connect(os.path.join(data_dir, "capture.db"))
            _px = _c.execute("select close from bars where symbol='MNQ' and timeframe='5s' "
                             "order by bar_ts desc limit 1").fetchone()
            _c.close()
            if _px:
                q = float(rs["qty"]); d = int(rs.get("direction") or 0)
                live = (float(_px[0]) - float(rs["entry"])) * d * q * _VPP - _FEE * q
    except Exception:
        live = None

    st = {"armed": True, "limit_usd": lim, "take_profit_usd": tp,
          "armed_at": now.isoformat(), "session": sess}
    try:
        with open(path, "w") as fh:
            json.dump(st, fh, indent=1)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    imminent = live is not None and (live <= -lim or (tp and live >= tp))
    msg = (f"Step-away ARMED — flatten at −${lim:.0f}" + (f" or +${tp:.0f}" if tp else "")
           + ". Disarms at the 22:00Z reopen.")
    if live is not None:
        msg += f" Open P&L is {live:+.0f} right now"
        msg += (" — ⚠ THAT IS ALREADY PAST YOUR LEVEL, SO IT WILL FLATTEN WITHIN SECONDS."
                if imminent else f", inside the band.")
    return {"ok": True, "armed": True, "limit_usd": lim, "take_profit_usd": tp,
            "open_pnl": (round(live, 2) if live is not None else None),
            "fires_immediately": bool(imminent), "msg": msg}


def operator_pass_post(body, data_dir):
    """★★★ "LOOKED AND PASSED" — he considered a trade and decided against it. NO ORDER.

    THE GAP IT CLOSES (2026-09-18). Every record in operator_reads.jsonl is a "yes". You cannot
    learn a decision boundary from one side of it, and that is precisely why 119 calibrations
    failed to reproduce his judgement: they all reverse-engineered from the OUTCOME because nobody
    had ever recorded the times he looked and did nothing.

    ⚠⚠⚠ IT WRITES `operator_pass.txt`, WHICH NO ORDER PATH READS. day_rider consumes
    day_rider_buy.txt and day_rider_claim.txt and has never heard of this file, so the button
    cannot place an order however it is pressed, replayed or aged. That is a STRUCTURAL guarantee,
    not a check that could be forgotten — and `tests/test_looked_and_passed.py` asserts the rider's
    source never names it.

    ⚠ NO PIN, DELIBERATELY. The PIN on claim/buy guards an order. This places none, and a friction
    that makes him skip recording a pass would defeat the whole point — the sample is the product.
    ⚠ NOT age-bounded and never consumed: nothing acts on it, so a stale file is inert. It is
    overwritten by the next press; the RECORD lives in operator_reads.jsonl, written by the path
    unit, not here.
    """
    try:
        req = json.loads(body or b"{}")
    except Exception:
        req = {}
    # His own words at the moment, if he typed any — build-queue item 3, free here.
    note = str(req.get("note", ""))[:200].replace("|", " ").replace("\n", " ")
    stamp = datetime.now(UTC).isoformat()
    try:
        with open(os.path.join(data_dir, "operator_pass.txt"), "w") as fh:
            fh.write(f"{stamp}|PASS|{note}")
    except Exception as e:
        return {"ok": False, "error": f"could not record: {e}"}
    return {"ok": True, "recorded": stamp,
            "msg": "Noted — looked and passed. No order placed."}


def dayrider_claim_post(body, data_dir):
    """PIN-guarded REQUEST to bank the day rider's open position.

    Same shape as claim_post above and for the same reason: this layer writes a
    file and returns, and the DAY RIDER does the flatten on its own cycle through
    own_flatten_verdict. The web process never touches the broker. A button that
    reached the broker directly is how 2026-08-06 happened — a flatten fired
    without checking whose position it was and took the tournament's with it.

    ⚠ Not instant, but no longer slow: `gazbot7-day-rider-claim.path` watches this
    file and starts the rider on the inotify close-write, measured at 0.02s. The
    60s tick remains the FLOOR if that unit is down. This docstring said "up to
    ~60s" for a fortnight after the fast path shipped, contradicting the message
    the same function returns fifty lines below it.
    ⚠ The manual BUY/SELL path has NO such unit — it is still picked up on the
    next minute tick, and its response says so.
    ⚠ It ENDS the session: the `closed` latch means no re-entry today.
    """
    try:
        req = json.loads(body or b"{}")
    except Exception:
        return {"ok": False, "error": "bad request"}
    # ★★★2026-09-24 A FULL FLATTEN NEEDS NO PIN. Operator: "yes drop pin on flatten and keep on
    # sell... for flatten just keep the pop up confirm window but i can just click ok."
    # THE ASYMMETRY IS THE POINT: a PIN guards actions that ADD risk. Flattening everything can
    # only ever REDUCE it — it cannot open, size or reverse anything, and the worst a spurious one
    # does is close a position early. Friction on a kill switch costs money, and this is the button
    # he reaches for when something is already going wrong.
    # ⚠ A PER-LOT claim KEEPS the PIN: that is a discretionary exit of PART of a position, not a
    # kill switch, and a mis-tap leaves the rest running against a ladder that has silently moved.
    _lot = req.get("lot", None)
    _flatten_all = _lot in (None, "", "all") or bool(req.get("flatten"))
    if not _flatten_all:
        pin = str(req.get("pin", "")).strip()
        try:
            want = open(os.path.join(data_dir, "claim_pin.txt")).read().strip()
        except Exception:
            return {"ok": False, "error": "claim PIN not set on server"}
        if not want or pin != want:
            return {"ok": False, "error": "wrong PIN"}
    # Refuse when there is nothing to claim, so the button cannot leave a stale
    # request file lying in wait to fire against tomorrow's position.
    try:
        st = json.load(open(os.path.join(data_dir, "day_rider_state.json")))
    except Exception:
        st = {}
    if not st.get("entered") or st.get("closed"):
        return {"ok": False, "error": "nothing to claim — the day rider is not in a position"}
    # ★★2026-08-20 FOUR BUTTONS. The rider runs 4 lots on a profit ladder ($100/$200/$400/$600),
    # so each lot gets its own button. `lot` is 1-based from the UI and written 0-based.
    # ⚠ OMITTING `lot` STILL MEANS FLATTEN EVERYTHING — the original button is the operator's kill
    #   switch and must keep working byte-for-byte, so the bare stamp is left exactly as it was.
    # ⚠ These are ALSO kill buttons: there is no stop on the rider by operator decision, so a
    #   button fires in profit or loss. The endpoint does not check P&L and must not.
    lot = req.get("lot", None)
    spec = ""
    if lot not in (None, "", "all"):
        try:
            k = int(lot)
        except Exception:
            return {"ok": False, "error": "bad lot"}
        if not 1 <= k <= 4:
            return {"ok": False, "error": "lot must be 1-4"}
        done = set(st.get("targets_done") or [])
        if (k - 1) in done:
            return {"ok": False, "error": f"lot {k} is already out"}
        spec = f"|lot={k-1}"
    try:
        with open(os.path.join(data_dir, "day_rider_claim.txt"), "w") as f:
            f.write(datetime.now(UTC).isoformat() + spec + "\n")
    except Exception as e:
        return {"ok": False, "error": f"write failed: {e}"}
    if spec:
        left = max(0, int(st.get("lots_open") or 4) - 1)
        return {"ok": True, "msg": f"lot {lot} claimed — it exits immediately (~0.1s). "
                                   f"{left} lot(s) will remain open."}
    # ★2026-08-19 was "up to ~60s". gazbot7-day-rider-claim.path now watches this file and starts
    # the rider on the inotify close-write — measured at 0.02s. The 60s timer stays the FLOOR, so if
    # the path unit is down the claim is still picked up on the next tick exactly as before.
    return {"ok": True, "msg": "claim requested — the day rider flattens immediately (~0.1s; the 60s "
                               "tick is the fallback). This ends its session; it will not re-enter today."}


# ── STAY-OUT LIGHT ────────────────────────────────────────────────────────────
# ★★2026-08-20 MEASURED, NOT INVENTED. Six discretionary meters were scored on 225 lake sessions
# (decision 14:00Z, outcome to the 20:40 flat):
#     VWAP position 50.7% · VWAP slope 50.7% · VWAP slope FAST 55.1% · OR break 52.3%
#     · momentum net_atr_5 52.9% · volume surge 37.5% (n=8, dead at this resolution)
# CONFLUENCE DOES NOT STACK: strong agreement reaches only 55.9% up / 51.0% down, because five
# correlated indicators agreeing is one opinion said five times. So this does NOT say BUY.
# THE ONE CELL THAT SEPARATES IS DISAGREEMENT: when the meters are mixed (net score -1..+1) the
# hit rate falls to 44.4% and the mean session is -35.3pt across 54 of 225 sessions. That is a
# STAY-OUT signal, and it is the only honest product in the measurement.
# ⚠ Volume surge is deliberately EXCLUDED from the score: 8 calls in 225 sessions is not a meter.
def stayout_meters(capture_path):
    """Live meter board + the measured stay-out verdict. Read-only; never trades."""
    try:
        from .deciders import Bar, compute_features
        con = _conn(capture_path)
        rows = con.execute(
            "SELECT bar_ts,open,high,low,close,volume FROM bars WHERE symbol='MNQ' "
            "AND timeframe='5s' ORDER BY bar_ts DESC LIMIT 4320").fetchall()
        con.close()
        if len(rows) < 600:
            return {"ok": False, "detail": "not enough tape"}
        rows = list(reversed(rows))
        mins = {}
        for r in rows:                                   # 5s -> 1m, integer floor
            m = int(r[0]) - int(r[0]) % 60
            b = mins.get(m)
            mins[m] = (m, r[1] if not b else b[1], max(r[2], b[2] if b else r[2]),
                       min(r[3], b[3] if b else r[3]), r[4], (b[5] if b else 0) + (r[5] or 0))
        bars = [Bar(int(v[0]), float(v[1]), float(v[2]), float(v[3]), float(v[4]), float(v[5]))
                for _, v in sorted(mins.items())]
        if len(bars) < 65:
            return {"ok": False, "detail": "not enough minute bars"}
        f = compute_features(bars[-60:])
        px = bars[-1].close
        import datetime as _dt
        opn = 13 * 60 + 30
        todays = [b for b in bars
                  if opn <= _dt.datetime.fromtimestamp(b.ts, _dt.UTC).hour * 60
                  + _dt.datetime.fromtimestamp(b.ts, _dt.UTC).minute < opn + 15]
        orh = max((b.high for b in todays), default=None)
        orl = min((b.low for b in todays), default=None)
        meters = [
            ("VWAP position", 1 if px > f.vwap else -1, "50.7%"),
            ("VWAP slope", 1 if f.vwap_slope_atr > 0 else -1, "50.7%"),
            ("VWAP slope FAST", 1 if f.vwap_slope_fast > 0 else -1, "55.1%"),
            ("Momentum net_atr_5", 1 if f.net_atr_5 > 0 else -1, "52.9%"),
            ("Opening-range break",
             (1 if (orh and px > orh) else (-1 if (orl and px < orl) else 0)), "52.3%"),
        ]
        score = sum(v for _, v, _ in meters)
        mixed = -1 <= score <= 1
        return {"ok": True, "score": score, "mixed": mixed,
                "verdict": "STAY OUT — meters disagree" if mixed else
                           ("leaning UP" if score > 0 else "leaning DOWN"),
                "evidence": ("mixed: 44.4% hit, -35.3pt mean over 54 of 225 sessions"
                             if mixed else
                             "agreement: 55.9% up / 51.0% down — barely above a coin flip, NOT a buy signal"),
                "meters": [{"name": n, "vote": v, "hit": h} for n, v, h in meters],
                "px": round(px, 2), "vwap": round(f.vwap, 2),
                "ext_atr": round(f.ext_atr, 2), "atr": round(f.atr, 1)}
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


# ── POST /api/control/dayrider-buy — operator MANUAL entry ────────────────────
def dayrider_buy_post(body, data_dir):
    """PIN-guarded manual BUY/SELL request. Writes a file; the RIDER places the order.

    ★★ THE WEB PROCESS NEVER PLACES AN ORDER. Same indirection as every claim button and for the
    same reason — 2026-08-06: a button that reached the broker directly flattened without checking
    whose position it was and halted the desk for 11 minutes. This writes
    `ISO | SIDE | QTY | TARGET_USD` and returns; the rider validates and executes behind
    venue_first_ok() and the shared-account ownership check on its next tick.
    ⚠ REFUSES WHEN ALREADY IN A POSITION. The rider tracks one entry, one direction and one qty;
      a second buy on top would desync its book from the venue, which on a netted account is the
      08-06 cascade. Flatten first.
    """
    try:
        req = json.loads(body or "{}")
    except Exception:
        return {"ok": False, "error": "bad request"}
    pin = str(req.get("pin", "")).strip()
    try:
        want = open(os.path.join(data_dir, "claim_pin.txt")).read().strip()
    except Exception:
        return {"ok": False, "error": "claim PIN not set on server"}
    if not want or pin != want:
        return {"ok": False, "error": "wrong PIN"}
    side = str(req.get("side", "BUY")).upper()
    if side not in ("BUY", "SELL"):
        return {"ok": False, "error": "side must be BUY or SELL"}
    # ★2026-08-21 CASCADING per-lot targets: the operator sets a $ figure for each lot
    # ($100/$200/$400/$600 by default). A single `target_usd` is still accepted and applied to
    # every lot, so an older client cannot break.
    try:
        qty = int(req.get("qty", 0))
        raw_t = req.get("targets")
        if raw_t is None:
            tg = [float(req.get("target_usd", 0))] * max(1, qty)
        else:
            tg = [float(x) for x in raw_t]
    except Exception:
        return {"ok": False, "error": "qty and targets must be numbers"}
    if not 1 <= qty <= 8:
        return {"ok": False, "error": "qty must be 1-8"}
    if len(tg) < qty:
        return {"ok": False, "error": f"need {qty} target(s), got {len(tg)}"}
    tg = tg[:qty]
    if any(not 10 <= t <= 20000 for t in tg):
        return {"ok": False, "error": "each target must be $10-$20,000"}
    try:
        st = json.load(open(os.path.join(data_dir, "day_rider_state.json")))
    except Exception:
        st = {}
    if st.get("entered") and not st.get("closed"):
        return {"ok": False, "error": "already in a position — flatten before buying again"}
    # ★★2026-08-21 REFUSE OUTSIDE THE RIDER'S WINDOW, AT THE BUTTON.
    # The rider returns early with "outside 13:30-21:00 — flat, idle" long before it reaches the
    # manual-entry branch, so a press outside the window wrote a file that nothing consumed and
    # expired in silence. The operator pressed BUY, got "ok", and nothing happened — the worst
    # possible feedback on an order path. Say no HERE, immediately, with the reason and the clock.
    _now = datetime.now(UTC)
    _mod = _now.hour * 60 + _now.minute
    # ★2026-08-21 FULL CME SESSION (operator). Refuse only the flatten window and the halt:
    # 20:40-22:00Z. Everything else is tradeable, and the 20:40 flat still closes it inside the
    # same session, so "never hold overnight" is preserved.
    if 20 * 60 + 40 <= _mod < 22 * 60:
        _mins = (22 * 60) - _mod
        return {"ok": False,
                "error": (f"20:40-22:00Z is the flatten window and the CME halt — it is "
                          f"{_now:%H:%M}Z. The session reopens in {_mins // 60}h {_mins % 60}m. "
                          f"Nothing was sent.")}
    try:
        with open(os.path.join(data_dir, "day_rider_buy.txt"), "w") as f:
            f.write(f"{datetime.now(UTC).isoformat()}|{side}|{qty}|"
                    + ",".join(f"{t:g}" for t in tg) + "\n")
    except Exception as e:
        return {"ok": False, "error": f"write failed: {e}"}
    lad = " / ".join(f"L{i+1} ${t:g} ({t/2.0:.0f}pt)" for i, t in enumerate(tg))
    # ★2026-09-03 was "on its next tick (~60s)". gazbot7-day-rider-buy.path now watches this file
    # and starts the rider on the inotify close-write — MEASURED at 1.35s to a completed tick, twice,
    # with the test write deliberately made off the `*:*:05` boundary so no timer tick could be
    # mistaken for it. The 60s tick stays the FLOOR if that unit is down.
    return {"ok": True, "msg": f"{side} {qty} lot(s) requested — the rider places it now (~1.4s; "
                               f"the 60s tick is the fallback).\n{lad}\n"
                               f"Total if all fill: ${sum(tg):g}. NO STOP; hard flat 20:40Z."}


# ── /api/shadow/* — the shadow desk (V5 shadow_desk.html verbatim; V7 data) ────
# ★★★2026-08-18 THE SIM NUMBER COMES FROM THE REGISTRY, FULL STOP.
# shadow.html numbered sims off a HARDCODED `_ID_ORDER` array whose index+1 was shown as "#".
# data/sim_registry.json is the authority (scripts/sim_registry.py allocates ids ONCE and persists
# them; the Friday report already reads it). The two had drifted until **51 of 57 names on the board
# were mislabelled** and 15 registered sims were missing from the array entirely.
# It is not cosmetic: the operator asked "is sim 23 the same tech as rgv_short", the board's #23 was
# rg_long_fast_v (registry #29) while the registry's #23 is exhaustion_rev, and a whole exchange was
# spent confidently answering about the wrong strategy. Two surfaces numbering one thing differently
# is the failure pnl.py exists to prevent — four V5 surfaces each summing P&L their own way.
_SIM_REGISTRY = f"{os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))}/data/sim_registry.json"


def sim_ids(path: str | None = None) -> dict:
    """{sim name -> stable registry id}. Empty dict on any failure — a missing id renders as "?",
    which is honest, where a positional fallback would silently invent a WRONG number."""
    try:
        with open(path or _SIM_REGISTRY) as fh:
            d = json.load(fh)
        ids = d.get("ids", d)
        return {k: int(v) for k, v in ids.items() if isinstance(v, int)}
    except Exception:
        return {}


def _shadow_block(vals):
    """The {n, real_pnl, win} block the shadow UI reads — honest net, win% or null."""
    n = len(vals)
    if n == 0:
        return {"n": 0, "real_pnl": 0, "win": None}
    return {"n": n, "real_pnl": round(sum(vals), 2),
            "win": round(100 * sum(1 for v in vals if v > 0) / n)}


def _paris_day_bounds(date_str):
    """(day_start, day_end) unix-seconds for the viewed Paris day (default: today)."""
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_PARIS)
    else:
        d = datetime.now(_PARIS)
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = start.timestamp()
    return day_start, day_start + 86400


def mgc_shadow_json(mgc_path, depth_path="/home/alphabot/gazbot7/data/depth.db"):
    """The GOLD shadow desk — its own board, because it is its own desk.

    ★★2026-08-16 (operator: "add a dashboard for mgc shadow? it needs its own").
    It cannot share /shadow: that board reads shadow.db and prices everything at MNQ's $2.00/pt.
    Gold is $10.00/pt in a SEPARATE store, and that separation is deliberate — reprice_pending()
    applies ONE multiplier to every pending trade, so a shared store would price gold at a fifth of
    reality, intermittently, decided by whichever service called first.

    ⚠ THIS BOARD'S JOB IS TO MAKE "ARMED BUT RECORDING NOTHING" VISIBLE. Three of the four blockers
    in MGC_SHADOW_SCOPE.md fail SILENTLY, and an armed variant that never fires looks exactly like a
    quiet tape. So every armed arm is listed even at zero, and the payload carries the two facts that
    tell those apart: whether the DEPTH FEED is fresh (the gates fail closed without a book) and how
    long since this desk recorded anything at all.
    """
    from .shadow import mgc_slate

    out = {"arms": [], "store": mgc_path, "vpp": 10.0,
           "fee_note": "repriced at $1.50/RT commission — the repricer already crosses both legs. "
                       "$4.50 is the MID-priced all-in and is NOT what is applied here.",
           "caveat": "The lab's +$1,387 / +$1,261 are DEPTH-MID numbers. This service folds md "
                     "TRADE bars and only 41% of the lab's fires exist on that tape. The forward "
                     "numbers below are the ones that count.",
           "depth_rows": 0, "depth_age_s": None, "last_trade_age_s": None, "recording": False}
    # web.py has no `time` import — it works in datetime throughout, so match that rather than
    # adding a second clock to the module.
    now = int(datetime.now(UTC).timestamp())
    armed = {v.name: v for v in mgc_slate()}
    rows = {}
    try:
        con = sqlite3.connect(f"file:{mgc_path}?mode=ro", uri=True, timeout=3.0)
        con.row_factory = sqlite3.Row
        # ⚠⚠ shadow_mgc.db HAS NO data_quality COLUMN. shadow.db does — it was ALTERed in by
        # scripts/quarantine_shadow_md_corruption.py, which only ever targeted the MNQ store. The
        # first version of this query filtered on it unconditionally and threw OperationalError on
        # EVERY request; the page then rendered "trades 0 / net $0.00 / NOTHING YET" — which is
        # indistinguishable from the true "armed but recording nothing" alarm this board exists to
        # raise. A broken instrument imitating its own alarm is the worst of both.
        cols = {r[1] for r in con.execute("PRAGMA table_info(shadow_trades)")}
        dq = "AND t.data_quality IS NULL" if "data_quality" in cols else ""
        out["data_quality_filtered"] = bool(dq)
        for r in con.execute(f"""
                SELECT t.strategy s, COUNT(*) n,
                       ROUND(SUM(r.real_pnl), 2) net, ROUND(AVG(r.real_pnl), 2) exp,
                       ROUND(AVG(CASE WHEN r.real_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) win,
                       MAX(t.exit_ts) last_ts
                FROM shadow_real r JOIN shadow_trades t ON t.id = r.trade_id
                WHERE r.fill_status = 'filled' {dq}
                GROUP BY t.strategy"""):
            rows[r["s"]] = dict(r)
        # ★★2026-08-18 THE TWO PANELS ON THIS PAGE READ TWO DIFFERENT SOURCES.
        # The arms table joins shadow_real (SCORED), the header's "last trade" reads shadow_trades
        # (RECORDED). The repricer runs on an interval, so between a sim closing and being repriced
        # the page truthfully says "last trade 1 minute ago" beside a table showing NOTHING — which
        # is exactly what the operator hit on the gold desk's first-ever sim (exit 18:33:00,
        # repriced 18:36:03, a 3-minute window). Neither number was wrong; the page just never said
        # they measure different things. Publish the gap so the UI can name it.
        pend = con.execute(
            "SELECT COUNT(*) FROM shadow_trades t LEFT JOIN shadow_real r ON r.trade_id = t.id "
            "WHERE r.trade_id IS NULL OR r.fill_status <> 'filled'").fetchone()[0]
        out["pending_reprice"] = int(pend or 0)
        out["recorded_total"] = con.execute("SELECT COUNT(*) FROM shadow_trades").fetchone()[0]
        o = con.execute("SELECT MAX(exit_ts) FROM shadow_trades").fetchone()[0]
        if o:
            out["last_trade_age_s"] = now - int(o)
            out["recording"] = (now - int(o)) < 86400 * 3
        con.close()
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    for name, v in armed.items():
        r = rows.get(name, {})
        out["arms"].append({
            "name": name, "side": v.side or "both",
            "control": name.endswith("_nobook"),
            "n": r.get("n", 0), "net": r.get("net", 0.0),
            "exp": r.get("exp", 0.0), "win": r.get("win", 0.0),
            "last_ts": r.get("last_ts"),
        })
    try:
        d = sqlite3.connect(f"file:{depth_path}?mode=ro", uri=True, timeout=3.0)
        n, mx = d.execute(
            "SELECT COUNT(*), MAX(ts_ms) FROM depth_snap WHERE symbol='MGC'").fetchone()
        out["depth_rows"] = n or 0
        if mx:
            out["depth_age_s"] = max(0, now - int(mx) // 1000)
        d.close()
    except Exception:
        pass
    return out


def _shadow_open_snapshot(shadow_path):
    """The sim's OPEN positions, from the snapshot ShadowSim publishes beside its store.

    Returns {} when there is no snapshot — and the caller must render that as UNKNOWN, never as
    "nothing open". Absence of a file is not evidence of an empty book.
    """
    try:
        with open(f"{shadow_path}.open.json") as fh:
            snap = json.load(fh)
        return {"ts": snap.get("ts"), "open": snap.get("open") or {}}
    except Exception:
        return {}


def shadow_overview_json(shadow_path, date=None):
    """Per-variant honest P&L (real_pnl, filled trades) over today/week/all, plus
    by-symbol — the shape shadow_desk.html renders. real_available always True in
    V7 (the repricer writes real_pnl; no ceiling-mirage fallback)."""
    from .cb import CB_STRATEGIES
    from .shadow import default_slate
    day_start, day_end = _paris_day_bounds(date)
    wk_start = day_end - 7 * 86400
    # registered fleet (shown even if idle) = the variant slate + the circuit-breaker legs
    # ★2026-08-04: + the CL- sims. They are driven by cl_sims.ClSims / scripts/cl_worker.py rather
    # than default_slate(), so building the fleet from the slate alone made them INVISIBLE on the
    # shadow board — they would not have appeared even once they started trading. Registered here so
    # they show (at zero) from the outset, which also means "CL sim not trading" is visible rather
    # than indistinguishable from "CL sim does not exist".
    from .cl_sims import CL_GATES
    fleet = [v.name for v in default_slate()] + list(CB_STRATEGIES) + list(CL_GATES)
    try:
        c = _conn(shadow_path)
        rows = c.execute(
            "SELECT st.strategy s, st.symbol sym, st.exit_ts ts, sr.real_pnl pnl "
            "FROM shadow_trades st JOIN shadow_real sr ON sr.trade_id=st.id "
            "WHERE sr.fill_status='filled'").fetchall()
        c.close()
    except Exception:
        rows = []
    # the board shows the REGISTERED fleet only — a variant culled from the slate
    # vanishes from the dashboard (its history stays in shadow.db for analysis).
    names = fleet
    fleet_set = set(fleet)
    agg = {s: {"today": [], "week": [], "all": [], "by_symbol": {}, "min_ts": None} for s in names}
    for r in rows:
        if r["s"] not in fleet_set:  # culled variant — excluded from the board + totals
            continue
        a = agg[r["s"]]
        ts, p = r["ts"], r["pnl"]
        if ts >= day_end:  # future relative to the viewed day
            continue
        bs = a["by_symbol"].setdefault(r["sym"], {"today": [], "week": [], "all": []})
        a["all"].append(p); bs["all"].append(p)
        a["min_ts"] = ts if a["min_ts"] is None else min(a["min_ts"], ts)
        if ts >= wk_start:
            a["week"].append(p); bs["week"].append(p)
        if day_start <= ts < day_end:
            a["today"].append(p); bs["today"].append(p)
    _ids = sim_ids()
    strategies = []
    for s in names:
        a = agg[s]
        strategies.append({
            "strategy": s, "armed": True, "sim_id": _ids.get(s),
            "days_live": None if a["min_ts"] is None else max(0, round((day_end - a["min_ts"]) / 86400)),
            "today": _shadow_block(a["today"]), "week": _shadow_block(a["week"]), "all": _shadow_block(a["all"]),
            "by_symbol": {sym: {"today": _shadow_block(b["today"]), "week": _shadow_block(b["week"]),
                                "all": _shadow_block(b["all"])} for sym, b in a["by_symbol"].items()},
        })
    return {
        "today_total": round(sum(sum(a["today"]) for a in agg.values()), 2),
        "week_total": round(sum(sum(a["week"]) for a in agg.values()), 2),
        "all_total": round(sum(sum(a["all"]) for a in agg.values()), 2),
        "n_strategies": len(names), "as_of": (date or datetime.now(_PARIS).strftime("%Y-%m-%d")),
        "real_available": True, "strategies": strategies,
        "sim_ids_source": "data/sim_registry.json", "sim_ids_loaded": len(_ids),
        # ★2026-08-18 open sim positions. shadow_trades records only on EXIT, so a variant sitting
        # in a trade and a variant not firing at all looked identical on this board. The snapshot is
        # published by ShadowSim on open/close beside the store.
        "open_positions": _shadow_open_snapshot(shadow_path),
    }


def shadow_activity_json(shadow_path, limit=50):
    """Most-recent filled shadow trades, honest net — the Activity tab feed."""
    try:
        c = _conn(shadow_path)
        rows = c.execute(
            "SELECT st.strategy, st.symbol, st.side, st.exit_ts, st.exit_reason, sr.real_pnl "
            "FROM shadow_trades st JOIN shadow_real sr ON sr.trade_id=st.id "
            "WHERE sr.fill_status='filled' ORDER BY st.exit_ts DESC, st.id DESC LIMIT ?",
            (limit,)).fetchall()
        c.close()
    except Exception:
        rows = []
    return {"trades": [{"exit_ts": r["exit_ts"], "strategy": r["strategy"], "symbol": r["symbol"],
                        "side": r["side"], "exit_reason": r["exit_reason"],
                        "pnl": round(r["real_pnl"], 2)} for r in rows]}


def tradeability_json(cap_path):
    """★2026-08-03 — the live 0-10 tape gauge (operator: "show me what we are currently sitting in").

    A GUIDE, not a gate: nothing arms or benches off this. Rolling, not day-cumulative, because the
    existing untradeable meter is cumulative and on 08-03 still read 37/TRADEABLE at 19:36 when ATR
    had collapsed to 9pt. Validated against the shadow book (the honest counterfactual for what the
    desk's mechanisms would have made): correlation +0.50 over 16 days, low-score days averaging
    -$1,904 of shadow P&L against +$612 for high-score days. Two known misses, 07-30 and 07-31 — both
    scored ~4.2 and lost >$3,000, so a good score is NOT permission to size up."""
    try:
        from .tradeability import live
        r = live(cap_path)
        return {"score": r.score, "label": r.label, "detail": r.detail,
                "er30": r.er30, "atr": r.atr,
                "components": {"efficiency": r.efficiency, "room": r.room,
                               "persistence": r.persistence}}
    except Exception as e:
        # a gauge that silently shows a stale number is worse than one that admits it cannot see
        return {"score": None, "label": "unavailable", "detail": str(e)}


def reports_json(static_dir):
    """List the weekly_<date>.html reports in web_static, newest first, with the
    <title> pulled from each file. The reports index reads this to render its cards."""
    import re
    out = []
    for fn in sorted(os.listdir(static_dir)):
        # ★2026-08-18 + "dossier": the product/architecture dossier is a report like any other and
        # belongs on the same index, with the same PDF-sibling convention.
        # ★2026-09-03 + "tunnel": the MGC compression study is a standalone research report and
        # belongs on the same index as the greenfield/gates pages, same dated-slug convention.
        # ★★2026-09-13 A WHITELIST MADE EVERY NEW REPORT INVISIBLE, SILENTLY. The operator could not
        # find three reports written for him in 24h (edge_hunt, promise, litreview) because the
        # pattern named five slugs and nothing else matched — the files WERE served at their URLs, so
        # every check of "is it published?" passed while the page he actually reads showed nothing.
        # Now it is a DENYLIST: any <slug>_<date>.html is a report unless it is a known sibling
        # (monday_ playbooks are rendered as the `play` link on another card) or a superseded copy.
        # A new report appears by DEFAULT; forgetting to register one can no longer hide it.
        m = re.match(r"([a-z0-9_]+)_(\d{4}-\d{2}-\d{2})\.html$", fn)
        if m and (m.group(1) in ("monday", "superseded_weekly") or "partial" in fn):
            continue
        if not m:
            continue
        title = fn
        try:
            head = open(os.path.join(static_dir, fn), encoding="utf-8").read(2000)
            tm = re.search(r"<title>(.*?)</title>", head, re.S)
            if tm:
                title = tm.group(1).strip()
        except OSError:
            pass
        pdf = fn[:-5] + ".pdf"  # weekly_<date>.pdf sibling, if a PDF was rendered
        has_pdf = os.path.exists(os.path.join(static_dir, pdf))
        play = "monday_" + m.group(2) + ".html"  # the Monday playbook for this week, if built
        has_play = os.path.exists(os.path.join(static_dir, play))
        out.append({"date": m.group(2), "file": fn, "title": title,
                    "pdf": pdf if has_pdf else None, "play": play if has_play else None})
    out.sort(key=lambda r: r["date"], reverse=True)
    # ★2026-08-13 PIN THE PROGRESS PAGE AT THE TOP. Operator: "put it on reports page."
    # It is not a dated archive like the weeklies — it is a LIVE page rebuilt from the trade record
    # every Friday, so it deliberately does not match the weekly_<date> pattern above and would
    # otherwise never appear. Pinned rather than dated because "is the desk getting better?" is
    # always a question about NOW; a reader should never have to pick which copy is current.
    # Fail-soft: if it has not been generated yet, the index renders exactly as before.
    if os.path.exists(os.path.join(static_dir, "progress.html")):
        out.insert(0, {"date": "live", "file": "progress.html", "pinned": True,
                       "title": "Are we getting better? — every day the desk has traded",
                       "pdf": None, "play": None})
    return {"reports": out}


# ── /api/cube/* — the daily-capture X-ray (market × session-phase grid) ────────
# Faithful V7 port of the retired V5 Cube: each cell = what the tape did (regime / flow
# from capture.db) + what we traded (P&L / gates from the store), sliced by session phase.
# Descriptive, NOT edge — a rough per-minute heuristic, not the courtroom verdict.
_CUBE_MARKETS = ["US"]
_CUBE_PHASES = ["overnight", "eu_session", "us_open", "us_midday", "us_pm"]


def _cube_iso_epoch(iso):
    """ISO-8601 text → epoch seconds (UTC-anchored; naive treated as UTC)."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _cube_paris_date(iso):
    """The Paris calendar date (YYYY-MM-DD) an ISO-8601 UTC instant falls on."""
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(_PARIS).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _session_phase(ts_epoch):
    """UTC session phase for an epoch timestamp (seconds; ms auto-normalised). Ported
    verbatim from V5 intelligence/session_phase.py — same UTC boundaries so the grid's
    time buckets match the desk's capture convention."""
    ts = float(ts_epoch)
    if ts > 1e12:  # milliseconds
        ts /= 1000.0
    dt = datetime.fromtimestamp(ts, tz=UTC)
    h = dt.hour + dt.minute / 60.0
    if h < 7.0 or h >= 22.0:
        return "overnight"
    if h < 13.5:
        return "eu_session"
    if h < 15.5:
        return "us_open"
    if h < 19.0:
        return "us_midday"
    return "us_pm"


def _paris_day_utc_bounds(date_str):
    """(start, end) UTC datetimes bracketing the Paris day ``date_str`` — DST-correct
    (each midnight localised independently, so a 23h/25h DST day is exact)."""
    d0 = datetime.strptime(date_str, "%Y-%m-%d")
    start = d0.replace(tzinfo=_PARIS).astimezone(UTC)
    end = (d0 + timedelta(days=1)).replace(tzinfo=_PARIS).astimezone(UTC)
    return start, end


def _cube_classify(bars):
    """Regime read for a phase's 5s bars: aggregate to 1-min windows, classify each window
    (dead / shock / trending / chop) by its range + own efficiency, return the dominant, the
    mix (pct), the window count (cycles) and mean net-move-in-ATR. Rough by design — MVP."""
    if not bars:
        return {"cycles": 0, "dominant_regime": None, "regime_mix": {}, "avg_net_atr": None}
    agg: dict = {}
    for b in bars:
        m = (b["bar_ts"] // 60) * 60
        a = agg.get(m)
        if a is None:
            agg[m] = [b["open"], b["high"], b["low"], b["close"]]
        else:
            a[1] = max(a[1], b["high"])
            a[2] = min(a[2], b["low"])
            a[3] = b["close"]
    windows = [agg[m] for m in sorted(agg)]
    cycles = len(windows)
    ranges = [w[1] - w[2] for w in windows]
    atr = (sum(ranges) / len(ranges)) if ranges else 0.0
    counts = {"trending": 0, "chop": 0, "shock": 0, "dead": 0}
    net_atrs = []
    for o, h, low, cl in windows:
        rng = h - low
        net = cl - o
        er = abs(net) / rng if rng > 1e-9 else 0.0
        # cutoffs calibrated to MNQ 1-min range percentiles (p10≈7pt, median≈13pt, p90≈29pt):
        # dead = the quietest ~decile, shock = the most violent ~decile, the rest split by efficiency.
        if rng < 6.0:
            reg = "dead"
        elif rng > 30.0:
            reg = "shock"
        elif er >= 0.5:
            reg = "trending"
        else:
            reg = "chop"
        counts[reg] += 1
        if atr > 1e-9:
            net_atrs.append(net / atr)
    dom = max(counts, key=lambda k: counts[k]) if cycles else None
    if dom and counts[dom] == 0:
        dom = None
    mix = {k: round(100.0 * v / cycles, 1) for k, v in counts.items() if v > 0} if cycles else {}
    avg_net_atr = round(sum(net_atrs) / len(net_atrs), 2) if net_atrs else None
    return {"cycles": cycles, "dominant_regime": dom, "regime_mix": mix, "avg_net_atr": avg_net_atr}


def cube_days_json(store_path):
    """Distinct Paris-days present in the trades store (by ``closed_at``), newest first —
    the day picker's option list."""
    days = set()
    try:
        c = _conn(store_path)
        rows = c.execute(
            "SELECT DISTINCT closed_at FROM trades WHERE symbol='MNQ' AND exit_reason NOT IN ("
            + ",".join("?" * len(_CLEANUP)) + ")" + _dq(c), tuple(_CLEANUP)).fetchall()
        c.close()
        for r in rows:
            d = _cube_paris_date(r["closed_at"])
            if d:
                days.add(d)
    except Exception:
        pass
    return {"days": sorted(days, reverse=True)}


def cube_json(store_path, cap_path, day):
    """The X-ray for one Paris day (or ``latest``): a dense market×phase grid + per-contract
    drill. Cells fuse the trades store (P&L / trades / win% / gates, phase-bucketed by
    ``opened_at``) with capture.db (regime + cycles from 5s ``bars``; signed-aggressor OFI
    from ``ticks``). ``themes`` is always null in V7 (no desk_analysis) — the UI degrades."""
    now = datetime.now(UTC)
    avail = cube_days_json(store_path)["days"]
    if day == "latest" or not day:
        day = avail[0] if avail else now.astimezone(_PARIS).strftime("%Y-%m-%d")
    try:
        start, end = _paris_day_utc_bounds(day)
    except Exception:
        day = now.astimezone(_PARIS).strftime("%Y-%m-%d")
        start, end = _paris_day_utc_bounds(day)

    phases = _CUBE_PHASES
    # --- what we traded: P&L / trades / wins / gates per phase (from the store) ---
    pnl_by_phase = {ph: {"pnl": 0.0, "n": 0, "w": 0, "gates": {}} for ph in phases}
    try:
        c = _conn(store_path)
        trows = c.execute(
            "SELECT opened_at, closed_at, pnl_usd, gate FROM trades WHERE symbol='MNQ' "
            "AND exit_reason NOT IN (" + ",".join("?" * len(_CLEANUP)) + ")" + _dq(c),
            tuple(_CLEANUP)).fetchall()
        c.close()
        for r in trows:
            if _cube_paris_date(r["closed_at"]) != day:  # same day-convention as available-days
                continue
            ph = _session_phase(_cube_iso_epoch(r["opened_at"]))
            b = pnl_by_phase[ph]
            b["pnl"] += r["pnl_usd"]
            b["n"] += 1
            if r["pnl_usd"] > 0:
                b["w"] += 1
            g = r["gate"] or "—"
            b["gates"][g] = b["gates"].get(g, 0) + 1
    except Exception:
        pass

    # --- what the tape did: FLOW (signed-aggressor OFI) per phase, aggregated in SQL ---
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    ofi_by_phase: dict = {}
    try:
        c = _conn(cap_path)
        hx = ("(CAST(strftime('%H', ts_ms/1000, 'unixepoch') AS REAL)"
              " + CAST(strftime('%M', ts_ms/1000, 'unixepoch') AS REAL)/60.0)")
        rows = c.execute(
            f"SELECT CASE WHEN {hx}<7.0 OR {hx}>=22.0 THEN 'overnight' "
            f"WHEN {hx}<13.5 THEN 'eu_session' WHEN {hx}<15.5 THEN 'us_open' "
            f"WHEN {hx}<19.0 THEN 'us_midday' ELSE 'us_pm' END phase, "
            f"SUM(CASE aggressor WHEN 'buy' THEN size WHEN 'sell' THEN -size ELSE 0 END) signed, "
            f"COUNT(*) n FROM ticks WHERE symbol='MNQ' AND ts_ms>=? AND ts_ms<? GROUP BY phase",
            (start_ms, end_ms)).fetchall()
        c.close()
        for r in rows:
            n = r["n"] or 0
            ofi_by_phase[r["phase"]] = (r["signed"] / n) if n else None
    except Exception:
        pass

    # --- what the tape did: REGIME + cycles + net-ATR per phase (from 5s bars) ---
    regime_by_phase = {ph: _cube_classify([]) for ph in phases}
    try:
        c = _conn(cap_path)
        brows = c.execute(
            "SELECT bar_ts, open, high, low, close FROM bars WHERE symbol='MNQ' "
            "AND timeframe='5s' AND bar_ts>=? AND bar_ts<? ORDER BY bar_ts",
            (int(start.timestamp()), int(end.timestamp()))).fetchall()
        c.close()
        buckets = {ph: [] for ph in phases}
        for b in brows:
            buckets[_session_phase(b["bar_ts"])].append(b)
        for ph, bars in buckets.items():
            regime_by_phase[ph] = _cube_classify(bars)
    except Exception:
        pass

    # --- assemble the dense grid + per-contract drill ---
    grid: dict = {"US": {}}
    drill: dict = {"US": {}}
    for ph in phases:
        reg = regime_by_phase[ph]
        pb = pnl_by_phase[ph]
        ofi = ofi_by_phase.get(ph)
        ofi = round(ofi, 2) if ofi is not None else None
        n = pb["n"]
        wr = (pb["w"] / n) if n else None
        grid["US"][ph] = {
            "cycles": reg["cycles"], "dominant_regime": reg["dominant_regime"],
            "regime_mix": reg["regime_mix"], "pnl": round(pb["pnl"], 2), "trades": n,
            "win_rate": wr, "avg_ofi": ofi,
        }
        if reg["cycles"] or n:
            drill["US"][ph] = [{
                "symbol": "MNQ", "dominant_regime": reg["dominant_regime"], "avg_ofi": ofi,
                "avg_net_atr": reg["avg_net_atr"], "cycles": reg["cycles"], "trades": n,
                "win_rate": wr, "pnl": round(pb["pnl"], 2), "gates": pb["gates"],
            }]
        else:
            drill["US"][ph] = []

    return {
        "day": day, "markets": _CUBE_MARKETS, "phases": phases, "grid": grid, "drill": drill,
        "themes": None,  # V7 has no desk_analysis — the frontend shows the "generate nightly" note
        "note": "Descriptive X-ray from capture + trades. Regime is a rough per-minute heuristic "
                "(range + efficiency), not the courtroom verdict.",
    }


def serve(port, store_path, cap_path, data_dir, shadow_path):
    class H(http.server.BaseHTTPRequestHandler):
        # 2026-07-22: drop a slow/dead client after this long so its thread is freed (a client that
        # gave up mid-response left a BrokenPipe + tied up the single thread → the whole page froze).
        timeout = 30

        def _send(self, body, ct, code=200):
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj):
            self._send(json.dumps(obj).encode(), "application/json")

        # ★★★2026-09-24 THE ORDER PATH IS NOW CLOSED TO SCRIPTS. On this date an assistant test of
        # the no-PIN flatten POSTed to /api/control/dayrider-claim and the rider flattened the
        # operator's live SHORT 4 THREE SECONDS LATER (trade 1019, -$842.50). It was the third time
        # in one session that a test touched a live position, and twice before it had been promised
        # it would not happen again. A promise is not a control.
        #
        # THE RULE: an endpoint that can move money must arrive FROM THE DASHBOARD. A browser
        # fetching from the page always sends a same-origin Referer (verified in nginx: every
        # button press carries "http://.../v7/"); curl sends none unless told to. So a bare curl —
        # which is every accidental call from a shell — is refused before it reaches the handler.
        #
        # ⚠ THIS IS NOT SECURITY. A Referer is trivially forged and it is not meant to stop an
        # attacker; it is meant to make the ACCIDENT impossible, which is the failure that actually
        # happened. Anything that legitimately needs to act without a browser writes the request
        # FILE directly (step_away.py does exactly that) and is unaffected.
        # ⚠ Only the paths that can OPEN OR CLOSE A POSITION are gated. `pass` and `clienterr`
        # record data and place nothing, so gating them would cost the sample for no safety.
        ORDER_PATHS = ("/api/control/claim", "/api/control/dayrider-buy",
                       "/api/control/dayrider-claim")

        def _from_dashboard(self) -> bool:
            ref = (self.headers.get("Referer") or self.headers.get("Origin") or "")
            return "/v7" in ref or ref.rstrip("/").endswith(":8087")

        def do_POST(self):
            try:
                path = urlparse(self.path).path
                n = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(n) if n else b""
                if path in self.ORDER_PATHS and not self._from_dashboard():
                    self._json({"ok": False, "error":
                                "refused: this endpoint can move money and must be called from the "
                                "dashboard, not a script. If you are a human and meant this, press "
                                "the button."})
                    return
                if path == "/api/control/claim":
                    self._json(claim_post(body, data_dir))
                elif path == "/api/control/dayrider-buy":
                    self._json(dayrider_buy_post(body, data_dir))
                elif path == "/api/control/dayrider-claim":
                    self._json(dayrider_claim_post(body, data_dir))
                elif path == "/api/control/pass":
                    self._json(operator_pass_post(body, data_dir))
                elif path == "/api/control/clienterr":
                    self._json(client_error_post(body, data_dir))
                elif path == "/api/control/step-away":
                    self._json(step_away_post(body, data_dir))
                else:
                    self._send(b"not found", "text/plain", 404)
            except Exception as e:
                self._send(f"error: {e}".encode(), "text/plain", 500)

        def do_GET(self):
            try:
                p = urlparse(self.path)
                path, qs = p.path, parse_qs(p.query)
                if path == "/" or path.startswith("/index"):
                    self._send(open(os.path.join(_STATIC, "app.html"), "rb").read(), _CT[".html"])
                elif path == "/shadow" or path == "/shadow/":
                    self._send(open(os.path.join(_STATIC, "shadow.html"), "rb").read(), _CT[".html"])
                elif path == "/reports" or path == "/reports/":
                    self._send(open(os.path.join(_STATIC, "reports.html"), "rb").read(), _CT[".html"])
                elif path == "/cube" or path == "/cube/":
                    self._send(open(os.path.join(_STATIC, "cube.html"), "rb").read(), _CT[".html"])
                elif path == "/router" or path == "/router/":
                    self._send(open(os.path.join(_STATIC, "router.html"), "rb").read(), _CT[".html"])
                elif path in ("/mgcshadow", "/mgcshadow/"):
                    self._send(open(os.path.join(_STATIC, "mgcshadow.html"), "rb").read(),
                               _CT[".html"])
                elif path.startswith("/api/mgcshadow"):
                    self._json(mgc_shadow_json(
                        os.environ.get("GAZBOT7_SHADOW_MGC",
                                       os.path.join(data_dir, "shadow_mgc.db"))))
                elif path.startswith("/api/futures/router"):
                    self._json(router_json(store_path, cap_path, data_dir))
                elif path.startswith("/api/futures/context"):
                    self._json(context_json(cap_path, data_dir, store_path))
                elif path.startswith("/api/futures/days"):
                    self._json(days_json(store_path, min(60, int(qs.get("n", ["14"])[0]))))
                elif path.startswith("/api/tradeability"):
                    self._json(tradeability_json(cap_path))
                elif path.startswith("/api/reports"):
                    self._json(reports_json(_STATIC))
                elif path.startswith("/api/cube/available-days"):
                    self._json(cube_days_json(store_path))
                elif path.startswith("/api/cube/"):
                    self._json(cube_json(store_path, cap_path, path.rsplit("/", 1)[-1]))
                elif path.startswith("/static/"):
                    fp = os.path.join(_STATIC, os.path.basename(path))
                    self._send(open(fp, "rb").read(), _CT.get(os.path.splitext(fp)[1], "text/plain"))
                elif path.startswith("/api/shadow/overview"):
                    self._json(shadow_overview_json(shadow_path, (qs.get("date", [None])[0])))
                elif path.startswith("/api/shadow/activity"):
                    self._json(shadow_activity_json(shadow_path, min(200, int(qs.get("limit", ["50"])[0]))))
                elif path.startswith("/api/futures/bars/"):
                    # ★2026-08-29 600 -> 1500. 600 minutes capped the chart at 10h, so a "since Paris midnight"
                    # view (22:00Z -> now, up to 23h) was impossible to request. 1500 covers a full CME
                    # session with room; the query reads count*12 5s rows, so 1500 is ~18k rows — fine.
                    self._json(bars_json(cap_path, min(1500, int(qs.get("count", ["120"])[0])),
                                         path.rsplit("/", 1)[-1]))
                elif path.startswith("/api/futures/us-terminal"):
                    self._json(us_terminal_json(cap_path, data_dir))
                elif path.startswith("/api/futures/tournament"):
                    self._json(tournament_json(store_path, data_dir, cap_path))
                elif path.startswith("/api/futures/promotion"):
                    self._json(promotion_json(shadow_path))
                elif path.startswith("/api/futures/mnq"):
                    self._json(mnq_json(store_path))
                elif path.startswith("/api/futures/execution"):
                    self._json(execution_json(store_path))
                else:
                    self._send(b"not found", "text/plain", 404)
            except Exception as e:
                self._send(f"error: {e}".encode(), "text/plain", 500)

        def log_message(self, *a):
            pass

    # THREADING: one request per thread so a slow query (e.g. a scan over a large capture.db) can't
    # block every other request and freeze the dashboard (2026-07-22). Each handler opens its own DB
    # connections per call (functions take paths, not shared conns) → thread-safe. daemon threads so
    # a stuck request can't block shutdown.
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), H)
    srv.daemon_threads = True
    srv.serve_forever()


def main():
    port = int(os.environ.get("GAZBOT7_WEB_PORT", "8087"))
    store = os.environ.get("GAZBOT7_STORE", "data/gazbot7.db")
    cap = os.environ.get("GAZBOT7_CAPTURE", "data/capture.db")
    data_dir = os.path.dirname(store) or "."
    shadow = os.environ.get("GAZBOT7_SHADOW", os.path.join(data_dir, "shadow.db"))
    serve(port, store, cap, data_dir, shadow)


if __name__ == "__main__":
    main()
