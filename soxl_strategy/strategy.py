"""Deterministic SOXL covered-call rules from soxl.md."""

from dataclasses import dataclass
from datetime import date

from alpaca_infra.options_chain import OptionChain, OptionContract
from ai_agent.strategies.base import TradeCandidate, TradeLeg

SOXL_MIN_DTE = 5
SOXL_MAX_DTE = 12
SOXL_IDEAL_DTE = 7
SOXL_TARGET_DELTA = 0.20
SOXX_TRIGGER_RETURN = 0.05
QQQ_SMA_DAYS = 252
QQQ_REVERSAL_BLOCK_DAYS = 30
SOXX_HIGH_LOOKBACK = 252
SOXX_MA_DAYS = 20
SOXX_VOLUME_DAYS = 60
TOP_ZONE_RATIO = 0.95
VOLUME_SPIKE_MULTIPLIER = 2.0
CASH_DRAWDOWN = -0.15
BULL_DEEP_DRAWDOWN = -0.20
BEAR_DEEP_DRAWDOWN = -0.40
THRESHOLD_EPSILON = 1e-12


@dataclass(frozen=True)
class UnderlyingDecision:
    state: str
    target_symbol: str | None
    target_allocation: float
    reason: str
    qqq_above_sma: bool
    soxx_drawdown: float | None


@dataclass(frozen=True)
class SoxlSetup:
    eligible: bool
    reason: str
    qqq_above_sma: bool
    soxx_five_day_return: float | None
    qqq_days_since_cross: int | None
    underlying: UnderlyingDecision


def _closes(bars: list[dict]) -> list[float]:
    return [float(bar["close"]) for bar in bars]


def five_session_return(bars: list[dict]) -> float | None:
    """Five close-to-close returns require six daily closes."""
    closes = _closes(bars)
    if len(closes) < 6 or closes[-6] <= 0:
        return None
    return closes[-1] / closes[-6] - 1


def qqq_trend(bars: list[dict], sma_days: int = QQQ_SMA_DAYS) -> tuple[bool, int | None]:
    """Return whether QQQ is above its SMA and sessions since its last up-cross."""
    closes = _closes(bars)
    if len(closes) < sma_days:
        return False, None

    rolling_sums: list[float] = []
    window = sum(closes[:sma_days])
    rolling_sums.append(window)
    for index in range(sma_days, len(closes)):
        window += closes[index] - closes[index - sma_days]
        rolling_sums.append(window)

    above = [
        closes[index + sma_days - 1] > total / sma_days
        for index, total in enumerate(rolling_sums)
    ]
    if not above[-1]:
        return False, None

    last_cross: int | None = None
    for index in range(1, len(above)):
        if above[index] and not above[index - 1]:
            last_cross = index
    return True, None if last_cross is None else len(above) - 1 - last_cross


def _average(values: list[float]) -> float:
    return sum(values) / len(values)


def _reversal_confirmed(soxx_bars: list[dict], sessions: int) -> bool:
    closes = _closes(soxx_bars)
    if len(closes) < SOXX_MA_DAYS + sessions:
        return False

    for offset in range(sessions):
        end = len(closes) - offset
        if closes[end - 1] <= _average(closes[end - SOXX_MA_DAYS : end]):
            return False
    current_ma = _average(closes[-SOXX_MA_DAYS:])
    prior_ma = _average(closes[-SOXX_MA_DAYS - 1 : -1])
    return current_ma > prior_ma


