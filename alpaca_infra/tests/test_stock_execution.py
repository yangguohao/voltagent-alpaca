from types import SimpleNamespace

from alpaca.trading.requests import LimitOrderRequest

from alpaca_infra.execution.executor import OrderExecutor
from tradier_infra.option_quotes import Quote


class FakeQuotes:
    def get_quotes(self, symbols):
        return {symbols[0]: Quote(bid_price=499.9, ask_price=500.1)}


class FakeTrading:
    def __init__(self):
        self.request = None

    def submit_order(self, request):
        self.request = request
        return SimpleNamespace(id="order-id", status="accepted")


class FakeState:
    def __init__(self):
        self.payload = None

    def log_trade(self, client_order_id, symbol, strategy, status, payload):
        self.payload = payload


def test_stock_buy_uses_live_ask_as_limit():
    trading = FakeTrading()
    state = FakeState()
    clients = SimpleNamespace(trading=trading)
    settings = SimpleNamespace(limit_slippage_pct=0.05, quote_fallback_market=True)
    executor = OrderExecutor(clients, state, settings, dry_run=False, quote_service=FakeQuotes())

    assert executor.submit_stock("SOXX", "buy", 2, "rebalance") is not None
    assert isinstance(trading.request, LimitOrderRequest)
    assert float(trading.request.limit_price) == 500.1
    assert state.payload["bid"] == 499.9
    assert state.payload["ask"] == 500.1


def test_stock_sell_uses_live_bid_as_limit():
    trading = FakeTrading()
    clients = SimpleNamespace(trading=trading)
    settings = SimpleNamespace(limit_slippage_pct=0.05, quote_fallback_market=True)
    executor = OrderExecutor(clients, FakeState(), settings, dry_run=False, quote_service=FakeQuotes())

    executor.submit_stock("SOXX", "sell", 2, "rebalance")

    assert isinstance(trading.request, LimitOrderRequest)
    assert float(trading.request.limit_price) == 499.9
