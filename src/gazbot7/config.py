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
    # V5 tw_mnq_thrust_loose parity (2026-07-15): thr 1.5 + amplitude floor
    # (atr_pct >= 0.04% = 0.0004 fraction) + volume surge — decided on 1-MINUTE
    # bars (strategy aggregates the 5s stream). The earlier thr=2.5 was a 5s-bar
    # artifact: net_atr_5 was a 25s blip, not the sim's 5-min thrust, so it fired
    # constantly. On 1m bars the selective sim edge is restored.
    gate_params: dict = field(default_factory=lambda: {"thr": 1.5, "amp_floor": 0.0004})
    target_r: float = 2.0
    stop_atr_mult: float = 1.0
    # strategy-side managed exits (the native STP owns STOP; these are on top)
    adverse_cut_atr: float = 1.5
    absorption_flow_min: float = 50.0
    # session discipline (S4) — never hold overnight, never open into the close
    max_hold_minutes: float = 120.0    # hard ceiling regardless of P&L
    no_open_minutes: float = 20.0      # suppress new entries this long before close
    session_flat_minutes: float = 5.0  # in-loop session-end flatten backstop (timer is primary)
    # kill-switches (S8) — bound the catastrophic day (0 disables)
    max_daily_loss_usd: float = 300.0  # halt new entries once today's realized P&L ≤ −this
    loss_streak_halt: int = 4          # halt after this many consecutive losing trades
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
