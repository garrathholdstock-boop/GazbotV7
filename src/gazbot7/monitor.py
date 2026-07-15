"""GAZBOT V7 — execution health monitor (D9). Fills-based, no false positives.

The V5 monitor CRIT'd on a benign event: a partial-fill scalp that recorded via
the ~2-min backfill looked like "fills WEDGED", firing an unnecessary gateway
reboot that cascaded (re-stuck the 5s farm → MD bounce). That happened because
V5 conflated "recording deferred" with "fills ceased".

In V7 that conflation is impossible: there is **no backfill path** — every fill
is a real-time execDetails fill recorded atomically (D3). So the monitor measures
ACTUAL fills, and a CRIT means fills genuinely ceased while signals fired — a real
wedge, unambiguously. A normal 2-lot scalp (the thing that false-CRIT'd V5) reads
OK. Clean-room: nothing copied.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

_ORDER = {"OK": 0, "WARN": 1, "CRIT": 2}


@dataclass(frozen=True, slots=True)
class HealthVerdict:
    submitted: int
    fills: int
    rejects: int
    status: str  # OK / WARN / CRIT
    detail: str


def classify_execution(*, submitted: int, fills: int, rejects: int, min_submitted_crit: int = 3) -> tuple[str, str]:
    """Pure classifier. CRIT only when fills actually ceased under real activity."""
    if rejects >= min_submitted_crit and fills == 0:
        return "CRIT", f"{rejects} rejects / 0 fills — orders rejected, execution down"
    if submitted >= min_submitted_crit and fills == 0:
        return "CRIT", f"{submitted} signals submitted / 0 fills — execution WEDGED"
    if submitted > 0 and fills == 0:
        return "WARN", f"{submitted} submitted / 0 fills (below CRIT threshold — watch)"
    return "OK", f"{fills} fills / {submitted} submitted / {rejects} rejects"


def execution_health(store, *, since_iso: str) -> HealthVerdict:
    submitted = store.execute(
        "SELECT COUNT(*) FROM signals WHERE outcome='submitted' AND ts>=?", (since_iso,)
    ).fetchone()[0]
    rejects = store.execute(
        "SELECT COUNT(*) FROM signals WHERE outcome='rejected' AND ts>=?", (since_iso,)
    ).fetchone()[0]
    fills = store.execute(
        "SELECT COUNT(*) FROM fills WHERE ingested_at>=?", (since_iso,)
    ).fetchone()[0]
    status, detail = classify_execution(submitted=submitted, fills=fills, rejects=rejects)
    return HealthVerdict(submitted, fills, rejects, status, detail)


def heartbeat_status(path: str, now_iso: str, *, max_age_s: float = 120.0) -> tuple[str, str]:
    """Is core alive? Reads its heartbeat file's ts vs now. Missing = CRIT (core
    down / never wrote); stale beyond max_age_s = CRIT (core hung)."""
    try:
        with open(path) as f:
            hb = json.load(f)
        age = (datetime.fromisoformat(now_iso) - datetime.fromisoformat(hb["ts"])).total_seconds()
    except FileNotFoundError:
        return "CRIT", "core heartbeat missing (core down?)"
    except Exception:
        return "WARN", "core heartbeat unreadable"
    if age > max_age_s:
        return "CRIT", f"core heartbeat stale {age:.0f}s (hung/dead)"
    return "OK", f"core alive ({age:.0f}s)"


def _worst(*statuses: str) -> str:
    return max(statuses, key=lambda s: _ORDER[s])


def main() -> int:  # `python -m gazbot7.monitor` — the external 10-min sweep
    import os
    from datetime import UTC, timedelta

    from .store import open_store

    store_path = os.environ.get("GAZBOT7_STORE", "data/gazbot7.db")
    data_dir = os.path.dirname(store_path) or "."
    now = datetime.now(UTC)
    store = open_store(store_path)
    ex = execution_health(store, since_iso=(now - timedelta(minutes=30)).isoformat())
    hb_status, hb_detail = heartbeat_status(os.path.join(data_dir, "core_health.json"), now.isoformat())
    status = _worst(ex.status, hb_status)
    line = f"MONITOR {status}: exec[{ex.detail}] hb[{hb_detail}]"
    print(line)
    if status == "CRIT":  # judged on FILLS, not submits — a real wedge/outage pages
        from .notify import notify
        notify(f"Garrath — V7 {line} (need you on Termius to check the desk)", critical=True)
    return 0  # a monitor must never fail its host


if __name__ == "__main__":
    raise SystemExit(main())
