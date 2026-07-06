from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TESTWARDEN_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/testwarden.db"
    artifact_dir: Path = Path("./data/artifacts")
    max_artifact_bytes: int = 50 * 1024 * 1024
    # Runs still "running" after this many minutes are swept to "interrupted".
    interrupted_run_ttl_minutes: int = 120
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
