"""Stock market data helpers."""

from datetime import datetime, timedelta, timezone

from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from data.alpaca_client import AlpacaClients
from observability.logger import get_logger

logger = get_logger("market_data")


class MarketDataService:
    def __init__(self, clients: AlpacaClients) -> None:
        self.clients = clients

    def get_daily_bars(self, symbol: str, days: int = 252) -> list[dict]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days + 30)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )
        bars = self.clients.stock_data.get_stock_bars(request)
        result = []
        if symbol not in bars.data:
            logger.warning("No bars for %s", symbol)
            return result
        for bar in bars.data[symbol]:
            result.append({
                "timestamp": bar.timestamp,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            })
        return result[-days:]

    def get_latest_price(self, symbol: str) -> float | None:
        bars = self.get_daily_bars(symbol, days=5)
        if not bars:
            return None
        return bars[-1]["close"]
