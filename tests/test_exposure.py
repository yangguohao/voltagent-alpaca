"""Tests for exposure tracking and duplicate-position guards."""

from config.settings import Settings
from risk.gates import RiskDecisionType, RiskGate
from risk.position_sizer import PortfolioSnapshot
from strategies.base import TradeCandidate


def test_risk_gate_rejects_existing_underlying():
    gate = RiskGate(Settings())
    portfolio = PortfolioSnapshot(
        equity=100_000,
        buying_power=100_000,
        open_positions=1,
        open_underlyings=frozenset({"SPY"}),
    )
    candidate = TradeCandidate(symbol="SPY", strategy_name="straddle", legs=[])
    decision = gate.check(candidate, portfolio)
    assert decision.decision == RiskDecisionType.REJECT
    assert "SPY" in decision.reason


def test_risk_gate_allows_new_underlying():
    gate = RiskGate(Settings())
    portfolio = PortfolioSnapshot(
        equity=100_000,
        buying_power=100_000,
        open_positions=1,
        open_underlyings=frozenset({"SPY"}),
    )
    candidate = TradeCandidate(symbol="NVDA", strategy_name="straddle", legs=[])
    decision = gate.check(candidate, portfolio)
    assert decision.decision == RiskDecisionType.PASS
