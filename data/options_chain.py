"""Options chain fetching and filtering."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from alpaca.trading.enums import AssetStatus, ContractType
from alpaca.trading.requests import GetOptionContractsRequest

from data.alpaca_client import AlpacaClients
from observability.logger import get_logger

logger = get_logger("options_chain")


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
        if mid is None or mid == 0 or self.bid is None or self.ask is None:
            return None
        return (self.ask - self.bid) / mid


@dataclass
class OptionChain:
    underlying: str
    underlying_price: float
    contracts: list[OptionContract] = field(default_factory=list)

    def filter_by_dte(self, min_dte: int, max_dte: int) -> list[OptionContract]:
        return [c for c in self.contracts if min_dte <= c.dte <= max_dte]

    def filter_by_type(self, contract_type: str) -> list[OptionContract]:
        return [c for c in self.contracts if c.contract_type == contract_type]


class OptionsChainService:
    def __init__(self, clients: AlpacaClients) -> None:
        self.clients = clients

    def fetch_chain(
        self,
        underlying: str,
        underlying_price: float,
        min_dte: int = 7,
        max_dte: int = 45,
    ) -> OptionChain:
        today = date.today()
        exp_gte = today + timedelta(days=min_dte)
        exp_lte = today + timedelta(days=max_dte)

        contracts: list[OptionContract] = []
        page_token: str | None = None

        while True:
            request = GetOptionContractsRequest(
                underlying_symbols=[underlying],
                status=AssetStatus.ACTIVE,
                expiration_date_gte=exp_gte,
                expiration_date_lte=exp_lte,
                limit=1000,
                page_token=page_token,
            )
            response = self.clients.trading.get_option_contracts(request)

            for c in response.option_contracts or []:
                exp = c.expiration_date
                if isinstance(exp, datetime):
                    exp = exp.date()
                ctype = "call" if c.type == ContractType.CALL else "put"
                contracts.append(OptionContract(
                    symbol=c.symbol,
                    underlying=underlying,
                    strike=float(c.strike_price),
                    expiration=exp,
                    contract_type=ctype,
                    open_interest=int(c.open_interest or 0),
                ))

            page_token = response.next_page_token
            if not page_token:
                break

        logger.info(
            "Fetched %d contracts for %s (DTE %d-%d, exp %s to %s)",
            len(contracts),
            underlying,
            min_dte,
            max_dte,
            exp_gte,
            exp_lte,
        )
        return OptionChain(underlying=underlying, underlying_price=underlying_price, contracts=contracts)
