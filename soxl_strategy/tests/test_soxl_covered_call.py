from datetime import date, timedelta

import pytest

from alpaca_infra.options_chain import OptionChain, OptionContract
from soxl_strategy.strategy import (
    build_soxl_covered_call,
    evaluate_soxl_setup,
    evaluate_underlying_timing,
    five_session_return,
    qqq_trend,
    trading_sessions_to_expiration,
)


def _bars(closes: list[float]) -> list[dict]:
    return [{"open": close, "close": close, "volume": 100} for close in closes]


def _soxx_with_rally() -> list[dict]:
    return _bars([100.0] * 284 + [100, 101, 102, 103, 104, 106])


def _call(symbol: str, strike: float, dte: int, delta: float) -> OptionContract:
    return OptionContract(
        symbol=symbol,
        underlying="SOXL",
        strike=strike,
        expiration=date.today() + timedelta(days=dte),
        contract_type="call",
        open_interest=500,
        delta=delta,
    )


def test_five_session_return_uses_six_closes():
    assert five_session_return(_bars([100, 101, 102, 103, 104, 105])) == pytest.approx(0.05)


def test_qqq_reversal_window_counts_sessions_since_cross():
    closes = [100.0] * 252 + [99.0, 102.0] + [103.0] * 10
    above, sessions = qqq_trend(_bars(closes))
    assert above is True
    assert sessions == 10


def test_setup_requires_all_three_entry_conditions():
    old_uptrend = _bars([100 + index * 0.1 for index in range(290)])
    soxx_rally = _soxx_with_rally()
    setup = evaluate_soxl_setup(old_uptrend, soxx_rally, soxl_shares=200)
    assert setup.eligible is True

    assert evaluate_soxl_setup(old_uptrend, soxx_rally, soxl_shares=99).eligible is False
    assert evaluate_soxl_setup(old_uptrend, _bars([100] * 6), soxl_shares=200).eligible is False


def test_v27_normal_allocations_follow_qqq_ma252():
    bull = _bars([100 + index * 0.1 for index in range(290)])
    bear = _bars([130 - index * 0.1 for index in range(290)])
    soxx = _bars([100.0] * 290)

    bull_decision = evaluate_underlying_timing(bull, soxx)
    assert (bull_decision.state, bull_decision.target_symbol, bull_decision.target_allocation) == (
        "bull_normal", "SOXL", 0.99,
    )
    bear_decision = evaluate_underlying_timing(bear, soxx)
    assert (bear_decision.state, bear_decision.target_symbol, bear_decision.target_allocation) == (
        "bear_normal", "SOXX", 0.50,
    )


def test_v27_top_exit_requires_top_zone_double_volume_and_bearish_close():
    qqq = _bars([100 + index * 0.1 for index in range(290)])
    soxx = _bars([100.0] * 289 + [96.0])
    soxx[-1] = {"open": 98.0, "close": 96.0, "volume": 200}

    decision = evaluate_underlying_timing(qqq, soxx)
    assert (decision.state, decision.target_symbol, decision.target_allocation) == (
        "top_exit", "SOXX", 0.90,
    )


def test_v27_cash_and_bull_deep_thresholds():
    qqq = _bars([100 + index * 0.1 for index in range(290)])
    cash = _bars([100.0] * 270 + [85.0] * 20)
    assert evaluate_underlying_timing(qqq, cash).state == "cash"

    unconfirmed = _bars([100.0] * 270 + [79.0] * 20)
    defense = evaluate_underlying_timing(qqq, unconfirmed)
    assert (defense.state, defense.target_symbol, defense.target_allocation) == (
        "deep_defense", "SOXX", 0.90,
    )

    confirmed = _bars([100.0] * 268 + [70.0] * 20 + [75.0, 80.0])
    rebound = evaluate_underlying_timing(qqq, confirmed)
    assert (rebound.state, rebound.target_symbol, rebound.target_allocation) == (
        "deep_rebound", "SOXL", 0.99,
    )


def test_v27_bear_deep_rebound_requires_two_confirming_sessions():
    qqq = _bars([130 - index * 0.1 for index in range(290)])
    soxx = _bars([100.0] * 268 + [50.0] * 20 + [55.0, 60.0])
    decision = evaluate_underlying_timing(qqq, soxx)
    assert (decision.state, decision.target_symbol, decision.target_allocation) == (
        "deep_rebound", "SOXL", 0.99,
    )


def test_contract_selection_prefers_one_week_then_nearest_point_two_delta():
    chain = OptionChain(
        underlying="SOXL",
        underlying_price=50,
        contracts=[
            _call("C55", 55, 7, 0.30),
            _call("C60", 60, 7, 0.21),
            _call("C65", 65, 8, 0.20),
            _call("ITM", 45, 7, 0.20),
        ],
    )
    candidate = build_soxl_covered_call(chain)
    assert candidate is not None
    assert candidate.legs[0].symbol == "C60"
    assert candidate.legs[0].position_intent == "sell_to_open"


def test_t_minus_one_counts_weekdays():
    friday = date(2026, 10, 23)
    assert trading_sessions_to_expiration(friday, today=date(2026, 10, 22)) == 1
    assert trading_sessions_to_expiration(friday, today=date(2026, 10, 21)) == 2
    assert trading_sessions_to_expiration(date(2026, 10, 26), today=friday) == 1
