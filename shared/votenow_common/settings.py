from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "votenow-service"
    service_port: int = 8500
    environment: str = "dev"

    postgres_dsn: str = "postgresql+psycopg://votenow:votenow@postgres:5432/votenow"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret: str = "votenow-dev-secret"
    encryption_key: str = "votenow-dev-encryption-key"
    captcha_shared_secret: str = "demo-captcha-secret"
    token_exp_minutes: int = 240
    export_root: str = "/tmp/votenow-exports"
    celery_task_always_eager: bool = True

    survey_service_url: str = "http://survey-service:8501"
    response_service_url: str = "http://response-service:8502"
    verification_service_url: str = "http://verification-service:8503"
    analytics_service_url: str = "http://analytics-service:8504"
    export_service_url: str = "http://export-service:8505"
    notification_service_url: str = "http://notification-service:8506"

    page_load_target_seconds: float = 2.0
    throughput_target_per_minute: int = 10000
    respondent_target: int = 1_000_000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
