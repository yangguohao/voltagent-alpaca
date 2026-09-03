"""Application settings loaded from environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Alpaca
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True

    # Groq
    groq_api_key: str = ""
    groq_model_fast: str = "qwen/qwen3.8-27b"
    groq_model_smart: str = "openai/gpt-oss-120b"
    gpt_oss_max_tokens: int = 512

    # Orders
    order_type: str = "limit"  # limit | market
    limit_slippage_pct: float = 0.05
    quote_fallback_market: bool = True

    # LLM
    llm_review_fallback_approve: bool = True
    llm_selector_fallback_rules: bool = True

    # Regime gate
    regime_gate_enabled: bool = True
    regime_min_confidence: float = 0.5

    # Risk
    max_risk_per_trade: float = 0.02
    max_contracts_per_trade: int = 10
    max_portfolio_delta: float = 0.3
    max_daily_loss: float = 0.03
    max_positions: int = 5  # unique underlying symbols with open option exposure
    min_open_interest: int = 100
    max_bid_ask_spread_pct: float = 0.10
    min_dte: int = 7

    # Scheduler / daemon
    market_timezone: str = "America/New_York"
    intraday_interval_minutes: int = 30
    premarket_hour: int = 9
    premarket_minute: int = 25
    intraday_end_hour: int = 15
    intraday_end_minute: int = 30
    postmarket_hour: int = 15
    postmarket_minute: int = 50

    # Exit management (adaptive TP/SL scales with DTE)
    exit_enabled: bool = True
    exit_force_dte: int = 7
    exit_dte_scale_max: int = 35
    exit_tp_min: float = 0.15
    exit_tp_max: float = 0.40
    exit_sl_min: float = 0.20
    exit_sl_max: float = 0.40

    # State
    state_db_path: Path = Path("data/agent_state.db")

    # Watchlist for volatility scanning (comma-separated in env)
    watchlist: str = "SPY,QQQ,AAPL,MSFT,NVDA"

    @property
    def watchlist_symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.watchlist.split(",") if s.strip()]


def get_settings() -> Settings:
    return Settings()
