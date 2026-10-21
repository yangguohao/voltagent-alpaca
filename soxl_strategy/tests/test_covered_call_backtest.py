from datetime import date
from types import SimpleNamespace

import pytest

from soxl_strategy.covered_call_backtest import (
    CoveredCallTrade,
    account_comparison,
    call_price,
    implied_delta,
    select_contract,
)


def test_implied_delta_recovers_price_consistently():
    spot, strike, days, volatility = 50.0, 55.0, 7, 0.8
    price = call_price(spot, strike, days / 365, 0.045, volatility)
    delta = implied_delta(spot, strike, days, price)
    assert delta is not None
    assert 0 < delta < 0.5


def test_select_contract_uses_delta_nearest_point_two():
    contracts = [
        SimpleNamespace(symbol="A", strike_price=52.0, expiration_date=date(2026, 1, 8)),
        SimpleNamespace(symbol="B", strike_price=55.0, expiration_date=date(2026, 1, 8)),
    ]
    bars = {
        "A": [{"o": call_price(50, 52, 7 / 365, 0.045, 0.8), "c": 0.01, "v": 100}],
        "B": [{"o": call_price(50, 55, 7 / 365, 0.045, 0.8), "c": 0.01, "v": 100}],
    }
    selected = select_contract(contracts, bars, 50, date(2026, 1, 1))
    assert selected is not None
    assert selected[0].symbol == "B"
    assert selected[2] == pytest.approx(0.20, abs=0.08)


def test_account_comparison_uses_same_starting_capital():
    trade = CoveredCallTrade(
        symbol="X", entry_date=date(2026, 1, 1), exit_date=date(2026, 1, 2),
        expiration=date(2026, 1, 8), strike=110, delta=0.2,
        entry_price=1, exit_price=0, pnl=100, option_return=0.01,
        stock_return=0.10, exit_reason="t_minus_one",
    )
    bars = [
        {"date": date(2026, 1, 1), "raw_open": 100, "open": 100, "close": 100},
        {"date": date(2026, 1, 2), "raw_close": 110, "close": 110},
    ]
    result = account_comparison([trade], bars)
    assert result["initial"] == 10_000
    assert result["soxl_final"] == 11_000
    assert result["fixed_call_final"] == 11_100
    assert result["proportional_call_final"] == 11_100
