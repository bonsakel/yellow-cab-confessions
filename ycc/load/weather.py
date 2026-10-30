"""Loading of normalized hourly weather records into DuckDB."""

import logging

import duckdb

from ycc.config import Settings

logger = logging.getLogger(__name__)


def load_weather_year(settings: Settings, year: int | None = None) -> int:
    """Replace ``raw.weather_hourly`` with the cached local-hour parquet."""
    selected_year = year if year is not None else settings.year
    parquet_path = settings.download_dir / f"weather_hourly_{selected_year}.parquet"
    if not parquet_path.is_file():
        raise FileNotFoundError(
            f"Weather parquet is missing at {parquet_path}; run extract-weather first."
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
                CREATE OR REPLACE TABLE raw.weather_hourly AS
                SELECT
                    CAST(local_hour AS TIMESTAMP) AS local_hour,
                    TRY_CAST(temperature_2m AS DOUBLE) AS temperature_2m,
                    TRY_CAST(precipitation AS DOUBLE) AS precipitation,
                    TRY_CAST(rain AS DOUBLE) AS rain,
                    TRY_CAST(snowfall AS DOUBLE) AS snowfall,
                    TRY_CAST(wind_speed_10m AS DOUBLE) AS wind_speed_10m,
                    TRY_CAST(weather_code AS INTEGER) AS weather_code
                FROM read_parquet(?)
                """,
                [str(parquet_path)],
            )
            row_count = int(
                connection.execute("SELECT count(*) FROM raw.weather_hourly").fetchone()[0]
            )
            duplicate_hours = int(
                connection.execute(
                    """
                    SELECT count(*) - count(DISTINCT local_hour)
                    FROM raw.weather_hourly
                    """
                ).fetchone()[0]
            )
            expected_hours = 8784 if _is_leap_year(selected_year) else 8760
            if row_count != expected_hours or duplicate_hours:
                raise ValueError(
                    f"Invalid {selected_year} weather coverage: {row_count} rows, "
                    f"{duplicate_hours} duplicate hours; expected {expected_hours}."
                )
    finally:
        connection.close()

    logger.info(
        "weather.load.completed",
        extra={"year": selected_year, "row_count": row_count},
    )
    return row_count


def _is_leap_year(year: int) -> bool:
    """Return whether a Gregorian calendar year contains February 29."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
