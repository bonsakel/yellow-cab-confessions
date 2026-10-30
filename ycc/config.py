"""Environment-driven settings for the Yellow Cab Confessions pipeline."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pipeline settings loaded from YCC-prefixed environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="YCC_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    year: int = 2024
    demo_months: str = "2024-01"
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "ycc-raw"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    duckdb_path: Path = Path("warehouse/ycc.duckdb")
    duckdb_memory_limit: str = "6GB"
    duckdb_threads: int = Field(default=4, ge=1)
    work_dir: Path = Path("warehouse")
    dbt_project_dir: Path = Path("dbt")

    @property
    def download_dir(self) -> Path:
        """Return the directory used for cached raw source files."""
        return self.work_dir / "downloads"
