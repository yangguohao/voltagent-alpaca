"""Alpaca SDK client factory."""

from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.trading.client import TradingClient

from config.settings import Settings


class AlpacaClients:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.trading = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=settings.alpaca_paper,
        )
        self.stock_data = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )
        self.option_data = OptionHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )


def create_clients(settings: Settings) -> AlpacaClients:
    return AlpacaClients(settings)
