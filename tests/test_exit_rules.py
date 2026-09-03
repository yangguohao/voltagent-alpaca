"""Tests for adaptive exit rules."""

from config.settings import Settings
from risk.exit_rules import ExitReason, adaptive_exit_thresholds, evaluate_exit


def test_adaptive_thresholds_widen_with_dte():
    settings = Settings(
        exit_force_dte=7,
        exit_dte_scale_max=35,
        exit_tp_min=0.15,
        exit_tp_max=0.40,
        exit_sl_min=0.20,
        exit_sl_max=0.40,
    )
    low = adaptive_exit_thresholds(7, settings)
    high = adaptive_exit_thresholds(35, settings)
    assert low.take_profit_pct == 0.15
    assert high.take_profit_pct == 0.40
    assert low.stop_loss_pct == -0.20
    assert high.stop_loss_pct == -0.40


def test_take_profit_trigger():
    settings = Settings(exit_enabled=True, exit_force_dte=7)
    thresholds = adaptive_exit_thresholds(23, settings)
    decision = evaluate_exit(thresholds.take_profit_pct + 0.01, 23, settings)
    assert decision is not None
    assert decision.reason == ExitReason.TAKE_PROFIT


def test_stop_loss_trigger():
    settings = Settings(exit_enabled=True, exit_force_dte=7)
    thresholds = adaptive_exit_thresholds(23, settings)
    decision = evaluate_exit(thresholds.stop_loss_pct - 0.01, 23, settings)
    assert decision is not None
    assert decision.reason == ExitReason.STOP_LOSS


def test_force_close_on_dte():
    settings = Settings(exit_enabled=True, exit_force_dte=7)
    decision = evaluate_exit(0.05, 7, settings)
    assert decision is not None
    assert decision.reason == ExitReason.FORCE_DTE


def test_hold_inside_band():
    settings = Settings(exit_enabled=True, exit_force_dte=7)
    decision = evaluate_exit(-0.05, 23, settings)
    assert decision is None
