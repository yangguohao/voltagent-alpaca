"""Position sizing utilities."""

from dataclasses import dataclass


@dataclass
class PortfolioSnapshot:
    equity: float
    buying_power: float
    open_positions: int = 0
    daily_pnl_pct: float = 0.0
    open_underlyings: frozenset[str] = frozenset()


def compute_position_qty(
    equity: float,
    max_risk_pct: float,
    max_loss_per_contract: float,
) -> int:
    if max_loss_per_contract <= 0:
        return 0
    risk_budget = equity * max_risk_pct
    return max(1, int(risk_budget / max_loss_per_contract))
