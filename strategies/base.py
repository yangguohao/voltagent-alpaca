"""Strategy base types and registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from data.options_chain import OptionChain
from signals.base import Signal


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


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate_candidates(self, signal: Signal, chain: OptionChain) -> list[TradeCandidate]:
        ...

    @abstractmethod
    def build_legs(self, candidate: TradeCandidate) -> list[TradeLeg]:
        ...


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> BaseStrategy | None:
        return self._strategies.get(name)

    def all(self) -> list[BaseStrategy]:
        return list(self._strategies.values())

    def select_for_signal(self, signal: Signal, chain: OptionChain) -> list[TradeCandidate]:
        candidates: list[TradeCandidate] = []
        for strategy in self._strategies.values():
            candidates.extend(strategy.generate_candidates(signal, chain))
        return candidates
