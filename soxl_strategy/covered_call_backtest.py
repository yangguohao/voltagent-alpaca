"""Approximate SOXL covered-call backtest using Alpaca historical option trades."""

from __future__ import annotations

import argparse
import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetStatus, ContractType
from alpaca.trading.requests import GetOptionContractsRequest

from ai_agent.config.settings import get_settings
from soxl_strategy.backtest import fetch_yahoo_daily
from soxl_strategy.strategy import evaluate_soxl_setup


@dataclass(frozen=True)
class CoveredCallTrade:
    symbol: str
    entry_date: date
    exit_date: date
    expiration: date
    strike: float
    delta: float
    entry_price: float
    exit_price: float
    pnl: float
    option_return: float
    stock_return: float
    exit_reason: str


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def call_price(spot: float, strike: float, years: float, rate: float, volatility: float) -> float:
    if years <= 0 or volatility <= 0:
        return max(spot - strike, 0.0)
    root_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + volatility * volatility / 2) * years) / (volatility * root_t)
    d2 = d1 - volatility * root_t
    return spot * _normal_cdf(d1) - strike * math.exp(-rate * years) * _normal_cdf(d2)


def implied_delta(spot: float, strike: float, days: int, option_price: float, rate: float = 0.045) -> float | None:
    """Infer European-call delta from a traded price; sufficient for strike ranking."""
    years = max(days, 1) / 365
    intrinsic = max(spot - strike * math.exp(-rate * years), 0.0)
    if option_price <= intrinsic or option_price >= spot:
        return None
    low, high = 0.01, 5.0
    if call_price(spot, strike, years, rate, high) < option_price:
        return None
    for _ in range(60):
        middle = (low + high) / 2
        if call_price(spot, strike, years, rate, middle) < option_price:
            low = middle
        else:
            high = middle
    volatility = (low + high) / 2
    d1 = (
        math.log(spot / strike) + (rate + volatility * volatility / 2) * years
    ) / (volatility * math.sqrt(years))
    return _normal_cdf(d1)


def select_contract(
    contracts: list,
    bars: dict[str, list[dict]],
    spot: float,
    entry_date: date,
) -> tuple[object, dict, float] | None:
    choices = []
    for contract in contracts:
        symbol_bars = bars.get(contract.symbol, [])
        if not symbol_bars:
            continue
        bar = symbol_bars[-1]
        price = float(bar.get("o", bar["c"]))
        dte = (contract.expiration_date - entry_date).days
        delta = implied_delta(spot, float(contract.strike_price), dte, price)
        if delta is None:
            continue
        choices.append((abs(delta - 0.20), -float(bar.get("v", 0)), contract, bar, delta))
    if not choices:
        return None
    _, _, contract, bar, delta = min(choices, key=lambda item: item[:2])
    return contract, bar, delta


class AlpacaOptionHistory:
    def __init__(self, api_key: str, secret_key: str) -> None:
        self.trading = TradingClient(api_key, secret_key, paper=True)
        self.data = OptionHistoricalDataClient(api_key, secret_key, raw_data=True)

    def contracts(self, entry: date, spot: float) -> list:
        request = GetOptionContractsRequest(
            underlying_symbols=["SOXL"],
            status=AssetStatus.INACTIVE,
            expiration_date_gte=entry + timedelta(days=5),
            expiration_date_lte=entry + timedelta(days=12),
            type=ContractType.CALL,
            strike_price_gte=str(round(spot * 1.001, 2)),
            strike_price_lte=str(round(spot * 1.60, 2)),
            limit=1000,
        )
        contracts = self.trading.get_option_contracts(request).option_contracts
        if not contracts:
            return []
        best_dte_distance = min(abs((item.expiration_date - entry).days - 7) for item in contracts)
        return [
            item for item in contracts
            if abs((item.expiration_date - entry).days - 7) == best_dte_distance
        ][:100]

    def bars(self, symbols: list[str], day: date) -> dict[str, list[dict]]:
        if not symbols:
            return {}
        return self.data.get_option_bars(OptionBarsRequest(
            symbol_or_symbols=symbols,
            start=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
            end=datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
            timeframe=TimeFrame.Day,
            limit=10_000,
        ))


