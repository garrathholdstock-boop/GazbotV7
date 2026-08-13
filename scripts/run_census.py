#!/usr/bin/env python3
"""V7 RUN CENSUS — the Friday report's "big runs → did we show up?" engine (MNQ, L1+L2 deep).

Reproduces the V5 footprint_scorecard `missed` census on the LIVE V7 data (the V5 tool is hardcoded
to the retired alphabot.db/ticks.db). Cold, tape-first: ignores what the desk did mid-week and asks
where the money was and whether we showed up. A "big run" = a 15-min close-to-close move >= min_atr ×
MNQ's TYPICAL 15-min range (median hi-lo). FULL census, every run, no top-N cap (the thing 07-17
dropped). Per run: direction, move, $ 1-lot ceiling, participation (which GATE fired + its real $),
net aggressor FLOW (ticks), pre-run amplitude, L2 far-side depletion (book), and a cause-CLUSTER.

Data (gazbot7): capture.db (bars 5s · ticks aggressor · book L2 depth) + gazbot7.db (trades: gate/
side/pnl for participation). DuckDB. Read-only. Feeds the report's closing greenfield section.

  PYTHONPATH=src python scripts/run_census.py [--days 7] [--min-atr 1.5]
"""
from __future__ import annotations

import argparse
import datetime as dt

import duckdb

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
# ★★2026-08-13 PER-SYMBOL MULTIPLIER. Operator: "make sure the census, greenfield and associated
# sections include mgc. we want to find some gates that work for mgc."
# MGC is $10/point — FIVE TIMES MNQ. Pricing a gold move with the MNQ multiplier understates every
# number on the page by 5x, which would make gold look unworthy of a gate on arithmetic alone.
VPP_BY_SYMBOL = {"MNQ": 2.0, "MGC": 10.0}
VPP = 2.0   # rebound per-run in main(); kept for import-compatibility
W = 180     # 15-min window in 5s bars
STEP = 12   # slide every 60s


FLOW_Z = 1.0                  # ★2026-08-01: |z| >= this is a real flow event (was: raw |flow| > 50)
FLOW_Z_LOOKBACK = 2 * 3600    # standardise against the trailing 2 hours of the SAME statistic
FLOW_Z_MIN_BUCKETS = 30       # need >= 30 one-minute buckets of history before a z means anything


