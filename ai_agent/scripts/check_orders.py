#!/usr/bin/env python3
"""Check Alpaca paper account orders and positions from the terminal."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

from ai_agent.config.settings import get_settings
from ai_agent.core.state import StateStore
from alpaca_infra.clients import create_clients
from alpaca_infra.metrics import MetricsService


def _fmt_money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def print_account(clients) -> None:
    account = clients.trading.get_account()
    metrics = MetricsService(clients).snapshot()
    print("=== Account ===")
    print(f"Status:        {account.status}")
    print(f"Equity:        {_fmt_money(account.equity)}")
    print(f"Cash:          {_fmt_money(account.cash)}")
    print(f"Buying Power:  {_fmt_money(account.buying_power)}")
    print(f"Daily P&L:     {_fmt_money(float(account.equity) - float(account.last_equity or account.equity))}")
    print(f"Open Trades:   {metrics.position_count} underlyings / {metrics.leg_count} legs (max {get_settings().max_positions})")
    print(f"Paper:         {get_settings().alpaca_paper}")


def print_positions(clients) -> None:
    positions = clients.trading.get_all_positions()
    print("\n=== Positions ===")
    if not positions:
        print("(none)")
        return

    print(f"{'Symbol':<24} {'Qty':>6} {'Side':<6} {'Avg Entry':>12} {'Mkt Value':>12} {'Unrealized':>12}")
    print("-" * 78)
    for p in positions:
        side = "long" if float(p.qty) > 0 else "short"
        print(
            f"{p.symbol:<24} {p.qty:>6} {side:<6} "
            f"{_fmt_money(p.avg_entry_price):>12} "
            f"{_fmt_money(p.market_value):>12} "
            f"{_fmt_money(p.unrealized_pl):>12}"
        )


def print_orders(clients, limit: int, status: str | None) -> None:
    kwargs: dict = {"limit": limit}
    if status:
        kwargs["status"] = QueryOrderStatus(status)

    orders = clients.trading.get_orders(filter=GetOrdersRequest(**kwargs))
    print(f"\n=== Orders (latest {limit}{f', status={status}' if status else ''}) ===")
    if not orders:
        print("(none)")
        return

    print(f"{'ID':<38} {'Symbol':<8} {'Type':<8} {'Status':<12} {'Limit':>10} {'Qty':>5} {'Filled':>6}")
    print("-" * 95)
    for o in orders:
        symbol = o.symbol or "MLEG"
        limit_price = _fmt_money(o.limit_price) if o.limit_price is not None else "-"
        filled = o.filled_qty or 0
        print(
            f"{str(o.id):<38} {symbol:<8} {str(o.order_type or '-'):<8} "
            f"{str(o.status):<12} {limit_price:>10} {o.qty:>5} {filled:>6}"
        )


def print_local_trades(state: StateStore, limit: int) -> None:
    print(f"\n=== Local Trade Log (latest {limit}) ===")
    with state._connect() as conn:
        rows = conn.execute(
            "SELECT created_at, symbol, strategy, status, client_order_id, payload FROM trade_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    if not rows:
        print("(none)")
        return

    for row in rows:
        print(f"{row['created_at']} | {row['symbol']:<6} | {row['strategy']:<12} | {row['status']:<10} | {row['client_order_id']}")


def print_regime(state: StateStore) -> None:
    regime = state.get("current_regime")
    print("\n=== Current Regime ===")
    if not regime:
        print("(not set — run premarket first)")
        return
    print(f"Regime:      {regime.get('regime')}")
    print(f"Confidence:  {float(regime.get('confidence', 0)) * 100:.0f}%")
    print(f"Notes:       {regime.get('notes', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Alpaca orders, positions, and local agent state")
    parser.add_argument("--orders", type=int, default=10, help="Number of recent orders to show")
    parser.add_argument("--trades", type=int, default=10, help="Number of local trade log entries")
    parser.add_argument("--status", choices=["open", "closed", "all"], default="all", help="Order filter")
    parser.add_argument("--no-account", action="store_true")
    parser.add_argument("--no-positions", action="store_true")
    parser.add_argument("--no-orders", action="store_true")
    parser.add_argument("--no-trades", action="store_true")
    parser.add_argument("--no-regime", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.alpaca_api_key:
        print("ERROR: ALPACA_API_KEY not set in .env")
        sys.exit(1)

    clients = create_clients(settings)
    state = StateStore(settings.state_db_path)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"Alpaca Agent Status @ {now}")

    if not args.no_account:
        print_account(clients)
    if not args.no_positions:
        print_positions(clients)
    if not args.no_orders:
        status = None if args.status == "all" else args.status
        print_orders(clients, args.orders, status)
    if not args.no_trades:
        print_local_trades(state, args.trades)
    if not args.no_regime:
        print_regime(state)


if __name__ == "__main__":
    main()
