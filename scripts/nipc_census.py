#!/usr/bin/env python3
"""NIPC state-machine census + the report's own ablation trade-counts as a fingerprint.

The report publishes n for six ablations. Those counts are a structural signature of the
state machine that is independent of the P&L, so if our n's track theirs the entry engine
is the same shape and the divergence is downstream; if they don't, the disputed rule is
upstream. Prints both.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

import duckdb  # noqa: E402

import gazbot7.deciders as D  # noqa: E402
from nipc_replay import CAP, DAYS, load_day, replay_day  # noqa: E402


class Census(D.NipcTracker):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.c = {"impulse": 0, "rmax_abandon": 0, "no_pullback": 0, "armed": 0,
                  "arm_rejected": 0, "expired_nofill": 0, "filled": 0}

    def _detect_impulse(self, bar, er15):
        before = self.setup
        super()._detect_impulse(bar, er15)
        if before is None and self.setup is not None:
            self.c["impulse"] += 1

    def _advance_pullback(self, bar):
        s = self.setup
        n0 = s.bars_seen
        super()._advance_pullback(bar)
        if self.setup is None:
            self.c["rmax_abandon" if n0 + 1 < D.NIPC_PULLBACK_BARS else "no_pullback"] += 1
        elif self.setup.armed_ms:
            self.c["armed"] += 1

    def _arm(self, bar, r):
        super()._arm(bar, r)
        if self.setup is None:
            self.c["arm_rejected"] += 1

    def on_bar(self, bar, *, atr1m, er15, busy=False):
        s = self.setup
        super().on_bar(bar, atr1m=atr1m, er15=er15, busy=busy)
        if s is not None and s.armed_ms and self.setup is None:
            self.c["expired_nofill"] += 1

    def trigger(self, ts_ms, price):
        r = super().trigger(ts_ms, price)
        if r is not None:
            self.c["filled"] += 1
        return r


def run(tape, cls=D.NipcTracker, lot_b=2.5):
    allt, cens = [], {}
    for d in DAYS:
        b5, tk = tape[d]
        if not b5:
            continue
        holder = {}

        def mk(**kw):
            t = cls(**kw)
            holder["t"] = t
            return t
        allt += replay_day(d, b5, tk, lot_a=None, lot_b=lot_b, tracker_cls=mk)
        if isinstance(holder.get("t"), Census):
            for k, v in holder["t"].c.items():
                cens[k] = cens.get(k, 0) + v
    return allt, cens


def line(tag, allt, lab_n=None):
    home = [t for t in allt if t["regime"] != "dead-chop"]
    net = sum(t["net"] for t in home)
    w = sum(1 for t in home if t["net"] > 0) / max(1, len(home))
    lab = f"   (lab n={lab_n})" if lab_n else ""
    return (f"{tag:<42} blanket_n={len(allt):>4}  home_n={len(home):>4}  "
            f"net={net:>+7.0f}  win={100*w:>4.1f}%{lab}")


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS cap (TYPE SQLITE, READ_ONLY)")
    tape = {d: load_day(con, d) for d in DAYS}

    allt, cens = run(tape, Census)
    print("── state-machine census (blanket, 12 days) ──")
    for k in ("impulse", "rmax_abandon", "no_pullback", "arm_rejected", "armed",
              "expired_nofill", "filled"):
        print(f"  {k:<16} {cens.get(k, 0):>5}")

    print("\n── ablations: our n vs the report's published n ──")
    print(line("FULL NIPC", allt, 171))

    base = dict(RMIN=D.NIPC_RMIN, RMAX=D.NIPC_RMAX, RES=D.NIPC_RES, IMP=D.NIPC_IMPULSE_BARS)
    for tag, patch, lab_n in [
        ("shallow pullback only (RMIN=0.15)", {"NIPC_RMIN": 0.15}, 257),
        ("no invalidation (RMAX=1.5)", {"NIPC_RMAX": 1.5}, 173),
        ("no resumption trigger (RES=0)", {"NIPC_RES": 0.0}, 230),
        ("no pullback req (RMIN=0, RES=0)", {"NIPC_RMIN": 0.0, "NIPC_RES": 0.0}, 290),
        ("impulse window too short (1 min)", {"NIPC_IMPULSE_BARS": 12}, 167),
    ]:
        old = {k: getattr(D, k) for k in patch}
        for k, v in patch.items():
            setattr(D, k, v)
        a, _ = run(tape)
        print(line(tag, a, lab_n))
        for k, v in old.items():
            setattr(D, k, v)
    assert (D.NIPC_RMIN, D.NIPC_RMAX, D.NIPC_RES, D.NIPC_IMPULSE_BARS) == \
        (base["RMIN"], base["RMAX"], base["RES"], base["IMP"])


if __name__ == "__main__":
    main()
