"""SOXL covered-call entry and mandatory exit lifecycle."""

from datetime import date

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetCalendarRequest, GetOrdersRequest

from ai_agent.config.settings import Settings
from alpaca_infra.market_data import MarketDataService
from alpaca_infra.occ import option_expiration, option_type, underlying_symbol
from alpaca_infra.options_chain import OptionsChainService
from alpaca_infra.execution.executor import OrderExecutor
from ai_agent.observability.logger import get_logger
from ai_agent.strategies.base import TradeCandidate, TradeLeg
from soxl_strategy.strategy import (
    SOXL_MAX_DTE,
    SOXL_MIN_DTE,
    build_soxl_covered_call,
    evaluate_soxl_setup,
    trading_sessions_to_expiration,
)

logger = get_logger("soxl_manager")


class SoxlCoveredCallManager:
    def __init__(
        self,
        clients,
        settings: Settings,
        market_data: MarketDataService,
        options_chain: OptionsChainService,
        executor: OrderExecutor,
    ) -> None:
        self.clients = clients
        self.settings = settings
        self.market_data = market_data
        self.options_chain = options_chain
        self.executor = executor

    def _positions(self) -> tuple[int, list]:
        shares = 0
        short_calls = []
        for position in self.clients.trading.get_all_positions():
            symbol = position.symbol
            side = str(position.side).lower()
            qty = abs(int(float(position.qty)))
            if symbol == "SOXL" and "long" in side:
                shares = qty
            elif (
                underlying_symbol(symbol) == "SOXL"
                and option_type(symbol) == "call"
                and "short" in side
            ):
                short_calls.append(position)
        return shares, short_calls

    def _has_working_option_order(self) -> bool:
        try:
            orders = self.clients.trading.get_orders(
                filter=GetOrdersRequest(status=QueryOrderStatus.OPEN),
            )
        except Exception as exc:
            logger.warning("[SOXL] unable to inspect working orders: %s", exc)
            return True
        for order in orders:
            symbols = [getattr(order, "symbol", None)]
            symbols.extend(getattr(leg, "symbol", None) for leg in (getattr(order, "legs", None) or []))
            if any(symbol and underlying_symbol(symbol) == "SOXL" and symbol != "SOXL" for symbol in symbols):
                return True
        return False

    def _close(self, position, reason: str, qty: int | None = None) -> str | None:
        qty = qty or abs(int(float(position.qty)))
        candidate = TradeCandidate(
            symbol="SOXL",
            strategy_name="soxl_covered_call_close",
            order_type=self.settings.order_type,
            legs=[TradeLeg(position.symbol, "buy", position_intent="buy_to_close")],
            metadata={"exit_reason": reason, "close_qty": qty},
        )
        logger.info("[SOXL] buy to close %s qty=%d reason=%s", position.symbol, qty, reason)
        return self.executor.submit(candidate, qty=qty)

    def _sessions_to_expiration(self, expiration: date, today: date | None) -> int:
        current = today or date.today()
        try:
            return len(self.clients.trading.get_calendar(GetCalendarRequest(start=current, end=expiration))) - 1
        except Exception as exc:
            logger.warning("[SOXL] calendar lookup failed, using weekdays: %s", exc)
            return trading_sessions_to_expiration(expiration, current)

    def run(self, today: date | None = None) -> list[str]:
        qqq_bars = self.market_data.get_daily_bars("QQQ", days=320)
        soxx_bars = self.market_data.get_daily_bars("SOXX", days=320)
        shares, short_calls = self._positions()
        setup = evaluate_soxl_setup(qqq_bars, soxx_bars, shares)
        logger.info(
            "[SOXL] eligible=%s state=%s target=%s@%.0f%% reason=%s shares=%d "
            "drawdown=%s soxx_5d=%s cross_sessions=%s",
            setup.eligible,
            setup.underlying.state,
            setup.underlying.target_symbol or "cash",
            setup.underlying.target_allocation * 100,
            setup.reason,
            shares,
            f"{setup.underlying.soxx_drawdown:.2%}" if setup.underlying.soxx_drawdown is not None else "n/a",
            f"{setup.soxx_five_day_return:.2%}" if setup.soxx_five_day_return is not None else "n/a",
            setup.qqq_days_since_cross,
        )

        submitted: list[str] = []
        remaining_covered_lots = shares // 100
        for position in short_calls:
            position_qty = abs(int(float(position.qty)))
            expiration = option_expiration(position.symbol)
            t_minus_one = expiration is not None and self._sessions_to_expiration(expiration, today) <= 1
            if t_minus_one or setup.underlying.target_symbol != "SOXL":
                reason = "t_minus_one" if t_minus_one else "underlying_exit_signal"
                order_id = self._close(position, reason)
                if order_id:
                    submitted.append(order_id)
            else:
                uncovered_qty = max(position_qty - remaining_covered_lots, 0)
                remaining_covered_lots = max(remaining_covered_lots - position_qty, 0)
                if uncovered_qty:
                    order_id = self._close(position, "insufficient_share_coverage", qty=uncovered_qty)
                    if order_id:
                        submitted.append(order_id)

        if submitted or not setup.eligible or self._has_working_option_order():
            return submitted

        covered_capacity = shares // 100 - sum(abs(int(float(position.qty))) for position in short_calls)
        if covered_capacity <= 0:
            logger.info("[SOXL] no uncovered 100-share lots available")
            return submitted

        price = self.market_data.get_latest_price("SOXL")
        if price is None:
            logger.info("[SOXL] no SOXL market price")
            return submitted
        chain = self.options_chain.fetch_chain(
            "SOXL",
            price,
            min_dte=SOXL_MIN_DTE,
            max_dte=SOXL_MAX_DTE,
            include_snapshots=True,
        )
        chain.contracts = [
            contract
            for contract in chain.contracts
            if contract.open_interest >= self.settings.min_open_interest
            and (contract.spread_pct is None or contract.spread_pct <= self.settings.max_bid_ask_spread_pct)
        ]
        candidate = build_soxl_covered_call(chain)
        if candidate is None:
            logger.info("[SOXL] no liquid 5-12 DTE call with delta data")
            return submitted

        qty = min(covered_capacity, self.settings.max_contracts_per_trade)
        logger.info(
            "[SOXL] sell to open qty=%d strike=%.2f delta=%.3f dte=%d",
            qty,
            candidate.metadata["strike"],
            candidate.metadata["delta"],
            candidate.metadata["dte"],
        )
        order_id = self.executor.submit(candidate, qty=qty)
        if order_id:
            submitted.append(order_id)
        return submitted
