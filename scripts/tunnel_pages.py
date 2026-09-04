#!/usr/bin/env python3
"""TUNNEL PAGES — one A4 page per session: the tape, the tunnels, the breaks.

★2026-09-04, operator: *"show me the last 4 weeks tape. 1 day per A4 page. with yellow shading over
what you consider a tunnel. and then a green circular shading at the break up or down. do that first
so i can look at it so i know we are thinking about the same thing."*

THE POINT OF THIS FILE IS AGREEMENT, NOT ANALYSIS. It renders exactly what the LIVE detector calls a
tunnel and a break, so the operator can say "no, that is not what I mean" before another hour goes
into measuring the wrong object.

★ IT USES THE SHIPPED MODEL, IMPORTED — never a re-implementation. `scripts/tunnel_watch.py` is the
thing running in production; if this drew a different tunnel the whole exercise would be worthless.
Forward filter only (`filter_states`), never Viterbi — smoothing re-labels the past using the future,
which would draw tunnels the live service could not have known about.

★ THE FILTER RUNS CONTINUOUSLY ACROSS THE WHOLE WINDOW, then the result is sliced per session. The
live service reads a rolling 400-minute window that does not reset at the session boundary, so
restarting the filter each morning would draw a tape the service never sees.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sqlite3
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates          # noqa: E402
import matplotlib.pyplot as plt            # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages   # noqa: E402
from matplotlib.patches import Ellipse, Rectangle      # noqa: E402

GB = "/home/alphabot/gazbot7"
CAPTURE = f"{GB}/data/capture.db"
SYMBOL = os.environ.get("TP_SYMBOL", "MNQ")
WEEKS = float(os.environ.get("TP_WEEKS", "4"))
BUF_PCT = float(os.environ.get("TP_BUF_PCT", "0.10"))     # the operator's 10% of tunnel WIDTH
A4_LANDSCAPE = (11.69, 8.27)

_spec = importlib.util.spec_from_file_location("tw", f"{GB}/scripts/tunnel_watch.py")
tw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tw)               # the SHIPPED model: MU/SD/A, true_range, filter_states


def minute_bars(start_ts: float, end_ts: float):
    """5s capture rows -> 1-minute bars, aggregated so the CLOSE is the real last print.

    ⚠ `bar_ts - (bar_ts % 60)`, never `bar_ts/60*60`: SQLite `/` is float and that expression is a
    silent no-op which once read 5s bars as '1m' for hours.
    ⚠ symbol AND timeframe filtered — capture carries MGC too, and folding them once made ATR read
    1848 against a true 15.
    """
    uri = f"file:{CAPTURE}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as c:
        rows = c.execute(
            """select bar_ts - (bar_ts % 60) as m, bar_ts, high, low, "close", volume
               from bars where symbol=? and timeframe='5s' and bar_ts>=? and bar_ts<=?
               order by bar_ts""",
            (SYMBOL, int(start_ts), int(end_ts))).fetchall()
    out = {}
    for m, bts, hi, lo, cl, vol in rows:
        b = out.get(m)
        if b is None:
            out[m] = {"m": int(m), "hi": float(hi), "lo": float(lo),
                      "close": float(cl), "_l": bts, "vol": float(vol or 0)}
        else:
            b["hi"] = max(b["hi"], float(hi)); b["lo"] = min(b["lo"], float(lo))
            b["vol"] += float(vol or 0)
            if bts >= b["_l"]:
                b["_l"], b["close"] = bts, float(cl)
    return [out[k] for k in sorted(out)]


def session_key(ts: float) -> str:
    """CME session runs 22:00Z -> 21:00Z; shift +2h so one session gets one date. Same rule as the
    live service, so a page boundary here is a session boundary there."""
    return (dt.datetime.fromtimestamp(ts, dt.UTC) + dt.timedelta(hours=2)).date().isoformat()


def quiet_runs(post, floor_min=1):
    """Contiguous runs of P(quiet) >= 0.5 — the same test `find_tunnel` applies to the live tape."""
    runs, cur = [], None
    for i, p in enumerate(post):
        if p >= 0.5 and cur is None:
            cur = i
        elif p < 0.5 and cur is not None:
            if i - cur >= floor_min:
                runs.append((cur, i - 1))
            cur = None
    if cur is not None and len(post) - cur >= floor_min:
        runs.append((cur, len(post) - 1))
    return runs


def first_break(bars, a, b, hi, lo, buf):
    """The first minute CLOSING beyond the buffered edge after the tunnel ends.

    ★ CLOSE, not a wick. On 2026-09-03 16:24Z a close 0.75pt (0.08 ATR) outside satisfied a naive
    'outside' test and meant nothing; the real move came a minute later 5.8pt out on 4,222 lots.
    """
    up, dn = hi + buf, lo - buf
    for j in range(b + 1, len(bars)):
        c = bars[j]["close"]
        if c > up:
            return j, "UP", c
        if c < dn:
            return j, "DOWN", c
        # stop looking once a NEW quiet stretch has clearly begun
        if j - b > 240:
            break
    return None, None, None


def main() -> int:
    now = dt.datetime.now(dt.UTC)
    start = now - dt.timedelta(weeks=WEEKS)
    bars = minute_bars(start.timestamp(), now.timestamp())
    if len(bars) < 100:
        print(f"tunnel_pages: only {len(bars)} minute bars in the window — nothing to draw")
        return 1
    trs = tw.true_range(bars)
    post = tw.filter_states(trs)                    # ONE continuous causal pass, then slice

    by_sess: dict[str, list[int]] = {}
    for i, b in enumerate(bars):
        by_sess.setdefault(session_key(b["m"]), []).append(i)

    out_pdf = f"{GB}/reports/friday_v2/tape_tunnels_{SYMBOL}_{now:%Y-%m-%d}.pdf"
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    sessions = sorted(by_sess)
    n_tun = n_brk = 0

    with PdfPages(out_pdf) as pdf:
        for sk in sessions:
            idx = by_sess[sk]
            if len(idx) < 60:                        # a stub session (holiday/outage) is not a page
                continue
            sb = [bars[i] for i in idx]
            sp = [post[i] for i in idx]
            st = [trs[i] for i in idx]
            x = [dt.datetime.fromtimestamp(b["m"], dt.UTC) for b in sb]
            close = [b["close"] for b in sb]

            fig, ax = plt.subplots(figsize=A4_LANDSCAPE)
            # the Asia block is entry-blocked by config; the operator should see where it sits
            for i, t in enumerate(x):
                pass
            a0 = x[0].replace(hour=0, minute=0, second=0, microsecond=0)
            for shift in (0, 1):
                lo_a = a0 + dt.timedelta(days=shift)
                hi_a = lo_a + dt.timedelta(hours=7)
                if hi_a >= x[0] and lo_a <= x[-1]:
                    ax.axvspan(max(lo_a, x[0]), min(hi_a, x[-1]), color="#9aa0a6", alpha=0.10, lw=0)

            ax.plot(x, close, lw=0.8, color="#202124", zorder=3)

            runs = quiet_runs(sp, floor_min=1)
            page_tun = page_brk = 0
            for a, b in runs:
                seg = sb[a:b + 1]
                n = len(seg)
                hi = max(s["hi"] for s in seg); lo = min(s["lo"] for s in seg)
                big = n >= tw.MIN_TUNNEL_MIN
                # ★ THE RECTANGLE IS THE POINT: its top and bottom ARE the ceiling and floor.
                ax.add_patch(Rectangle((mdates.date2num(x[a]), lo),
                                       mdates.date2num(x[b]) - mdates.date2num(x[a]), hi - lo,
                                       facecolor="#FFD400" if big else "#FFF3B0",
                                       alpha=0.55 if big else 0.30, edgecolor="none", zorder=1))
                if not big:
                    continue
                page_tun += 1
                width = hi - lo
                buf = BUF_PCT * width
                ax.hlines([hi + buf, lo - buf], x[a], x[b], colors="#B8860B",
                          linestyles=(0, (4, 3)), lw=0.7, zorder=2)
                ax.annotate(f"{n}m·{width:.0f}pt", (x[a], hi if page_tun % 2 else lo), fontsize=5.5,
                            color="#6b5900", va="bottom" if page_tun % 2 else "top",
                            xytext=(1, 3 if page_tun % 2 else -3), textcoords="offset points",
                            zorder=5)
                j, side, cpx = first_break(sb, a, b, hi, lo, buf)
                if j is None:
                    continue
                page_brk += 1
                # green circular shading at the break — sized in data units, so it must be an
                # Ellipse: a Circle in data coords would be squashed by the axes aspect ratio.
                w_days = (mdates.date2num(x[-1]) - mdates.date2num(x[0])) * 0.016
                h_px = (max(close) - min(close)) * 0.038
                ax.add_patch(Ellipse((mdates.date2num(x[j]), cpx), w_days, h_px,
                                     facecolor="#00A651", alpha=0.30, edgecolor="#00A651",
                                     lw=1.0, zorder=4))
                ax.annotate(side, (x[j], cpx), fontsize=6, weight="bold", color="#00703C",
                            xytext=(7, -3), textcoords="offset points", zorder=6)

            n_tun += page_tun; n_brk += page_brk
            for hh, lab, col in ((13.5, "13:30Z US open", "#1a73e8"), (20 + 40 / 60, "20:40Z flat", "#d93025")):
                for shift in (0, 1):
                    t = a0 + dt.timedelta(days=shift, hours=hh)
                    if x[0] <= t <= x[-1]:
                        ax.axvline(t, color=col, lw=0.7, ls=":", zorder=2)
                        ax.annotate(lab, (t, min(close)), fontsize=5.5, color=col,
                                    xytext=(2, 2), textcoords="offset points", zorder=6)
            ax.set_title(f"{SYMBOL} — CME session {sk}    "
                         f"{page_tun} tunnel(s) ≥{tw.MIN_TUNNEL_MIN}m   ·   {page_brk} break(s)",
                         fontsize=11, loc="left")
            ax.set_ylabel("price"); ax.grid(alpha=0.15, lw=0.5)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=dt.timezone.utc))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
            ax.tick_params(labelsize=7)
            fig.text(0.01, 0.015,
                     f"yellow = tunnel (solid ≥{tw.MIN_TUNNEL_MIN}m, pale = shorter quiet run) · "
                     f"dashed = ±{BUF_PCT*100:.0f}% of width · green = first CLOSE beyond it · "
                     f"grey = 00–07Z Asia (entry-blocked) · shipped HMM, forward filter only",
                     fontsize=6.5, color="#5f6368")
            fig.tight_layout(rect=(0, 0.03, 1, 1))
            pdf.savefig(fig); plt.close(fig)

        d = pdf.infodict()
        d["Title"] = f"{SYMBOL} tape — tunnels and breaks, {WEEKS:g} weeks to {now:%Y-%m-%d}"
        d["Subject"] = "One CME session per A4 page. Shipped tunnel_watch HMM, forward filter only."

    print(f"tunnel_pages: {out_pdf}")
    print(f"  sessions drawn: {len([s for s in sessions if len(by_sess[s])>=60])}   "
          f"tunnels ≥{tw.MIN_TUNNEL_MIN}m: {n_tun}   breaks: {n_brk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
