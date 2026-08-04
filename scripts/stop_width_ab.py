#!/usr/bin/env python3
"""FORWARD A/B SCOREBOARD — stop width (sw_) and quiet-tape clip (cx_), both paired.

Reads the sw_*_k10 (control) / sw_*_k20 (test) shadow arms. Both arms run the same gate on the same
feed with the same target; the ONLY difference is stop_atr_mult. So the deliverable is the DELTA.

★ SCORED ON real_pnl, NEVER ceiling_pnl. shadow.py's own rule: real_pnl "is the only number we trust".
Trades still awaiting the tick repricer are reported as unscored rather than counted at zero, so
repricer lag can never masquerade as a flat result.

★ PAIRED WHERE POSSIBLE. The honest comparison is over signals BOTH arms took: a like-for-like sum on
the same entries. Unpaired trades (one arm entered, the other did not) are reported separately rather
than folded in.

★ EXPECT THE ARMS TO TAKE DIFFERENT NUMBERS OF TRADES — IT IS AN EFFECT, NOT A BUG.
A 7-day dry-run gave grind_A 141 entries at 1.0x but only 128 at 2.0x. The entry logic is identical; the
cause is OCCUPANCY. A wider stop is not hit as quickly, so the arm holds its position longer and is
still busy when the next signal arrives. Widening the stop therefore does two things at once — it
changes the outcome of each trade AND reduces how many trades the slot can take. Anyone reading only
the P&L delta will miss the second, which is why n is printed for both arms on every row.

  PYTHONPATH=src .venv/bin/python scripts/stop_width_ab.py [--days N]
"""
from __future__ import annotations

import argparse
import sys

import duckdb

GB = "/home/alphabot/gazbot7"
# ★2026-08-04 the scoreboard now covers BOTH forward A/Bs. Same pairing machinery: arms fire on the
# same signal, so entries within BUCKET_S are the same trade and the DELTA is the answer.
CLIP_PAIRS = [("grindA", "CLIP grind_long_A 2.5R  (sweep: clip much worse)"),
              ("absLA", "CLIP abs_veto_long_A 1.0R (sweep: clip RESCUES it)"),
              ("absSB", "CLIP abs_veto_short_B 2.5R (sweep: clip WINS)")]
PAIRS = [("grind_A", "grind_long Lot A (2.5R scalp)"),
         ("grind_B", "grind_long Lot B (lock-chandelier)"),
         ("absL_A", "abs_veto_long Lot A (1.0R)"),
         ("absL_B", "abs_veto_long Lot B (1.5R)"),
         ("absS_A", "abs_veto_short Lot A (1.5R)"),
         ("absS_B", "abs_veto_short Lot B (2.5R)")]
