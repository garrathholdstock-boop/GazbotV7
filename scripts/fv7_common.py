#!/usr/bin/env python3
"""Shared helpers for the 2026-08-21 Friday-report section builders.

The six sections in this cycle that had no fragment on disk (part1_live, part1_5_rehab,
part2_shadow, part25_musings, part2_6_router_review, movement2_idle_gates) are rebuilt from
the week's own artefacts by scripts/fv7_*.py, all of which import this module.

Everything here obeys the desk's data contract, and it is worth restating because every one of
these constants has been got wrong in a shipped harness before:

    FEE = $1.50 per ROUND TRIP per lot   (never $5, never per side)
    VPP = $2.00 per point on MNQ         (MGC is $10.00 — priced separately in the p25 section)
    capture.db is a ROLLING WINDOW       (5 trading days of ticks/quotes/book, 60 of bars) —
                                          fine for THIS week, wrong for anything older
    data_quality IS NULL                 for the strategy book; the FLAGGED book is the cash
                                          book and reconciles to IB (see hour-watch/desk_view)
"""
from __future__ import annotations

import datetime as dt
import html
import sqlite3

ROOT = "/home/alphabot/gazbot7"
DESK_DB = f"{ROOT}/data/gazbot7.db"
SHADOW_DB = f"{ROOT}/data/shadow.db"
CAP_DB = f"{ROOT}/data/capture.db"
SEC = f"{ROOT}/reports/friday_v7/sections"

FEE = 1.50      # per lot, per round trip
VPP = 2.00      # MNQ dollars per point
MGC_VPP = 10.0  # gold dollars per point — never price MGC with VPP

WEEK_LO = "2026-08-17"
WEEK_HI = "2026-08-22"          # exclusive
WEEK_LO_TS = int(dt.datetime(2026, 8, 17, tzinfo=dt.UTC).timestamp())
WEEK_HI_TS = int(dt.datetime(2026, 8, 22, tzinfo=dt.UTC).timestamp())

DAYS = ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]
DAYNAME = {"2026-08-17": "Mon 17 Aug", "2026-08-18": "Tue 18 Aug", "2026-08-19": "Wed 19 Aug",
           "2026-08-20": "Thu 20 Aug", "2026-08-21": "Fri 21 Aug"}


# ────────────────────────────────────────────────────────────────────────────────── formatting

def esc(s) -> str:
    return html.escape(str(s))


def m(v) -> str:
    """Money, with the sign carried in the text rather than only in a colour."""
    if v is None:
        return "&mdash;"
    v = float(v)
    return f"&minus;${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def m0(v) -> str:
    if v is None:
        return "&mdash;"
    v = float(v)
    return f"&minus;${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def pct(v, d=0) -> str:
    return "&mdash;" if v is None else f"{v:.{d}f}%"


def cls(v) -> str:
    """Row shading class used by the report shell."""
    if v is None:
        return ""
    return ' class="row-bad"' if float(v) < 0 else (' class="row-hl"' if float(v) > 0 else "")


def table(headers, rows, foot=None, note=None, numeric=None) -> str:
    """headers: list[str]; rows: list[list[str]] (already-escaped HTML); numeric: set of col idx."""
    numeric = numeric or set()
    th = "".join(f'<th class="{"num" if i in numeric else "ln"}">{h}</th>'
                 for i, h in enumerate(headers))
    body = []
    for r in rows:
        rowcls = ""
        if r and isinstance(r[0], tuple):      # ('class', cells...) form
            rowcls, r = r[0][1], list(r[1:])
            rowcls = f' class="{rowcls}"' if rowcls else ""
        tds = "".join(f'<td class="{"num" if i in numeric else "ln"}">{c}</td>'
                      for i, c in enumerate(r))
        body.append(f"<tr{rowcls}>{tds}</tr>")
    f = ""
    if foot:
        f = ("<tfoot><tr>" + "".join(
            f'<td class="{"num" if i in numeric else "ln"}"><strong>{c}</strong></td>'
            for i, c in enumerate(foot)) + "</tr></tfoot>")
    n = f'<p class="ln">{note}</p>' if note else ""
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody>{f}</table>{n}"


def callout(title, *paras, kind="callout") -> str:
    body = "".join(f"<p>{p}</p>" for p in paras)
    return f'<div class="{kind}"><div class="ct">{title}</div>{body}</div>'


def correction(title, *paras) -> str:
    return callout(title, *paras, kind="rev3")


def pill(tier: str) -> str:
    k = {"LIVE": "pill-live", "SHADOW": "pill-shadow", "PARKED": "pill-parked",
         "REFUTED": "pill-dontarm", "FIXED": "pill-live", "NULL": "pill-null",
         "HOLD": "pill-live", "FAULT": "pill-dontarm"}.get(tier.split()[0].upper(), "")
    return f'<span class="tag {k}">{esc(tier)}</span>'


def disposition(rows) -> str:
    """rows: (lead, verdict, the required sentence). Every section ends with one of these."""
    out = [[pill(v).join(("", "")) if False else f"<strong>{esc(lead)}</strong>", pill(v), req]
           for lead, v, req in rows]
    return ("<h3>Disposition &mdash; every lead this section touched</h3>"
            + table(["Lead", "Verdict", "For PARKED: what would revive it. For REFUTED: the test "
                     "that killed it."], out))


# ───────────────────────────────────────────────────────────────────────────────────── the tape

