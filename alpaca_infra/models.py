"""Broker-facing trade request models shared by trading strategies."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TradeLeg:
    symbol: str
    side: str  # buy / sell
    ratio_qty: int = 1
    position_intent: str = "buy_to_open"


@dataclass
class TradeCandidate:
    symbol: str
    strategy_name: str
    legs: list[TradeLeg] = field(default_factory=list)
    limit_price: float | None = None
    order_type: str = "market"  # market | limit
    metadata: dict[str, Any] = field(default_factory=dict)
