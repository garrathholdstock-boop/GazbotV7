#!/usr/bin/env python3
"""DRIFT PERSISTENCE — once the day-rider's detector CONFIRMS, how often does the day stay that way?

Operator, 2026-08-18: "use our confirmation formula and go back 10 years of public MNQ data and see
what % of days once our thresholds are met how often does it stay in that direction".

★ THE EXISTING NUMBER IS 71% ON 31 SESSIONS (drift.py's own docstring: 22 persisted, 9 reversed),
measured on THIS desk's tape. That is the number to try to break, not to confirm.

★ SYMBOL. 10 years of MNQ does not exist — MNQ launched 2019-05-06. NQ (E-mini) has traded since
1999 and is the SAME index at the SAME price, 1/10 the notional, so for a DIRECTION study they are
interchangeable. NQ carries the 10-year span; MNQ is pulled over its own life as a cross-check that
the two agree. If they disagree, that is a finding, not a nuisance.

★ CAUSAL. drift.compute() is called minute by minute from 13:30Z on bars 13:30..t only. Nothing may
see forward. And it reads `confirmed`, NEVER `ok` — gating on `ok` once invented a +12.5pp edge here.

★ THE REAL DETECTOR IS CALLED, never re-derived. A hand-rolled drift detector missing MIN_BARS=9 once
fabricated a +$819 counterfactual on this desk.

★ RESUMABLE BY CONSTRUCTION. One parquet per contract-month; a run skips what is already on disk, so
this survives being cut off by the 22:00 reopen and continues at the next halt. The artifact IS the
checkpoint — the Friday-report lesson.

⚠ THE BOX IS 7.5GB WITH THREE LOGGED OOM KILLS. Bars are streamed to parquet per request and never
accumulated in memory. 10y of 1-min NQ is ~3.4M rows; held as python objects that is >1GB.

⚠ IT SHARES THE LIVE TRADING GATEWAY. Preflight REFUSES to run unless the desk is flat and the venue
is halted. readonly=True, its own clientId, and no order path is imported.
"""
from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import os
import sys
import time

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
OUT = f"{GB}/data/driftlab"
CLIENT_ID = 77
PACE_S = 10.5                      # 60 historical reqs / 10 min is the hard limit; stay under it
MONTHS = {3: "H", 6: "M", 9: "U", 12: "Z"}

def log(m: str) -> None:
    print(f"{dt.datetime.now(dt.UTC):%H:%M:%S} {m}", flush=True)

def preflight(force: bool = False) -> tuple[bool, str]:
    """The desk owns this gateway. Never compete with a live position for it.

    Returns (ok, kind). kind="declined" means a CORRECT refusal on an expected desk state — the
    caller exits 0, because a unit sitting red for behaving properly is the alarm-outage pattern
    ([[a-correct-decision-repeated-every-tick-is-an-alarm-outage]]) and trains the operator to
    ignore `systemctl --failed`. kind="error" is a genuine fault and exits non-zero.
    """
    try:
        h = json.load(open(f"{GB}/data/core_health.json"))
        flat = bool(h.get("flat", False))
    except Exception as e:
        log(f"ABORT: cannot read core_health.json ({e})")
        return (False, "error")
    try:
        rid = json.load(open(f"{GB}/data/day_rider_state.json"))
        rider_open = bool(rid.get("entered")) and not bool(rid.get("closed"))
    except Exception:
        rider_open = False
    now = dt.datetime.now(dt.UTC)
    halted = (now.weekday() == 4 and now.hour >= 21) or now.weekday() == 5 \
        or (now.weekday() == 6 and now.hour < 22) or (now.weekday() <= 3 and now.hour == 21)
    log(f"preflight: tournament_flat={flat} rider_open={rider_open} venue_halted={halted}")
    if rider_open and not force:
        log("DECLINED: the day rider holds a position — not touching the gateway")
        return (False, "declined")
    if not flat and not force:
        log("DECLINED: tournament is not flat")
        return (False, "declined")
    if not halted and not force:
        log("DECLINED: venue is OPEN — runs inside the 21:00-22:00Z halt or at the weekend")
        return (False, "declined")
    return (True, "ok")


