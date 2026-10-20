"""Tests for baseline contract selection."""

from datetime import date, timedelta

from alpaca_infra.options_chain import OptionChain, OptionContract
from ai_agent.strategies.selection import pick_atm_straddle, pick_iron_condor_legs, pick_strangle_legs


def _contract(symbol: str, strike: float, ctype: str, dte: int, oi: int = 500) -> OptionContract:
    return OptionContract(
        symbol=symbol,
        underlying="SPY",
        strike=strike,
        expiration=date.today() + timedelta(days=dte),
        contract_type=ctype,
        open_interest=oi,
    )


def _chain(price: float, dte: int = 21) -> OptionChain:
    contracts = []
    for strike in range(int(price - 50), int(price + 55), 5):
        contracts.append(_contract(f"P{strike}", float(strike), "put", dte))
        contracts.append(_contract(f"C{strike}", float(strike), "call", dte))
    return OptionChain(underlying="SPY", underlying_price=price, contracts=contracts)


def test_pick_iron_condor_legs():
    legs = pick_iron_condor_legs(_chain(500.0))
    assert legs is not None
    short_put, long_put, short_call, long_call = legs
    assert long_put.strike < short_put.strike < 500 < short_call.strike < long_call.strike


def test_pick_atm_straddle():
    pair = pick_atm_straddle(_chain(500.0))
    assert pair is not None
    put, call = pair
    assert put.strike == call.strike


def test_pick_strangle_legs():
    pair = pick_strangle_legs(_chain(500.0))
    assert pair is not None
    put, call = pair
    assert put.strike < 500 < call.strike