def find_exit(
    entry_index: int,
    expiration: date,
    dates: list[date],
    setups: dict[date, object],
) -> tuple[date, str] | None:
    before_expiration = [day for day in dates if day < expiration]
    if not before_expiration:
        return None
    t_minus_one = before_expiration[-1]
    for current in dates[entry_index:]:
        if current > t_minus_one:
            break
        if setups[current].underlying.target_symbol != "SOXL":
            return current, "underlying_exit"
    return t_minus_one, "t_minus_one"


def run_covered_call_backtest(
    qqq_bars: list[dict],
    soxx_bars: list[dict],
    soxl_bars: list[dict],
    history: AlpacaOptionHistory,
    start: date,
    end: date,
    slippage: float = 0.05,
) -> list[CoveredCallTrade]:
    qqq = {bar["date"]: bar for bar in qqq_bars}
    soxx = {bar["date"]: bar for bar in soxx_bars}
    soxl = {bar["date"]: bar for bar in soxl_bars}
    dates = sorted(set(qqq) & set(soxx) & set(soxl))
    qqq_history: list[dict] = []
    soxx_history: list[dict] = []
    setups = {}
    for current in dates:
        qqq_history.append(qqq[current])
        soxx_history.append(soxx[current])
        setups[current] = evaluate_soxl_setup(qqq_history, soxx_history, 100)

    trades: list[CoveredCallTrade] = []
    blocked_until: date | None = None
    for signal_index, signal_date in enumerate(dates[:-1]):
        if signal_date < start or signal_date > end or (blocked_until and signal_date <= blocked_until):
            continue
        if not setups[signal_date].eligible:
            continue
        entry_index = signal_index + 1
        entry_date = dates[entry_index]
        if entry_date > end or (blocked_until and entry_date <= blocked_until):
            continue
        spot = float(soxl[entry_date]["raw_open"])
        contracts = history.contracts(entry_date, spot)
        entry_bars = history.bars([item.symbol for item in contracts], entry_date)
        selected = select_contract(contracts, entry_bars, spot, entry_date)
        if selected is None:
            continue
        contract, entry_bar, delta = selected
        exit_info = find_exit(entry_index, contract.expiration_date, dates, setups)
        if exit_info is None:
            continue
        exit_date, exit_reason = exit_info
        exit_bars = history.bars([contract.symbol], exit_date).get(contract.symbol, [])
        if not exit_bars:
            continue

        raw_ratio = float(soxl[exit_date]["raw_close"]) / spot
        adjusted_ratio = float(soxl[exit_date]["close"]) / float(soxl[entry_date]["open"])
        # shortcut: adjusted option deliverables around splits are excluded.
        if not 0.8 <= raw_ratio / adjusted_ratio <= 1.2:
            continue

        entry_price = max(float(entry_bar.get("o", entry_bar["c"])) * (1 - slippage), 0.01)
        exit_price = max(float(exit_bars[-1]["c"]) * (1 + slippage), 0.01)
        pnl = (entry_price - exit_price) * 100
        trades.append(CoveredCallTrade(
            symbol=contract.symbol,
            entry_date=entry_date,
            exit_date=exit_date,
            expiration=contract.expiration_date,
            strike=float(contract.strike_price),
            delta=delta,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            option_return=pnl / (spot * 100),
            stock_return=adjusted_ratio - 1,
            exit_reason=exit_reason,
        ))
        blocked_until = exit_date
    return trades


