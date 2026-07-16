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
    # momentum PROFIT exit (2026-07-16, operator: "chandelier shouldve always been
    # live"). The tightening ATR chandelier (V5 go-live logic, clean-room) REPLACES
    # the fixed 2R target for the thrust gate: k = max(min_k, start_k - tighten*peak_r),
    # give-back = k*ATR from peak, profit-only (native 1-ATR stop owns the downside).
    # It uncaps the runner. chandelier_enabled=False → back to the fixed 2R target.
    chandelier_enabled: bool = True
    chandelier_start_k: float = 3.5
    chandelier_min_k: float = 0.5
    chandelier_tighten: float = 0.75
    # delayed-entry absorption confirm (2026-07-16, operator idea): on a thrust
    # signal, WAIT this long watching the tape — enter only if the thrust still
    # fires (continuation) AND no absorption appeared. Turns absorption from a
    # post-entry loss-cutter into a pre-entry veto. 0 = immediate (disables the wait).
    entry_confirm_s: float = 45.0
    # strategy-side managed exits (the native STP owns STOP; these are on top)
    adverse_cut_atr: float = 1.5
    absorption_flow_min: float = 50.0
    # absorption is a CATASTROPHE backstop, not a scalp-cutter (2026-07-16 operator:
    # "supposed to cut huge losses of $200, not cut every trade off; happy to wear
    # $40-50 losses"). It fires ONLY once a trade is at least this far underwater —
    # so it can never cut a winner (no loss) or a small loss; the native ~1-ATR stop
    # is the normal loss exit, absorption catches a runaway that escapes it.
    absorption_min_loss_usd: float = 60.0
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
    shadow_store_path: str = "data/shadow.db"  # isolated shadow-desk store (no live path)
    # loop
    cadence_s: float = 1.0
    bar_lookback: int = 60  # 5s bars fed to the deciders
    tape_window_s: int = 60
    # SAFETY: default is dry-run — capture + decide + shadow, NO live orders.
    # Cutover flips this to True (V7 solo on the paper account).
    place_live: bool = False