def contracts(symbol: str, years: int, today: dt.date):
    """Quarterly contracts covering `years` back, each with the window it was front month.

    A contract is front month for the quarter ENDING at its expiry, so the pull window is
    [expiry-3mo, expiry-1wk] — stopping a week early avoids the roll, where volume migrates and the
    front month's tape stops being the market's tape.
    """
    out = []
    y0 = today.year - years
    for y in range(y0, today.year + 1):
        for m, code in MONTHS.items():
            exp = dt.date(y, m, 18)                       # 3rd-Friday-ish; only used to window
            start = exp - dt.timedelta(days=90)
            end = exp - dt.timedelta(days=7)
            if end >= today or start.year < y0:
                continue
            out.append({"code": f"{symbol}{code}{str(y)[-1]}", "symbol": symbol,
                        "ym": f"{y}{m:02d}", "start": start, "end": end})
    return out


async def pull(ib, spec, whatToShow="TRADES"):
    """Stream one contract's active window to parquet, one request per day, resumable.

    ⚠ 1 REQUEST PER DAY, not per week. IBKR's duration ceiling for 1-min bars is inconsistent across
    contracts and a too-large ask returns a SHORT result rather than an error — a silent truncation
    that would look like thin days. One day per request is slower and cannot lie.
    """
    from ib_async import Future
    path = f"{OUT}/{spec['symbol']}_{spec['ym']}.parquet"
    if os.path.exists(path):
        return ("skip", path, 0)
    # ★★★2026-08-18 includeExpired=True IS MANDATORY. Without it every EXPIRED contract fails to
    # resolve, so a 10-year walk backwards returns nothing at all — which is what this job was about
    # to do on its first run. And qualifyContractsAsync returns a list that can contain None: `if
    # not q` is True for [] but FALSE for [None], so the None then blows up downstream as an
    # AttributeError that reads like "IBKR has no data". It is not; it is an unresolved contract.
    con = Future(symbol=spec["symbol"], exchange=spec.get("exchange", "CME"), currency="USD",
                 lastTradeDateOrContractMonth=spec["ym"], includeExpired=True)
    try:
        q = [c for c in (await ib.qualifyContractsAsync(con) or []) if c is not None]
        if not q:
            return ("no-contract", path, 0)
    except Exception as e:
        return (f"qualify-fail {str(e)[:60]}", path, 0)
    rows, d = [], spec["start"]
    while d <= spec["end"]:
        if d.weekday() < 5:
            end_s = dt.datetime(d.year, d.month, d.day, 21, 30, tzinfo=dt.UTC).strftime("%Y%m%d-%H:%M:%S")
            try:
                bars = await ib.reqHistoricalDataAsync(
                    q[0], endDateTime=end_s, durationStr="1 D", barSizeSetting="1 min",
                    whatToShow=whatToShow, useRTH=False, formatDate=2)
                for b in bars:
                    rows.append((int(b.date.timestamp()), float(b.open), float(b.high),
                                 float(b.low), float(b.close), float(b.volume)))
            except Exception as e:
                log(f"    {spec['code']} {d}: {str(e)[:70]}")
            await asyncio.sleep(PACE_S)
        d += dt.timedelta(days=1)
    if not rows:
        return ("empty", path, 0)
    rows = sorted(set(rows))                    # ts-unique, ordered
    n = _write_parquet(rows, path)
    del rows                                    # do not let a 10-year loop accumulate
    return ("ok", path, n)



