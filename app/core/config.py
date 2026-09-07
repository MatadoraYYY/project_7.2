"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_debug: bool = False
    app_secret_key: str = "insecure-default-secret-change-me"

    database_url: str = "sqlite:///./data/promo_engine.db"
    allowed_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 120

    elasticity_min: float = 0.3
    elasticity_max: float = 2.0
    vip_ltv_threshold: float = 50_000.0
    vip_min_orders: int = 10
    dormant_days_threshold: int = 30

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
