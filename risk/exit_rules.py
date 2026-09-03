"""Adaptive take-profit / stop-loss / DTE exit rules."""

from dataclasses import dataclass
from enum import Enum

from config.settings import Settings


class ExitReason(str, Enum):
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    FORCE_DTE = "force_dte"


@dataclass
class ExitThresholds:
    take_profit_pct: float
    stop_loss_pct: float
  # stop_loss_pct is negative, e.g. -0.25


@dataclass
class ExitDecision:
    reason: ExitReason
    pnl_pct: float
    dte: int
    thresholds: ExitThresholds


def adaptive_exit_thresholds(dte: int, settings: Settings) -> ExitThresholds:
    """Scale TP/SL with remaining DTE — more time allows wider targets and stops."""
    lo = settings.exit_force_dte
    hi = max(settings.exit_dte_scale_max, lo + 1)
    span = hi - lo
    t = max(0.0, min(1.0, (dte - lo) / span))

    take_profit = settings.exit_tp_min + t * (settings.exit_tp_max - settings.exit_tp_min)
    stop_mag = settings.exit_sl_min + t * (settings.exit_sl_max - settings.exit_sl_min)
    return ExitThresholds(take_profit_pct=take_profit, stop_loss_pct=-stop_mag)


def evaluate_exit(pnl_pct: float, min_dte: int, settings: Settings) -> ExitDecision | None:
    if not settings.exit_enabled:
        return None

    thresholds = adaptive_exit_thresholds(min_dte, settings)

    if min_dte <= settings.exit_force_dte:
        return ExitDecision(
            reason=ExitReason.FORCE_DTE,
            pnl_pct=pnl_pct,
            dte=min_dte,
            thresholds=thresholds,
        )

    if pnl_pct >= thresholds.take_profit_pct:
        return ExitDecision(
            reason=ExitReason.TAKE_PROFIT,
            pnl_pct=pnl_pct,
            dte=min_dte,
            thresholds=thresholds,
        )

    if pnl_pct <= thresholds.stop_loss_pct:
        return ExitDecision(
            reason=ExitReason.STOP_LOSS,
            pnl_pct=pnl_pct,
            dte=min_dte,
            thresholds=thresholds,
        )

    return None
