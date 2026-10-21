from tradier_infra.option_quotes import OptionQuoteService


class FakeClient:
    def get(self, path, params):
        return {
            "quotes": {
                "quote": {
                    "symbol": "SOXL  261120C00060000",
                    "bid": 1.2,
                    "ask": 1.3,
                }
            }
        }


def test_get_quotes_normalizes_tradier_symbol():
    quotes = OptionQuoteService(FakeClient()).get_quotes(["SOXL261120C00060000"])

    assert quotes["SOXL261120C00060000"].bid_price == 1.2
    assert quotes["SOXL261120C00060000"].ask_price == 1.3
