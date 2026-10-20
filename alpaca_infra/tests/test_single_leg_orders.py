from alpaca.trading.enums import OrderClass, OrderSide

from alpaca_infra.execution.order_builder import build_mleg_order
from alpaca_infra.models import TradeCandidate, TradeLeg


def test_single_leg_option_order_is_not_mleg_and_uses_positive_limit():
    candidate = TradeCandidate(
        symbol="SOXL",
        strategy_name="soxl_covered_call",
        order_type="limit",
        limit_price=-1.25,
        legs=[TradeLeg("SOXL261023C00060000", "sell", position_intent="sell_to_open")],
    )
    order = build_mleg_order(candidate, qty=2)
    assert order.order_class != OrderClass.MLEG
    assert order.side == OrderSide.SELL
    assert order.limit_price == 1.25
    assert order.qty == 2
