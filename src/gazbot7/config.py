"""GAZBOT V7 — run configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateSpec:
    """One live gate in the (single-position) two-gate lineup. The desk takes whichever
    gate fires when flat, sizes it, and routes its exit — all keyed off this spec."""
    name: str                          # position tag / reason ("grind" | "rgv")
    kind: str                          # "grind" | "reversal_grab" | "thrust"
    params: dict = field(default_factory=dict)
    sizing: str = "flat"               # "flat" (base_size) | "conviction" (0..base by ER)
    base_size: int = 2
    exit: str = "scalp"                # "chandelier" (momentum, uncapped) | "scalp" (fixed R)
    target_r: float = 2.0              # scalp target (× stop)
    stop_atr_mult: float = 1.0         # native 1-ATR stop mirror
    chandelier_start_k: float = 3.5
    chandelier_min_k: float = 0.5
    chandelier_tighten: float = 0.75
    vol_adaptive_chandelier: bool = False  # start_k from chandelier_start_k(entry_atr)
    adverse_cut_atr: float = 0.0       # 0 = disabled (kept off for backtest parity)
    # dollar give-back ("ratchet 2", 2026-07-20): once >= arm_usd favorable, cut on a
    # giveback_usd retrace from peak (position $, incl. qty). Caps the green-then-reverse
    # deep losers the wide chandelier / trail-less scalp miss. See GIVEBACK_EXIT_SCOPE.md.
    giveback_enabled: bool = False
    giveback_arm_usd: float = 50.0
    giveback_usd: float = 40.0


def live_gates() -> list[GateSpec]:
    """The 2026-07-19 go-live lineup (replaces thrust; thrust stays in the shadow slate):
    grind_fast (early-entry momentum, ER conviction 0/1/2, vol-adaptive chandelier) +
    rg_long_fast_v (chop reversion, 2R). Single-position — first to fire wins."""
    return [
        GateSpec(name="grind", kind="grind",
                 params={"slope_min": 0.4, "fast_slope": True},
                 sizing="conviction", base_size=2,
                 exit="chandelier", vol_adaptive_chandelier=True,
                 giveback_enabled=True, giveback_arm_usd=50.0, giveback_usd=40.0),
        GateSpec(name="rgv", kind="reversal_grab",
                 params={"side": "LONG", "ext_min": 2.0, "turn_atr": 0.15,
                         "fast_slope": True, "fast_turn": True, "atr_min": 13.0},
                 sizing="flat", base_size=2, exit="scalp", target_r=2.0, stop_atr_mult=1.0,
                 giveback_enabled=True, giveback_arm_usd=50.0, giveback_usd=40.0),
    ]


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
    # two-gate lineup (empty = legacy single-gate via `gate`/`gate_params`). live cutover
    # sets this to live_gates() → grind + rgv, single-position, first-to-fire.
    gates: list = field(default_factory=list)
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
    # 2026-07-17 operator: KILLED on the live desk — it cut ~70% of thrust fires
    # (14 shadow -> 4 live) and removed winners on trend days. The veto lives on in
    # shadow (abs_veto_50s/55s/60s) for duration study; live fires immediately.
    entry_confirm_s: float = 0.0
    # strategy-side managed exits (the native STP owns STOP; these are on top)
    adverse_cut_atr: float = 1.5
    absorption_flow_min: float = 50.0
    # absorption is a CATASTROPHE backstop, not a scalp-cutter (2026-07-16 operator:
    # "supposed to cut huge losses of $200, not cut every trade off; happy to wear
    # $40-50 losses"). It fires ONLY once a trade is at least this far underwater —
    # so it can never cut a winner (no loss) or a small loss; the native ~1-ATR stop
    # is the normal loss exit, absorption catches a runaway that escapes it.
    absorption_min_loss_usd: float = 60.0
    # dollar give-back ("ratchet 2", 2026-07-20) for the legacy single-gate path; the
    # two-gate lineup carries its own per-GateSpec giveback_* (both enabled at go-live).
    giveback_enabled: bool = False
    giveback_arm_usd: float = 50.0
    giveback_usd: float = 40.0
    # session discipline (S4) — never hold overnight, never open into the close
    max_hold_minutes: float = 120.0    # hard ceiling regardless of P&L
    no_open_minutes: float = 20.0      # suppress new entries this long before close
    session_flat_minutes: float = 5.0  # in-loop session-end flatten backstop (timer is primary)
    # kill-switches (S8) — bound the catastrophic day (0 disables)
    # KILL-SWITCHES — live-money safety, DISABLED for paper tuning (2026-07-16 operator:
    # "its paper, we need to see action"). Both work (proven); re-enable for go-live:
    # daily 300, streak 4. The native 1-ATR stop still caps every individual trade.
    max_daily_loss_usd: float = 0.0    # 0 = no daily-loss halt (paper tuning)
    loss_streak_halt: int = 0          # 0 = no loss-streak halt (paper tuning)
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
