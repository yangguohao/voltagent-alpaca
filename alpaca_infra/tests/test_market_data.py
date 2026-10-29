from alpaca_infra.market_data import MarketDataService
from tradier_infra.option_quotes import Quote


class FakeQuotes:
    def get_quotes(self, symbols):
        return {symbols[0]: Quote(bid_price=499.8, ask_price=500.2)}


def test_latest_price_uses_live_quote_midpoint():
    service = MarketDataService(clients=None, quote_service=FakeQuotes())

    assert service.get_latest_price("SOXX") == 500.0
