"""Shared contract selection utilities for baseline strategies."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from alpaca_infra.options_chain import OptionChain, OptionContract

# Baseline strategy parameters
TARGET_DTE_MIN = 14
TARGET_DTE_MAX = 35
TARGET_DTE_IDEAL = 21
SHORT_OTM_PCT = 0.05
STRANGLE_OTM_PCT = 0.07
WING_WIDTH_PCT = 0.02
MIN_OI_BASELINE = 100


@dataclass
class ExpirationSlice:
    expiration: date
    dte: int
    contracts: list[OptionContract]


def filter_liquid(contracts: list[OptionContract], min_oi: int = MIN_OI_BASELINE) -> list[OptionContract]:
    return [c for c in contracts if c.open_interest >= min_oi]


def filter_dte(contracts: list[OptionContract], min_dte: int, max_dte: int) -> list[OptionContract]:
    return [c for c in contracts if min_dte <= c.dte <= max_dte]


def group_by_expiration(contracts: list[OptionContract]) -> dict[date, list[OptionContract]]:
    groups: dict[date, list[OptionContract]] = defaultdict(list)
    for c in contracts:
        groups[c.expiration].append(c)
    return dict(groups)


def pick_expiration(
    contracts: list[OptionContract],
    min_dte: int = TARGET_DTE_MIN,
    max_dte: int = TARGET_DTE_MAX,
    ideal_dte: int = TARGET_DTE_IDEAL,
    min_oi: int = MIN_OI_BASELINE,
) -> ExpirationSlice | None:
    """Pick expiration closest to ideal DTE with enough liquid contracts."""
    liquid = filter_liquid(filter_dte(contracts, min_dte, max_dte), min_oi)
    if not liquid:
        return None

    groups = group_by_expiration(liquid)
    best_exp = min(groups.keys(), key=lambda exp: abs((exp - date.today()).days - ideal_dte))
    slice_contracts = groups[best_exp]
    dte = (best_exp - date.today()).days
    return ExpirationSlice(expiration=best_exp, dte=dte, contracts=slice_contracts)


def closest_strike(
    contracts: list[OptionContract],
    target: float,
    contract_type: str,
) -> OptionContract | None:
    typed = [c for c in contracts if c.contract_type == contract_type]
    if not typed:
        return None
    return min(typed, key=lambda c: abs(c.strike - target))


def pick_wing_contract(
    contracts: list[OptionContract],
    anchor: OptionContract,
    contract_type: str,
    direction: str,
) -> OptionContract | None:
    """Pick the next strike further OTM from anchor (for spread wings)."""
    typed = [c for c in contracts if c.contract_type == contract_type]
    if contract_type == "put":
        if direction == "lower":
            candidates = [c for c in typed if c.strike < anchor.strike]
            return max(candidates, key=lambda c: c.strike) if candidates else None
        candidates = [c for c in typed if c.strike > anchor.strike]
        return min(candidates, key=lambda c: c.strike) if candidates else None

    # call
    if direction == "higher":
        candidates = [c for c in typed if c.strike > anchor.strike]
        return min(candidates, key=lambda c: c.strike) if candidates else None
    candidates = [c for c in typed if c.strike < anchor.strike]
    return max(candidates, key=lambda c: c.strike) if candidates else None


def wing_width(price: float) -> float:
    """Approximate wing width in strike dollars (~2% of underlying, min $1)."""
    return max(1.0, round(price * WING_WIDTH_PCT))


def pick_atm_straddle(
    chain: OptionChain,
    min_dte: int = TARGET_DTE_MIN,
    max_dte: int = TARGET_DTE_MAX,
) -> tuple[OptionContract, OptionContract] | None:
    """Pick ATM call + put at the same strike for a straddle."""
    slice_ = pick_expiration(chain.contracts, min_dte, max_dte)
    if slice_ is None:
        return None

    price = chain.underlying_price
    atm_put = closest_strike(slice_.contracts, price, "put")
    atm_call = closest_strike(slice_.contracts, price, "call")
    if atm_put is None or atm_call is None:
        return None

    # Require same strike for true straddle
    if atm_put.strike != atm_call.strike:
        # Try to find a shared strike
        put_strikes = {c.strike: c for c in slice_.contracts if c.contract_type == "put"}
        call_strikes = {c.strike: c for c in slice_.contracts if c.contract_type == "call"}
        common = set(put_strikes) & set(call_strikes)
        if not common:
            return None
        strike = min(common, key=lambda s: abs(s - price))
        return put_strikes[strike], call_strikes[strike]

    return atm_put, atm_call


def pick_iron_condor_legs(
    chain: OptionChain,
    min_dte: int = TARGET_DTE_MIN,
    max_dte: int = TARGET_DTE_MAX,
) -> tuple[OptionContract, OptionContract, OptionContract, OptionContract] | None:
    """Short iron condor: short OTM put/call + long further OTM wings."""
    slice_ = pick_expiration(chain.contracts, min_dte, max_dte)
    if slice_ is None:
        return None

    price = chain.underlying_price
    short_put = closest_strike(slice_.contracts, price * (1 - SHORT_OTM_PCT), "put")
    short_call = closest_strike(slice_.contracts, price * (1 + SHORT_OTM_PCT), "call")
    if short_put is None or short_call is None:
        return None

    long_put = pick_wing_contract(slice_.contracts, short_put, "put", "lower")
    long_call = pick_wing_contract(slice_.contracts, short_call, "call", "higher")
    if long_put is None or long_call is None:
        return None

    return short_put, long_put, short_call, long_call


def pick_strangle_legs(
    chain: OptionChain,
    otm_pct: float = STRANGLE_OTM_PCT,
    min_dte: int = TARGET_DTE_MIN,
    max_dte: int = TARGET_DTE_MAX,
) -> tuple[OptionContract, OptionContract] | None:
    slice_ = pick_expiration(chain.contracts, min_dte, max_dte)
    if slice_ is None:
        return None

    price = chain.underlying_price
    put = closest_strike(slice_.contracts, price * (1 - otm_pct), "put")
    call = closest_strike(slice_.contracts, price * (1 + otm_pct), "call")
    if put is None or call is None:
        return None
    return put, call