def evaluate_underlying_timing(
    qqq_bars: list[dict],
    soxx_bars: list[dict],
) -> UnderlyingDecision:
    """Evaluate the SOXX/SOXL V27.0 four-season allocation thresholds."""
    qqq_above_sma, _ = qqq_trend(qqq_bars)
    if len(qqq_bars) < QQQ_SMA_DAYS or len(soxx_bars) < SOXX_HIGH_LOOKBACK:
        return UnderlyingDecision(
            "insufficient_data", None, 0.0, "requires 252 QQQ and SOXX sessions", qqq_above_sma, None,
        )

    recent_soxx = soxx_bars[-SOXX_HIGH_LOOKBACK:]
    closes = _closes(recent_soxx)
    latest_close = closes[-1]
    high_252 = max(closes)
    drawdown = latest_close / high_252 - 1

    latest = recent_soxx[-1]
    prior_volumes = [
        float(bar.get("volume", 0))
        for bar in recent_soxx[-SOXX_VOLUME_DAYS - 1 : -1]
    ]
    latest_volume = float(latest.get("volume", 0))
    volume_average = _average(prior_volumes)
    bearish_day = latest_close < float(latest.get("open", latest_close))
    top_exit = (
        latest_close >= high_252 * TOP_ZONE_RATIO
        and volume_average > 0
        and latest_volume >= volume_average * VOLUME_SPIKE_MULTIPLIER
        and bearish_day
    )
    if top_exit:
        return UnderlyingDecision(
            "top_exit", "SOXX", 0.90, "within 5% of high with 2x volume bearish close", qqq_above_sma, drawdown,
        )

    deep_threshold = BULL_DEEP_DRAWDOWN if qqq_above_sma else BEAR_DEEP_DRAWDOWN
    if drawdown <= deep_threshold + THRESHOLD_EPSILON:
        confirmation_days = 1 if qqq_above_sma else 2
        if _reversal_confirmed(soxx_bars, confirmation_days):
            return UnderlyingDecision(
                "deep_rebound", "SOXL", 0.99,
                f"drawdown {drawdown:.2%} with {confirmation_days}-session MA20 confirmation",
                qqq_above_sma, drawdown,
            )
        return UnderlyingDecision(
            "deep_defense", "SOXX", 0.90,
            f"drawdown {drawdown:.2%} without MA20 reversal confirmation",
            qqq_above_sma, drawdown,
        )

    if drawdown <= CASH_DRAWDOWN + THRESHOLD_EPSILON:
        return UnderlyingDecision(
            "cash", None, 0.0, f"drawdown {drawdown:.2%} crossed -15% cash line", qqq_above_sma, drawdown,
        )

    if qqq_above_sma:
        return UnderlyingDecision(
            "bull_normal", "SOXL", 0.99, "QQQ above MA252", True, drawdown,
        )
    return UnderlyingDecision(
        "bear_normal", "SOXX", 0.50, "QQQ below MA252", False, drawdown,
    )


def evaluate_soxl_setup(
    qqq_bars: list[dict],
    soxx_bars: list[dict],
    soxl_shares: int,
) -> SoxlSetup:
    above_sma, days_since_cross = qqq_trend(qqq_bars)
    soxx_return = five_session_return(soxx_bars)
    underlying = evaluate_underlying_timing(qqq_bars, soxx_bars)

    if soxl_shares < 100:
        reason = "requires at least 100 SOXL shares"
    elif underlying.target_symbol != "SOXL":
        reason = f"underlying state {underlying.state} targets {underlying.target_symbol or 'cash'}"
    elif soxx_return is None:
        reason = "insufficient SOXX history"
    elif soxx_return < SOXX_TRIGGER_RETURN:
        reason = f"SOXX five-session return {soxx_return:.2%} is below 5%"
    elif days_since_cross is not None and days_since_cross < QQQ_REVERSAL_BLOCK_DAYS:
        reason = f"QQQ crossed above its SMA {days_since_cross} sessions ago (30-session block)"
    else:
        return SoxlSetup(
            True, "all covered-call entry conditions passed", above_sma,
            soxx_return, days_since_cross, underlying,
        )

    return SoxlSetup(False, reason, above_sma, soxx_return, days_since_cross, underlying)


def pick_soxl_call(chain: OptionChain) -> OptionContract | None:
    calls = [
        contract
        for contract in chain.contracts
        if contract.contract_type == "call"
        and SOXL_MIN_DTE <= contract.dte <= SOXL_MAX_DTE
        and contract.strike > chain.underlying_price
        and contract.delta is not None
    ]
    if not calls:
        return None
    return min(
        calls,
        key=lambda contract: (
            abs(contract.dte - SOXL_IDEAL_DTE),
            abs(abs(float(contract.delta)) - SOXL_TARGET_DELTA),
            -contract.open_interest,
        ),
    )


def build_soxl_covered_call(chain: OptionChain) -> TradeCandidate | None:
    contract = pick_soxl_call(chain)
    if contract is None:
        return None
    return TradeCandidate(
        symbol="SOXL",
        strategy_name="soxl_covered_call",
        order_type="limit",
        legs=[
            TradeLeg(
                symbol=contract.symbol,
                side="sell",
                position_intent="sell_to_open",
            )
        ],
        metadata={
            "expiration": str(contract.expiration),
            "dte": contract.dte,
            "strike": contract.strike,
            "delta": contract.delta,
        },
    )


def trading_sessions_to_expiration(expiration: date, today: date | None = None) -> int:
    """Count remaining weekdays, excluding today (exchange holidays are not inferred)."""
    current = today or date.today()
    return sum(
        day.weekday() < 5
        for ordinal in range(current.toordinal() + 1, expiration.toordinal() + 1)
        for day in [date.fromordinal(ordinal)]
    )
