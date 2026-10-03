#!/usr/bin/env python3
"""THE ONE-PAGE SNAKE — the day's legs with the entries and exits drawn on them.

★★★ Operator: *"the nightly review needs to look at the whole day. the 3-5 legs. and analyse where
we did trade and how we get those trades to be on the legs. simple. claude needs to look at the tape
every night like i do. a 1 page snake with entries and exits."*

⚠⚠ WHY THIS EXISTS: THE NIGHTLY REVIEW NEVER SAW THE TAPE. It was handed its own trades — side,
times, hold, points, P&L, peak-while-held, and the entry note it wrote at the time — and NOTHING
ELSE. No bars, no leg structure, no idea what the day did AFTER an exit, and no sight of the setups
it passed on. So it could see that it banked +25 against a +83 peak DURING a hold, and could not see
that the leg then ran another hour.

Which means its lessons were inferred sideways: Monday's "the session low 30535 was already in at
09:11Z" was read back out of the price quotes in its OWN entry notes, not off a chart. Resourceful,
and far weaker than it reads. It also explains why every lesson was a variant of "I traded too
much" and never "I missed three" — a trade not taken leaves no trace in the only material it had.

★ So: draw the snake. Legs labelled, entries and exits marked where they actually happened, and a
per-leg table saying which trades landed on which leg, with or against it, and how much of the leg
each one captured. That last column is his actual question — "how do we get those trades to be ON
the legs" — expressed as a number he can watch move.

⚠ EVERY NUMBER HERE IS HINDSIGHT AND THAT IS FINE, because this is the REVIEW, run after the close.
It must never be fed into a live decision. The live context gets the causal version only.
"""

from __future__ import annotations

import datetime as dt

ROWS = 34          # ★2026-10-03 THE PICTURE IS THE REVIEW. Operator: "the numbers
                   # are secondary. first review is looking at the image of the
                   # snake." So it gets the vertical resolution to actually show a
                   # shape — 26 rows flattened a 300pt day into mush.
COLS = 110         # one column per 4 minutes across the window


