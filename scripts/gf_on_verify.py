#!/usr/bin/env python3
"""Cross-check simulate_fast against the plain tick loop. If these ever disagree, every sweep number
in the section is worthless — so this runs before the sweeps, not after."""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_cands as C  # noqa: E402
import gf_on_engine as E  # noqa: E402

days = E.load_days()
E.attach_regimes(days)
rng = np.random.default_rng(7)
tdays = [d for d in sorted(days) if days[d]["ticks"] is not None]

bad = n = 0
for d in tdays:
    tk = days[d]["ticks"]
    for _ in range(25):
        sod = int(rng.integers(13 * 3600, 15 * 3600))
        direction = int(rng.choice([-1, 1]))
        cfg = dict(stop_pt=float(rng.choice([8, 15, 25, 40])),
                   target_pt=float(rng.choice([20, 40, 80])) if rng.random() < 0.6 else None,
                   trail_arm=float(rng.choice([10, 20, 30])) if rng.random() < 0.6 else None,
                   trail_pt=float(rng.choice([8, 15, 25])),
                   be_arm=float(rng.choice([10, 20])) if rng.random() < 0.4 else None,
                   time_stop_sod=int(rng.choice([15 * 3600, 16 * 3600])))
        if cfg["trail_arm"] is None:
            cfg["trail_pt"] = None
        a = E.simulate(tk, sod, direction, **cfg)
        b = E.simulate_fast(tk, sod, direction, **cfg)
        n += 1
        if (a is None) != (b is None):
            bad += 1
            continue
        if a is None:
            continue
        if abs(a["net"] - b["net"]) > 1e-6 or a["reason"] != b["reason"] or a["exit_sod"] != b["exit_sod"]:
            bad += 1
            if bad < 6:
                print("MISMATCH", d, sod, direction, cfg)
                print("  loop", {k: a[k] for k in ("entry", "exit", "net", "reason", "exit_sod")})
                print("  fast", {k: b[k] for k in ("entry", "exit", "net", "reason", "exit_sod")})

print(f"\nchecked {n} simulations across {len(tdays)} days — mismatches: {bad}")
_ = C
sys.exit(1 if bad else 0)
