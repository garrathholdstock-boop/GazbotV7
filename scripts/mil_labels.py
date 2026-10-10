"""Operator-labelled major intraday legs (MILs), 2026-10-05..09, from his description of durations.
Labels are his words; turning points are snapped to the nearest extreme on the 1-min tape (+-SNAP_MIN)."""
import os, sqlite3, collections, datetime as dt

GB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP_MIN = 75
# (direction, hours) in order from the 22:00Z session open. Operator, 2026-10-09.
LABELS = {
    "2026-10-05": [(+1, 4), (-1, 9), (+1, 8)],
    "2026-10-06": [(+1, 3), (-1, 1.5), (+1, 12.5), (-1, 6)],
    "2026-10-07": [(-1, 4), (+1, 3), (-1, 8), (+1, 7)],
    "2026-10-08": [(-1, 12), (+1, 5), (-1, 2), (+1, 3)],
    "2026-10-09": [(-1, 2), (+1, 8), (-1, 5), (+1, 3)],   # today's, from earlier ("a few up")
}


def minute_bars(day):
    c = sqlite3.connect("file:" + os.path.join(GB, "data", "capture.db") + "?mode=ro", uri=True)
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    rows = c.execute("select bar_ts,high,low,close from bars where symbol='MNQ' and timeframe='5s' "
                     "and bar_ts>=? and bar_ts<? order by bar_ts", (d0 - 7200, d0 + 21 * 3600)).fetchall()
    m = collections.OrderedDict()
    for t, h, l, cl in rows:
        k = t // 60 * 60
        if k not in m:
            m[k] = [k, h, l, cl]
        else:
            m[k][1] = max(m[k][1], h); m[k][2] = min(m[k][2], l); m[k][3] = cl
    return [tuple(v) for v in m.values()]


def snapped_turns(day, bars):
    """Turn points between consecutive labelled legs: (ts, price, new_direction)."""
    s = bars[0][0]
    t = s
    out = []
    legs = LABELS[day]
    for i, (d, hrs) in enumerate(legs[:-1]):
        t += int(hrs * 3600)
        nxt = legs[i + 1][0]
        w = [b for b in bars if abs(b[0] - t) <= SNAP_MIN * 60]
        if not w:
            continue
        # the turn from leg d to leg nxt: a top if d>0 else a bottom
        pick = max(w, key=lambda b: b[1]) if d > 0 else min(w, key=lambda b: b[2])
        out.append((pick[0], pick[1] if d > 0 else pick[2], nxt))
    return out


if __name__ == "__main__":
    f = lambda t: dt.datetime.fromtimestamp(t, dt.UTC).strftime("%a %H:%MZ")
    for day in LABELS:
        bars = minute_bars(day)
        print(day, len(bars), "bars; open", bars[0][3], "last", f(bars[-1][0]))
        tp = snapped_turns(day, bars)
        prev_t, prev_p = bars[0][0], bars[0][3]
        for (t, p, nd), (d, hrs) in zip(tp, LABELS[day]):
            print(f"   {'UP' if d>0 else 'DN'} stated {hrs:>4}h  {f(prev_t)} {prev_p:.0f} -> {f(t)} {p:.0f}  {p-prev_p:+.0f}pt  actual {(t-prev_t)/3600:.1f}h")
            prev_t, prev_p = t, p
        d, hrs = LABELS[day][-1]
        print(f"   {'UP' if d>0 else 'DN'} stated {hrs:>4}h  {f(prev_t)} {prev_p:.0f} -> {f(bars[-1][0])} {bars[-1][3]:.0f}  {bars[-1][3]-prev_p:+.0f}pt (to session end)")