def _legs(bars, min_swing_pt: float | None = None):
    """THE SNAKE AS THE EYE SEES IT — a ZigZag on a minimum SWING IN POINTS, not an ATR multiple.

    ⚠⚠⚠ THIS DELIBERATELY DOES NOT USE 15xATR, AND THE PICTURE IS WHY. On 2026-09-28 the chart shows
    an unmistakable day: down ~139pt all morning to 30535, then up ~219pt to 30754. The 15xATR rule
    reported **ONE leg, "UP +62pt"** — because a quiet ATR of ~9 puts the confirmation threshold at
    135-150pt and the morning's collapse was 139pt, right on the line. It then scored the ten
    morning shorts as trading AGAINST a leg that never existed.
    ★ That is the operator's whole complaint made visible: *"if you just snapshot the days tape and
      look at it from a distance you can see it has turned."* The eye sees SWINGS. An ATR multiple
      sees a ratio, and on a quiet day a real 139pt reversal does not clear it.

    So this page uses a ZigZag: a swing counts once price reverses `min_swing_pt` from the running
    extreme, and the leg ends at that extreme. Defaults to 25% of the day's range, floored at 40pt —
    scale-free across a quiet day and a wild one, and it has no ATR in it to collapse.
    ⚠ HINDSIGHT IS ALLOWED HERE AND NOWHERE ELSE. This runs after the close, for the review. The
      LIVE context gets the causal version in sim_week_recursive.legs(), which cannot know the
      current leg has ended and says so.
    """
    if len(bars) < 20:
        return []
    hi = max(b[1] for b in bars)
    lo = min(b[2] for b in bars)
    if min_swing_pt is None:
        min_swing_pt = max(40.0, 0.25 * (hi - lo))
    out = []
    dirn, start_i = 0, 0
    ext, ext_i = bars[0][3], 0
    for i in range(1, len(bars)):
        c = bars[i][3]
        if dirn == 0:
            if c - ext >= min_swing_pt:
                dirn, ext, ext_i = 1, c, i
            elif ext - c >= min_swing_pt:
                dirn, ext, ext_i = -1, c, i
            elif (dirn == 0 and ((c > ext and False) or False)):
                pass
            if dirn == 0:
                if c > ext and bars[ext_i][3] < c and False:
                    pass
            continue
        if dirn * (c - ext) > 0:
            ext, ext_i = c, i
        elif dirn * (ext - c) >= min_swing_pt:
            out.append({"dir": dirn, "si": start_i, "ei": ext_i,
                        "pts": dirn * (ext - bars[start_i][3]),
                        "mins": (bars[ext_i][0] - bars[start_i][0]) // 60})
            start_i, dirn = ext_i, -dirn
            ext, ext_i = c, i
    out.append({"dir": dirn or 1, "si": start_i, "ei": len(bars) - 1,
                "pts": (dirn or 1) * (bars[-1][3] - bars[start_i][3]),
                "mins": (bars[-1][0] - bars[start_i][0]) // 60})
    return out


def page(bars, trades, day: str, window=(2 * 60, 13 * 60 + 30)) -> str:
    """One page: the snake, the entries/exits on it, and the per-leg capture table."""
    if not bars:
        return "NO TAPE."
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    w0, w1 = d0 + window[0] * 60, d0 + window[1] * 60
    vis = [b for b in bars if w0 <= b[0] <= w1]
    if len(vis) < 30:
        return "NOT ENOUGH TAPE IN THE WINDOW."

    hi = max(b[1] for b in vis)
    lo = min(b[2] for b in vis)
    rng = max(hi - lo, 1e-9)
    t0, t1 = vis[0][0], vis[-1][0]
    span = max(t1 - t0, 1)

    def col(ts):
        return min(COLS - 1, max(0, int((ts - t0) / span * (COLS - 1))))

    def row(px):
        return min(ROWS - 1, max(0, int((hi - px) / rng * (ROWS - 1))))

    grid = [[" "] * COLS for _ in range(ROWS)]
    # ⚠ JOIN THE DOTS. Plotting one cell per bar leaves a dotted cloud at 110 columns and a
    #   300-point day reads as noise. Filling between consecutive rows draws the LINE, which is
    #   what he actually looks at.
    prev = None
    for b in vis:
        c, r = col(b[0]), row(b[3])
        if prev is not None and prev[0] == c:
            r0, r1 = sorted((prev[1], r))
            for rr in range(r0, r1 + 1):
                grid[rr][c] = "│" if grid[rr][c] == " " else grid[rr][c]
        elif prev is not None:
            r0, r1 = sorted((prev[1], r))
            for rr in range(r0, r1 + 1):
                if grid[rr][c] == " ":
                    grid[rr][c] = "│" if r1 - r0 > 1 else "─"
        if grid[r][c] in (" ", "│", "─"):
            grid[r][c] = "─"
        prev = (c, r)

    # ── entries and exits ON the snake. A clash is marked '*' rather than silently overwritten,
    #    because a lost marker is a lie about where a trade happened.
    marks = []
    for n, t in enumerate(trades, 1):
        for kind, iso, px in (("in", t["opened"], t["entry"]), ("out", t["closed"], t["exit"])):
            ts = int(dt.datetime.fromisoformat(iso).timestamp())
            if not (w0 <= ts <= w1):
                continue
            ch = ("L" if t["side"] == "LONG" else "S") if kind == "in" else "x"
            r, c = row(px), col(ts)
            # ⚠ ONLY CLASH WITH ANOTHER MARKER, never with the price line. The first version
            #   collide-checked against the drawn line too, so almost every entry and exit — which
            #   by definition sits ON the price — rendered as "*" and the picture became unreadable:
            #   you could see there were trades but not whether they were longs or shorts.
            if grid[r][c] in ("L", "S", "x", "*"):
                ch = "*"
            grid[r][c] = ch
            marks.append((n, kind, iso[11:16], px, t["side"]))

    L = ["=" * (COLS + 14),
         f"  THE SNAKE — {day}   {window[0]//60:02d}:00-{window[1]//60:02d}:{window[1]%60:02d}Z"
         f"   ·   LOOK AT THE SHAPE FIRST. The numbers are underneath and they are secondary.",
         f"  L = long entry   S = short entry   x = exit   * = two markers in one cell",
         "=" * (COLS + 14), ""]
    for r in range(ROWS):
        price = hi - (r / max(ROWS - 1, 1)) * rng
        L.append(f"  {price:9.0f} |{''.join(grid[r])}")
    ticks = " " * 12
    for c in range(0, COLS, 12):
        ticks += f"{dt.datetime.fromtimestamp(t0 + int(c / (COLS - 1) * span), dt.UTC):%H:%M}" + " " * 7
    L.append(ticks[:12 + COLS])

    L += ["", "=" * (COLS + 14),
          "  NOW THE NUMBERS — only after you have read the shape above",
          "=" * (COLS + 14)]

    # ── the legs, and which trades landed on them ───────────────────────────────────────────────
    legs = _legs(vis)
    L += ["", f"THE LEGS — {len(legs)} of them (ZigZag on a minimum swing in POINTS, the snake the eye sees)", ""]
    L.append(f"  {'#':>2} {'dir':5}{'points':>8}{'mins':>6}  {'from':>5}-{'to':<5}  trades on it")
    cap_rows = []
    for i, lg in enumerate(legs, 1):
        a, b = vis[lg["si"]][0], vis[lg["ei"]][0]
        on = []
        for n, t in enumerate(trades, 1):
            ts = int(dt.datetime.fromisoformat(t["opened"]).timestamp())
            if a <= ts <= b:
                with_leg = (t["side"] == "LONG") == (lg["dir"] > 0)
                share = abs(t["points"]) / max(abs(lg["pts"]), 1e-9) * 100
                on.append(f"#{n}{'+' if with_leg else '-'}{share:.0f}%")
                cap_rows.append((n, i, with_leg, t["points"], lg["pts"], share, t["pnl_usd"]))
        L.append(f"  {i:>2} {'UP' if lg['dir'] > 0 else 'DOWN':5}{lg['pts']:>+8.0f}{lg['mins']:>6.0f}"
                 f"  {dt.datetime.fromtimestamp(a, dt.UTC):%H:%M}-"
                 f"{dt.datetime.fromtimestamp(b, dt.UTC):%H:%M}  "
                 + (" ".join(on) if on else "— none —"))
    L.append("  (+ = traded WITH the leg, - = AGAINST it, % = share of the leg's points captured)")

    # ── the question he actually asked ──────────────────────────────────────────────────────────
    L += ["", "ARE THE TRADES ON THE LEGS?"]
    if not trades:
        L.append("  no trades today.")
    else:
        withl = [c for c in cap_rows if c[2]]
        against = [c for c in cap_rows if not c[2]]
        orphan = len(trades) - len(cap_rows)
        total_leg_pts = sum(abs(l["pts"]) for l in legs)
        got = sum(t["points"] for t in trades)
        L += [f"  {len(withl)} trade(s) WITH a leg, {len(against)} AGAINST, {orphan} outside any leg",
              f"  the day offered {total_leg_pts:.0f}pt across {len(legs)} leg(s); we took "
              f"{got:+.0f}pt = {100*got/max(total_leg_pts,1e-9):+.1f}% of it",
              f"  biggest leg: {max((abs(l['pts']) for l in legs), default=0):.0f}pt — "
              f"largest single trade: {max((abs(t['points']) for t in trades), default=0):.0f}pt"]
        miss = [l for i, l in enumerate(legs, 1)
                if not any(c[1] == i for c in cap_rows) and abs(l["pts"]) >= 40]
        if miss:
            L.append(f"  ⚠ {len(miss)} leg(s) of 40pt+ had NO trade on them at all: "
                     + ", ".join(f"{'UP' if m['dir']>0 else 'DOWN'} {abs(m['pts']):.0f}pt "
                                 f"@{dt.datetime.fromtimestamp(vis[m['si']][0], dt.UTC):%H:%M}"
                                 for m in miss))
        if against:
            L.append(f"  ⚠ against-the-leg trades cost "
                     f"${sum(c[6] for c in against):+,.0f} over {len(against)}")
    return "\n".join(L)


# ──────────────────────────────────────────────────────────────────────────────────────────────────
# THE LIVE SNAKE — the same picture, drawn causally, for the decision rather than the review.
# ──────────────────────────────────────────────────────────────────────────────────────────────────

def live_page(bars_upto, trades_so_far, now_epoch: int, pos: dict | None = None,
              cols: int = 110, rows: int = 30) -> str:
    """The session so far AS A SHAPE, from the 22:00Z open to now. Causal by construction.

    ★★★ Operator: *"so make the live context show the shape not the metrics."*

    ⚠⚠ WHAT IT REPLACES AND WHY. The live context led with numbers — price, ATR, position in range,
    minutes of tape — and buried the structure in a list of 15-minute OHLC rows. But the day's shape
    has about five segments in it, and at one-minute resolution that structure is invisible: plain
    direction flips fire 42-87 times a session on the same tape where the ZigZag finds five legs.
    The whole night's signal search was conducted at the resolution where the answer cannot be seen.
    ★ The review page proved the point: Tuesday read UP 194 / DOWN 88 / UP 174 / DOWN 82 / UP 78 and
      the simulator took SIX trades on the 194pt leg capturing 0-12% each. Nobody reading the shape
      would do that; something reading per-minute metrics does it every time.

    ⚠⚠⚠ CAUSALITY. Only `bars_upto` is drawn, the chart ends at NOW, and the last leg is labelled
    RUNNING with its extent measured only to here. A ZigZag confirms a swing after the retrace, so
    the leg in progress may still read as part of the previous one — that ambiguity is STATED rather
    than resolved, because resolving it would require the future.
    ⚠ No hindsight summary here: the "were the trades on the legs" table is review-only.
    """
    if len(bars_upto) < 20:
        return "NOT ENOUGH TAPE YET."
    hi = max(b[1] for b in bars_upto)
    lo = min(b[2] for b in bars_upto)
    rng = max(hi - lo, 1e-9)
    t0, t1 = bars_upto[0][0], bars_upto[-1][0]
    span = max(t1 - t0, 1)

    def col(ts):
        return min(cols - 1, max(0, int((ts - t0) / span * (cols - 1))))

    def row(px):
        return min(rows - 1, max(0, int((hi - px) / rng * (rows - 1))))

    grid = [[" "] * cols for _ in range(rows)]
    prev = None
    for b in bars_upto:
        c, r = col(b[0]), row(b[3])
        if prev is not None:
            r0, r1 = sorted((prev[1], r))
            for rr in range(r0, r1 + 1):
                if grid[rr][c] == " ":
                    grid[rr][c] = "│" if r1 - r0 > 1 else "─"
        if grid[r][c] in (" ", "│", "─"):
            grid[r][c] = "─"
        prev = (c, r)

    for t in trades_so_far or []:
        for kind, iso, px in (("in", t["opened"], t["entry"]), ("out", t["closed"], t["exit"])):
            ts = int(dt.datetime.fromisoformat(iso).timestamp())
            if not (t0 <= ts <= t1):
                continue
            ch = ("L" if t["side"] == "LONG" else "S") if kind == "in" else "x"
            r, c = row(px), col(ts)
            if grid[r][c] in ("L", "S", "x", "*"):
                ch = "*"
            grid[r][c] = ch
    if pos:                                        # where you are RIGHT NOW
        r, c = row(pos["entry"]), col(int(pos["opened"].timestamp()))
        grid[r][c] = "◆"

    legs = _legs(bars_upto)
    L = ["THE SESSION SO FAR, AS A SHAPE — read this before anything else.",
         f"  22:00Z open to now ({dt.datetime.fromtimestamp(t1, dt.UTC):%H:%M}Z) · "
         f"range {lo:.0f}-{hi:.0f} ({rng:.0f}pt)",
         "  L/S = your entries · x = your exits · ◆ = the position you hold now", ""]
    for r in range(rows):
        L.append(f"  {hi - (r / max(rows - 1, 1)) * rng:9.0f} |{''.join(grid[r])}")
    ticks = " " * 12
    for c in range(0, cols, 14):
        ticks += f"{dt.datetime.fromtimestamp(t0 + int(c / (cols - 1) * span), dt.UTC):%H:%M}" + " " * 9
    L.append(ticks[:12 + cols])

    L += ["", "THE LEGS BEHIND YOU, AND THE ONE YOU ARE IN"]
    for i, lg in enumerate(legs, 1):
        a, b = bars_upto[lg["si"]][0], bars_upto[lg["ei"]][0]
        running = (i == len(legs))
        L.append(f"  {i}. {'UP  ' if lg['dir'] > 0 else 'DOWN'} {abs(lg['pts']):>6.0f}pt over "
                 f"{lg['mins']:>4.0f}min  {dt.datetime.fromtimestamp(a, dt.UTC):%H:%M}-"
                 + (f"now   ← RUNNING, extent so far only"
                    if running else f"{dt.datetime.fromtimestamp(b, dt.UTC):%H:%M}"))
    L.append("  ⚠ a swing is only recognised after price reverses off its extreme, so the leg you "
             "are in may still read as part of the one before it. That is the live cost of not "
             "knowing the future, not an error.")
    return "\n".join(L)
