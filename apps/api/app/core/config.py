from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./tinkerlab.db"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    app_name: str = "TinkerLab API"
    api_version: str = "0.11.1"
    environment: str = Field(default="development")
    materials_project_api_key: str | None = None
    epa_comptox_api_key: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
