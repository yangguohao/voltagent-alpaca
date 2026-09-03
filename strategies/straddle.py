"""Long Straddle baseline — buy volatility when IV rank is low."""

from data.options_chain import OptionChain
from signals.base import Signal
from strategies.base import BaseStrategy, TradeCandidate, TradeLeg
from strategies.selection import TARGET_DTE_MAX, TARGET_DTE_MIN, pick_atm_straddle


class StraddleStrategy(BaseStrategy):
    name = "straddle"
    max_iv_rank = 0.35
    min_strength = 0.3

    def generate_candidates(self, signal: Signal, chain: OptionChain) -> list[TradeCandidate]:
        iv_rank = signal.metadata.get("iv_rank", 1.0)
        if signal.signal_type != "low_iv" or signal.strength < self.min_strength:
            return []
        if iv_rank > self.max_iv_rank:
            return []

        pair = pick_atm_straddle(chain, TARGET_DTE_MIN, TARGET_DTE_MAX)
        if pair is None:
            return []

        put, call = pair
        return [TradeCandidate(
            symbol=signal.symbol,
            strategy_name=self.name,
            order_type="limit",
            legs=[
                TradeLeg(symbol=put.symbol, side="buy", position_intent="buy_to_open"),
                TradeLeg(symbol=call.symbol, side="buy", position_intent="buy_to_open"),
            ],
            metadata={
                "signal_strength": signal.strength,
                "iv_rank": iv_rank,
                "expiration": str(put.expiration),
                "dte": put.dte,
                "strike": put.strike,
            },
        )]

    def build_legs(self, candidate: TradeCandidate) -> list[TradeLeg]:
        return candidate.legs
