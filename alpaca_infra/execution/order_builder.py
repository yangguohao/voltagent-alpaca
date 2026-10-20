"""Build Alpaca multi-leg option orders."""

from datetime import datetime, timezone

from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest, OptionLegRequest

from alpaca_infra.models import TradeCandidate, TradeLeg


def _map_side(side: str) -> OrderSide:
    return OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL


def _build_legs(candidate: TradeCandidate) -> list[OptionLegRequest]:
    return [
        OptionLegRequest(
            symbol=leg.symbol,
            side=_map_side(leg.side),
            ratio_qty=leg.ratio_qty,
            position_intent=leg.position_intent,
        )
        for leg in candidate.legs
    ]


def build_mleg_order(
    candidate: TradeCandidate,
    qty: int = 1,
    time_in_force: TimeInForce = TimeInForce.DAY,
) -> MarketOrderRequest | LimitOrderRequest:
    client_order_id = (
        f"{candidate.strategy_name}-{candidate.symbol}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )

    if len(candidate.legs) == 1:
        leg = candidate.legs[0]
        common = {
            "symbol": leg.symbol,
            "qty": qty,
            "side": _map_side(leg.side),
            "time_in_force": time_in_force,
            "position_intent": leg.position_intent,
            "client_order_id": client_order_id,
        }
        if candidate.order_type == "limit" and candidate.limit_price is not None:
            return LimitOrderRequest(limit_price=abs(candidate.limit_price), **common)
        return MarketOrderRequest(**common)

    legs = _build_legs(candidate)

    if candidate.order_type == "limit" and candidate.limit_price is not None:
        return LimitOrderRequest(
            order_class=OrderClass.MLEG,
            qty=qty,
            time_in_force=time_in_force,
            legs=legs,
            limit_price=candidate.limit_price,
            client_order_id=client_order_id,
        )

    return MarketOrderRequest(
        order_class=OrderClass.MLEG,
        qty=qty,
        time_in_force=time_in_force,
        legs=legs,
        client_order_id=client_order_id,
    )
