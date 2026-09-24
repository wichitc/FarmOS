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

    # Hardening (Phase 18, SEC-007). Redis-backed so limits are shared
    # across workers/restarts, not just per-process memory. Disabled via
    # `RATE_LIMIT_ENABLED=false` for test/CI runs, where every request
    # shares one fake client identity (Starlette's TestClient) and would
    # otherwise trip the limiter almost immediately - see
    # `core/rate_limit.py`'s module docstring.
    rate_limit_enabled: bool = True
    redis_url: str = "redis://localhost:6380/0"
    rate_limit_default_per_minute: int = 300
    rate_limit_login_per_minute: int = 10
    rate_limit_public_per_minute: int = 30

    # Subscription limit enforcement (master-prompt integration, Phase 29).
    # Same "disabled for the whole suite, flipped on by individual tests
    # that need it" pattern as `rate_limit_enabled` (Phase 18) - most of
    # the regression suite creates 2+ farms per tenant to exercise
    # cross-farm ABAC, which the free plan's farm_limit=1 would otherwise
    # block on every one of those tests, not just the ones actually
    # testing enforcement.
    subscription_enforcement_enabled: bool = True

    # Knowledge Base real semantic search (Phase 28). ADR-011's Ollama-
    # local default, applied to embeddings the same way it already
    # applies to chat - `knowledge/embeddings.py::OllamaEmbeddingProvider`
    # calls this directly; there is no OpenAI-compatible embeddings
    # provider wired yet (same "one default, seam for the other" shape
    # ADR-011 itself describes, not fully built out on both sides).
    ollama_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"

    # SLA breach watcher (master-prompt integration, Phase 33) - same
    # polling-loop shape as `iot_offline_check_interval_seconds` (Phase
    # 7), just for support tickets' `sla_due_at` instead of device
    # last-seen timestamps.
    sla_watch_interval_seconds: int = 300

    # Trial expiry watcher (master-prompt integration, Phase 34) - same
    # polling-loop shape as `sla_watch_interval_seconds`, for
    # `Subscription.trial_ends_at` instead of ticket SLAs.
    trial_watch_interval_seconds: int = 3600

    # File attachments (master-prompt integration, Phase 39, SEC-005) -
    # MinIO was already provisioned as infrastructure since Phase 3
    # (DEP-001) but nothing used it until now; no new vendor decision
    # needed, it's the vendor this platform already picked.
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "durianos"
    minio_secret_key: str = "durianos123"
    minio_secure: bool = False
    minio_attachments_bucket: str = "attachments"
    max_attachment_size_bytes: int = 10 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
