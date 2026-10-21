"""Historical backtest for the V27 underlying allocation rules."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from soxl_strategy.strategy import evaluate_underlying_timing


@dataclass(frozen=True)
class BacktestResult:
    start: date
    end: date
    equity: list[float]
    daily_returns: list[float]
    state_counts: Counter
    rebalances: int


def fetch_yahoo_daily(symbol: str, start: date, end: date) -> list[dict]:
    """Download split/dividend-adjusted daily bars from Yahoo's chart endpoint."""
    params = urlencode({
        "period1": int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp()),
        "period2": int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp()),
        "interval": "1d",
        "events": "history",
    })
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == 2:
                raise RuntimeError(f"unable to download {symbol}: {exc}") from exc
            time.sleep(2 ** attempt)
    else:  # pragma: no cover
        raise RuntimeError(f"unable to download {symbol}: {last_error}")

    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose", quote["close"])
    bars: list[dict] = []
    for index, timestamp in enumerate(result.get("timestamp", [])):
        raw_close = quote["close"][index]
        adj_close = adjusted[index]
        raw_open = quote["open"][index]
        if raw_close is None or adj_close is None or raw_open is None:
            continue
        adjustment = adj_close / raw_close
        bars.append({
            "date": datetime.fromtimestamp(timestamp, timezone.utc).date(),
            "open": float(raw_open) * adjustment,
            "close": float(adj_close),
            "raw_open": float(raw_open),
            "raw_close": float(raw_close),
            "volume": float(quote["volume"][index] or 0),
        })
    return bars


def run_backtest(
    qqq_bars: list[dict],
    soxx_bars: list[dict],
    soxl_bars: list[dict],
    cost_bps: float = 5.0,
) -> BacktestResult:
    qqq_by_date = {bar["date"]: bar for bar in qqq_bars}
    soxx_by_date = {bar["date"]: bar for bar in soxx_bars}
    soxl_by_date = {bar["date"]: bar for bar in soxl_bars}
    dates = sorted(set(qqq_by_date) & set(soxx_by_date) & set(soxl_by_date))
    qqq_history: list[dict] = []
    soxx_history: list[dict] = []
    sorted_qqq = sorted(qqq_bars, key=lambda bar: bar["date"])
    sorted_soxx = sorted(soxx_bars, key=lambda bar: bar["date"])
    qqq_index = soxx_index = 0
    usable: list[tuple[date, object]] = []

    for current in dates:
        while qqq_index < len(sorted_qqq) and sorted_qqq[qqq_index]["date"] <= current:
            qqq_history.append(sorted_qqq[qqq_index])
            qqq_index += 1
        while soxx_index < len(sorted_soxx) and sorted_soxx[soxx_index]["date"] <= current:
            soxx_history.append(sorted_soxx[soxx_index])
            soxx_index += 1
        decision = evaluate_underlying_timing(qqq_history, soxx_history)
        if decision.state != "insufficient_data":
            usable.append((current, decision))

    if len(usable) < 2:
        raise ValueError("not enough aligned history for the 252-session warm-up")

    equity = [1.0]
    daily_returns: list[float] = []
    state_counts: Counter = Counter()
    previous_target: tuple[str | None, float] = (None, 0.0)
    rebalances = 0

    for index in range(len(usable) - 1):
        current, decision = usable[index]
        next_date = usable[index + 1][0]
        target = (decision.target_symbol, decision.target_allocation)
        state_counts[decision.state] += 1

        if target == previous_target:
            turnover = 0.0
        elif target[0] == previous_target[0]:
            turnover = abs(target[1] - previous_target[1])
        else:
            turnover = target[1] + previous_target[1]
        if turnover:
            rebalances += 1

        asset_return = 0.0
        if decision.target_symbol == "SOXL":
            asset_return = soxl_by_date[next_date]["close"] / soxl_by_date[current]["close"] - 1
        elif decision.target_symbol == "SOXX":
            asset_return = soxx_by_date[next_date]["close"] / soxx_by_date[current]["close"] - 1

        net_return = (1 - turnover * cost_bps / 10_000) * (
            1 + decision.target_allocation * asset_return
        ) - 1
        daily_returns.append(net_return)
        equity.append(equity[-1] * (1 + net_return))
        previous_target = target

    return BacktestResult(
        start=usable[0][0],
        end=usable[-1][0],
        equity=equity,
        daily_returns=daily_returns,
        state_counts=state_counts,
        rebalances=rebalances,
    )


def performance(equity: list[float], daily_returns: list[float], start: date, end: date) -> dict:
    years = max((end - start).days / 365.25, 1 / 365.25)
    peak = equity[0]
    max_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1)
    cagr = equity[-1] ** (1 / years) - 1
    volatility = statistics.stdev(daily_returns) * math.sqrt(252) if len(daily_returns) > 1 else 0.0
    return {
        "total_return": equity[-1] - 1,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "calmar": cagr / abs(max_drawdown) if max_drawdown else math.inf,
        "volatility": volatility,
    }


def buy_and_hold(bars: list[dict], start: date, end: date) -> dict:
    selected = [bar for bar in bars if start <= bar["date"] <= end]
    daily_returns = [
        selected[index]["close"] / selected[index - 1]["close"] - 1
        for index in range(1, len(selected))
    ]
    equity = [1.0]
    for value in daily_returns:
        equity.append(equity[-1] * (1 + value))
    return performance(equity, daily_returns, selected[0]["date"], selected[-1]["date"])


def _percent(value: float) -> str:
    return f"{value * 100:,.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest V27 underlying allocation (options excluded)")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2009, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--cost-bps", type=float, default=5.0)
    args = parser.parse_args()
    if args.start >= args.end or args.cost_bps < 0:
        parser.error("start must precede end and cost-bps must be non-negative")

    bars = {
        symbol: fetch_yahoo_daily(symbol, args.start, args.end)
        for symbol in ("QQQ", "SOXX", "SOXL")
    }
    result = run_backtest(bars["QQQ"], bars["SOXX"], bars["SOXL"], args.cost_bps)
    rows = {
        "V27 underlying": performance(result.equity, result.daily_returns, result.start, result.end),
        "SOXL buy/hold": buy_and_hold(bars["SOXL"], result.start, result.end),
        "SOXX buy/hold": buy_and_hold(bars["SOXX"], result.start, result.end),
    }

    print(f"Period: {result.start} to {result.end} | cost: {args.cost_bps:g} bps | options: excluded")
    print(f"{'Strategy':<18} {'Total':>12} {'CAGR':>10} {'Max DD':>10} {'Calmar':>9} {'Volatility':>12}")
    for name, metrics in rows.items():
        print(
            f"{name:<18} {_percent(metrics['total_return']):>12} {_percent(metrics['cagr']):>10} "
            f"{_percent(metrics['max_drawdown']):>10} {metrics['calmar']:>9.2f} "
            f"{_percent(metrics['volatility']):>12}"
        )
    print(f"Rebalances: {result.rebalances}")
    print("State sessions: " + ", ".join(f"{key}={value}" for key, value in result.state_counts.most_common()))


if __name__ == "__main__":
    main()
