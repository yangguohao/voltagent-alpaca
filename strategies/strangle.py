"""Strangle baseline — short OTM strangle on high IV, long on low IV."""

from data.options_chain import OptionChain
from signals.base import Signal
from strategies.base import BaseStrategy, TradeCandidate, TradeLeg
from strategies.selection import TARGET_DTE_MAX, TARGET_DTE_MIN, pick_strangle_legs


class StrangleStrategy(BaseStrategy):
    name = "strangle"
    min_strength = 0.3

    def generate_candidates(self, signal: Signal, chain: OptionChain) -> list[TradeCandidate]:
        if signal.signal_type not in ("high_iv", "low_iv") or signal.strength < self.min_strength:
            return []

        pair = pick_strangle_legs(chain, min_dte=TARGET_DTE_MIN, max_dte=TARGET_DTE_MAX)
        if pair is None:
            return []

        put, call = pair
        if signal.signal_type == "high_iv":
            side, intent = "sell", "sell_to_open"
        else:
            side, intent = "buy", "buy_to_open"
        wing_width = abs(call.strike - put.strike)

        return [TradeCandidate(
            symbol=signal.symbol,
            strategy_name=self.name,
            order_type="limit",
            legs=[
                TradeLeg(symbol=put.symbol, side=side, position_intent=intent),
                TradeLeg(symbol=call.symbol, side=side, position_intent=intent),
            ],
            metadata={
                "signal_strength": signal.strength,
                "iv_rank": signal.metadata.get("iv_rank"),
                "direction": side,
                "expiration": str(put.expiration),
                "dte": put.dte,
                "put_strike": put.strike,
                "call_strike": call.strike,
                "wing_width": wing_width,
            },
        )]

    def build_legs(self, candidate: TradeCandidate) -> list[TradeLeg]:
        return candidate.legs
