"""Evaluate open positions and submit closing orders."""

from config.settings import Settings
from data.alpaca_client import AlpacaClients
from execution.executor import OrderExecutor
from execution.positions import PositionGroup, group_option_positions
from observability.logger import get_logger
from risk.exit_rules import ExitDecision, ExitReason, adaptive_exit_thresholds, evaluate_exit
from strategies.base import TradeCandidate, TradeLeg

logger = get_logger("exit_manager")


def build_close_candidate(group: PositionGroup, settings: Settings, decision: ExitDecision) -> TradeCandidate | None:
    qty = group.close_qty
    if qty <= 0:
        return None

    legs: list[TradeLeg] = []
    for leg in group.legs:
        if leg.is_long:
            legs.append(
                TradeLeg(
                    symbol=leg.symbol,
                    side="sell",
                    ratio_qty=1,
                    position_intent="sell_to_close",
                )
            )
        else:
            legs.append(
                TradeLeg(
                    symbol=leg.symbol,
                    side="buy",
                    ratio_qty=1,
                    position_intent="buy_to_close",
                )
            )

    thresholds = decision.thresholds
    return TradeCandidate(
        symbol=group.underlying,
        strategy_name="close",
        legs=legs,
        order_type=settings.order_type,
        metadata={
            "exit_reason": decision.reason.value,
            "pnl_pct": round(decision.pnl_pct, 4),
            "dte": decision.dte,
            "take_profit_threshold": round(thresholds.take_profit_pct, 4),
            "stop_loss_threshold": round(thresholds.stop_loss_pct, 4),
            "close_qty": qty,
        },
    )


class ExitManager:
    def __init__(self, clients: AlpacaClients, settings: Settings, executor: OrderExecutor) -> None:
        self.clients = clients
        self.settings = settings
        self.executor = executor

    def run(self) -> list[str]:
        if not self.settings.exit_enabled:
            return []

        submitted: list[str] = []
        for group in group_option_positions(self.clients):
            decision = evaluate_exit(group.pnl_pct, group.min_dte, self.settings)
            thresholds = adaptive_exit_thresholds(group.min_dte, self.settings)

            if decision is None:
                logger.info(
                    "[EXIT] hold %s pnl=%.1f%% dte=%d thresholds=tp%.0f%%/sl%.0f%%",
                    group.underlying,
                    group.pnl_pct * 100,
                    group.min_dte,
                    thresholds.take_profit_pct * 100,
                    thresholds.stop_loss_pct * 100,
                )
                continue

            candidate = build_close_candidate(group, self.settings, decision)
            if candidate is None:
                logger.warning("[EXIT] skip %s: unable to build close order", group.underlying)
                continue

            logger.info(
                "[EXIT] close %s reason=%s pnl=%.1f%% dte=%d tp=%.0f%% sl=%.0f%% qty=%d",
                group.underlying,
                decision.reason.value,
                decision.pnl_pct * 100,
                decision.dte,
                thresholds.take_profit_pct * 100,
                thresholds.stop_loss_pct * 100,
                group.close_qty,
            )

            prepared = self.executor.prepare_candidate(candidate)
            order_id = self.executor.submit(prepared, qty=group.close_qty)
            if order_id:
                submitted.append(order_id)

        return submitted
