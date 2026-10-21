"""Small Tradier REST client for live market data."""

import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TradierSettings(Protocol):
    tradier_api_key: str


class TradierAPIError(RuntimeError):
    pass


class TradierClient:
    def __init__(self, api_key: str, base_url: str = "https://api.tradier.com/v1") -> None:
        if not api_key:
            raise ValueError("TRADIER_API_KEY is required when OPTION_DATA_PROVIDER=tradier")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            detail = exc.read(500).decode("utf-8", errors="replace")
            raise TradierAPIError(f"Tradier returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise TradierAPIError(f"Tradier request failed: {exc}") from exc


def create_client(settings: TradierSettings) -> TradierClient:
    return TradierClient(settings.tradier_api_key)
