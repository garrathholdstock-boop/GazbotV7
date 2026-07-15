"""GAZBOT V7 — run configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunConfig:
    # IBKR
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 7
    # instrument (LIVE is MNQ-only)
    symbol: str = "MNQ"
    exchange: str = "CME"
    value_per_point: float = 2.0
    fee_rt: float = 1.5
    # desk
    size: int = 1
    gate: str = "thrust"
    # thr 1.5→2.5 (2026-07-15): the trade-so-far analysis showed weak thrusts
    # (net_atr<1.5) are pure churn (-$51, 29% win); strong (≥2.5) are the edge
    # (+$41.5, +5.19/tr). A gate filter, not a blocker. thrust_shadow keeps 1.5 as
    # the control for the honest A/B.
    gate_params: dict = field(default_factory=lambda: {"thr": 2.5})
    target_r: float = 2.0
    # paths
    store_path: str = "data/gazbot7.db"
    capture_path: str = "data/capture.db"
    # loop
    cadence_s: float = 1.0
    bar_lookback: int = 60  # 5s bars fed to the deciders
    tape_window_s: int = 60
    # SAFETY: default is dry-run — capture + decide + shadow, NO live orders.
    # Cutover flips this to True (V7 solo on the paper account).
    place_live: bool = False
