#!/usr/bin/env python3
"""Main entry point for the Alpaca volatility options trading agent."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings
from core.agent import TradingAgent
from core.scheduler import create_scheduler, run_daemon
from observability.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpaca Volatility Options Trading Agent")
    parser.add_argument(
        "--mode",
        choices=["once", "schedule", "daemon", "health"],
        default="once",
        help="daemon: sleep outside market hours; schedule: legacy APScheduler cron",
    )
    parser.add_argument("--phase", choices=["premarket", "intraday", "postmarket", "exit"], default="intraday")
    parser.add_argument("--live", action="store_true", help="Submit real orders (default: dry-run)")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    settings = get_settings()
    dry_run = not args.live

    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        print("ERROR: Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env")
        sys.exit(1)

    agent = TradingAgent(settings=settings, dry_run=dry_run)

    if args.mode == "health":
        print(f"Account status: {agent.health_check()}")
        return

    if args.mode == "daemon":
        print(f"Starting daemon (timezone={settings.market_timezone}, dry_run={dry_run})")
        run_daemon(agent, settings)
        return

    if args.mode == "schedule":
        scheduler = create_scheduler(agent, settings)
        print(f"Starting legacy scheduler (timezone={settings.market_timezone}, dry_run={dry_run})")
        scheduler.start()
        return

    asyncio.run(agent.run_once(phase=args.phase))


if __name__ == "__main__":
    main()
