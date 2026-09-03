"""Order execution and status tracking."""

import time

from alpaca.trading.enums import QueryOrderStatus

from config.settings import Settings
from core.state import StateStore
from data.alpaca_client import AlpacaClients
from data.option_quotes import OptionQuoteService
from execution.order_builder import build_mleg_order
from execution.pricing import LimitPricer
from observability.logger import get_logger
from strategies.base import TradeCandidate

logger = get_logger("executor")


class OrderExecutor:
    def __init__(
        self,
        clients: AlpacaClients,
        state: StateStore,
        settings: Settings,
        dry_run: bool = True,
    ) -> None:
        self.clients = clients
        self.state = state
        self.dry_run = dry_run
        self.settings = settings
        self.pricer = LimitPricer(
            quote_service=OptionQuoteService(clients),
            slippage_pct=settings.limit_slippage_pct,
            fallback_to_market=settings.quote_fallback_market,
        )

    def _prepare_candidate(self, candidate: TradeCandidate) -> TradeCandidate:
        prepared = candidate
        if prepared.order_type == "limit" and prepared.limit_price is None:
            prepared = self.pricer.price(prepared)
        return prepared

    def prepare_candidate(self, candidate: TradeCandidate) -> TradeCandidate:
        return self._prepare_candidate(candidate)

    def submit(self, candidate: TradeCandidate, qty: int = 1) -> str | None:
        candidate = self._prepare_candidate(candidate)
        order_request = build_mleg_order(candidate, qty=qty)
        client_order_id = order_request.client_order_id or "unknown"

        payload = {
            "legs": [leg.symbol for leg in candidate.legs],
            "order_type": candidate.order_type,
            "limit_price": candidate.limit_price,
            "qty": qty,
            "pricing": candidate.metadata.get("pricing"),
            "sizing": candidate.metadata.get("sizing"),
        }

        if self.dry_run:
            logger.info(
                "[DRY RUN] Would submit %s for %s type=%s limit=%s",
                client_order_id, candidate.symbol, candidate.order_type, candidate.limit_price,
            )
            self.state.log_trade(
                client_order_id, candidate.symbol, candidate.strategy_name, "dry_run", payload,
            )
            return client_order_id

        try:
            order = self.clients.trading.submit_order(order_request)
        except Exception as exc:
            logger.error("Order submission failed for %s: %s", candidate.symbol, exc)
            self.state.log_trade(
                client_order_id, candidate.symbol, candidate.strategy_name, "error",
                {**payload, "error": str(exc)},
            )
            return None

        payload["order_id"] = str(order.id)
        self.state.log_trade(
            client_order_id, candidate.symbol, candidate.strategy_name, str(order.status), payload,
        )
        logger.info(
            "Submitted order %s status=%s limit=%s qty=%s",
            order.id, order.status, candidate.limit_price, qty,
        )
        return client_order_id

    def wait_for_fill(self, client_order_id: str, timeout_sec: int = 60) -> str:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            order = self.clients.trading.get_order_by_client_id(client_order_id)
            if order.status in (QueryOrderStatus.FILLED, QueryOrderStatus.CANCELED, QueryOrderStatus.EXPIRED):
                return str(order.status)
            time.sleep(2)
        return "timeout"
