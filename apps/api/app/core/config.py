from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./tinkerlab.db"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    app_name: str = "TinkerLab API"
    api_version: str = "0.12.2.3"
    environment: str = Field(default="development")
    # Server-side only. Never expose the Materials Project key through NEXT_PUBLIC_* variables.
    materials_project_api_key: str | None = None
    materials_project_api_base_url: str = "https://api.materialsproject.org"
    epa_comptox_api_key: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
