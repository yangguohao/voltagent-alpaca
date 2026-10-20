"""Hard risk gates — LLM cannot override."""

from dataclasses import dataclass
from enum import Enum

from ai_agent.config.settings import Settings
from alpaca_infra.options_chain import OptionContract
from ai_agent.risk.position_sizer import PortfolioSnapshot
from ai_agent.strategies.base import TradeCandidate


class RiskDecisionType(str, Enum):
    PASS = "pass"
    REJECT = "reject"


@dataclass
class RiskDecision:
    decision: RiskDecisionType
    reason: str = ""


class RiskGate:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def check(
        self,
        candidate: TradeCandidate,
        portfolio: PortfolioSnapshot,
        contracts: dict[str, OptionContract] | None = None,
    ) -> RiskDecision:
        if portfolio.daily_pnl_pct <= -self.settings.max_daily_loss:
            return RiskDecision(RiskDecisionType.REJECT, "Daily loss limit breached")

        if portfolio.open_positions >= self.settings.max_positions:
            return RiskDecision(
                RiskDecisionType.REJECT,
                f"Max underlying positions reached ({portfolio.open_positions}/{self.settings.max_positions})",
            )

        if candidate.symbol in portfolio.open_underlyings:
            return RiskDecision(
                RiskDecisionType.REJECT,
                f"Already have exposure in {candidate.symbol}",
            )

        contracts = contracts or {}
        for leg in candidate.legs:
            contract = contracts.get(leg.symbol)
            if contract is None:
                continue
            if contract.open_interest < self.settings.min_open_interest:
                return RiskDecision(
                    RiskDecisionType.REJECT,
                    f"Insufficient OI for {leg.symbol}: {contract.open_interest}",
                )
            spread = contract.spread_pct
            if spread is not None and spread > self.settings.max_bid_ask_spread_pct:
                return RiskDecision(
                    RiskDecisionType.REJECT,
                    f"Bid-ask spread too wide for {leg.symbol}: {spread:.2%}",
                )
            if contract.dte < self.settings.min_dte:
                return RiskDecision(
                    RiskDecisionType.REJECT,
                    f"DTE too low for {leg.symbol}: {contract.dte}",
                )

        return RiskDecision(RiskDecisionType.PASS, "All risk checks passed")