class Tape:
    """MNQ ticks out of capture.db for one window. The week 08-17..08-21 is entirely inside the
    5-trading-day rolling window, verified by the caller before any of this is trusted."""

    def __init__(self, t0: float, t1: float):
        con = sqlite3.connect(f"file:{CAP_DB}?mode=ro", uri=True)
        self.rows = con.execute(
            "SELECT ts_ms/1000.0, price FROM ticks WHERE symbol='MNQ' AND ts_ms>=? AND ts_ms<=? "
            "ORDER BY ts_ms", (int(t0 * 1000), int(t1 * 1000))).fetchall()
        con.close()

    def slice(self, t0, t1):
        return [(t, p) for t, p in self.rows if t0 <= t <= t1]


def minute_atr14(ts: float, con: sqlite3.Connection | None = None) -> float | None:
    """ATR-14 on 1-minute bars ending at the minute BEFORE ts, built from capture.db's 5s bars.

    ⚠ This is a local reconstruction, not the desk's own logged atr=. It matches in quiet tape
    and runs HOT through the 13:30 open, so every number derived from it is quoted as an
    estimate and never as the gate's own floor test.
    """
    own = con is None
    if own:
        con = sqlite3.connect(f"file:{CAP_DB}?mode=ro", uri=True)
    t_end = int(ts // 60 * 60)
    t_start = t_end - 60 * 60          # an hour of 5s bars is plenty for 14 one-minute bars
    rows = con.execute(
        "SELECT bar_ts, high, low, close FROM bars WHERE symbol='MNQ' AND bar_ts>=? AND bar_ts<? "
        "ORDER BY bar_ts", (t_start, t_end)).fetchall()
    if own:
        con.close()
    mins: dict[int, list] = {}
    for bt, h, lo, c in rows:
        k = bt // 60 * 60
        if k not in mins:
            mins[k] = [h, lo, c]
        else:
            mins[k][0] = max(mins[k][0], h)
            mins[k][1] = min(mins[k][1], lo)
            mins[k][2] = c
    keys = sorted(mins)[-15:]
    if len(keys) < 15:
        return None
    trs = []
    for i in range(1, len(keys)):
        h, lo, _ = mins[keys[i]]
        pc = mins[keys[i - 1]][2]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return sum(trs[-14:]) / 14


def race(ticks, side: str, entry: float, stop_pt: float, target_pt: float, t_cap: float):
    """First-touch race between a stop and a target on the real tick path.

    Returns (exit_price, why, exit_ts). Sequential, one position, no look-ahead: the first level
    the tape touches wins. Where both would be inside one tick's gap the STOP wins — the
    pessimistic convention, because a hopeful tie is how a repricer beats the desk on paper.
    """
    sgn = 1.0 if side == "LONG" else -1.0
    stop = entry - sgn * stop_pt
    targ = entry + sgn * target_pt
    last = entry
    for t, p in ticks:
        if t > t_cap:
            break
        last = p
        if sgn * (stop - p) >= 0:
            return stop, "STOP", t
        if sgn * (p - targ) >= 0:
            return targ, "TARGET", t
    return last, "CAP", t_cap


def usd(side: str, entry: float, exit_: float, qty: float = 1.0) -> float:
    sgn = 1.0 if side == "LONG" else -1.0
    return round(sgn * (exit_ - entry) * VPP * qty - FEE * qty, 2)


def excursion(ticks, side: str, entry: float):
    """MFE / MAE in points, INSIDE the trade's own life only — a favourable excursion after the
    trade is closed is money we were flat for, and counting it accuses our own book."""
    sgn = 1.0 if side == "LONG" else -1.0
    mfe = mae = 0.0
    for _t, p in ticks:
        d = sgn * (p - entry)
        mfe = max(mfe, d)
        mae = min(mae, d)
    return round(mfe, 2), round(mae, 2)


# ───────────────────────────────────────────────────────────────────────────────────── the book

def week_trades(clean=True):
    con = sqlite3.connect(f"file:{DESK_DB}?mode=ro", uri=True)
    q = ("SELECT id,gate,side,qty,entry_price,exit_price,opened_at,closed_at,"
         "pnl_usd,fees_usd,exit_reason,data_quality FROM trades "
         "WHERE closed_at>=? AND closed_at<? ")
    q += "AND data_quality IS NULL " if clean else ""
    rows = [dict(zip(("id", "gate", "side", "qty", "entry", "exit", "opened", "closed",
                      "gross", "fees", "why", "dq"), r))
            for r in con.execute(q + "ORDER BY closed_at", (WEEK_LO, WEEK_HI))]
    con.close()
    for r in rows:
        r["net"] = round(r["gross"] - r["fees"], 2)
        r["day"] = r["closed"][:10]
        r["t_in"] = dt.datetime.fromisoformat(r["opened"]).timestamp()
        r["t_out"] = dt.datetime.fromisoformat(r["closed"]).timestamp()
        r["base"] = r["gate"][:-2] if r["gate"].endswith(("_A", "_B")) else r["gate"]
        r["leg"] = r["gate"][-1] if r["gate"].endswith(("_A", "_B")) else ""
    return rows


def strip_best(vals, k=1):
    v = sorted(vals, reverse=True)
    return round(sum(v[k:]), 2)


def lodo(rows, keyf=lambda r: r["day"], valf=lambda r: r["net"]):
    """Leave-one-day-out: the WORST day-removed total. If a result only exists because of one
    session it shows up here and nowhere else."""
    days = sorted({keyf(r) for r in rows})
    if len(days) < 2:
        return None
    return round(min(sum(valf(r) for r in rows if keyf(r) != d) for d in days), 2)


def write(fname: str, body: str):
    import pathlib
    p = pathlib.Path(SEC) / fname
    p.write_text(body)
    print(f"→ {p}  ({len(body):,} bytes)")
