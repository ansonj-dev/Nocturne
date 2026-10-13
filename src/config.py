"""NOCTURNE — Central configuration using pydantic-settings."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "NOCTURNE"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # --- Bitget API ---
    bitget_api_key: str = Field(default="", description="Bitget REST API key")
    bitget_api_secret: str = Field(default="", description="Bitget REST API secret")
    bitget_api_passphrase: str = Field(default="", description="Bitget API passphrase")
    bitget_use_sandbox: bool = Field(default=True, description="Use Bitget sandbox/demo environment")

    # --- LLM ---
    openai_api_key: str = Field(default="", description="OpenAI API key for GPT models")
    anthropic_api_key: str = Field(default="", description="Anthropic API key for Claude models")
    llm_provider: str = Field(default="openai", description="LLM provider: openai | anthropic")
    llm_model: str = Field(default="gpt-4o-mini", description="Model name to use")

    # --- Database ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///nocturne.db",
        description="Async SQLAlchemy database URL",
    )

    # --- Redis (optional caching) ---
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_enabled: bool = False

    # --- Risk limits (global defaults, overridden per-symbol) ---
    max_spread_multiplier: float = Field(
        default=2.0,
        description="Max spread vs 30-day median before STORM is triggered",
    )
    max_volatility_multiplier: float = Field(
        default=2.5,
        description="Max realized-vol vs baseline before STORM is triggered",
    )
    min_depth_ratio: float = Field(
        default=0.4,
        description="Min order-book depth ratio vs normal before STORM is triggered",
    )
    max_position_pct: float = Field(
        default=0.05,
        description="Max position size as fraction of account equity (5%)",
    )
    max_daily_loss_pct: float = Field(
        default=0.02,
        description="Daily loss limit as fraction of account equity (2%)",
    )
    max_per_trade_risk_pct: float = Field(
        default=0.005,
        description="Max risk per trade as fraction of equity (0.5%)",
    )
    max_consecutive_losses: int = Field(default=3)

    # --- Liquidity Weather Score weights ---
    weight_spread: float = 0.30
    weight_depth: float = 0.25
    weight_volatility: float = 0.25
    weight_lead_lag: float = 0.10
    weight_event: float = 0.10

    # --- Score thresholds ---
    clear_threshold: float = 70.0   # >= CLEAR
    cloudy_threshold: float = 45.0  # >= CLOUDY (< clear)
    storm_threshold: float = 20.0   # >= STORM  (< cloudy)
    # < storm_threshold => BLACKOUT

    # --- Scheduler ---
    weather_poll_seconds: int = Field(default=30, description="How often the weather engine refreshes")
    history_window_days: int = Field(default=30, description="Rolling window for spread/vol baselines")


settings = Settings()
