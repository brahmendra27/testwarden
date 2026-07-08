from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from the working directory (repo root) into the process environment
# so keys like ANTHROPIC_API_KEY / GITHUB_TOKEN are visible to the SDKs too.
load_dotenv(encoding="utf-8-sig")  # BOM-tolerant: Windows editors often add one


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLAKELENS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/flakelens.db"
    artifact_dir: Path = Path("./data/artifacts")
    max_artifact_bytes: int = 50 * 1024 * 1024
    # Runs still "running" after this many minutes are swept to "interrupted".
    interrupted_run_ttl_minutes: int = 120
    cors_origins: list[str] = ["http://localhost:5173"]
    # URL agents use to report generated-suite results back into this server.
    public_url: str = "http://localhost:8787"


settings = Settings()
