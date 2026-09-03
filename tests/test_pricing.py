"""Tests for multi-leg limit pricing."""

from datetime import datetime, timezone

from alpaca.data.models.quotes import Quote

from execution.pricing import compute_mleg_limit_price
from strategies.base import TradeLeg


def _quote(symbol: str, bid: float, ask: float) -> Quote:
    return Quote(symbol, {
        "t": datetime.now(timezone.utc).isoformat(),
        "bp": bid,
        "bs": 10,
        "ap": ask,
        "as": 10,
    })


def test_debit_straddle_limit_price():
    legs = [
        TradeLeg(symbol="P1", side="buy"),
        TradeLeg(symbol="C1", side="buy"),
    ]
    quotes = {
        "P1": _quote("P1", 4.0, 4.2),
        "C1": _quote("C1", 3.8, 4.0),
    }
    limit, meta = compute_mleg_limit_price(legs, quotes, slippage_pct=0.0)
    # ask 4.2 + 4.0 = 8.2 debit
    assert limit == 8.2
    assert meta["order_side"] == "debit"


def test_credit_iron_condor_limit_price():
    legs = [
        TradeLeg(symbol="SP", side="sell"),
        TradeLeg(symbol="LP", side="buy"),
        TradeLeg(symbol="SC", side="sell"),
        TradeLeg(symbol="LC", side="buy"),
    ]
    quotes = {
        "SP": _quote("SP", 2.0, 2.2),
        "LP": _quote("LP", 1.0, 1.1),
        "SC": _quote("SC", 2.1, 2.3),
        "LC": _quote("LC", 1.1, 1.2),
    }
    limit, meta = compute_mleg_limit_price(legs, quotes, slippage_pct=0.0)
    # sell bid: 2.0 + 2.1 = 4.1 credit, buy ask: 1.1 + 1.2 = 2.3 debit => net -1.8 credit
    assert limit == -1.8
    assert meta["order_side"] == "credit"


def test_slippage_worsens_debit():
    legs = [TradeLeg(symbol="C1", side="buy")]
    quotes = {"C1": _quote("C1", 1.0, 2.0)}
    base, _ = compute_mleg_limit_price(legs, quotes, slippage_pct=0.0)
    slipped, _ = compute_mleg_limit_price(legs, quotes, slippage_pct=0.1)
    assert slipped > base
