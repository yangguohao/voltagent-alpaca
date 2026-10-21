from datetime import date, timedelta
from types import SimpleNamespace

from ai_agent.config.settings import Settings
from alpaca_infra.options_chain import OptionChain, OptionContract
from soxl_strategy.manager import SoxlCoveredCallManager


def _uptrend() -> list[dict]:
    return [{"close": 100 + index * 0.1} for index in range(290)]


class FakeMarketData:
    def get_daily_bars(self, symbol, days):
        if symbol == "QQQ":
            return _uptrend()
        closes = [100.0] * 314 + [100, 101, 102, 103, 104, 106]
        return [{"open": close, "close": close, "volume": 100} for close in closes]

    def get_latest_price(self, symbol):
        return 50.0


class BearMarketData(FakeMarketData):
    def get_daily_bars(self, symbol, days):
        if symbol == "QQQ":
            return [{"open": 130 - index * 0.1, "close": 130 - index * 0.1, "volume": 100} for index in range(320)]
        return [{"open": 100, "close": 100, "volume": 100} for _ in range(320)]


class DeepDefenseMarketData(FakeMarketData):
    def get_daily_bars(self, symbol, days):
        if symbol == "QQQ":
            return super().get_daily_bars(symbol, days)
        return [
            {"open": close, "close": close, "volume": 100}
            for close in ([100.0] * 300 + [70.0] * 20)
        ]


class FakeExecutor:
    def __init__(self):
        self.orders = []

    def submit(self, candidate, qty):
        self.orders.append((candidate, qty))
        return "test-order"

    def submit_stock(self, symbol, side, qty, strategy):
        self.orders.append((symbol, side, qty, strategy))
        return "test-stock-order"


class FakeTrading:
    def __init__(self, positions, calendar=None):
        self.positions = positions
        self.calendar = calendar or []

    def get_all_positions(self):
        return self.positions

    def get_orders(self, filter):
        return []

    def get_calendar(self, request):
        return self.calendar


class RebalanceTrading(FakeTrading):
    def get_clock(self):
        return SimpleNamespace(is_open=True)

    def get_account(self):
        return SimpleNamespace(equity="100000")


def _stock(qty=200):
    return SimpleNamespace(symbol="SOXL", side="long", qty=str(qty))


def test_manager_closes_covered_call_on_t_minus_one():
    call = SimpleNamespace(symbol="SOXL261023C00060000", side="short", qty="1")
    clients = SimpleNamespace(trading=FakeTrading([_stock(), call], calendar=[object(), object()]))
    executor = FakeExecutor()
    manager = SoxlCoveredCallManager(clients, Settings(), FakeMarketData(), None, executor)

    assert manager.run(today=date(2026, 10, 22)) == ["test-order"]
    candidate, qty = executor.orders[0]
    assert qty == 1
    assert candidate.legs[0].position_intent == "buy_to_close"
    assert candidate.metadata["exit_reason"] == "t_minus_one"


def test_manager_sells_only_covered_quantity():
    expiration = date.today() + timedelta(days=7)
    contract = OptionContract(
        symbol="SOXL_CALL",
        underlying="SOXL",
        strike=60,
        expiration=expiration,
        contract_type="call",
        open_interest=500,
        delta=0.2,
        bid=1.0,
        ask=1.05,
    )
    chain = OptionChain("SOXL", 50, [contract])
    options = SimpleNamespace(fetch_chain=lambda *args, **kwargs: chain)
    clients = SimpleNamespace(trading=FakeTrading([_stock(qty=250)]))
    executor = FakeExecutor()
    manager = SoxlCoveredCallManager(clients, Settings(max_contracts_per_trade=10), FakeMarketData(), options, executor)

    assert manager.run() == ["test-order"]
    candidate, qty = executor.orders[0]
    assert qty == 2
    assert candidate.legs[0].position_intent == "sell_to_open"


def test_manager_closes_uncovered_contracts_if_share_count_falls():
    call = SimpleNamespace(symbol="SOXL261030C00060000", side="short", qty="2")
    clients = SimpleNamespace(trading=FakeTrading([_stock(qty=150), call], calendar=[object()] * 5))
    executor = FakeExecutor()
    manager = SoxlCoveredCallManager(clients, Settings(), FakeMarketData(), None, executor)

    manager.run(today=date(2026, 10, 19))
    candidate, qty = executor.orders[0]
    assert qty == 1
    assert candidate.metadata["exit_reason"] == "insufficient_share_coverage"


def test_manager_closes_call_when_v27_targets_defensive_asset():
    call = SimpleNamespace(symbol="SOXL261030C00060000", side="short", qty="1")
    clients = SimpleNamespace(trading=FakeTrading([_stock(), call], calendar=[object()] * 5))
    executor = FakeExecutor()
    manager = SoxlCoveredCallManager(clients, Settings(), BearMarketData(), None, executor)

    manager.run(today=date(2026, 10, 19))
    candidate, qty = executor.orders[0]
    assert qty == 1
    assert candidate.metadata["exit_reason"] == "underlying_exit_signal"


def test_manager_rebalances_defensive_state_into_soxx_on_paper():
    clients = SimpleNamespace(trading=RebalanceTrading([]))
    executor = FakeExecutor()
    settings = Settings(soxl_underlying_rebalance_enabled=True, alpaca_paper=True)
    manager = SoxlCoveredCallManager(clients, settings, DeepDefenseMarketData(), None, executor)

    assert manager.run() == ["test-stock-order"]
    assert executor.orders[0] == ("SOXX", "buy", 1800, "soxl_underlying_rebalance")