def _write_parquet(rows, path) -> int:
    """DuckDB COPY, not pandas.to_parquet — THIS BOX HAS NO pyarrow/fastparquet, so to_parquet
    raises ImportError. Caught by smoke-testing before the unattended run rather than at 21:05.
    Same mechanism tape_mirror.py uses, including its row-count verification after the write.
    """
    import duckdb
    import pandas as pd
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    c = duckdb.connect()
    c.register("t", df)
    c.execute(f"COPY (SELECT * FROM t ORDER BY ts) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
    n = c.execute(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()[0]
    c.close()
    return int(n)


def _read_parquet(paths):
    import duckdb
    c = duckdb.connect()
    lst = "[" + ",".join(f"'{x}'" for x in paths) + "]"
    df = c.execute(f"SELECT * FROM read_parquet({lst}) ORDER BY ts").df()
    c.close()
    return df.drop_duplicates("ts")


def _minute_bars(df, day: dt.date):
    """(ts, high, low, close) minute bars for 13:30..21:00Z — the shape drift.compute() expects."""
    lo = dt.datetime(day.year, day.month, day.day, 13, 30, tzinfo=dt.UTC).timestamp()
    hi = dt.datetime(day.year, day.month, day.day, 21, 0, tzinfo=dt.UTC).timestamp()
    d = df[(df.ts >= lo) & (df.ts < hi)]
    return [(int(r.ts), float(r.high), float(r.low), float(r.close)) for r in d.itertuples()]


def our_minute_bars(day: dt.date):
    """Our OWN 5s tape folded to minute bars — the exact input drift was calibrated on.

    ⚠ DuckDB, not a correlated sqlite subquery. The first version of this was
    `(SELECT close ... ORDER BY bar_ts DESC LIMIT 1)` per minute, which is O(n^2) and hung past two
    minutes on one month of 5s bars — it would have wedged this job at 21:05 with nobody watching.
    ⚠ CAST(bar_ts/60 AS INT)*60, never bar_ts/60*60: DuckDB `/` is FLOAT and that is a silent no-op
    which once read 5s bars as "1m" for hours.
    """
    import duckdb
    lo = dt.datetime(day.year, day.month, day.day, 13, 30, tzinfo=dt.UTC).timestamp()
    hi = dt.datetime(day.year, day.month, day.day, 21, 0, tzinfo=dt.UTC).timestamp()
    c = duckdb.connect()
    c.execute(f"ATTACH '{GB}/data/capture.db' AS cap (TYPE sqlite, READ_ONLY)")
    q = c.execute("""
        SELECT CAST(bar_ts/60 AS INT)*60 AS t, MAX(high), MIN(low), arg_max(close, bar_ts)
        FROM cap.bars WHERE symbol='MNQ' AND bar_ts >= ? AND bar_ts < ?
        GROUP BY t ORDER BY t""", [lo, hi]).fetchall()
    c.close()
    return [(int(a), float(b), float(cc), float(d)) for a, b, cc, d in q]


def validate(limit_days: int = 30) -> dict:
    """★ THE CHECK THAT DECIDES WHETHER ANY OF THIS IS TRUSTWORTHY.

    drift's thresholds were calibrated on MINUTE BARS AGGREGATED FROM 5s — our capture. This study
    feeds IBKR's own 1-min bars. If those two disagree, every percentage below is measuring IBKR's
    tape, not the desk's, and the answer does not transfer. [[the-labs-tape-is-not-productions-tape]]
    So: on every overlapping day, run the REAL detector on both and compare.
    """
    import glob
    import duckdb
    from gazbot7.drift import compute
    if not os.path.exists(f"{GB}/data/capture.db"):
        return {"status": "no capture.db"}
    files = sorted(glob.glob(f"{OUT}/*.parquet"))
    if not files:
        return {"status": "no parquet pulled yet"}
    ext = _read_parquet(files)
    c = duckdb.connect()
    c.execute(f"ATTACH '{GB}/data/capture.db' AS cap (TYPE sqlite, READ_ONLY)")
    days = [r[0] for r in c.execute(
        "SELECT DISTINCT CAST(to_timestamp(bar_ts) AS DATE) d FROM cap.bars "
        "WHERE symbol='MNQ' ORDER BY d").fetchall()][-limit_days:]
    c.close()
    rows = []
    for day in days:
        ours = our_minute_bars(day)
        theirs = _minute_bars(ext, day)
        if len(ours) < 30 or len(theirs) < 30:
            continue
        a, b = compute(ours), compute(theirs)
        rows.append({"day": str(day), "our_min": len(ours), "ext_min": len(theirs),
                     "our_dir": a.direction, "ext_dir": b.direction,
                     "our_eff": round(a.efficiency, 3), "ext_eff": round(b.efficiency, 3),
                     "our_conf": a.confirmed, "ext_conf": b.confirmed,
                     "agree": a.direction == b.direction and a.confirmed == b.confirmed})
    n = len(rows)
    ag = sum(r["agree"] for r in rows)
    return {"status": "ok", "days": n, "agree": ag,
            "agree_pct": round(100 * ag / n, 1) if n else None, "rows": rows}


def replay() -> dict:
    """Causal minute-by-minute replay. For each day: the FIRST minute drift.compute() reports
    `confirmed`, then whether the day stayed that way.

    ★ TWO DEFINITIONS OF "STAYED", REPORTED SEPARATELY, because they are not the same question and
    conflating them is how a study flatters itself:
      DRIFT_HELD  the day's close is on the same side of the 13:30 OPEN as the confirmed direction.
                  This is what drift.py's 71% measures.
      ENTRY_PAID  the close is beyond the price AT CONFIRMATION in that direction — i.e. what the
                  day rider, which enters at confirmation, actually experiences. This is the
                  tradeable question and it is always the weaker of the two.
    Both are reported at the rider's real 20:40Z hard flat AND at the 21:00Z close.
    """
    import glob
    import pandas as pd
    from gazbot7.day_rider import ENTRY_CUTOFF_MIN
    from gazbot7.drift import MIN_BARS, OPEN_UTC_MIN, compute
    files = sorted(glob.glob(f"{OUT}/*.parquet"))
    if not files:
        return {"status": "no data"}
    per_sym = {}
    for f in files:
        sym = os.path.basename(f).split("_")[0]
        per_sym.setdefault(sym, []).append(f)
    res = {}
    for sym, fs in per_sym.items():
        df = _read_parquet(fs)
        df["day"] = pd.to_datetime(df.ts, unit="s", utc=True).dt.date
        days = sorted(df.day.unique())
        out = []
        for day in days:
            bars = _minute_bars(df[df.day == day], day)
            if len(bars) < 120:                 # a stub session cannot answer the question
                continue
            # ★ THE SCAN STOPS AT THE RIDER'S ENTRY CUTOFF (15:00Z), not at the close.
            # A first cut scanned to 21:00 and reported 100% of days "confirmed" — true, and
            # meaningless: given ~450 minutes SOME minute crosses the thresholds, but the rider
            # cannot act on a 19:00Z confirmation. day_rider.py: "no new entry after this ...
            # across all 31 validated sessions the detector confirmed between 13:38 and 14:09".
            # Measuring confirmations the desk would never trade is measuring a different strategy.
            max_i = min(len(bars), ENTRY_CUTOFF_MIN - OPEN_UTC_MIN)
            conf = None
            for i in range(MIN_BARS, max_i + 1):
                r = compute(bars[:i])
                if r.confirmed:                 # ⚠ `confirmed`, never `ok`
                    conf = (i, r.direction, bars[i - 1][3], bars[0][3])
                    break
            if not conf:
                out.append({"day": str(day), "confirmed": False})
                continue
            i, d, px_conf, px_open = conf
            sgn = 1 if d == "UP" else -1
            def px_at(hh, mm):
                want = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=dt.UTC).timestamp()
                pri = [b for b in bars if b[0] <= want]
                return pri[-1][3] if pri else bars[-1][3]
            c2040, c2100 = px_at(20, 40), px_at(21, 0)
            out.append({"day": str(day), "confirmed": True, "minute": i, "dir": d,
                        "drift_held_2040": (c2040 - px_open) * sgn > 0,
                        "drift_held_2100": (c2100 - px_open) * sgn > 0,
                        "entry_paid_2040": (c2040 - px_conf) * sgn > 0,
                        "entry_paid_2100": (c2100 - px_conf) * sgn > 0,
                        "pt_2040": round((c2040 - px_conf) * sgn, 2),
                        "year": str(day)[:4]})
        res[sym] = out
    return {"status": "ok", "by_symbol": res}


def report(rep: dict) -> str:
    if rep.get("status") != "ok":
        return f"no report: {rep}"
    L = []
    for sym, rows in rep["by_symbol"].items():
        c = [r for r in rows if r.get("confirmed")]
        L.append(f"\n{'='*72}\n{sym}: {len(rows)} sessions, {len(c)} confirmed "
                 f"({100*len(c)/max(len(rows),1):.1f}% of days fire at all)")
        if not c:
            continue
        for k, lab in (("drift_held_2100", "DRIFT_HELD to 21:00 (drift.py's 71% metric)"),
                       ("drift_held_2040", "DRIFT_HELD to 20:40 (rider's hard flat)"),
                       ("entry_paid_2100", "ENTRY_PAID to 21:00 — the tradeable one"),
                       ("entry_paid_2040", "ENTRY_PAID to 20:40 — what the rider lives")):
            n = sum(r[k] for r in c)
            L.append(f"   {lab:<48} {n:4d}/{len(c):<4d} = {100*n/len(c):5.1f}%")
        L.append("   by year (ENTRY_PAID to 20:40):")
        for y in sorted({r["year"] for r in c}):
            ys = [r for r in c if r["year"] == y]
            n = sum(r["entry_paid_2040"] for r in ys)
            L.append(f"      {y}  {n:3d}/{len(ys):<3d} = {100*n/len(ys):5.1f}%   "
                     f"median {sorted(r['pt_2040'] for r in ys)[len(ys)//2]:+.1f}pt")
        for d in ("UP", "DOWN"):
            ds = [r for r in c if r["dir"] == d]
            if ds:
                n = sum(r["entry_paid_2040"] for r in ds)
                L.append(f"   {d:<5} {n:4d}/{len(ds):<4d} = {100*n/len(ds):5.1f}%")
        med = sorted(r["minute"] for r in c)[len(c) // 2]
        tot = 13 * 60 + 30 + med - 1
        L.append(f"   median confirmation: minute {med} of the session = {tot//60:02d}:{tot%60:02d}Z"
                 f"   (drift.py's sweep plateaus 9-12, peak 10)")
    return "\n".join(L)


async def do_pull(years: int, symbols, deadline_ts: float, force: bool):
    from ib_async import IB, util
    util.logToConsole(50)
    ib = IB()
    await ib.connectAsync("127.0.0.1", 4002, clientId=CLIENT_ID, timeout=25, readonly=True)
    log(f"connected readonly clientId={CLIENT_ID}")
    today = dt.date.today()
    todo = []
    for s in symbols:
        todo += contracts(s, years, today)
    todo.sort(key=lambda c: c["ym"], reverse=True)     # newest first: partial data is still useful
    done = skipped = 0
    for c in todo:
        if time.time() > deadline_ts:
            log(f"DEADLINE reached — stopping cleanly with {done} pulled, resumable")
            break
        st, path, n = await pull(ib, c)
        if st == "skip":
            skipped += 1
        else:
            log(f"  {c['code']} {c['ym']}: {st} ({n} rows)")
            done += 1
    ib.disconnect()
    log(f"pull finished: {done} contracts written, {skipped} already on disk")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--symbols", default="NQ,MNQ")
    ap.add_argument("--minutes", type=int, default=50, help="wall-clock budget; halt is 60min")
    ap.add_argument("--phase", default="all", choices=["pull", "validate", "replay", "all"])
    ap.add_argument("--force", action="store_true", help="bypass preflight (NOT for a live session)")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    deadline = time.time() + a.minutes * 60
    if a.phase in ("pull", "all"):
        ok, kind = preflight(a.force)
        if not ok:
            sys.exit(0 if kind == "declined" else 1)
        asyncio.run(do_pull(a.years, [s.strip() for s in a.symbols.split(",")], deadline, a.force))
    if a.phase in ("validate", "all"):
        v = validate()
        json.dump(v, open(f"{OUT}/_validation.json", "w"), indent=1)
        log(f"VALIDATION vs our own 5s-aggregated tape: {v.get('agree')}/{v.get('days')} days agree "
            f"({v.get('agree_pct')}%)")
        if v.get("status") == "ok" and v.get("days", 0) >= 5 and (v.get("agree_pct") or 0) < 90:
            log("⚠ FEED DISAGREES WITH OUR TAPE — the persistence numbers below describe IBKR's "
                "bars, not the desk's. Do not act on them until this is explained.")
    if a.phase in ("replay", "all"):
        rep = replay()
        json.dump(rep, open(f"{OUT}/_persistence.json", "w"), indent=1, default=str)
        txt = report(rep)
        open(f"{OUT}/_REPORT.txt", "w").write(txt)
        print(txt)


if __name__ == "__main__":
    main()
