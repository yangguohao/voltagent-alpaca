"""Iron Condor baseline — short premium when IV rank is elevated."""

from alpaca_infra.options_chain import OptionChain
from ai_agent.signals.base import Signal
from ai_agent.strategies.base import BaseStrategy, TradeCandidate, TradeLeg
from ai_agent.strategies.selection import TARGET_DTE_MAX, TARGET_DTE_MIN, pick_iron_condor_legs


class IronCondorStrategy(BaseStrategy):
    name = "iron_condor"
    min_iv_rank = 0.65
    min_strength = 0.3

    def generate_candidates(self, signal: Signal, chain: OptionChain) -> list[TradeCandidate]:
        iv_rank = signal.metadata.get("iv_rank", 0)
        if signal.signal_type != "high_iv" or signal.strength < self.min_strength:
            return []
        if iv_rank < self.min_iv_rank:
            return []

        legs = pick_iron_condor_legs(chain, TARGET_DTE_MIN, TARGET_DTE_MAX)
        if legs is None:
            return []

        short_put, long_put, short_call, long_call = legs
        wing_width = abs(short_put.strike - long_put.strike)
        return [TradeCandidate(
            symbol=signal.symbol,
            strategy_name=self.name,
            order_type="limit",
            legs=[
                TradeLeg(symbol=short_put.symbol, side="sell", position_intent="sell_to_open"),
                TradeLeg(symbol=long_put.symbol, side="buy", position_intent="buy_to_open"),
                TradeLeg(symbol=short_call.symbol, side="sell", position_intent="sell_to_open"),
                TradeLeg(symbol=long_call.symbol, side="buy", position_intent="buy_to_open"),
            ],
            metadata={
                "signal_strength": signal.strength,
                "iv_rank": iv_rank,
                "expiration": str(short_put.expiration),
                "dte": short_put.dte,
                "short_put_strike": short_put.strike,
                "long_put_strike": long_put.strike,
                "short_call_strike": short_call.strike,
                "long_call_strike": long_call.strike,
                "wing_width": wing_width,
            },
        )]

    def build_legs(self, candidate: TradeCandidate) -> list[TradeLeg]:
        return candidate.legs
