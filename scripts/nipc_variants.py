#!/usr/bin/env python3
"""NIPC divergence hunt — which reading of the report's ambiguous geometry (if any)
reproduces the lab? Subclasses the shipped NipcTracker so only the disputed rule changes;
everything else (sequencing, cooldown, exits, costs, tape) is the acceptance harness.

Also prints an MFE/MAE census: was a 43.3% hit rate on a 2.5R target even AVAILABLE from
the entries each variant produces? That separates "wrong entry" from "wrong exit".
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

import duckdb  # noqa: E402

from gazbot7.deciders import (  # noqa: E402
    NIPC_ATR_MULT,
    NIPC_IMPULSE_BARS,
    NIPC_RES,
    NIPC_RMAX,
    NIPC_RMIN,
    NIPC_SPAN_MIN_PT,
    NIPC_STOP_BUF_PT,
    NipcSetup,
    NipcTracker,
    nipc_dead_chop,
    nipc_in_window,
)
from nipc_replay import CAP, DAYS, load_day, replay_day  # noqa: E402


class V_HL(NipcTracker):
    """org = the OPPOSITE extreme inside the impulse window (low for a LONG), not close[i-24]
    — the widest reasonable reading of 'span = |ext - org|'."""

    def _detect_impulse(self, bar, er15):
        if len(self._bars) < NIPC_IMPULSE_BARS + 1 or not nipc_in_window(bar.ts * 1000):
            return
        org_bar = self._bars[-(NIPC_IMPULSE_BARS + 1)]
        atr_pre = self._atrs[-(NIPC_IMPULSE_BARS + 1)]
        if atr_pre <= 0:
            return
        dead = nipc_dead_chop(atr_pre, er15)
        if dead and self._apply_regime:
            return
        leg = bar.close - org_bar.close
        if abs(leg) < NIPC_ATR_MULT * atr_pre:
            return
        side = "LONG" if leg > 0 else "SHORT"
        w = list(self._bars)[-NIPC_IMPULSE_BARS:]
        ext = max(b.high for b in w) if side == "LONG" else min(b.low for b in w)
        org = min(b.low for b in w) if side == "LONG" else max(b.high for b in w)
        span = abs(ext - org)
        if span < NIPC_SPAN_MIN_PT:
            return
        self.setup = NipcSetup(side=side, ext=ext, org=org, span=span, detect_ms=bar.ts * 1000,
                               atr1m=atr_pre, er15=er15, dead_chop=dead, pb_ext=ext)


class V_CLOSE(NipcTracker):
    """ext = close[i] (the impulse END), org = close[i-24] — the pure-leg reading."""

    def _detect_impulse(self, bar, er15):
        if len(self._bars) < NIPC_IMPULSE_BARS + 1 or not nipc_in_window(bar.ts * 1000):
            return
        org_bar = self._bars[-(NIPC_IMPULSE_BARS + 1)]
        atr_pre = self._atrs[-(NIPC_IMPULSE_BARS + 1)]
        if atr_pre <= 0:
            return
        dead = nipc_dead_chop(atr_pre, er15)
        if dead and self._apply_regime:
            return
        leg = bar.close - org_bar.close
        if abs(leg) < NIPC_ATR_MULT * atr_pre:
            return
        span = abs(leg)
        if span < NIPC_SPAN_MIN_PT:
            return
        self.setup = NipcSetup(side=("LONG" if leg > 0 else "SHORT"), ext=bar.close,
                               org=org_bar.close, span=span, detect_ms=bar.ts * 1000,
                               atr1m=atr_pre, er15=er15, dead_chop=dead, pb_ext=bar.close)


class V_EXTEND(NipcTracker):
    """The impulse keeps EXTENDING while we wait: a new extreme moves ext and grows span,
    and resets the pullback. (Reading: 'walk forward tracking the retrace' from a live ext.)"""

    def _advance_pullback(self, bar):
        s = self.setup
        s.bars_seen += 1
        if s.side == "LONG":
            if bar.high > s.ext:
                s.ext = bar.high
                s.span = abs(s.ext - s.org)
                s.pb_ext = s.ext
            s.pb_ext = min(s.pb_ext, bar.low)
            r = (s.ext - s.pb_ext) / s.span
        else:
            if bar.low < s.ext:
                s.ext = bar.low
                s.span = abs(s.ext - s.org)
                s.pb_ext = s.ext
            s.pb_ext = max(s.pb_ext, bar.high)
            r = (s.pb_ext - s.ext) / s.span
        if r > NIPC_RMAX:
            self.setup = None
            return
        if r >= NIPC_RMIN:
            self._arm(bar, r)
            return
        if s.bars_seen >= 36:
            self.setup = None


class V_DEEP(NipcTracker):
    """The half-back level TRACKS a deepening pullback while the 1-min trigger is live
    (i.e. the resting order is re-priced off the running pullback extreme)."""

    def on_bar(self, bar, *, atr1m, er15, busy=False):
        s = self.setup
        if s is not None and s.armed_ms:
            self._bars.append(bar)
            self._atrs.append(atr1m)
            if (bar.ts + 5) * 1000 >= s.expires_ms:
                self.setup = None
                return
            if s.side == "LONG" and bar.low < s.pb_ext:
                s.pb_ext = bar.low
                s.entry_level = s.pb_ext + NIPC_RES * (s.ext - s.pb_ext)
                s.stop = s.pb_ext - NIPC_STOP_BUF_PT
                s.r_pt = abs(s.entry_level - s.stop)
            elif s.side == "SHORT" and bar.high > s.pb_ext:
                s.pb_ext = bar.high
                s.entry_level = s.pb_ext - NIPC_RES * (s.pb_ext - s.ext)
                s.stop = s.pb_ext + NIPC_STOP_BUF_PT
                s.r_pt = abs(s.entry_level - s.stop)
            return
        super().on_bar(bar, atr1m=atr1m, er15=er15, busy=busy)


VARIANTS = {
    "SHIPPED  ext=maxHigh org=close[i-24]": NipcTracker,
    "V_HL     org=opposite extreme       ": V_HL,
    "V_CLOSE  ext=close[i] (pure leg)    ": V_CLOSE,
    "V_EXTEND impulse may extend         ": V_EXTEND,
    "V_DEEP   level tracks deeper pullback": V_DEEP,
}


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS cap (TYPE SQLITE, READ_ONLY)")
    tape = {d: load_day(con, d) for d in DAYS}
    print(f"{'variant':38} {'n':>4} {'HOMEn':>6} {'net$':>8} {'$/tr':>6} {'win%':>6} "
          f"{'medR':>5} {'hold_m':>6} {'green':>6}")
    for name, cls in VARIANTS.items():
        allt = []
        for d in DAYS:
            b5, tk = tape[d]
            if b5:
                allt += replay_day(d, b5, tk, lot_a=None, lot_b=2.5, tracker_cls=cls)
        home = [t for t in allt if t["regime"] != "dead-chop"]
        if not home:
            print(f"{name:38} {len(allt):>4} 0"); continue
        net = sum(t["net"] for t in home)
        w = sum(1 for t in home if t["net"] > 0)
        rs = sorted(t["R"] for t in home)
        byday = {}
        for t in home:
            byday[t["day"]] = byday.get(t["day"], 0) + t["net"]
        print(f"{name:38} {len(allt):>4} {len(home):>6} {net:>+8.0f} {net/len(home):>+6.1f} "
              f"{100*w/len(home):>5.1f}% {rs[len(rs)//2]:>5.1f} "
              f"{sum(t['hold_s'] for t in home)/len(home)/60:>6.1f} "
              f"{sum(1 for v in byday.values() if v > 0):>3}/{len(byday)}")
    print("\nLAB TARGET                             205    171    +2676  +15.6  43.3%  17.2    2.4   9/12")


if __name__ == "__main__":
    main()
