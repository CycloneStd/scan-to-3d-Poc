from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEBXR_", env_file=".env", extra="ignore")

    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://localhost:5432/scan3d"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: SecretStr
    jwt_issuer: str = "cyclone-scan-api"
    jwt_audience: str = "cyclone-webxr"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    verification_token_minutes: int = 60 * 24
    password_reset_token_minutes: int = 30
    frontend_base_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"
    email_from_email: str | None = None
    email_from_name: str | None = None
    resend_api_key: SecretStr | None = None
    storage_backend: str = "local"
    storage_local_root: Path = Path("./var/storage")
    storage_s3_bucket: str | None = None
    storage_s3_region: str | None = None
    storage_s3_endpoint_url: str | None = None
    storage_s3_public_endpoint_url: str | None = None
    storage_s3_access_key: SecretStr | None = None
    storage_s3_secret_key: SecretStr | None = None
    upload_max_bytes: int = 2 * 1024 * 1024 * 1024
    upload_max_files_per_scan: int = 200
    user_storage_quota_bytes: int = 20 * 1024 * 1024 * 1024
    max_active_jobs_per_user: int = 2
    upload_session_minutes: int = 60
    rate_limit_per_minute: int = 10
    worker_concurrency: int = 1
    pipeline_config_template: Path = Path("../../configs/house.yaml")
    pipeline_work_root: Path = Path("./var/pipeline")
    pipeline_track: str = "mesh"
    pipeline_timeout_seconds: int = 6 * 60 * 60
    pipeline_work_retention_days: int = 7
    artifact_download_ttl_seconds: int = 900

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        # Railway's Postgres connection variables use postgres:// or postgresql://.
        # This project installs psycopg v3, so make the driver explicit.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @field_validator("storage_backend")
    @classmethod
    def validate_storage_backend(cls, value: str) -> str:
        if value not in {"local", "s3"}:
            raise ValueError("storage_backend must be 'local' or 's3'")
        return value

    @field_validator("pipeline_track")
    @classmethod
    def validate_pipeline_track(cls, value: str) -> str:
        if value not in {"mesh", "splat"}:
            raise ValueError("pipeline_track must be 'mesh' or 'splat'")
        return value

    @model_validator(mode="after")
    def validate_secrets_and_storage(self):
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32:
            raise ValueError("WEBXR_JWT_SECRET must contain at least 32 characters")
        if self.environment == "production" and secret.lower() in {"change-me", "changeme", "secret"}:
            raise ValueError("Set a unique WEBXR_JWT_SECRET in production")
        if self.storage_backend == "s3" and not self.storage_s3_bucket:
            raise ValueError("WEBXR_STORAGE_S3_BUCKET is required when storage_backend=s3")
        if self.environment == "production" and not self.resend_api_key:
            raise ValueError("WEBXR_RESEND_API_KEY is required in production")
        if self.environment == "production" and not self.email_from_email:
            raise ValueError("WEBXR_EMAIL_FROM_EMAIL is required in production")
        if self.environment == "production" and "*" in self.origins:
            raise ValueError("Production CORS origins must be explicit, not '*'")
        if (self.environment == "production" and self.storage_backend == "s3"
                and self.storage_s3_endpoint_url and not self.storage_s3_public_endpoint_url):
            raise ValueError("Set a browser-reachable WEBXR_STORAGE_S3_PUBLIC_ENDPOINT_URL in production")
        return self

    @property
    def origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
