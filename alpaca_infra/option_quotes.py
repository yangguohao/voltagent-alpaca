"""Latest option quote fetching."""

import logging

from alpaca.data.enums import OptionsFeed
from alpaca.data.models.quotes import Quote
from alpaca.data.requests import OptionLatestQuoteRequest

from alpaca_infra.clients import AlpacaClients

logger = logging.getLogger("alpaca_infra.option_quotes")

BATCH_SIZE = 100


class OptionQuoteService:
    def __init__(self, clients: AlpacaClients, feed: OptionsFeed = OptionsFeed.INDICATIVE) -> None:
        self.clients = clients
        self.feed = feed

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        if not symbols:
            return {}

        quotes: dict[str, Quote] = {}
        unique = list(dict.fromkeys(symbols))

        for i in range(0, len(unique), BATCH_SIZE):
            batch = unique[i : i + BATCH_SIZE]
            request = OptionLatestQuoteRequest(symbol_or_symbols=batch, feed=self.feed)
            try:
                result = self.clients.option_data.get_option_latest_quote(request)
                quotes.update(result)
            except Exception as exc:
                logger.warning("Failed to fetch quotes for batch: %s", exc)

        return quotes
