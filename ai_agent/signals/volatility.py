"""Volatility-based signal generation."""

import math
from statistics import mean, stdev

from ai_agent.signals.base import Signal


def _realized_volatility(closes: list[float], window: int = 20) -> float | None:
    if len(closes) < window + 1:
        return None
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(-window, 0)]
    return stdev(returns) * math.sqrt(252)


def _iv_rank(current_iv: float, iv_history: list[float]) -> float | None:
    if not iv_history:
        return None
    low, high = min(iv_history), max(iv_history)
    if high == low:
        return 0.5
    return (current_iv - low) / (high - low)


class VolatilitySignalGenerator:
    """Generate IV rank / HV-IV spread signals from price history."""

    def __init__(self, iv_history_days: int = 252) -> None:
        self.iv_history_days = iv_history_days

    def generate(self, symbol: str, bars: list[dict] | None = None, current_iv: float | None = None, **_) -> Signal | None:
        if not bars or len(bars) < 30:
            return None

        closes = [b["close"] for b in bars]
        hv = _realized_volatility(closes)
        if hv is None:
            return None

        # Use HV as IV proxy when no options IV available yet
        iv = current_iv if current_iv is not None else hv
        hv_iv_spread = iv - hv

        # Build synthetic IV history from rolling HV for rank calculation
        iv_history: list[float] = []
        for i in range(30, len(closes)):
            window = closes[i - 30 : i]
            rv = _realized_volatility(window, window=min(20, len(window) - 1))
            if rv is not None:
                iv_history.append(rv)

        iv_rank = _iv_rank(iv, iv_history)
        if iv_rank is None:
            return None

        if iv_rank >= 0.7:
            signal_type = "high_iv"
            strength = min(1.0, (iv_rank - 0.7) / 0.3)
        elif iv_rank <= 0.3:
            signal_type = "low_iv"
            strength = min(1.0, (0.3 - iv_rank) / 0.3)
        else:
            signal_type = "neutral"
            strength = 0.0

        return Signal(
            symbol=symbol,
            signal_type=signal_type,
            strength=strength,
            metadata={
                "iv_rank": round(iv_rank, 4),
                "hv": round(hv, 4),
                "iv": round(iv, 4),
                "hv_iv_spread": round(hv_iv_spread, 4),
            },
        )
