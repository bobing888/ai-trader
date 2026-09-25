"""配置模块 — pydantic-settings 加载环境变量"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AI_TRADER_",
        extra="ignore",
    )

    app_name: str = "ai-trader"
    app_version: str = "0.1.0"
    debug: bool = False

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # CORS: 接受 JSON array 或逗号分隔字符串
    cors_origins_raw: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://localhost,http://127.0.0.1,http://154.219.111.145"

    @property
    def cors_origins(self) -> list[str]:
        raw = self.cors_origins_raw.strip()
        if raw.startswith("["):
            import json
            try:
                return json.loads(raw)
            except Exception:
                pass
        return [s.strip() for s in raw.split(",") if s.strip()]

    freqtrade_db_path: Path = Path("./data/freqtrade/tradesv3.sqlite")
    freqtrade_user_data_dir: Path = Path("./data/freqtrade/user_data")

    # Strategy 持久化（SQLite）
    strategies_db_path: str = "strategies.db"
    github_sync_interval_hours: int = 6
    github_sync_enabled: bool = True
    github_search_query: str = "crypto trading strategy language:python"
    github_sync_limit: int = 10

    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True
    binance_base_url: str = "https://api.binance.com"

    # 数据源：mock = 本地生成，binance = 真实公开 API
    use_mock_data: bool = False

    # Redis 缓存（避免 Binance 公开 API 限流）
    redis_url: str = "redis://127.0.0.1:6379/0"
    cache_ttl_klines: int = 30
    cache_ttl_ticker: int = 5
    cache_ttl_signals: int = 60

    recommendation_refresh_interval: int = 60
    regime_retrain_interval_days: int = 90


settings = Settings()
