"""Loading of the TLC taxi zone lookup into the raw DuckDB schema."""

import logging
from pathlib import Path

import duckdb

from ycc.config import Settings

logger = logging.getLogger(__name__)


def load_zone_lookup(
    settings: Settings,
    csv_path: Path | None = None,
) -> int:
    """Load the TLC zone lookup CSV into ``raw.taxi_zone_lookup``."""
    source_path = csv_path or settings.download_dir / "taxi_zone_lookup.csv"
    if not source_path.is_file():
        raise FileNotFoundError(
            f"TLC zone lookup file is missing at {source_path}; run extract-zones first."
        )

    settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(
        str(settings.duckdb_path),
        config={
            "memory_limit": settings.duckdb_memory_limit,
            "threads": settings.duckdb_threads,
        },
    )
    try:
        with connection:
            connection.execute("CREATE SCHEMA IF NOT EXISTS raw")
            connection.execute(
                """
                CREATE OR REPLACE TABLE raw.taxi_zone_lookup AS
                SELECT
                    TRY_CAST(LocationID AS INTEGER) AS location_id,
                    NULLIF(trim(Borough), '') AS borough,
                    NULLIF(trim(Zone), '') AS zone,
                    NULLIF(trim(service_zone), '') AS service_zone
                FROM read_csv(?, header = true, all_varchar = true)
                """,
                [str(source_path)],
            )
            row_count = int(
                connection.execute("SELECT count(*) FROM raw.taxi_zone_lookup").fetchone()[0]
            )
            invalid_count = int(
                connection.execute(
                    "SELECT count(*) FROM raw.taxi_zone_lookup WHERE location_id IS NULL"
                ).fetchone()[0]
            )
            if row_count == 0 or invalid_count:
                raise ValueError(
                    f"Invalid TLC zone lookup: {row_count} rows, {invalid_count} invalid IDs."
                )
    finally:
        connection.close()

    logger.info("zones.load.completed", extra={"row_count": row_count})
    return row_count
