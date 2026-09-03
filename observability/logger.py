"""Structured logging setup."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    return logging.getLogger("alpaca_agent")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"alpaca_agent.{name}")
