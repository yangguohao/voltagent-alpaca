"""Group Alpaca option positions by underlying for spread-level P&L."""

from dataclasses import dataclass, field
from datetime import date

from alpaca_infra.clients import AlpacaClients
from alpaca_infra.occ import option_dte, underlying_symbol


@dataclass
class LegPosition:
    symbol: str
    qty: int
    is_long: bool
    avg_entry: float
    market_value: float
    unrealized_pl: float
    cost_basis: float
    dte: int | None


@dataclass
class PositionGroup:
    underlying: str
    legs: list[LegPosition] = field(default_factory=list)

    @property
    def close_qty(self) -> int:
        if not self.legs:
            return 0
        return min(leg.qty for leg in self.legs)

    @property
    def total_cost_basis(self) -> float:
        return sum(leg.cost_basis for leg in self.legs)

    @property
    def total_market_value(self) -> float:
        return sum(leg.market_value for leg in self.legs)

    @property
    def total_unrealized_pl(self) -> float:
        return sum(leg.unrealized_pl for leg in self.legs)

    @property
    def pnl_pct(self) -> float:
        cost = self.total_cost_basis
        if cost <= 0:
            return 0.0
        return self.total_unrealized_pl / cost

    @property
    def min_dte(self) -> int:
        dtes = [leg.dte for leg in self.legs if leg.dte is not None]
        return min(dtes) if dtes else 0


def group_option_positions(clients: AlpacaClients, today: date | None = None) -> list[PositionGroup]:
    groups: dict[str, PositionGroup] = {}

    for position in clients.trading.get_all_positions():
        symbol = position.symbol
        if len(symbol) < 15:
            continue

        root = underlying_symbol(symbol)
        qty = abs(int(float(position.qty)))
        if qty == 0:
            continue

        is_long = "long" in str(position.side).lower()
        cost_basis = float(position.cost_basis) if position.cost_basis else abs(qty) * float(position.avg_entry_price) * 100

        leg = LegPosition(
            symbol=symbol,
            qty=qty,
            is_long=is_long,
            avg_entry=float(position.avg_entry_price),
            market_value=float(position.market_value),
            unrealized_pl=float(position.unrealized_pl),
            cost_basis=cost_basis,
            dte=option_dte(symbol, today=today),
        )

        if root not in groups:
            groups[root] = PositionGroup(underlying=root)
        groups[root].legs.append(leg)

    return list(groups.values())
