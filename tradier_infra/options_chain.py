"""Tradier live option-chain adapter used by the trading strategies."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from tradier_infra.client import TradierClient

logger = logging.getLogger("tradier_infra.options_chain")


def _items(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _float(value: Any) -> float | None:
    return None if value in (None, "") else float(value)


@dataclass
class OptionContract:
    symbol: str
    underlying: str
    strike: float
    expiration: date
    contract_type: str
    open_interest: int = 0
    implied_volatility: float | None = None
    delta: float | None = None
    bid: float | None = None
    ask: float | None = None

    @property
    def dte(self) -> int:
        return (self.expiration - date.today()).days

    @property
    def mid_price(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> float | None:
        mid = self.mid_price
        if not mid or self.bid is None or self.ask is None:
            return None
        return (self.ask - self.bid) / mid


@dataclass
class OptionChain:
    underlying: str
    underlying_price: float
    contracts: list[OptionContract] = field(default_factory=list)


class OptionsChainService:
    def __init__(self, client: TradierClient) -> None:
        self.client = client

    def fetch_chain(
        self,
        underlying: str,
        underlying_price: float,
        min_dte: int = 7,
        max_dte: int = 45,
        include_snapshots: bool = False,
    ) -> OptionChain:
        del include_snapshots  # Tradier chains already include live quotes and requested Greeks.
        today = date.today()
        minimum = today + timedelta(days=min_dte)
        maximum = today + timedelta(days=max_dte)
        payload = self.client.get(
            "/markets/options/expirations",
            {"symbol": underlying, "includeAllRoots": "false"},
        )
        raw_dates = (payload.get("expirations") or {}).get("date")
        expirations = [
            parsed
            for value in ([] if raw_dates is None else raw_dates if isinstance(raw_dates, list) else [raw_dates])
            for parsed in [datetime.strptime(str(value), "%Y-%m-%d").date()]
            if minimum <= parsed <= maximum
        ]

        contracts: list[OptionContract] = []
        for expiration in expirations:
            response = self.client.get(
                "/markets/options/chains",
                {"symbol": underlying, "expiration": expiration.isoformat(), "greeks": "true"},
            )
            for option in _items((response.get("options") or {}).get("option")):
                option_type = str(option.get("option_type") or option.get("type") or "").lower()
                if option_type not in {"call", "put"}:
                    continue
                greeks = option.get("greeks") or {}
                contracts.append(OptionContract(
                    symbol=str(option["symbol"]).replace(" ", ""),
                    underlying=underlying,
                    strike=float(option["strike"]),
                    expiration=expiration,
                    contract_type=option_type,
                    open_interest=int(option.get("open_interest") or 0),
                    implied_volatility=_float(
                        greeks.get("mid_iv") if greeks.get("mid_iv") is not None else greeks.get("smv_vol")
                    ),
                    delta=_float(greeks.get("delta")),
                    bid=_float(option.get("bid")),
                    ask=_float(option.get("ask")),
                ))

        logger.info(
            "Fetched %d Tradier contracts for %s (DTE %d-%d)",
            len(contracts), underlying, min_dte, max_dte,
        )
        return OptionChain(underlying, underlying_price, contracts)
