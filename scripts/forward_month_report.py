#!/usr/bin/env python3
"""FORWARD-MONTH REPORT — one page per trading day: the snake, where we got in and out, and why.

Operator, 2026-10-07: "make me a report on June. 1 page per day. Full picture of the snake and where
we got in and out. And why?"

EVERY WORD OF "WHY" IS THE MODEL'S OWN, RECORDED AT THE TIME. The entry reason is the reason on the
ENTER call, the exit reason is the reason on the EXIT call, and a missed leg quotes what the model
said while that leg was running. Nothing here is inferred after the fact. Figures I derive (true
peak, give-back, what happened after the exit, which leg a trade sat on) are labelled as hindsight
and drawn from the minute bars; they never feed a live decision.

READ-ONLY: reads day artefacts and the lake, writes one HTML file.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import html
import json
import os
import statistics as st
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import sim_week_recursive as SW          # noqa: E402
import snake_page as SP                  # noqa: E402

POISON = SW.POISON_RATE
WIN0, WIN1 = SW.WIN_START_MIN, SW.WIN_END_MIN
MISS_MIN_PT = 40.0
IT2_REF = "IT2 on the 10 held-out days: $620/day · 9 of 10 positive · SD $724 · worst −$496 · 6.4 trades/day"


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def hhmm(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%H:%M")


def epoch(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).timestamp())


def usd(v: float, plus: bool = True) -> str:
    s = f"{abs(v):,.0f}"
    return (("+" if v > 0 and plus else "−" if v < 0 else "") + "$" + s)


def pt(v: float) -> str:
    return f"{v:+.1f}".replace("-", "−")


def weekdays(month: str):
    d = dt.date.fromisoformat(month + "-01")
    while d.month == int(month[5:]):
        if d.weekday() < 5:
            yield d.isoformat()
        d += dt.timedelta(days=1)


# ── per-day analysis ─────────────────────────────────────────────────────────────────────────────

def analyse(day: str, rec: dict, bars: list, d0: int) -> dict:
    w0, w1 = d0 + WIN0 * 60, d0 + WIN1 * 60
    legs = SP._legs(bars)
    for lg in legs:
        lg["a"], lg["b"] = bars[lg["si"]][0], bars[lg["ei"]][0]
        # points inside the tradable window only — a leg that began at 22:30 offered less than its total
        inside = [b for b in bars if max(lg["a"], w0) <= b[0] <= min(lg["b"], w1)]
        lg["win_pts"] = lg["dir"] * (inside[-1][3] - inside[0][3]) if len(inside) > 1 else 0.0
    calls = {c["ts"]: c for c in rec.get("calls") or []}
    by_ts = sorted(rec.get("calls") or [], key=lambda c: c["ts"])

    trades = []
    for n, t in enumerate(rec.get("trades") or [], 1):
        o, c = epoch(t["opened"]), epoch(t["closed"])
        dirn = 1 if t["side"] == "LONG" else -1
        held = [b for b in bars if o <= b[0] <= c]
        if held:
            best = max(dirn * ((b[1] if dirn > 0 else b[2]) - t["entry"]) for b in held)
            worst = min(dirn * ((b[2] if dirn > 0 else b[1]) - t["entry"]) for b in held)
            peak_ts = max(held, key=lambda b: dirn * ((b[1] if dirn > 0 else b[2]) - t["entry"]))[0]
        else:
            best = worst = 0.0
            peak_ts = o
        after = [b for b in bars if c < b[0] <= c + 3600]
        a_best = max((dirn * ((b[1] if dirn > 0 else b[2]) - t["exit"]) for b in after), default=None)
        a_worst = min((dirn * ((b[2] if dirn > 0 else b[1]) - t["exit"]) for b in after), default=None)
        a_end = dirn * (after[-1][3] - t["exit"]) if after else None
        ec = calls.get(t["opened"]) or {}
        xc = calls.get(t["closed"]) or {}
        leg_i = next((i for i, lg in enumerate(legs, 1) if lg["a"] <= o < lg["b"]), None)
        if leg_i is None and legs:
            leg_i = len(legs)
        lg = legs[leg_i - 1] if leg_i else None
        with_leg = lg is not None and (dirn == (1 if lg["dir"] > 0 else -1))
        trades.append({
            **t, "n": n, "o": o, "c": c, "dir": dirn, "best": best, "worst": worst, "peak_ts": peak_ts,
            "after_best": a_best, "after_worst": a_worst, "after_end": a_end,
            "why_in": ec.get("reason") or t.get("entry_reason") or "", "conf_in": ec.get("conf"),
            "why_out": xc.get("reason") if xc.get("action") == "EXIT" else None,
            "leg": leg_i, "with_leg": with_leg,
            "share": (t["points"] / abs(lg["win_pts"]) * 100) if lg and with_leg and t["points"] > 0 and abs(lg["win_pts"]) > 1 else None,
            "held_checks": sum(1 for cc in by_ts if o < epoch(cc["ts"]) < c),
        })

    for i, lg in enumerate(legs, 1):
        lg["trades"] = [t["n"] for t in trades if t["leg"] == i]

    # legs we never traded on: quote what the model said once the leg had run a quarter of its way
    missed = []
    for i, lg in enumerate(legs, 1):
        if abs(lg["win_pts"]) < MISS_MIN_PT or lg["trades"]:
            continue
        a, b = max(lg["a"], w0), min(lg["b"], w1)
        seg = [bb for bb in bars if a <= bb[0] <= b]
        if len(seg) < 3:
            continue
        pick = next((bb for bb in seg if lg["dir"] * (bb[3] - seg[0][3]) >= 0.25 * abs(lg["win_pts"])), seg[0])
        cc = min((c for c in by_ts), key=lambda c: abs(epoch(c["ts"]) - pick[0]), default=None)
        missed.append({"leg": i, "dir": lg["dir"], "pts": lg["win_pts"], "a": a, "b": b,
                       "at": epoch(cc["ts"]) if cc else None,
                       "act": cc["action"] if cc else None, "why": cc["reason"] if cc else None})

    offered = sum(abs(lg["win_pts"]) for lg in legs)
    took = sum(t["points"] for t in trades)
    live_legs, cur = SW.legs(bars)
    errs = sum(1 for c in rec.get("calls") or [] if c.get("error"))
    return {"day": day, "rec": rec, "legs": legs, "trades": trades, "missed": missed,
            "offered": offered, "took": took, "net": rec.get("net_usd", 0.0),
            "live_legs": len(live_legs) + (1 if cur else 0), "errors": errs,
            "ncalls": len(rec.get("calls") or []),
            "in_market": sum(t["held_min"] for t in trades)}


# ── the picture ──────────────────────────────────────────────────────────────────────────────────

def nice_step(rng: float) -> float:
    for s in (5, 10, 20, 25, 50, 100, 200, 250, 500):
        if rng / s <= 7:
            return s
    return 500


def chart(bars: list, A: dict, d0: int) -> str:
    W, H, ml, mr, mt, mb = 1180, 360, 60, 14, 18, 26
    t0, t1 = bars[0][0], bars[-1][0]
    hi, lo = max(b[1] for b in bars), min(b[2] for b in bars)
    pad = (hi - lo) * 0.05
    hi, lo = hi + pad, lo - pad

    def X(ts):
        return ml + (ts - t0) / max(t1 - t0, 1) * (W - ml - mr)

    def Y(px):
        return mt + (hi - px) / max(hi - lo, 1e-9) * (H - mt - mb)

    o = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
         f'aria-label="Price with the snake legs, entries and exits">']
    # pre-window band
    xw0, xw1 = X(d0 + WIN0 * 60), X(d0 + WIN1 * 60)
    o.append(f'<rect class="band" x="{ml}" y="{mt}" width="{xw0 - ml:.1f}" height="{H - mt - mb}"/>')
    step = nice_step(hi - lo)
    p = (int(lo // step) + 1) * step
    while p < hi:
        o.append(f'<line class="grid" x1="{ml}" x2="{W - mr}" y1="{Y(p):.1f}" y2="{Y(p):.1f}"/>'
                 f'<text class="ylab" x="{ml - 6}" y="{Y(p) + 3.5:.1f}" text-anchor="end">{p:,.0f}</text>')
        p += step
    tk = (t0 // 3600 + 1) * 3600
    while tk <= t1:
        if (tk // 3600) % 2 == 0:
            o.append(f'<line class="grid v" x1="{X(tk):.1f}" x2="{X(tk):.1f}" y1="{mt}" y2="{H - mb}"/>'
                     f'<text class="xlab" x="{X(tk):.1f}" y="{H - 8}" text-anchor="middle">{hhmm(tk)}</text>')
        tk += 3600
    o.append(f'<line class="winedge" x1="{xw0:.1f}" x2="{xw0:.1f}" y1="{mt}" y2="{H - mb}"/>'
             f'<text class="note" x="{xw0 - 6:.1f}" y="{mt + 11}" text-anchor="end">before the window · not tradable</text>'
             f'<line class="winedge" x1="{xw1:.1f}" x2="{xw1:.1f}" y1="{mt}" y2="{H - mb}"/>')
    pts = " ".join(f"{X(b[0]):.1f},{Y(b[3]):.1f}" for b in bars)
    o.append(f'<polyline class="px" fill="none" points="{pts}"/>')
    # the snake
    for i, lg in enumerate(A["legs"], 1):
        x1, y1 = X(lg["a"]), Y(bars[lg["si"]][3])
        x2, y2 = X(lg["b"]), Y(bars[lg["ei"]][3])
        cls = "up" if lg["dir"] > 0 else "dn"
        o.append(f'<line class="leg {cls}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if abs(x2 - x1) > 26 or abs(y2 - y1) > 30:
            side = -1 if lg["dir"] > 0 else 1
            anchor = "end" if lg["dir"] > 0 else "start"
            lab = f'L{i} {"↑" if lg["dir"] > 0 else "↓"}{abs(lg["pts"]):.0f}'
            pos = f'x="{mx + side * 12:.1f}" y="{my - 7:.1f}" text-anchor="{anchor}"'
            o.append(f'<text class="halo leglab" {pos}>{lab}</text><text class="leglab {cls}" {pos}>{lab}</text>')
    # the trades
    for t in A["trades"]:
        x1, y1, x2, y2 = X(t["o"]), Y(t["entry"]), X(t["c"]), Y(t["exit"])
        res = "win" if t["pnl_usd"] > 0 else "loss"
        o.append(f'<line class="tie {res}" fill="none" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
        s = 7
        tri = (f"{x1:.1f},{y1 - s - 1:.1f} {x1 - s:.1f},{y1 + s - 1:.1f} {x1 + s:.1f},{y1 + s - 1:.1f}" if t["dir"] > 0
               else f"{x1:.1f},{y1 + s + 1:.1f} {x1 - s:.1f},{y1 - s + 1:.1f} {x1 + s:.1f},{y1 - s + 1:.1f}")
        o.append(f'<polygon class="mk {res}" points="{tri}"/>')
        ly = y1 - s - 6 if t["dir"] > 0 else y1 + s + 14
        tpos = f'x="{x1:.1f}" y="{ly:.1f}" text-anchor="middle"'
        o.append(f'<text class="halo tn" {tpos}>{t["n"]}</text><text class="tn" {tpos}>{t["n"]}</text>')
        o.append(f'<path class="xk {res}" fill="none" d="M{x2 - 5:.1f},{y2 - 5:.1f}L{x2 + 5:.1f},{y2 + 5:.1f}'
                 f'M{x2 + 5:.1f},{y2 - 5:.1f}L{x2 - 5:.1f},{y2 + 5:.1f}"/>')
    o.append("</svg>")
    return "".join(o)


# ── page sections ────────────────────────────────────────────────────────────────────────────────

def trade_html(t: dict) -> str:
    res = "win" if t["pnl_usd"] > 0 else "loss"
    gave = t["best"] - t["points"]
    leg_note = ""
    if t["leg"]:
        leg_note = (f'<span class="tag {"with" if t["with_leg"] else "against"}">'
                    f'{"WITH" if t["with_leg"] else "AGAINST"} leg L{t["leg"]}'
                    + (f' · took {t["share"]:.0f}% of it' if t["share"] is not None else "") + "</span>")
    exit_kind = ("the simulator's forced flat at 13:30Z — the model never chose this exit"
                 if t["why"].startswith("WINDOW") else None)
    out_html = (f'<blockquote class="why"><b>Out</b> <span>{esc(t["why_out"])}</span></blockquote>'
                if t["why_out"] else
                f'<p class="why plain"><b>Out</b> {esc(exit_kind or "no EXIT call matches this close")}</p>')
    in_cap = " <i class='cap'>(recorded text is cut at 300 characters)</i>" if len(t["why_in"]) >= 295 else ""
    after = ""
    if t["after_end"] is not None:
        after = (f'<p class="after">After the exit, over the next 60 min: price went '
                 f'<b>{pt(t["after_best"])}</b> at best and <b>{pt(t["after_worst"])}</b> at worst in this '
                 f'trade\'s direction, and was <b>{pt(t["after_end"])}</b> from the exit price at +60 min.</p>')
    return (
        f'<article class="trade {res}">'
        f'<h4><span class="n">{t["n"]}</span><span class="side {t["side"].lower()}">{t["side"]}</span>'
        f'<span class="when">{hhmm(t["o"])} → {hhmm(t["c"])}</span>'
        f'<span class="held">{t["held_min"]:.0f} min</span><span class="pnl">{usd(t["pnl_usd"])}</span></h4>'
        f'<p class="nums"><span>in {t["entry"]:,.2f}</span><span>out {t["exit"]:,.2f}</span>'
        f'<span>{pt(t["points"])} pt</span>'
        f'<span>best {pt(t["best"])} @ {hhmm(t["peak_ts"])}</span><span>worst {pt(t["worst"])}</span>'
        f'<span>gave back {gave:.1f} pt from its best</span></p>'
        f'<p class="tags">{leg_note}<span class="tag">{t["held_checks"]} checks while holding</span>'
        f'<span class="tag">exit: {esc(t["why"].replace("_", " ").lower())}</span></p>'
        f'<blockquote class="why"><b>In</b> <span>{esc(t["why_in"])}</span>{in_cap}</blockquote>'
        f'{out_html}{after}</article>')


def legs_html(A: dict) -> str:
    if not A["legs"]:
        return "<p class='muted'>The tape produced no legs.</p>"
    rows = []
    for i, lg in enumerate(A["legs"], 1):
        win = "" if abs(abs(lg["win_pts"]) - abs(lg["pts"])) < 1 else f' <small>({abs(lg["win_pts"]):.0f} in window)</small>'
        tr = ", ".join(f"#{n}" for n in lg["trades"]) or "—"
        rows.append(f'<tr><td>L{i}</td><td class="{"upc" if lg["dir"] > 0 else "dnc"}">'
                    f'{"UP" if lg["dir"] > 0 else "DOWN"}</td><td>{abs(lg["pts"]):.0f} pt{win}</td>'
                    f'<td>{hhmm(lg["a"])}–{hhmm(lg["b"])}</td><td>{lg["mins"]:.0f} min</td><td>{tr}</td></tr>')
    return ('<table class="legs"><thead><tr><th>leg</th><th>dir</th><th>size</th><th>from–to (Z)</th>'
            '<th>length</th><th>our entries</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")


def missed_html(A: dict) -> str:
    if not A["missed"]:
        return ""
    o = ['<div class="missed"><h3>Legs of 40 pt or more we never entered</h3>']
    for m in A["missed"]:
        o.append(f'<div class="m"><p><b>L{m["leg"]} {"UP" if m["dir"] > 0 else "DOWN"} {abs(m["pts"]):.0f} pt</b> '
                 f'· {hhmm(m["a"])}–{hhmm(m["b"])}Z')
        if m["why"]:
            o.append(f' — a quarter of the way in, at {hhmm(m["at"])}, the model chose '
                     f'<b>{esc(m["act"])}</b>:</p><blockquote class="why"><span>{esc(m["why"])}</span></blockquote>')
        else:
            o.append("</p>")
        o.append("</div>")
    o.append("</div>")
    return "".join(o)


def nav(day: str, days: list) -> str:
    i = days.index(day)
    prev = f'<a href="#d{days[i - 1]}">← {days[i - 1][8:]}</a>' if i else ""
    nxt = f'<a href="#d{days[i + 1]}">{days[i + 1][8:]} →</a>' if i + 1 < len(days) else ""
    return f'<nav class="pn">{prev}<a href="#top">month summary</a>{nxt}</nav>'


def day_page(A: dict, bars: list, d0: int, days: list) -> str:
    day = A["day"]
    d = dt.date.fromisoformat(day)
    tr = A["trades"]
    wins = sum(1 for t in tr if t["pnl_usd"] > 0)
    pct = (A["took"] / A["offered"] * 100) if A["offered"] else 0
    sign = "pos" if A["net"] > 0 else "neg" if A["net"] < 0 else "flat"
    lede = (f"The eye reads <b>{len(A['legs'])} leg{'s' if len(A['legs']) != 1 else ''}</b> "
            f"({A['offered']:.0f} pt offered inside the 02:00–13:30Z window); the model's own causal "
            f"detector (15×ATR) read <b>{A['live_legs']}</b> by the close. "
            + (f"We took <b>{pt(A['took'])} pt</b> across {len(tr)} trade{'s' if len(tr) != 1 else ''} = "
               f"<b>{pct:.0f}%</b> of what was offered, in the market {A['in_market']:.0f} of "
               f"{WIN1 - WIN0} minutes." if tr else "We took no trades."))
    if tr:
        won = [t for t in tr if t["pnl_usd"] > 0]
        lost = [t for t in tr if t["pnl_usd"] <= 0]
        bw_, bl_ = max(tr, key=lambda t: t["pnl_usd"]), min(tr, key=lambda t: t["pnl_usd"])
        lede += (f" The {len(won)} winner{'s' if len(won) != 1 else ''} made <b>{usd(sum(t['pnl_usd'] for t in won))}</b>, "
                 f"the {len(lost)} loser{'s' if len(lost) != 1 else ''} cost <b>{usd(sum(t['pnl_usd'] for t in lost))}</b>. "
                 f"Best trade #{bw_['n']} ({usd(bw_['pnl_usd'])}), worst #{bl_['n']} ({usd(bl_['pnl_usd'])}).")
    body = "".join(trade_html(t) for t in tr) or "<p class='muted'>No trades — the model waited all day.</p>"
    return (
        f'<section class="day" id="d{day}">'
        f'<header class="dh"><div><span class="dow">{d:%a}</span><h2>{d.day} {d:%B %Y}</h2></div>'
        f'<div class="net {sign}">{usd(A["net"])}</div>'
        f'<div class="facts"><span>{len(tr)} trades</span><span>{wins} won · {len(tr) - wins} lost</span>'
        f'<span>{A["ncalls"]} checks · {A["errors"]} failed</span></div>{nav(day, days)}</header>'
        f'<p class="lede">{lede}</p>'
        f'<figure>{chart(bars, A, d0)}'
        f'<figcaption class="legend"><span><i class="lg up"></i>up leg</span><span><i class="lg dn"></i>down leg</span>'
        f'<span><svg width="14" height="12"><polygon class="mk neutral" fill="currentColor" points="7,1 1,11 13,11"/></svg>long in</span>'
        f'<span><svg width="14" height="12"><polygon class="mk neutral" fill="currentColor" points="7,11 1,1 13,1"/></svg>short in</span>'
        f'<span><svg width="12" height="12"><path class="xk neutral" fill="none" stroke="currentColor" d="M1,1L11,11M11,1L1,11"/></svg>out</span>'
        f'<span><i class="lg tie win"></i>won</span><span><i class="lg tie loss"></i>lost</span>'
        f'<span class="muted">snake = hindsight ZigZag, swing ≥ max(40 pt, ¼ of the session range)</span>'
        f'</figcaption></figure>'
        f'<div class="cols"><aside>{legs_html(A)}{missed_html(A)}</aside>'
        f'<div class="trades">{body}</div></div></section>')


def failed_page(day: str, rec: dict | None) -> str:
    d = dt.date.fromisoformat(day)
    n = len((rec or {}).get("calls") or [])
    e = sum(1 for c in (rec or {}).get("calls") or [] if c.get("error"))
    why = (f"{e} of {n} calls failed — over the {POISON:.0%} limit, so the day is not scored"
           if rec else "no result file for this day")
    return (f'<section class="day" id="d{day}"><header class="dh"><div><span class="dow">{d:%a}</span>'
            f'<h2>{d.day} {d:%B %Y}</h2></div><div class="net flat">not scored</div></header>'
            f'<p class="lede">{esc(why)}.</p></section>')


# ── the front page ───────────────────────────────────────────────────────────────────────────────

def split_table(title: str, rows: list[tuple]) -> str:
    body = "".join(f"<tr><td>{esc(a)}</td><td>{n}</td><td>{usd(net)}</td><td>{usd(net / n) if n else '—'}</td>"
                   f"<td>{(100 * w / n):.0f}%</td></tr>" for a, n, net, w in rows if n)
    return (f'<table class="split"><caption>{esc(title)}</caption><thead><tr><th></th><th>trades</th>'
            f'<th>net</th><th>per trade</th><th>won</th></tr></thead><tbody>{body}</tbody></table>')


def front_page(month: str, As: list[dict], failed: list[str]) -> str:
    nets = [A["net"] for A in As]
    n = len(nets)
    allt = [t for A in As for t in A["trades"]]
    tot = sum(nets)
    sd = st.stdev(nets) if n > 1 else 0.0
    pos = sum(1 for v in nets if v > 0)
    mname = dt.date.fromisoformat(month + "-01").strftime("%B %Y")

    def grp(pred_rows):
        return [(lab, len(ts), sum(t["pnl_usd"] for t in ts), sum(1 for t in ts if t["pnl_usd"] > 0))
                for lab, ts in pred_rows]

    by_side = grp([(s, [t for t in allt if t["side"] == s]) for s in ("LONG", "SHORT")])
    by_leg = grp([("WITH the leg it entered on", [t for t in allt if t["leg"] and t["with_leg"]]),
                  ("AGAINST that leg", [t for t in allt if t["leg"] and not t["with_leg"]])])
    buckets = [("under 15 min", 0, 15), ("15–60 min", 15, 60), ("1–4 hours", 60, 240), ("over 4 hours", 240, 10**9)]
    by_hold = grp([(lab, [t for t in allt if lo <= t["held_min"] < hi]) for lab, lo, hi in buckets])
    by_exit = grp([("the model chose to exit", [t for t in allt if not t["why"].startswith("WINDOW")]),
                   ("forced flat at 13:30Z", [t for t in allt if t["why"].startswith("WINDOW")])])
    best = sum(t["best"] for t in allt)
    got = sum(t["points"] for t in allt)
    offered = sum(A["offered"] for A in As)

    # per-day net bars
    W, H, ml, mb, mt = 1180, 210, 44, 46, 18
    mx = max(max(nets, default=1), 1)
    mn = min(min(nets, default=-1), -1)
    zero = mt + (mx / (mx - mn)) * (H - mt - mb)
    bw = (W - ml - 8) / max(n, 1)
    bars = [f'<line class="grid" x1="{ml}" x2="{W - 8}" y1="{zero:.1f}" y2="{zero:.1f}"/>']
    for i, A in enumerate(As):
        v = A["net"]
        h = abs(v) / (mx - mn) * (H - mt - mb)
        y = zero - h if v >= 0 else zero
        cls = "win" if v > 0 else "loss"
        x = ml + i * bw + 3
        d = dt.date.fromisoformat(A["day"])
        bars.append(f'<a href="#d{A["day"]}"><rect class="bar {cls}" x="{x:.1f}" y="{y:.1f}" '
                    f'width="{bw - 6:.1f}" height="{max(h, 1):.1f}"><title>{A["day"]} {usd(v)}</title></rect>'
                    f'<text class="xlab" x="{x + (bw - 6) / 2:.1f}" y="{H - 22}" text-anchor="middle">{d.day}</text>'
                    f'<text class="vlab" x="{x + (bw - 6) / 2:.1f}" y="{(y - 4) if v >= 0 else (y + h + 11):.1f}" '
                    f'text-anchor="middle">{v:+,.0f}</text></a>'.replace("-", "−"))
    bars.append(f'<text class="note" x="{ml}" y="{H - 6}">day of the month · click a bar to jump to its page</text>')
    daystrip = f'<svg class="chart strip" viewBox="0 0 {W} {H}">{"".join(bars)}</svg>'

    fail_note = (f'<p class="warn">Not scored (model failed more than {POISON:.0%} of its checks): '
                 + ", ".join(failed) + ".</p>") if failed else ""
    return (
        f'<section class="day front" id="top"><header class="dh"><div><span class="dow">forward test · rules frozen</span>'
        f'<h2>{mname}</h2></div><div class="net {"pos" if tot > 0 else "neg"}">{usd(tot)}</div>'
        f'<div class="facts"><span>{n} days scored</span><span>{usd(tot / max(n, 1))} a day</span>'
        f'<span>{pos} of {n} days positive</span></div></header>'
        f'<div class="kpis"><div><b>{usd(tot / max(n, 1))}</b><span>per day</span></div>'
        f'<div><b>{pos}/{n}</b><span>days positive</span></div><div><b>${sd:,.0f}</b><span>day-to-day SD</span></div>'
        f'<div><b>{usd(min(nets, default=0))}</b><span>worst day</span></div>'
        f'<div><b>{len(allt) / max(n, 1):.1f}</b><span>trades a day</span></div>'
        f'<div><b>{usd(max(nets, default=0))}</b><span>best day</span></div></div>'
        f'<p class="muted ref">{IT2_REF}. June was never trained on or reviewed. Same rules, same harness, 4 lots, $2/pt, '
        f'$6 fees a round trip.</p>{fail_note}'
        f'<figure>{daystrip}</figure>'
        f'<div class="splits">'
        f'{split_table("By side", by_side)}{split_table("By leg", by_leg)}'
        f'{split_table("By time held", by_hold)}{split_table("By who ended it", by_exit)}</div>'
        f'<p class="lede">All {len(allt)} trades together reached {best:+,.0f} pt at their best and ended with '
        f'{got:+,.0f} pt; the legs offered {offered:,.0f} pt in the window, so we took '
        f'{100 * got / max(offered, 1):.1f}% of it.</p>'
        f'<h3>How to read a day page</h3><ul class="how">'
        f'<li><b>Snake</b> — the thick line is a hindsight ZigZag drawn after the close, as the eye would draw it. The thin '
        f'line is price. The model never sees this picture; it sees a causal 15×ATR version that cannot know a leg has ended.</li>'
        f'<li><b>Why</b> — every <i>In</i>, <i>Out</i> and missed-leg quote is the model\'s own recorded reason from that '
        f'moment, cut at 300 characters by the harness. Nothing is written after the fact.</li>'
        f'<li><b>Best, worst, give-back, after the exit, which leg</b> — worked out afterwards from the 1-minute bars. '
        f'Hindsight, for the review only.</li>'
        f'<li><b>Pages</b> — one section per day. Print it and each day is one landscape sheet.</li></ul></section>')


CSS = """
:root{--bg:#f2f5f8;--panel:#ffffff;--ink:#14202b;--mute:#667684;--rule:#d5dde4;--band:#e8edf2;
--up:#2f6fb0;--dn:#c27d12;--win:#1b7a57;--loss:#b53d36;--quote:#33506a;--accent:#2f6fb0}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0e1620;--panel:#15202c;--ink:#e5ecf2;
--mute:#8c9dac;--rule:#27384a;--band:#101b27;--up:#6aa5e0;--dn:#e0a548;--win:#46c08f;--loss:#ee7b73;--quote:#a9c3da;--accent:#6aa5e0}}
:root[data-theme="dark"]{--bg:#0e1620;--panel:#15202c;--ink:#e5ecf2;--mute:#8c9dac;--rule:#27384a;--band:#101b27;
--up:#6aa5e0;--dn:#e0a548;--win:#46c08f;--loss:#ee7b73;--quote:#a9c3da;--accent:#6aa5e0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "IBM Plex Sans",system-ui,sans-serif}
.day{max-width:1240px;margin:0 auto 28px;padding:22px 26px 26px;background:var(--panel);border-bottom:1px solid var(--rule)}
.dh{display:flex;align-items:flex-end;gap:28px;flex-wrap:wrap;border-bottom:2px solid var(--ink);padding-bottom:10px}
.dow{font:600 11px "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.12em;color:var(--mute)}
h2{margin:0;font:600 28px/1.1 "IBM Plex Sans",sans-serif;letter-spacing:-.01em}
h3{margin:18px 0 8px;font:600 12px "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.1em;color:var(--mute)}
.net{font:600 34px/1 "IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.net.pos{color:var(--win)}.net.neg{color:var(--loss)}.net.flat{color:var(--mute)}
.facts{display:flex;gap:14px;margin-left:auto;font:12px "IBM Plex Mono",monospace;color:var(--mute);flex-wrap:wrap}
.facts span+span{border-left:1px solid var(--rule);padding-left:14px}
.lede{margin:12px 0 6px;max-width:92ch}
.muted{color:var(--mute)}.warn{color:var(--loss)}
figure{margin:8px 0 0}
.chart{width:100%;height:auto;display:block}
.chart .band{fill:var(--band)}.chart .grid{stroke:var(--rule);stroke-width:1}.chart .grid.v{stroke-dasharray:2 4}
.chart .winedge{stroke:var(--mute);stroke-width:1;stroke-dasharray:1 3}
.chart text{font:10.5px "IBM Plex Mono",monospace;fill:var(--mute)}
.chart .note{font-size:10px}
.chart .px{fill:none;stroke:var(--mute);stroke-width:1.1;opacity:.75}
.chart .leg{stroke-width:5;stroke-linecap:round;opacity:.8}
.chart .leg.up{stroke:var(--up)}.chart .leg.dn{stroke:var(--dn)}
.chart .leglab{font-weight:600;font-size:11px}
.chart .leglab.up{fill:var(--up)}.chart .leglab.dn{fill:var(--dn)}
.chart .tie{stroke-width:1.8;stroke-dasharray:5 3;fill:none}
.chart .tie.win,.lg.tie.win{stroke:var(--win)}.chart .tie.loss,.lg.tie.loss{stroke:var(--loss)}
.mk{stroke:var(--panel);stroke-width:1.2}.mk.win{fill:var(--win)}.mk.loss{fill:var(--loss)}
.xk{fill:none;stroke-width:2.2;stroke-linecap:round}.xk.win{stroke:var(--win)}.xk.loss{stroke:var(--loss)}
.chart .tn{font-weight:700;font-size:12px;fill:var(--ink)}
.chart text.halo{fill:var(--panel);stroke:var(--panel);stroke-width:4px;stroke-linejoin:round}
.chart .bar.win{fill:var(--win)}.chart .bar.loss{fill:var(--loss)}.chart .vlab{font-size:10px;fill:var(--ink)}
.legend{display:flex;gap:16px;flex-wrap:wrap;align-items:center;font:11px "IBM Plex Mono",monospace;color:var(--mute);margin-top:4px}
.legend span{display:inline-flex;gap:6px;align-items:center}
.lg{display:inline-block;width:20px;height:0;border-top:5px solid;border-radius:3px}
.lg.up{border-color:var(--up)}.lg.dn{border-color:var(--dn)}
.lg.tie{border-top:2px dashed}
.cols{display:grid;grid-template-columns:minmax(260px,330px) 1fr;gap:22px;margin-top:12px;align-items:start}
@media (max-width:900px){.cols{grid-template-columns:1fr}}
.trades{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px}
.trade{border:1px solid var(--rule);border-left:4px solid var(--mute);padding:10px 12px;border-radius:3px}
.trade.win{border-left-color:var(--win)}.trade.loss{border-left-color:var(--loss)}
.trade h4{margin:0 0 4px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;font:600 13px "IBM Plex Mono",monospace}
.trade .n{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;background:var(--ink);color:var(--panel);font-size:11px}
.trade .side.long{color:var(--win)}.trade .side.short{color:var(--loss)}
.trade .held{color:var(--mute);font-weight:400}.trade .pnl{margin-left:auto;font-size:15px}
.trade.win .pnl{color:var(--win)}.trade.loss .pnl{color:var(--loss)}
.nums{display:flex;gap:4px 12px;flex-wrap:wrap;margin:0 0 6px;font:11px "IBM Plex Mono",monospace;color:var(--mute);font-variant-numeric:tabular-nums}
.tags{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 8px}
.tag{font:600 10.5px "IBM Plex Mono",monospace;padding:2px 7px;border:1px solid var(--rule);border-radius:10px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}
.tag.with{color:var(--win);border-color:var(--win)}.tag.against{color:var(--loss);border-color:var(--loss)}
blockquote.why,p.why{margin:6px 0;padding:0 0 0 10px;border-left:2px solid var(--rule);font:15px/1.45 "Source Serif 4",Georgia,serif;color:var(--quote)}
.why b{display:inline-block;min-width:26px;margin-right:6px;font:600 10px "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.1em;color:var(--mute)}
.why.plain{font-style:italic}.cap{color:var(--mute);font-size:11px}
.after{margin:8px 0 0;font-size:12.5px;color:var(--mute)}.after b{color:var(--ink);font-family:"IBM Plex Mono",monospace;font-weight:600}
table{border-collapse:collapse;width:100%;font:12px "IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
th{font-weight:600;color:var(--mute);text-align:left;border-bottom:1px solid var(--ink);padding:4px 6px 4px 0;text-transform:uppercase;font-size:10px;letter-spacing:.06em}
td{padding:4px 6px 4px 0;border-bottom:1px solid var(--rule)}
td.upc{color:var(--up);font-weight:600}td.dnc{color:var(--dn);font-weight:600}
.missed{margin-top:14px}.missed .m{margin-bottom:10px}.missed p{margin:0 0 2px;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:1px;background:var(--rule);border:1px solid var(--rule);margin:14px 0 8px}
.kpis div{background:var(--panel);padding:10px 12px;display:flex;flex-direction:column;gap:2px}
.kpis b{font:600 22px "IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.kpis span{font:11px "IBM Plex Mono",monospace;color:var(--mute);text-transform:uppercase;letter-spacing:.06em}
.splits{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px 26px;margin:14px 0}
caption{caption-side:top;text-align:left;font:600 11px "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.1em;color:var(--mute);padding-bottom:4px}
.how{max-width:96ch;padding-left:18px}.how li{margin:5px 0}
.pn{display:flex;gap:14px;font:11px "IBM Plex Mono",monospace;width:100%;justify-content:flex-end}
.pn a{text-decoration:none;color:var(--mute)}.pn a:hover{color:var(--accent)}
@media print{.pn{display:none}}
a{color:var(--accent)}
@page{size:A4 landscape;margin:10mm}
@media print{body{background:#fff}.day{break-before:page;margin:0;padding:0;border:0;max-width:none}}
"""

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700'
         '&family=IBM+Plex+Sans:wght@400;600&family=Source+Serif+4:ital,wght@0,400;1,400&display=swap">')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--label", default="it2")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    tag = f"fwd_{a.label}_{a.month}"
    As, pages, failed = [], [], []
    scored_days = [d for d in weekdays(a.month) if len(SW.load_day(d)[0]) >= 600]
    for day in weekdays(a.month):
        bars, _ = SW.load_day(day)
        if len(bars) < 600:
            continue                                   # a holiday: nothing was traded
        p = f"{SW.OUT}/{tag}_{day}.json"
        rec = json.load(open(p)) if os.path.exists(p) else None
        calls = (rec or {}).get("calls") or []
        clean = bool(calls) and sum(1 for c in calls if c.get("error")) / len(calls) <= POISON
        d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
        if not clean:
            failed.append(day)
            pages.append(failed_page(day, rec))
            continue
        A = analyse(day, rec, bars, d0)
        As.append(A)
        pages.append(day_page(A, bars, d0, scored_days))
    mname = dt.date.fromisoformat(a.month + "-01").strftime("%B %Y")
    doc = (f'<meta charset="utf-8"><title>{mname} Snake Report</title><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'{FONTS}<style>{CSS}</style>' + front_page(a.month, As, failed) + "".join(pages))
    out = a.out or f"{GB}/reports/forward_month/{a.month}_snake_report.html"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write(doc)
    print(f"{out}: {len(As)} scored days, {len(failed)} not scored, {len(doc) / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
