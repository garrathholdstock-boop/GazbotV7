#!/usr/bin/env python3
"""Render each session as a PNG plus an exact pixel->data transform, for hand-labelling.

★2026-09-04, operator: *"you are picking some of the tunnels correctly and not others. your green
dots are mostly all wrong. what is the best way for me to show you?"*

The bottleneck is no longer measurement, it is GROUND TRUTH. He can read these off the tape and I
cannot, so the fastest path is to let him draw his tunnels and breaks directly on the chart and hand
back exact timestamps — then my detector can be SCORED against his labels instead of argued about.

★ THE TRANSFORM IS THE WHOLE POINT. Each PNG ships with the axes' pixel bbox and data limits, so the
browser can invert a click to (timestamp, price) exactly. Eyeballing coordinates off an image would
reintroduce the imprecision this is meant to remove.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates          # noqa: E402
import matplotlib.pyplot as plt            # noqa: E402
from matplotlib.patches import Rectangle   # noqa: E402

GB = "/home/alphabot/gazbot7"
# ⚠ FLAT, NOT A SUBDIRECTORY. web.py's static route is
# `os.path.join(_STATIC, os.path.basename(path))` — basename only, so `label/x.png` resolves to
# `x.png` in the root and 500s. Prefixed filenames in the root are the routing the server has.
OUT = f"{GB}/src/gazbot7/web_static"
PREFIX = "tl_"
DPI = 110
FIG = (13.0, 6.2)

_s = importlib.util.spec_from_file_location("tp", f"{GB}/scripts/tunnel_pages.py")
tp = importlib.util.module_from_spec(_s)
_s.loader.exec_module(tp)
tw = tp.tw


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(dt.UTC)
    bars = tp.minute_bars((now - dt.timedelta(weeks=tp.WEEKS)).timestamp(), now.timestamp())
    trs = tw.true_range(bars)
    post = tw.filter_states(trs)                     # one continuous causal pass, then slice
    by: dict[str, list[int]] = {}
    for i, b in enumerate(bars):
        by.setdefault(tp.session_key(b["m"]), []).append(i)

    manifest = []
    for sk in sorted(by):
        idx = by[sk]
        if len(idx) < 60:
            continue
        sb = [bars[i] for i in idx]
        sp = [post[i] for i in idx]
        x = [dt.datetime.fromtimestamp(b["m"], dt.UTC) for b in sb]
        close = [b["close"] for b in sb]

        fig, ax = plt.subplots(figsize=FIG)
        a0 = x[0].replace(hour=0, minute=0, second=0, microsecond=0)
        for shift in (0, 1):
            lo_a = a0 + dt.timedelta(days=shift)
            hi_a = lo_a + dt.timedelta(hours=7)
            if hi_a >= x[0] and lo_a <= x[-1]:
                ax.axvspan(max(lo_a, x[0]), min(hi_a, x[-1]), color="#9aa0a6", alpha=.10, lw=0)
        ax.plot(x, close, lw=.9, color="#202124", zorder=3)

        mine = []
        for a, b in tp.quiet_runs(sp, 1):
            seg = sb[a:b + 1]
            n = len(seg)
            hi = max(s["hi"] for s in seg); lo = min(s["lo"] for s in seg)
            big = n >= tw.MIN_TUNNEL_MIN
            ax.add_patch(Rectangle((mdates.date2num(x[a]), lo),
                                   mdates.date2num(x[b]) - mdates.date2num(x[a]), hi - lo,
                                   facecolor="#FFD400" if big else "#FFF3B0",
                                   alpha=.45 if big else .25, edgecolor="none", zorder=1))
            if not big:
                continue
            buf = tp.BUF_PCT * (hi - lo)
            j, side, cpx = tp.first_break(sb, a, b, hi, lo, buf)
            rec = {"t0": int(sb[a]["m"]), "t1": int(sb[b]["m"]), "n": n,
                   "hi": round(hi, 2), "lo": round(lo, 2)}
            if j is not None:
                rec.update(bt=int(sb[j]["m"]), bside=side, bpx=round(cpx, 2))
                ax.scatter([x[j]], [cpx], s=150, facecolor="#00A651", alpha=.35,
                           edgecolor="#00703C", lw=1.0, zorder=4)
            mine.append(rec)

        ax.set_title(f"MNQ — CME session {sk}", fontsize=11, loc="left")
        ax.grid(alpha=.15, lw=.5)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=dt.timezone.utc))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        ax.tick_params(labelsize=8)
        fig.tight_layout()

        png = f"{OUT}/{PREFIX}{sk}.png"
        fig.savefig(png, dpi=DPI)
        # ★ the exact transform, AFTER tight_layout — the axes box moves, and a stale bbox would
        #   silently shift every label he gives us by a few minutes.
        bb = ax.get_position()
        w_px, h_px = fig.get_size_inches() * DPI
        meta = {"session": sk, "png": f"{PREFIX}{sk}.png",
                "px": {"w": int(round(w_px)), "h": int(round(h_px)),
                       "l": bb.x0 * w_px, "r": bb.x1 * w_px,
                       "t": (1 - bb.y1) * h_px, "b": (1 - bb.y0) * h_px},
                "data": {"t0": int(sb[0]["m"]), "t1": int(sb[-1]["m"]),
                         "y0": float(ax.get_ylim()[0]), "y1": float(ax.get_ylim()[1])},
                "mine": mine}
        plt.close(fig)
        manifest.append(meta)

    with open(f"{OUT}/{PREFIX}manifest.json", "w") as fh:
        json.dump({"built": now.isoformat(timespec="seconds"), "symbol": tp.SYMBOL,
                   "min_tunnel_min": tw.MIN_TUNNEL_MIN, "buf_pct": tp.BUF_PCT,
                   "sessions": manifest}, fh, indent=1)
    print(f"tunnel_label_build: {len(manifest)} sessions -> {OUT}")
    print(f"  my tunnels drawn: {sum(len(m['mine']) for m in manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
