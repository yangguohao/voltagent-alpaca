"""Position sizing based on per-trade risk budget."""

from dataclasses import dataclass

from ai_agent.config.settings import Settings
from ai_agent.observability.logger import get_logger
from ai_agent.risk.position_sizer import PortfolioSnapshot, compute_position_qty
from ai_agent.strategies.base import TradeCandidate

logger = get_logger("position_sizer")

OPTIONS_MULTIPLIER = 100
DEFAULT_WING_WIDTH = 5.0


@dataclass
class SizeResult:
    qty: int
    max_loss_per_contract: float
    risk_budget: float


def _per_share_net(candidate: TradeCandidate) -> float | None:
    pricing = candidate.metadata.get("pricing", {})
    raw = pricing.get("raw_net")
    if raw is not None:
        return abs(float(raw))
    if candidate.limit_price is not None:
        return abs(float(candidate.limit_price))
    return None


def estimate_max_loss_per_contract(candidate: TradeCandidate) -> float | None:
    """Estimate worst-case loss per 1-lot in dollars."""
    net = _per_share_net(candidate)
    strategy = candidate.strategy_name
    meta = candidate.metadata

    # Debit strategies: premium paid is max loss
    if strategy == "straddle":
        if net is None:
            return None
        return net * OPTIONS_MULTIPLIER

    if strategy == "strangle" and meta.get("direction") == "buy":
        if net is None:
            return None
        return net * OPTIONS_MULTIPLIER

    # Credit strategies: wing width minus credit received
    if strategy == "iron_condor":
        wing = meta.get("wing_width")
        if wing is None:
            sp = meta.get("short_put_strike")
            lp = meta.get("long_put_strike")
            if sp is not None and lp is not None:
                wing = abs(float(sp) - float(lp))
            else:
                wing = DEFAULT_WING_WIDTH
        credit = net or 0.0
        return max((float(wing) * OPTIONS_MULTIPLIER) - (credit * OPTIONS_MULTIPLIER), 1.0)

    if strategy == "strangle" and meta.get("direction") == "sell":
        wing = meta.get("wing_width", DEFAULT_WING_WIDTH)
        credit = net or 0.0
        return max((float(wing) * OPTIONS_MULTIPLIER) - (credit * OPTIONS_MULTIPLIER), 1.0)

    # Fallback
    if net is not None:
        return net * OPTIONS_MULTIPLIER
    return None


class PositionSizer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def size(self, candidate: TradeCandidate, portfolio: PortfolioSnapshot) -> SizeResult:
        max_loss = estimate_max_loss_per_contract(candidate)
        if max_loss is None or max_loss <= 0:
            logger.warning("Cannot estimate max loss for %s, defaulting to qty=1", candidate.strategy_name)
            return SizeResult(qty=1, max_loss_per_contract=0.0, risk_budget=portfolio.equity * self.settings.max_risk_per_trade)

        risk_budget = portfolio.equity * self.settings.max_risk_per_trade
        qty = compute_position_qty(portfolio.equity, self.settings.max_risk_per_trade, max_loss)
        qty = min(qty, self.settings.max_contracts_per_trade)
        qty = max(1, qty)

        logger.info(
            "Sized %s %s: qty=%d max_loss/contract=$%.2f budget=$%.2f",
            candidate.strategy_name, candidate.symbol, qty, max_loss, risk_budget,
        )
        return SizeResult(qty=qty, max_loss_per_contract=max_loss, risk_budget=risk_budget)
