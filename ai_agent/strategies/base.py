"""Strategy base types and registry."""

from abc import ABC, abstractmethod

from alpaca_infra.models import TradeCandidate, TradeLeg
from alpaca_infra.options_chain import OptionChain
from ai_agent.signals.base import Signal


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
