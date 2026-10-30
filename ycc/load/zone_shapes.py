"""Loading of TLC zone centroids into DuckDB."""

import logging

import duckdb

from ycc.config import Settings

logger = logging.getLogger(__name__)


def load_zone_centroids(settings: Settings) -> int:
    """Replace ``raw.zone_centroids`` with the generated centroid parquet."""
    parquet_path = settings.work_dir / "zone_centroids.parquet"
    if not parquet_path.is_file():
        raise FileNotFoundError(
            f"Zone centroids are missing at {parquet_path}; run extract-zone-shapes first."
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
                CREATE OR REPLACE TABLE raw.zone_centroids AS
                SELECT
                    TRY_CAST(zone_id AS INTEGER) AS zone_id,
                    TRY_CAST(centroid_lat AS DOUBLE) AS centroid_lat,
                    TRY_CAST(centroid_lon AS DOUBLE) AS centroid_lon
                FROM read_parquet(?)
                """,
                [str(parquet_path)],
            )
            row_count = int(
                connection.execute("SELECT count(*) FROM raw.zone_centroids").fetchone()[0]
            )
            invalid_count = int(
                connection.execute(
                    """
                    SELECT count(*) FROM raw.zone_centroids
                    WHERE zone_id IS NULL
                       OR centroid_lat IS NULL
                       OR centroid_lon IS NULL
                       OR centroid_lat NOT BETWEEN -90 AND 90
                       OR centroid_lon NOT BETWEEN -180 AND 180
                    """
                ).fetchone()[0]
            )
            if not row_count or invalid_count:
                raise ValueError(
                    f"Invalid zone centroids: {row_count} rows, {invalid_count} invalid."
                )
    finally:
        connection.close()

    logger.info("zones.shapes.load.completed", extra={"row_count": row_count})
    return row_count