def cluster(hour, flow, mv, amp, fz=None):
    """★2026-08-01 FIX — the flow test is a Z-SCORE now, not a raw threshold.

    The old rule (`abs(flow) > 50`) fired on 66.5% of ALL bars, which made FLOW-LED and VACUUM two
    names for one coin and split the tape into 21/17 runs that meant nothing. 50 contracts of net
    aggressor flow in 60s is unremarkable on MNQ — the desk's own measurement is ~2,664 contracts a
    minute of flow — so the threshold was labelling ordinary tape as an event. Standardising against
    the trailing 2 hours asks what was actually intended: is THIS minute's flow unusual *for now*?

    `flow` is still used for its SIGN (does flow agree with the move); `fz` carries the magnitude
    test. fz=None (insufficient history) means "no flow verdict" and falls through, which is correct
    — better UNCLASS than a fake label. Revert: drop fz, restore `abs(flow) > 50`."""
    if 13 <= hour < 15:
        return "OPEN/NEWS"
    if flow is not None and fz is not None and abs(fz) >= FLOW_Z:
        return "FLOW-LED" if (flow > 0) == (mv > 0) else "VACUUM"
    if amp is not None and amp > 0.30:
        return "VOL-EXPANSION"
    return "UNCLASS"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="MNQ", choices=sorted(VPP_BY_SYMBOL),
                    help="which instrument to census (MGC prices at $10/pt, MNQ at $2/pt)")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-atr", type=float, default=1.5)
    ap.add_argument("--html", type=str, default=None, help="write the Movement-1 light-theme HTML fragment here")
    a = ap.parse_args()
    t1 = dt.datetime.now(dt.UTC).timestamp()
    t0 = t1 - a.days * 86400
    global VPP
    SYM = a.symbol
    VPP = VPP_BY_SYMBOL[SYM]

    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    bars = con.execute(f"""
        SELECT bar_ts, open, high, low, close FROM c.bars
        WHERE symbol='{SYM}' AND timeframe='5s' AND bar_ts>={t0} AND bar_ts<={t1} ORDER BY bar_ts""").fetchall()
    if len(bars) < 400:
        print("too few 5s bars")
        return
    trades = con.execute(f"""
        SELECT epoch(opened_at::TIMESTAMPTZ) te, side, gate, pnl_usd FROM g.trades
        WHERE symbol='{SYM}' AND epoch(opened_at::TIMESTAMPTZ)>={t0 - 600} ORDER BY te""").fetchall()

    # typical 15-min range (the ATR-like unit) + threshold
    rng = [max(x[2] for x in bars[i:i + W]) - min(x[3] for x in bars[i:i + W]) for i in range(0, len(bars) - W, STEP)]
    typ = sorted(rng)[len(rng) // 2] if rng else 0.0
    thr = a.min_atr * typ
    # candidate runs (15-min move >= thr), dedup overlaps keep-strongest
    cands = sorted(((abs(bars[i + W][4] - bars[i][4]), i, bars[i + W][4] - bars[i][4])
                    for i in range(0, len(bars) - W, STEP) if abs(bars[i + W][4] - bars[i][4]) >= thr),
                   reverse=True)
    runs, used = [], []
    for _, i, mv in cands:
        if not any(abs(i - j) < W for j in used):
            used.append(i)
            runs.append((i, mv))
    runs.sort()

    def flow_at(ts):  # net aggressor (buy-sell) in the 60s before the run
        r = con.execute(f"""SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END),0)
            FROM c.ticks WHERE symbol='{SYM}' AND ts_ms<{ts * 1000} AND ts_ms>={(ts - 60) * 1000}""").fetchone()[0]
        return r

    def flow_z_at(ts, cur):
        """★2026-08-01 — standardise `cur` (the 60s net-aggressor sum at ts) against the distribution
        of the SAME statistic over the trailing FLOW_Z_LOOKBACK. Non-overlapping 60s buckets, so the
        comparison population is like-for-like with the value being scored. None => not enough history
        or a degenerate spread; cluster() then withholds a flow verdict rather than inventing one."""
        if cur is None:
            return None
        t0 = ts - FLOW_Z_LOOKBACK
        row = con.execute(f"""
            WITH s AS (
              SELECT CAST((ts_ms/1000 - {t0}) / 60 AS INTEGER) AS b,
                     SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END) AS f
              FROM c.ticks WHERE symbol='{SYM}' AND ts_ms < {ts * 1000} AND ts_ms >= {t0 * 1000}
              GROUP BY 1)
            SELECT AVG(f), STDDEV_SAMP(f), COUNT(*) FROM s WHERE f IS NOT NULL""").fetchone()
        mu, sd, n = row
        if n is None or n < FLOW_Z_MIN_BUCKETS or sd is None or sd <= 0:
            return None
        return (float(cur) - float(mu)) / float(sd)

    def book_depletion(ts, direction):  # far-side (the side price ran toward) depth vs near-side, pre-run
        row = con.execute(f"""
            WITH b AS (SELECT side, size FROM c.book WHERE symbol='{SYM}' AND ts_ms<{ts * 1000}
                       AND ts_ms>={(ts - 30) * 1000} AND level<=3)
            SELECT COALESCE(SUM(CASE WHEN side='bid' THEN size END),0), COALESCE(SUM(CASE WHEN side='ask' THEN size END),0) FROM b""").fetchone()
        bid, ask = row
        far = ask if direction == "UP" else bid   # price ran UP → into the asks
        near = bid if direction == "UP" else ask
        if far + near == 0:
            return None
        return far / (far + near)   # <0.5 = far side thin (depleted) = telegraphed the run

    print(f"═══ {SYM} RUN CENSUS — last {a.days}d · {len(runs)} runs ≥ {a.min_atr}×ATR "
          f"(15-min move ≥ {thr:.0f}pt; typical 15m range = {typ:.0f}pt) ═══\n")
    caught = fought = sat = 0
    ceil_caught = real_caught = ceil_fought = real_fought = ceil_sat = 0.0
    gate_pnl = {}
    crows = []
    print(f"{'time UTC':<14}{'dir':>4}{'move':>7}{'$ceil':>7}  {'us':<8}{'gate':<14}{'real$':>7}{'flow':>7}{'amp%':>6}  {'book':>5}  cluster")
    for i, mv in runs:
        b0 = bars[i]
        start = b0[0]
        direction = "UP" if mv > 0 else "DN"
        ceil = abs(mv) * VPP
        lo, hi = start - 300, start + 300
        near_trades = [(sd, gt, p) for te, sd, gt, p in trades if lo <= te <= hi]
        took = [(gt, p) for sd, gt, p in near_trades
                if (sd in ("LONG", "BUY") and mv > 0) or (sd in ("SHORT", "SELL") and mv < 0)]
        against = [(gt, p) for sd, gt, p in near_trades
                   if (sd in ("LONG", "BUY") and mv < 0) or (sd in ("SHORT", "SELL") and mv > 0)]
        flow = flow_at(start)
        seg = bars[max(0, i - 60):i]
        amp = (100 * (max(x[2] for x in seg) - min(x[3] for x in seg)) / b0[4]) if seg and b0[4] else None
        hour = dt.datetime.fromtimestamp(start, dt.UTC).hour
        cl = cluster(hour, flow, mv, amp, flow_z_at(start, flow))
        book = book_depletion(start, direction)
        if took:
            us, gate = "caught", took[0][0]
            realv = sum(p for _, p in took)
            caught += 1
            ceil_caught += ceil
            real_caught += realv
        elif against:
            us, gate = "FOUGHT", against[0][0]
            realv = sum(p for _, p in against)
            fought += 1
            ceil_fought += ceil
            real_fought += realv
        else:
            us, gate, realv = "sat out", "—", 0.0
            sat += 1
            ceil_sat += ceil
        for gt, p in took + against:
            gate_pnl[gt] = gate_pnl.get(gt, 0.0) + p
        tm = dt.datetime.fromtimestamp(start, dt.UTC).strftime("%m-%d %H:%M")
        bs = f"{book:.2f}" if book is not None else "  —"
        fs = f"{flow:+.0f}" if flow is not None else "  —"
        as_ = f"{amp:.2f}" if amp is not None else "  —"
        print(f"{tm:<14}{direction:>4}{mv:>+7.0f}{ceil:>7.0f}  {us:<8}{gate:<14}{realv:>+7.0f}{fs:>7}{as_:>6}  {bs:>5}  {cl}")
        crows.append((tm, direction, mv, ceil, us, gate, realv, flow, amp, book, cl))

    print("\n── CLUSTERS ──")
    cc = {}
    for i, mv in runs:
        b0 = bars[i]
        f = flow_at(b0[0])
        seg = bars[max(0, i - 60):i]
        amp = (100 * (max(x[2] for x in seg) - min(x[3] for x in seg)) / b0[4]) if seg and b0[4] else None
        cl = cluster(dt.datetime.fromtimestamp(b0[0], dt.UTC).hour, f, mv, amp, flow_z_at(b0[0], f))
        cc[cl] = cc.get(cl, 0) + 1
    for cl, n in sorted(cc.items(), key=lambda x: -x[1]):
        print(f"   {cl:<14} {n:>3} runs")

    print("\n── HONEST MONEY (ceiling = hindsight 1-lot; real = what a gate actually banked) ──")
    print(f"   CAUGHT  {caught:>3} runs · ceiling ${ceil_caught:>6.0f} · real ${real_caught:>+6.0f}"
          f"  ({100*real_caught/ceil_caught if ceil_caught else 0:.0f}% of ceiling)")
    print(f"   FOUGHT  {fought:>3} runs · ceiling ${ceil_fought:>6.0f} · real ${real_fought:>+6.0f}")
    print(f"   SAT OUT {sat:>3} runs · ceiling ${ceil_sat:>6.0f} · real $     0  ← the money on the table")
    print("\n── real $ by gate (near the runs) ──")
    for gt, p in sorted(gate_pnl.items(), key=lambda x: x[1]):
        print(f"   {gt:<16} ${p:>+7.0f}")
    con.close()

    if a.html:
        import html as _h
        conv = 100 * real_caught / ceil_caught if ceil_caught else 0
        h = [
            f'<h2><span class="n">M1</span> The biggest runs on {SYM} this week &mdash; did we show up?</h2>',
            f'<p class="lead">Forget what the desk did this week &mdash; start from the raw tape. {SYM} printed '
            f'<strong>{len(runs)} runs of 1.5&times;ATR or bigger</strong> in the last seven days (a 15-minute move of at '
            f'least {thr:.0f} points, against a typical 15-min range of {typ:.0f}). That is the whole tape, not a top-ten. '
            f'We <strong>caught {caught}</strong>, we were positioned <em>against</em> <strong>{fought}</strong>, and we '
            f'<strong>sat out {sat}</strong>. The runs we aligned with banked <strong>+${real_caught:.0f}</strong> of honest '
            f'money &mdash; but that is only {conv:.0f}% of their ${ceil_caught:.0f} hindsight ceiling, and the {sat} we sat out '
            f'left <strong>${ceil_sat:.0f}</strong> on the table. The bleed is not the runs; it is the fading we do around them.</p>',
            '<div class="callout"><div class="ct">THE FULL CENSUS</div><p>Every qualifying run, in order. '
            f'<strong>Move</strong> is the swing in points; <strong>$ 1lot</strong> is that move on one {SYM} lot (${VPP:.0f}/pt) &mdash; '
            'the hindsight ceiling. <strong>real $</strong> is what a gate actually banked near it. <strong>Flow</strong> is '
            'net aggressor volume in the 60s before; <strong>amp</strong> is pre-run amplitude; <strong>book</strong> is the '
            'far-side L2 depth share (below 0.50 = the side price ran toward was thin). Green = we caught it, red = we fought it.</p></div>',
            '<table><tr><th>Time (UTC)</th><th>Dir</th><th>Move</th><th>$ 1lot</th><th>Us</th><th>Gate</th>'
            '<th>real $</th><th>Flow</th><th>Amp</th><th>Book</th><th>Cluster</th></tr>']
        for tm, d, mv, ceil, us, gate, realv, flow, amp, book, cl in crows:
            rc = ' class="row-hl"' if us == "caught" else ' class="row-bad"' if us == "FOUGHT" else ''
            gg = "&mdash;" if gate == "—" else _h.escape(gate)
            rv = f'{realv:+.0f}' if us != "sat out" else ''
            fs = f'{flow:+.0f}' if flow is not None else '&mdash;'
            am = f'{amp:.2f}' if amp is not None else '&mdash;'
            bk = f'{book:.2f}' if book is not None else '&mdash;'
            h.append(f'<tr{rc}><td class="ln">{tm}</td><td>{d}</td><td class="num">{mv:+.0f}</td>'
                     f'<td class="num">{ceil:.0f}</td><td>{us}</td><td>{gg}</td><td class="num">{rv}</td>'
                     f'<td class="num">{fs}</td><td class="num">{am}</td><td class="num">{bk}</td><td>{_h.escape(cl)}</td></tr>')
        h.append('</table>')
        h.append('<div class="card"><h3>What the runs were &mdash; by cause</h3><p>Each run gets a cause fingerprint '
                 'from its pre-run tape. This is the map for where to hunt a new gate.</p>'
                 '<table><tr><th>Cluster</th><th>Runs</th><th>What it is</th></tr>')
        _what = {"VACUUM": "moved AGAINST the tape (a snap-back / stop-run)", "FLOW-LED": "aggressors drove it (a continuation)",
                 "OPEN/NEWS": "the 13:00&ndash;15:00 UTC cash-open / data window", "VOL-EXPANSION": "amplitude broke out of a coil",
                 "UNCLASS": "no clear tape tell (quiet ignition)"}
        for cl, n in sorted(cc.items(), key=lambda x: -x[1]):
            h.append(f'<tr><td>{cl}</td><td class="num">{n}</td><td>{_what.get(cl, "")}</td></tr>')
        h.append('</table></div>')
        h.append('<div class="callout"><div class="ct">HONEST MONEY &mdash; ceiling vs what we banked</div>'
                 '<table><tr><th></th><th>Runs</th><th>Hindsight ceiling</th><th>What we really made</th></tr>'
                 f'<tr class="row-hl"><td>Caught (aligned)</td><td class="num">{caught}</td><td class="num">${ceil_caught:.0f}</td>'
                 f'<td class="num">+${real_caught:.0f} &nbsp;({conv:.0f}%)</td></tr>'
                 f'<tr class="row-bad"><td>Fought (against)</td><td class="num">{fought}</td><td class="num">${ceil_fought:.0f}</td>'
                 f'<td class="num">${real_fought:+.0f}</td></tr>'
                 f'<tr><td>Sat out</td><td class="num">{sat}</td><td class="num">${ceil_sat:.0f}</td>'
                 f'<td class="num">$0 &larr; the money on the table</td></tr></table>'
                 '<p>The runs made money and the fading gave it back; we convert a fraction of the ceiling and ignore the rest. '
                 'The next two movements ask whether we can do better &mdash; first with the gates we own, then with new ones.</p></div>')
        import pathlib
        pathlib.Path(a.html).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.html).write_text("\n".join(h))
        print(f"\nMovement-1 HTML → {a.html} ({len(''.join(h))} bytes)")


if __name__ == "__main__":
    main()
