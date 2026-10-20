"""Multi-leg option limit price calculation.
  - positive = net debit (paying to open)
  - negative = net credit (receiving premium)
"""

from dataclasses import replace
import logging

from alpaca.data.models.quotes import Quote

from alpaca_infra.models import TradeCandidate, TradeLeg

logger = logging.getLogger("alpaca_infra.pricing")


def _leg_price(side: str, quote: Quote | None, use_mid: bool = False) -> float | None:
    if quote is None:
        return None
    bid, ask = quote.bid_price, quote.ask_price
    if bid <= 0 and ask <= 0:
        return None
    if use_mid and bid > 0 and ask > 0:
        return (bid + ask) / 2
    if side == "buy":
        return ask if ask > 0 else bid
    return bid if bid > 0 else ask


def compute_raw_net(legs: list[TradeLeg], quotes: dict[str, Quote], use_mid: bool = False) -> tuple[float | None, list[dict]]:
    """Natural net: positive = debit, negative = credit."""
    breakdown: list[dict] = []
    net = 0.0

    for leg in legs:
        price = _leg_price(leg.side, quotes.get(leg.symbol), use_mid=use_mid)
        if price is None:
            return None, breakdown
        contribution = price * leg.ratio_qty
        if leg.side == "buy":
            net += contribution
        else:
            net -= contribution
        breakdown.append({
            "symbol": leg.symbol,
            "side": leg.side,
            "price": round(price, 4),
            "contribution": round(contribution if leg.side == "buy" else -contribution, 4),
        })

    return net, breakdown


def apply_slippage(net: float, slippage_pct: float) -> float:
    """Worsen price slightly to improve fill probability."""
    if net > 0:
        return net * (1 + slippage_pct)
    if net < 0:
        return net * (1 - slippage_pct)
    return net


def round_limit_price(price: float, tick: float = 0.01) -> float:
    rounded = round(price / tick) * tick
    if rounded == 0:
        rounded = tick if price > 0 else -tick
    return round(rounded, 2)


def compute_mleg_limit_price(
    legs: list[TradeLeg],
    quotes: dict[str, Quote],
    slippage_pct: float = 0.05,
    use_mid: bool = False,
) -> tuple[float | None, dict]:
    """Return Alpaca-compatible mleg limit_price and pricing metadata."""
    raw_net, breakdown = compute_raw_net(legs, quotes, use_mid=use_mid)
    if raw_net is None:
        return None, {"breakdown": breakdown, "error": "missing_quotes"}

    adjusted = apply_slippage(raw_net, slippage_pct)
    limit_price = round_limit_price(adjusted)

    meta = {
        "raw_net": round(raw_net, 4),
        "adjusted_net": round(adjusted, 4),
        "limit_price": limit_price,
        "order_side": "debit" if limit_price > 0 else "credit",
        "slippage_pct": slippage_pct,
        "breakdown": breakdown,
    }
    return limit_price, meta


class LimitPricer:
    def __init__(self, quote_service, slippage_pct: float = 0.05, fallback_to_market: bool = True) -> None:
        self.quote_service = quote_service
        self.slippage_pct = slippage_pct
        self.fallback_to_market = fallback_to_market

    def price(self, candidate: TradeCandidate) -> TradeCandidate:
        if candidate.order_type != "limit" or candidate.limit_price is not None:
            return candidate

        symbols = [leg.symbol for leg in candidate.legs]
        quotes = self.quote_service.get_quotes(symbols)
        limit_price, meta = compute_mleg_limit_price(
            candidate.legs, quotes, slippage_pct=self.slippage_pct,
        )

        if limit_price is None:
            logger.warning(
                "Cannot price %s %s — missing quotes, fallback=%s",
                candidate.strategy_name, candidate.symbol, self.fallback_to_market,
            )
            if self.fallback_to_market:
                return replace(candidate, order_type="market", limit_price=None)
            return candidate

        merged_meta = {**candidate.metadata, "pricing": meta}
        logger.info(
            "Priced %s %s: %s limit=%.2f (raw=%.2f)",
            candidate.strategy_name,
            candidate.symbol,
            meta["order_side"],
            limit_price,
            meta["raw_net"],
        )
        return replace(candidate, limit_price=limit_price, metadata=merged_meta)
