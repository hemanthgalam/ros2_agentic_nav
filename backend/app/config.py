"""Central runtime configuration, loaded from environment / .env.

Nothing secret is hardcoded: GEMINI_API_KEY must come from the environment.
The datum here is only the startup default — the live value lives in
nav_client's DatumStore and can be recalibrated at runtime via /api/datum.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    rosbridge_host: str = "localhost"
    rosbridge_port: int = 9090

    datum_lat0: float = 37.4275
    datum_lon0: float = -122.1697
    datum_alt0: float = 0.0
    datum_heading_offset_deg: float = 0.0

    geofence_max_radius_m: float = 250.0

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
