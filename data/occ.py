"""OCC option symbol parsing utilities."""

import re
from datetime import date

_OCC_SYMBOL = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d+)$")


def underlying_symbol(option_symbol: str) -> str:
    match = _OCC_SYMBOL.match(option_symbol)
    return match.group(1) if match else option_symbol


def option_expiration(option_symbol: str) -> date | None:
    match = _OCC_SYMBOL.match(option_symbol)
    if match is None:
        return None
    yymmdd = match.group(2)
    return date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))


def option_dte(option_symbol: str, today: date | None = None) -> int | None:
    expiration = option_expiration(option_symbol)
    if expiration is None:
        return None
    ref = today or date.today()
    return (expiration - ref).days
