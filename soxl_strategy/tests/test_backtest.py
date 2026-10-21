from datetime import date, timedelta

import pytest

from soxl_strategy.backtest import performance, run_backtest


def _bars(closes: list[float], volumes: list[float] | None = None) -> list[dict]:
    start = date(2020, 1, 1)
    volumes = volumes or [100.0] * len(closes)
    return [
        {"date": start + timedelta(days=index), "open": close, "close": close, "volume": volumes[index]}
        for index, close in enumerate(closes)
    ]


def test_backtest_applies_signal_to_next_session_and_costs_turnover():
    qqq = _bars([100 + index for index in range(254)])
    soxx = _bars([100.0] * 254)
    soxl = _bars([100.0] * 252 + [110.0, 121.0])

    result = run_backtest(qqq, soxx, soxl, cost_bps=10)

    assert result.start == date(2020, 1, 1) + timedelta(days=251)
    assert result.rebalances == 1
    assert result.equity[-1] == pytest.approx((1 - 0.99 * 0.001) * (1 + 0.99 * 0.10) ** 2)


def test_performance_reports_drawdown():
    metrics = performance([1.0, 1.2, 0.9, 1.1], [0.2, -0.25, 1.1 / 0.9 - 1], date(2020, 1, 1), date(2021, 1, 1))
    assert metrics["max_drawdown"] == pytest.approx(-0.25)
