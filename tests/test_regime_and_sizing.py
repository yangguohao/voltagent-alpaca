"""Tests for regime gate and position sizing."""

from config.settings import Settings
from risk.position_sizer import PortfolioSnapshot
from risk.regime_gate import RegimeGate, RegimeState
from risk.sizer import PositionSizer, estimate_max_loss_per_contract
from strategies.base import TradeCandidate, TradeLeg


def test_regime_blocks_high_iv_in_low_vol():
    gate = RegimeGate(min_confidence=0.5, enabled=True)
    state = RegimeState(regime="low_vol", confidence=0.8)
    assert gate.allows_signal(state, "low_iv") is True
    assert gate.allows_signal(state, "high_iv") is False


def test_regime_blocks_iron_condor_in_trending():
    gate = RegimeGate(min_confidence=0.5, enabled=True)
    state = RegimeState(regime="trending", confidence=0.8)
    assert gate.allows_strategy(state, "iron_condor", "high_iv") is False
    assert gate.allows_strategy(state, "straddle", "low_iv") is True


def test_position_sizer_debit():
    candidate = TradeCandidate(
        symbol="SPY",
        strategy_name="straddle",
        legs=[TradeLeg("P", "buy"), TradeLeg("C", "buy")],
        metadata={"pricing": {"raw_net": 5.0}},
    )
    loss = estimate_max_loss_per_contract(candidate)
    assert loss == 500.0

    sizer = PositionSizer(Settings(max_risk_per_trade=0.02, max_contracts_per_trade=10))
    result = sizer.size(candidate, PortfolioSnapshot(equity=100_000, buying_power=100_000))
    assert result.qty == 4  # 2000 budget / 500 = 4


def test_position_sizer_credit_iron_condor():
    candidate = TradeCandidate(
        symbol="NVDA",
        strategy_name="iron_condor",
        legs=[],
        metadata={"pricing": {"raw_net": 0.87}, "wing_width": 5.0},
    )
    loss = estimate_max_loss_per_contract(candidate)
    assert loss == 413.0  # 500 - 87
