"""Signal base types."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Signal:
    symbol: str
    signal_type: str  # high_iv, low_iv, iv_expansion, neutral
    strength: float  # 0.0 - 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SignalEngine:
    """Aggregates multiple signal generators."""

    def __init__(self, generators: list | None = None) -> None:
        self.generators = generators or []

    def evaluate(self, symbol: str, **context) -> list[Signal]:
        signals: list[Signal] = []
        for gen in self.generators:
            result = gen.generate(symbol, **context)
            if result:
                if isinstance(result, list):
                    signals.extend(result)
                else:
                    signals.append(result)
        return signals
