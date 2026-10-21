"""Latest Tradier option quotes for Alpaca limit-price calculation."""

from dataclasses import dataclass

from tradier_infra.client import TradierClient
from tradier_infra.options_chain import _float, _items

BATCH_SIZE = 100


@dataclass(frozen=True)
class Quote:
    bid_price: float
    ask_price: float


class OptionQuoteService:
    def __init__(self, client: TradierClient) -> None:
        self.client = client

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        quotes: dict[str, Quote] = {}
        unique = list(dict.fromkeys(symbols))
        for start in range(0, len(unique), BATCH_SIZE):
            batch = unique[start : start + BATCH_SIZE]
            response = self.client.get(
                "/markets/quotes",
                {"symbols": ",".join(batch), "greeks": "false"},
            )
            for item in _items((response.get("quotes") or {}).get("quote")):
                symbol = str(item.get("symbol") or "").replace(" ", "")
                bid = _float(item.get("bid"))
                ask = _float(item.get("ask"))
                if symbol and bid is not None and ask is not None:
                    quotes[symbol] = Quote(bid, ask)
        return quotes
