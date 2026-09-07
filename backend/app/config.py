from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory, regardless of the process's current working directory
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ifcviewer"
    cors_origins: str = "http://localhost:5173"
    data_dir: str = str(BACKEND_DIR / "data" / "models")

    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
