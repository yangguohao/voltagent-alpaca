from datetime import date, timedelta

from tradier_infra.options_chain import OptionsChainService


class FakeClient:
    def __init__(self):
        self.expiration = (date.today() + timedelta(days=7)).isoformat()

    def get(self, path, params):
        if path.endswith("expirations"):
            return {"expirations": {"date": self.expiration}}
        return {
            "options": {
                "option": {
                    "symbol": "SOXL  261120C00060000",
                    "strike": 60,
                    "option_type": "call",
                    "open_interest": 321,
                    "bid": 1.2,
                    "ask": 1.3,
                    "greeks": {"delta": 0.21, "mid_iv": 0.65},
                }
            }
        }


def test_fetch_chain_normalizes_single_item_response():
    chain = OptionsChainService(FakeClient()).fetch_chain("SOXL", 50, min_dte=5, max_dte=12)

    assert len(chain.contracts) == 1
    contract = chain.contracts[0]
    assert contract.symbol == "SOXL261120C00060000"
    assert contract.delta == 0.21
    assert contract.open_interest == 321
    assert round(contract.spread_pct, 4) == 0.08
