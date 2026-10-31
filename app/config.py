from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    allowed_origin: str = "http://localhost:5173"
    search_time_limit_ms: int = Field(10000, ge=0)
    fallback_weights: list[float] = Field(default_factory=lambda: [1.5, 5])
    trace_limit: int = Field(500, ge=0)
    max_csv_bytes: int = Field(2_000_000, gt=0)

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origin.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
