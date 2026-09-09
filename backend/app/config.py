from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory, regardless of the process's current working directory
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Used by Alembic (DDL) - an elevated/owner role.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ifcviewer"
    # Used by the running application - a non-superuser role, deliberately
    # distinct from database_url. PostgreSQL never enforces row-level
    # security against a superuser even with FORCE ROW LEVEL SECURITY, so if
    # this ever points at the same superuser as `database_url`, every
    # tenant-isolation guarantee in 0002_platform_foundation.py silently
    # stops applying - see alembic/versions/0003_app_role.py.
    app_database_url: str = "postgresql+psycopg://durianos_app:durianos_app@localhost:5544/durianos"
    cors_origins: str = "http://localhost:5173"
    data_dir: str = str(BACKEND_DIR / "data" / "models")

    # Platform foundation (Phase 3). HS256 with a shared secret is the pragmatic
    # v1 choice for self-hosted/pilot deployments (documented assumption A-05 /
    # SEC-001); federating to a real OIDC provider is future work, not a rewrite
    # of the token-verification call sites, since `deps.get_current_user` is the
    # only place that decodes a token.
    secret_key: str = "dev-only-insecure-secret-change-me"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 7

    # IoT Platform (Phase 7). Mosquitto is `allow_anonymous true` in dev
    # (infrastructure/mosquitto/mosquitto.conf) - per-device application-level
    # secrets (IotDevice.hashed_secret) are the auth boundary for now; real
    # broker-level mTLS/ACLs (SEC-006) are Phase 18 hardening work.
    mqtt_host: str = "mqtt"
    mqtt_port: int = 1883
    iot_offline_check_interval_seconds: int = 60
    iot_offline_timeout_seconds: int = 300

    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