def account_comparison(trades: list[CoveredCallTrade], soxl_bars: list[dict]) -> dict:
    """Normalize both paths to the cost of 100 SOXL shares at the first entry."""
    bars = {bar["date"]: bar for bar in soxl_bars}
    first = bars[trades[0].entry_date]
    last = bars[trades[-1].exit_date]
    initial = float(first["raw_open"]) * 100
    soxl_factor = float(last["close"]) / float(first["open"])
    overlay_factor = 1.0
    for trade in trades:
        overlay_factor *= (
            1 + trade.stock_return + trade.option_return
        ) / (1 + trade.stock_return)
    return {
        "initial": initial,
        "initial_price": float(first["raw_open"]),
        "final_price": float(last["raw_close"]),
        "soxl_final": initial * soxl_factor,
        "fixed_call_final": initial * soxl_factor + sum(trade.pnl for trade in trades),
        "proportional_call_final": initial * soxl_factor * overlay_factor,
    }


def print_report(trades: list[CoveredCallTrade], slippage: float, soxl_bars: list[dict]) -> None:
    if not trades:
        print("No completed covered-call trades found.")
        return
    wins = [trade for trade in trades if trade.pnl > 0]
    option_returns = [trade.option_return for trade in trades]
    stock_equity = combined_equity = 1.0
    for trade in trades:
        stock_equity *= 1 + trade.stock_return
        combined_equity *= 1 + trade.stock_return + trade.option_return
    account = account_comparison(trades, soxl_bars)
    print(
        f"Period: {trades[0].entry_date} to {trades[-1].exit_date} | "
        f"completed trades: {len(trades)} | per-side option slippage: {slippage:.1%}"
    )
    print(f"Win rate: {len(wins) / len(trades):.1%}")
    print(f"Net option P&L (1 contract each): ${sum(trade.pnl for trade in trades):,.2f}")
    print(f"Average option overlay return/trade: {statistics.mean(option_returns):.2%}")
    print(f"Median option overlay return/trade: {statistics.median(option_returns):.2%}")
    print(f"Best / worst trade P&L: ${max(t.pnl for t in trades):,.2f} / ${min(t.pnl for t in trades):,.2f}")
    print(f"Compounded stock return during trade windows: {stock_equity - 1:.2%}")
    print(f"Compounded stock + call return during trade windows: {combined_equity - 1:.2%}")
    print(
        f"100-share account: start ${account['initial']:,.2f} at ${account['initial_price']:.2f}; "
        f"end SOXL price ${account['final_price']:.2f}"
    )
    print(
        f"Full-period final: SOXL only ${account['soxl_final']:,.2f}; "
        f"SOXL + fixed 1-call overlay ${account['fixed_call_final']:,.2f}; "
        f"difference ${account['fixed_call_final'] - account['soxl_final']:,.2f}"
    )
    print(
        f"Proportional reinvestment final: ${account['proportional_call_final']:,.2f}; "
        f"difference ${account['proportional_call_final'] - account['soxl_final']:,.2f}"
    )
    print("\nentry       exit        strike  delta   sell    buy      pnl  reason")
    for trade in trades:
        print(
            f"{trade.entry_date}  {trade.exit_date}  {trade.strike:>6.2f}  {trade.delta:>5.3f}  "
            f"{trade.entry_price:>6.2f}  {trade.exit_price:>6.2f}  "
            f"{trade.pnl:>7.2f}  {trade.exit_reason}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the SOXL covered-call overlay")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 2, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--slippage", type=float, default=0.05, help="per-side fraction of option price")
    args = parser.parse_args()
    if args.start >= args.end or not 0 <= args.slippage < 1:
        parser.error("start must precede end and slippage must be in [0, 1)")

    settings = get_settings()
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        parser.error("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
    warmup = args.start - timedelta(days=500)
    bars = {symbol: fetch_yahoo_daily(symbol, warmup, args.end) for symbol in ("QQQ", "SOXX", "SOXL")}
    trades = run_covered_call_backtest(
        bars["QQQ"], bars["SOXX"], bars["SOXL"],
        AlpacaOptionHistory(settings.alpaca_api_key, settings.alpaca_secret_key),
        args.start, args.end, args.slippage,
    )
    print_report(trades, args.slippage, bars["SOXL"])


if __name__ == "__main__":
    main()
