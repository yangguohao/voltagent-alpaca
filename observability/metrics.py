"""Portfolio metrics tracking."""

from dataclasses import dataclass

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

from data.alpaca_client import AlpacaClients

from data.occ import underlying_symbol
@dataclass
class PortfolioMetrics:
    equity: float
    cash: float
    buying_power: float
    daily_pnl: float
    daily_pnl_pct: float
    position_count: int
    leg_count: int
    open_underlyings: frozenset[str]


class MetricsService:
    def __init__(self, clients: AlpacaClients) -> None:
        self.clients = clients

    def exposure_underlyings(self) -> set[str]:
        """Underlyings with open positions or unfilled orders."""
        underlyings: set[str] = set()
        for position in self.clients.trading.get_all_positions():
            underlyings.add(underlying_symbol(position.symbol))

        try:
            orders = self.clients.trading.get_orders(
                filter=GetOrdersRequest(status=QueryOrderStatus.OPEN),
            )
            for order in orders:
                legs = getattr(order, "legs", None) or []
                if legs:
                    for leg in legs:
                        symbol = getattr(leg, "symbol", None)
                        if symbol:
                            underlyings.add(underlying_symbol(symbol))
                elif order.symbol:
                    underlyings.add(underlying_symbol(order.symbol))
        except Exception:
            pass

        return underlyings

    def snapshot(self) -> PortfolioMetrics:
        account = self.clients.trading.get_account()
        positions = self.clients.trading.get_all_positions()
        equity = float(account.equity)
        last_equity = float(account.last_equity or equity)
        daily_pnl = equity - last_equity
        daily_pnl_pct = daily_pnl / last_equity if last_equity else 0.0
        underlyings = self.exposure_underlyings()
        return PortfolioMetrics(
            equity=equity,
            cash=float(account.cash),
            buying_power=float(account.buying_power),
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            position_count=len(underlyings),
            leg_count=len(positions),
            open_underlyings=frozenset(underlyings),
        )
