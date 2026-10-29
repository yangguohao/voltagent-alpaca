"""Main trading agent orchestrator."""

import asyncio
from dataclasses import asdict, replace

from ai_agent.config.settings import Settings, get_settings
from ai_agent.core.state import StateStore
from alpaca_infra.clients import create_clients
from alpaca_infra.market_data import MarketDataService
from alpaca_infra.options_chain import OptionsChainService
from tradier_infra import OptionsChainService as TradierOptionsChainService
from tradier_infra import OptionQuoteService as TradierOptionQuoteService
from tradier_infra import create_client as create_tradier_client
from ai_agent.execution.exit_manager import ExitManager
from alpaca_infra.execution.executor import OrderExecutor
from soxl_strategy.manager import SoxlCoveredCallManager
from ai_agent.llm.agents.regime import RegimeAgent
from ai_agent.llm.agents.reviewer import ReviewerAgent
from ai_agent.llm.agents.selector import SelectorAgent
from ai_agent.llm.groq_client import GroqClient
from ai_agent.llm.router import ModelRouter
from ai_agent.observability.logger import get_logger
from alpaca_infra.metrics import MetricsService
from ai_agent.risk.gates import RiskDecisionType, RiskGate
from ai_agent.risk.position_sizer import PortfolioSnapshot
from ai_agent.risk.regime_gate import RegimeGate, RegimeState
from ai_agent.risk.sizer import PositionSizer
from ai_agent.signals.base import SignalEngine
from ai_agent.signals.volatility import VolatilitySignalGenerator
from ai_agent.strategies.base import StrategyRegistry, TradeCandidate
from ai_agent.strategies.iron_condor import IronCondorStrategy
from ai_agent.strategies.selection import TARGET_DTE_MAX, TARGET_DTE_MIN
from ai_agent.strategies.straddle import StraddleStrategy
from ai_agent.strategies.strangle import StrangleStrategy

logger = get_logger("agent")