BUCKET_S = 120   # entries within this window are the same signal (arms fire on the same bar)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()

    con = duckdb.connect()
    con.execute(f"ATTACH '{GB}/data/shadow.db' AS s (TYPE sqlite, READ_ONLY)")
    rows = con.execute(f"""
        SELECT t.strategy, CAST(t.entry_ts AS BIGINT) ts, r.real_pnl, t.exit_reason, t.entry_atr
        FROM s.shadow_trades t LEFT JOIN s.shadow_real r ON r.trade_id = t.id
        WHERE (t.strategy LIKE 'sw\\_%' ESCAPE '\\' OR t.strategy LIKE 'cx\\_%' ESCAPE '\\')
          AND CAST(t.entry_ts AS BIGINT) >= (SELECT max(CAST(entry_ts AS BIGINT)) FROM s.shadow_trades)
                                            - {a.days * 86400}
        ORDER BY ts""").fetchall()

    if not rows:
        print("No sw_* trades yet. The arms only enter when a momentum gate fires on the live feed —")
        print("give it a session. Verify the slate carries them:")
        print("  PYTHONPATH=src .venv/bin/python -c \"from gazbot7.shadow import default_slate;"
              " print([v.name for v in default_slate() if v.name.startswith('sw_')])\"")
        return 0

    by: dict = {}
    for strat, ts, rp, why, atr in rows:
        if strat.startswith("cx_"):                 # cx_<pair>_live / cx_<pair>_clip
            core = strat[3:]
            pair, arm = core.rsplit("_", 1)
        else:                                       # sw_<pair>_k10 / _k20
            pair, arm = strat[3:-4], strat[-3:]
        by.setdefault(pair, {}).setdefault(arm, []).append((ts, rp, why, atr))

    print(f"STOP-WIDTH A/B — last {a.days}d, scored on real_pnl (paired on entries within {BUCKET_S}s)\n")
    print(f"{'STOP WIDTH':<26}{'n':>4}{'k=1.0':>10}{'k=2.0':>10}{'delta':>10}{'stops 1.0':>11}{'stops 2.0':>11}")
    tot_a = tot_b = 0.0
    tot_n = 0
    unpaired_all = 0
    unscored_all = 0
    for pair, label in PAIRS:
        d = by.get(pair)
        if not d:
            print(f"{label:<26}{'—  no trades yet':>45}")
            continue
        ctl = {t // BUCKET_S: (p, w) for t, p, w, _ in d.get("k10", [])}
        tst = {t // BUCKET_S: (p, w) for t, p, w, _ in d.get("k20", [])}
        keys = sorted(set(ctl) & set(tst))
        unpaired = len(set(ctl) ^ set(tst))
        unpaired_all += unpaired
        unscored = sum(1 for k in keys if ctl[k][0] is None or tst[k][0] is None)
        unscored_all += unscored
        keys = [k for k in keys if ctl[k][0] is not None and tst[k][0] is not None]
        if not keys:
            print(f"{label:<26}{len(set(ctl) & set(tst)):>4}{'(all awaiting repricer)':>41}")
            continue
        pa = sum(ctl[k][0] for k in keys)
        pb = sum(tst[k][0] for k in keys)
        sa = sum(1 for k in keys if ctl[k][1] == "STOP")
        sb = sum(1 for k in keys if tst[k][1] == "STOP")
        tot_a += pa
        tot_b += pb
        tot_n += len(keys)
        print(f"{label:<26}{len(keys):>4}{pa:>+10.0f}{pb:>+10.0f}{pb - pa:>+10.0f}"
              f"{f'{sa}/{len(keys)}':>11}{f'{sb}/{len(keys)}':>11}")
    print("-" * 82)
    print(f"{'TOTAL (paired)':<26}{tot_n:>4}{tot_a:>+10.0f}{tot_b:>+10.0f}{tot_b - tot_a:>+10.0f}")
    if unpaired_all:
        print(f"  ⚠ {unpaired_all} unpaired entries excluded — arms should fire together; if this is "
              f"large the pairing assumption is wrong, not the result")
    if unscored_all:
        print(f"  {unscored_all} paired entries still awaiting the tick repricer (excluded, not zeroed)")
    # ── CLIP A/B ──
    print(f"\n{'CLIP vs LIVE EXIT (ATR<22 only)':<26}{'n':>4}{'live':>10}{'clip':>10}{'delta':>10}"
          f"{'wins live':>11}{'wins clip':>11}")
    ca, cb, cn = 0.0, 0.0, 0
    for pair, label in CLIP_PAIRS:
        d = by.get(pair)
        if not d or "live" not in d or "clip" not in d:
            print(f"{label:<26}{'—  no trades yet':>45}")
            continue
        lv = {t // BUCKET_S: (p, w) for t, p, w, _ in d["live"]}
        cl = {t // BUCKET_S: (p, w) for t, p, w, _ in d["clip"]}
        keys = [k for k in sorted(set(lv) & set(cl)) if lv[k][0] is not None and cl[k][0] is not None]
        if not keys:
            print(f"{label:<26}{'(awaiting repricer)':>45}")
            continue
        pl = sum(lv[k][0] for k in keys)
        pc = sum(cl[k][0] for k in keys)
        wl = sum(1 for k in keys if lv[k][0] > 0)
        wc = sum(1 for k in keys if cl[k][0] > 0)
        ca += pl
        cb += pc
        cn += len(keys)
        print(f"{label:<26}{len(keys):>4}{pl:>+10.0f}{pc:>+10.0f}{pc - pl:>+10.0f}"
              f"{f'{100*wl/len(keys):.0f}%':>11}{f'{100*wc/len(keys):.0f}%':>11}")
    if cn:
        print(f"{'  CLIP TOTAL':<26}{int(cn):>4}{ca:>+10.0f}{cb:>+10.0f}{cb - ca:>+10.0f}")
        print(f"  backtest predicted the clip LOSES ~$1.4/trade below ATR 22 — forward says "
              f"${(cb-ca)/cn:+.2f}/trade on n={int(cn)}")

    print(f"\n  VERDICT so far: {'2.0x AHEAD' if tot_b > tot_a else '1.0x AHEAD'} by "
          f"${abs(tot_b - tot_a):.0f} on n={tot_n}.")
    if tot_n < 40:
        print(f"  ⚠ n={tot_n} is too small to act on. stop_width_study.py already showed a 6-trade "
              f"sample reversing sign against a 52-trade one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
