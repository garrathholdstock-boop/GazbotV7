"""ACCEPTANCE TEST — does the Movement-2 harness reproduce the desk's own live fires?
The tournament took exactly three gate signals this week (5 of 6 gates were benched all
week). Replay the harness at 1Hz around each and see whether the same gate fires."""
import sys, datetime as dt
sys.path.insert(0, "/home/alphabot/gazbot7/scripts"); sys.path.insert(0, "/home/alphabot/gazbot7/src")
from m2_idle_gates import (bars_at, footprint_at, tape_window, gate_fires, GATES, SIDE,
                           compute_features, efficiency_ratio, last_tick_px, ATR_FLOOR, atr_blocks)

LIVE = [("capitulation_long", "2026-08-28T14:00:10Z"),
        ("grind_long",        "2026-08-28T14:45:04Z"),
        ("abs_veto_long",     "2026-08-28T14:46:01Z")]

for gate, iso in LIVE:
    t = int(dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp())
    hits = []
    for s in range(t - 180, t + 61):
        bars = bars_at(s)
        if len(bars) < 6:
            continue
        f = compute_features(bars)
        w = tape_window(s - 60, s - 1); nf = w[0] - w[1]
        fp = footprint_at(s)
        if gate_fires(gate, f, nf, fp):
            hits.append((s - t, round(f.atr, 2), round(efficiency_ratio(bars), 3)))
    print(f"{gate} live @{iso}: harness fires at offsets(s) "
          f"{[h[0] for h in hits][:12]}{' …' if len(hits) > 12 else ''}  n={len(hits)}")
    if hits:
        print(f"    nearest offset {min(hits, key=lambda h: abs(h[0]))}  "
              f"(atr, er) — ATR floor {ATR_FLOOR.get(gate, '—')}")