class TradingAgent:
    def __init__(self, settings: Settings | None = None, dry_run: bool = True) -> None:
        self.settings = settings or get_settings()
        self.state = StateStore(self.settings.state_db_path)
        self.clients = create_clients(self.settings)
        provider = self.settings.option_data_provider.lower()
        quote_service = None
        if provider == "tradier":
            tradier = create_tradier_client(self.settings)
            self.options_chain = TradierOptionsChainService(tradier)
            quote_service = TradierOptionQuoteService(tradier)
        elif provider == "alpaca":
            self.options_chain = OptionsChainService(self.clients)
        else:
            raise ValueError("OPTION_DATA_PROVIDER must be 'alpaca' or 'tradier'")
        self.market_data = MarketDataService(self.clients, quote_service=quote_service)
        self.metrics = MetricsService(self.clients)
        self.risk_gate = RiskGate(self.settings)
        self.regime_gate = RegimeGate(
            min_confidence=self.settings.regime_min_confidence,
            enabled=self.settings.regime_gate_enabled,
        )
        self.position_sizer = PositionSizer(self.settings)
        self.executor = OrderExecutor(
            self.clients,
            self.state,
            self.settings,
            dry_run=dry_run,
            quote_service=quote_service,
        )
        self.exit_manager = ExitManager(self.clients, self.settings, self.executor)
        self.soxl_manager = SoxlCoveredCallManager(
            self.clients,
            self.settings,
            self.market_data,
            self.options_chain,
            self.executor,
            state=self.state,
        )

        self.signal_engine = SignalEngine([VolatilitySignalGenerator()])
        self.strategies = StrategyRegistry()
        self.strategies.register(IronCondorStrategy())
        self.strategies.register(StraddleStrategy())
        self.strategies.register(StrangleStrategy())

        self.groq = GroqClient(self.settings, self.state)
        self.router = ModelRouter(self.settings)
        self.regime_agent = RegimeAgent(self.groq, self.router)
        self.selector_agent = SelectorAgent(self.groq, self.router)
        self.reviewer_agent = ReviewerAgent(self.groq, self.router, self.settings)

    def _portfolio_snapshot(self) -> PortfolioSnapshot:
        m = self.metrics.snapshot()
        return PortfolioSnapshot(
            equity=m.equity,
            buying_power=m.buying_power,
            open_positions=m.position_count,
            daily_pnl_pct=m.daily_pnl_pct,
            open_underlyings=m.open_underlyings,
        )

    def _load_regime_state(self) -> RegimeState | None:
        data = self.state.get("current_regime")
        if not data:
            return None
        return RegimeState(
            regime=data.get("regime", ""),
            confidence=float(data.get("confidence", 0)),
            notes=data.get("notes", ""),
        )

    async def _ensure_regime(self) -> RegimeState | None:
        state = self._load_regime_state()
        if state is not None:
            return state
        logger.info("No regime in state, running inline regime detection")
        await self.run_premarket()
        return self._load_regime_state()

    def _filter_by_regime(
        self,
        candidates: list[TradeCandidate],
        regime: RegimeState | None,
        signal_type: str,
    ) -> list[TradeCandidate]:
        return [
            c for c in candidates
            if self.regime_gate.allows_strategy(regime, c.strategy_name, signal_type)
        ]

    def _rule_based_pick(self, approved: list[TradeCandidate], signal_type: str) -> TradeCandidate:
        priority = {
            "low_iv": ["straddle", "strangle"],
            "high_iv": ["iron_condor", "strangle"],
        }.get(signal_type, [])
        by_name = {c.strategy_name: c for c in approved}
        for name in priority:
            if name in by_name:
                return by_name[name]
        return approved[0]

    async def run_premarket(self) -> None:
        logger.info("=== Premarket analysis ===")
        metrics = self.metrics.snapshot()
        summary = {
            "equity": round(metrics.equity, 2),
            "daily_pnl_pct": round(metrics.daily_pnl_pct, 4),
            "positions": metrics.position_count,
            "watchlist": self.settings.watchlist_symbols,
        }
        if self.settings.groq_api_key:
            try:
                regime = await self.regime_agent.analyze(summary)
                self.state.set("current_regime", regime.model_dump())
                logger.info(
                    "[AI:regime] %s confidence=%.0f%% notes=%s",
                    regime.regime,
                    regime.confidence * 100,
                    regime.notes[:120] if regime.notes else "",
                )
            except Exception as exc:
                logger.error("Regime analysis failed: %s", exc)
        else:
            logger.warning("GROQ_API_KEY not set, skipping LLM regime analysis")

    async def run_exit_cycle(self) -> None:
        logger.info("=== Exit cycle ===")
        closed = self.exit_manager.run()
        if closed:
            logger.info("[EXIT] submitted %d close order(s)", len(closed))
        else:
            logger.info("[EXIT] no positions met exit criteria")

    async def run_intraday_cycle(self) -> None:
        await self.run_exit_cycle()
        if self.settings.soxl_strategy_enabled:
            self.soxl_manager.run()
        logger.info("=== Intraday cycle ===")
        portfolio = self._portfolio_snapshot()
        held = sorted(portfolio.open_underlyings)
        if held:
            logger.info("[DECISION] Current exposure: %s", ", ".join(held))
        regime = await self._ensure_regime()
        if regime:
            logger.info(
                "[AI:regime] active=%s confidence=%.0f%%",
                regime.regime,
                regime.confidence * 100,
            )

        for symbol in self.settings.watchlist_symbols:
            if symbol in portfolio.open_underlyings:
                logger.info("[DECISION] skip %s: already have position or open order", symbol)
                continue

            bars = self.market_data.get_daily_bars(symbol)
            price = self.market_data.get_latest_price(symbol)
            if price is None:
                logger.info("[DECISION] skip %s: no market price", symbol)
                continue

            signals = self.signal_engine.evaluate(symbol, bars=bars)
            for signal in signals:
                if signal.strength < 0.3:
                    logger.info(
                        "[DECISION] skip %s %s: signal too weak (%.2f)",
                        symbol,
                        signal.signal_type,
                        signal.strength,
                    )
                    continue

                if not self.regime_gate.allows_signal(regime, signal.signal_type):
                    logger.info(
                        "[DECISION] skip %s %s: blocked by regime %s",
                        symbol,
                        signal.signal_type,
                        regime.regime if regime else "unknown",
                    )
                    continue

                self.state.log_signal(signal.symbol, signal.signal_type, signal.strength, signal.metadata)
                logger.info(
                    "[SIGNAL] %s %s strength=%.2f meta=%s",
                    symbol,
                    signal.signal_type,
                    signal.strength,
                    signal.metadata,
                )

                chain = self.options_chain.fetch_chain(
                    symbol, price, min_dte=TARGET_DTE_MIN, max_dte=TARGET_DTE_MAX,
                )
                candidates = self.strategies.select_for_signal(signal, chain)
                candidates = self._filter_by_regime(candidates, regime, signal.signal_type)
                if not candidates:
                    logger.info("[DECISION] skip %s: no strategy matches regime", symbol)
                    continue

                contract_map = {c.symbol: c for c in chain.contracts}
                approved: list[TradeCandidate] = []
                for candidate in candidates:
                    decision = self.risk_gate.check(candidate, portfolio, contract_map)
                    if decision.decision != RiskDecisionType.PASS:
                        logger.info(
                            "[DECISION] risk reject %s/%s: %s",
                            symbol,
                            candidate.strategy_name,
                            decision.reason,
                        )
                        continue
                    approved.append(candidate)

                if not approved:
                    logger.info("[DECISION] skip %s: no candidate passed risk gates", symbol)
                    continue

                chosen = approved[0]
                if self.settings.groq_api_key:
                    try:
                        selection = await self.selector_agent.select(
                            signal_summary={
                                "symbol": signal.symbol,
                                "type": signal.signal_type,
                                "strength": signal.strength,
                                "metadata": signal.metadata,
                            },
                            candidates=[c.strategy_name for c in approved],
                            held_symbols=held,
                        )
                        logger.info(
                            "[AI:selector] %s -> %s confidence=%.0f%% rationale=%s",
                            symbol,
                            selection.strategy,
                            selection.confidence * 100,
                            selection.rationale[:160] if selection.rationale else "",
                        )
                        if selection.strategy == "hold":
                            if self.settings.llm_selector_fallback_rules:
                                chosen = self._rule_based_pick(approved, signal.signal_type)
                                logger.info(
                                    "[AI:selector] %s hold overridden by rule fallback -> %s "
                                    "(low_iv->straddle/strangle, high_iv->iron_condor/strangle)",
                                    symbol,
                                    chosen.strategy_name,
                                )
                            else:
                                logger.info("[DECISION] skip %s: LLM selected hold", symbol)
                                continue
                        else:
                            matched = [c for c in approved if c.strategy_name == selection.strategy]
                            if matched:
                                chosen = matched[0]
                            else:
                                logger.warning(
                                    "[AI:selector] %s picked %s but not in approved list, using %s",
                                    symbol,
                                    selection.strategy,
                                    chosen.strategy_name,
                                )

                        review = await self.reviewer_agent.review(
                            trade_summary={
                                "strategy": chosen.strategy_name,
                                "symbol": chosen.symbol,
                                "legs": len(chosen.legs),
                                "dte": chosen.metadata.get("dte"),
                                "iv_rank": chosen.metadata.get("iv_rank"),
                            },
                            risk_context={
                                "equity": portfolio.equity,
                                "positions": portfolio.open_positions,
                                "held_symbols": held,
                            },
                        )
                        if not review.approve:
                            logger.info(
                                "[AI:reviewer] reject %s/%s [%s]: %s",
                                symbol,
                                chosen.strategy_name,
                                review.source,
                                review.reason,
                            )
                            continue
                        logger.info(
                            "[AI:reviewer] approve %s/%s [%s]: %s",
                            symbol,
                            chosen.strategy_name,
                            review.source,
                            review.reason,
                        )
                    except Exception as exc:
                        logger.error("[AI:pipeline] failed for %s: %s", symbol, exc)
                        if not self.settings.llm_review_fallback_approve:
                            continue
                        logger.warning(
                            "[AI:pipeline] %s proceeding via llm_review_fallback_approve",
                            symbol,
                        )

                logger.info(
                    "[DECISION] submit %s %s legs=%d",
                    symbol,
                    chosen.strategy_name,
                    len(chosen.legs),
                )

                prepared = self.executor.prepare_candidate(chosen)
                size = self.position_sizer.size(prepared, portfolio)
                prepared = replace(
                    prepared,
                    metadata={**prepared.metadata, "sizing": asdict(size)},
                )
                self.executor.submit(prepared, qty=size.qty)
                break  # one trade per symbol per cycle

    async def run_postmarket(self) -> None:
        logger.info("=== Postmarket sync ===")
        metrics = self.metrics.snapshot()
        payload = asdict(metrics)
        payload["open_underlyings"] = sorted(metrics.open_underlyings)
        self.state.set("last_metrics", payload)
        logger.info("Equity=%.2f daily_pnl=%.2f (%.2f%%)", metrics.equity, metrics.daily_pnl, metrics.daily_pnl_pct * 100)

    async def run_once(self, phase: str = "intraday") -> None:
        if phase == "premarket":
            await self.run_premarket()
        elif phase == "postmarket":
            await self.run_postmarket()
        elif phase == "exit":
            await self.run_exit_cycle()
        elif phase == "soxl":
            if self.settings.soxl_strategy_enabled:
                self.soxl_manager.run()
            else:
                logger.info("[SOXL] disabled; set SOXL_STRATEGY_ENABLED=true")
        else:
            await self.run_intraday_cycle()

    def health_check(self) -> dict:
        account = self.clients.trading.get_account()
        return {
            "status": str(account.status),
            "equity": float(account.equity),
            "paper": self.settings.alpaca_paper,
        }
