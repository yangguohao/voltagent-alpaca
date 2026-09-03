"""Regime-based strategy gating."""

from dataclasses import dataclass

from observability.logger import get_logger

logger = get_logger("regime_gate")

# signal_type -> allowed under each regime
REGIME_SIGNALS: dict[str, set[str]] = {
    "high_vol": {"high_iv"},
    "low_vol": {"low_iv"},
    "trending": {"low_iv"},  # buy vol before breakout; avoid short premium
    "choppy": {"high_iv"},
}

# strategy allowed per regime (strangle direction filtered separately)
REGIME_STRATEGIES: dict[str, set[str]] = {
    "high_vol": {"iron_condor", "strangle"},
    "low_vol": {"straddle", "strangle"},
    "trending": {"straddle", "strangle"},
    "choppy": {"iron_condor", "strangle"},
}

# short premium only on high_iv; long vol only on low_iv
STRANGLE_SHORT_SIGNALS = {"high_iv"}
STRANGLE_LONG_SIGNALS = {"low_iv"}


@dataclass
class RegimeState:
    regime: str
    confidence: float = 0.0
    notes: str = ""

    @property
    def is_valid(self) -> bool:
        return self.regime in REGIME_SIGNALS


class RegimeGate:
    def __init__(self, min_confidence: float = 0.5, enabled: bool = True) -> None:
        self.min_confidence = min_confidence
        self.enabled = enabled

    def allows_signal(self, state: RegimeState | None, signal_type: str) -> bool:
        if not self.enabled or state is None or not state.is_valid:
            return True
        if state.confidence < self.min_confidence:
            logger.info("Regime confidence %.2f below threshold, skipping gate", state.confidence)
            return True
        allowed = REGIME_SIGNALS.get(state.regime, set())
        ok = signal_type in allowed
        if not ok:
            logger.info("Regime %s blocked signal type %s", state.regime, signal_type)
        return ok

    def allows_strategy(
        self,
        state: RegimeState | None,
        strategy_name: str,
        signal_type: str,
    ) -> bool:
        if not self.enabled or state is None or not state.is_valid:
            return True
        if state.confidence < self.min_confidence:
            return True

        allowed = REGIME_STRATEGIES.get(state.regime, set())
        if strategy_name not in allowed:
            logger.info("Regime %s blocked strategy %s", state.regime, strategy_name)
            return False

        if strategy_name == "strangle":
            if signal_type in STRANGLE_SHORT_SIGNALS and state.regime in ("low_vol", "trending"):
                logger.info("Regime %s blocked short strangle", state.regime)
                return False
            if signal_type in STRANGLE_LONG_SIGNALS and state.regime in ("high_vol", "choppy"):
                logger.info("Regime %s blocked long strangle", state.regime)
                return False

        return True
