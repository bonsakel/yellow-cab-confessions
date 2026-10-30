"""Export dbt mart tables as small, compressed app-facing parquet files."""

import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

from ycc.config import Settings

logger = logging.getLogger(__name__)

MARTS = (
    "mart_rain_tax",
    "mart_airport_runs",
    "mart_zone_pairs",
    "mart_zone_summary",
    "mart_blooper_counts",
    "mart_blooper_examples",
    "mart_night_city",
)


@dataclass(frozen=True)
class ExportSummary:
    """Files and sizes written by one export run."""

    files: dict[str, int]
    total_bytes: int
    confessions: dict[str, object]


def _number(value: object) -> float | None:
    """Normalize a DuckDB numeric result to finite JSON-safe float."""
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _confessions(connection: duckdb.DuckDBPyConnection, year: int) -> dict[str, object]:
    totals = connection.execute(
        """
        SELECT
            (SELECT count(*) FROM core.fct_trips) AS clean_trips,
            (SELECT count(*) FROM quarantine.quarantine_trips) AS quarantined_trips,
            (SELECT sum(trip_distance) FROM core.fct_trips) AS total_miles,
            (
                SELECT sum(tip_amount)
                FROM core.fct_trips
                WHERE payment_type = 1
            ) AS credit_card_tips,
            (
                SELECT count(*)
                FROM core.fct_trips
                WHERE is_unknown_zone
            ) AS unknown_zone_trips
        """
    ).fetchone()
    weather = connection.execute(
        """
        SELECT
            weather_bucket,
            sum(trips) AS total_trips,
            sum(observed_days) AS observed_days,
            sum(trips) / nullif(sum(observed_days), 0) AS average_daily_trips,
            sum(dry_avg_trips_per_day * observed_days) AS expected_dry_trips,
            sum(avg_tip_pct * credit_card_tip_trips) AS tip_pct_total,
            sum(credit_card_tip_trips) AS credit_card_tip_trips
        FROM marts.mart_rain_tax
        WHERE weather_bucket IN ('dry', 'light_rain', 'moderate_rain', 'heavy_rain', 'snow')
        GROUP BY weather_bucket
        """
    ).fetchall()
    weather_stats = {
        row[0]: {
            "average_daily_trips": _number(row[3]),
            "average_credit_card_tip_pct": _number(
                row[5] / row[6] if row[5] is not None and row[6] else None
            ),
        }
        for row in weather
    }

    rain_buckets = [
        row for row in weather if row[0] in {"light_rain", "moderate_rain", "heavy_rain"}
    ]
    rain_trips = sum(row[1] for row in rain_buckets)
    expected_dry_trips = sum(row[4] or 0 for row in rain_buckets)
    rain_tip_pct_total = sum(row[5] or 0 for row in rain_buckets)
    rain_credit_card_tip_trips = sum(row[6] or 0 for row in rain_buckets)
    dry_stats = weather_stats.get("dry", {})
    dry_tip_pct = dry_stats.get("average_credit_card_tip_pct")
    rainy_tip_pct = (
        rain_tip_pct_total / rain_credit_card_tip_trips if rain_credit_card_tip_trips else None
    )

    return {
        "analysis_year": year,
        "clean_trips": int(totals[0]),
        "quarantined_trips": int(totals[1]),
        "total_miles": _number(totals[2]),
        "credit_card_tips_usd": _number(totals[3]),
        "unknown_zone_trips": int(totals[4]),
        "weather_bucket_stats": weather_stats,
        "rain_vs_dry_demand_pct": _number(
            (rain_trips / expected_dry_trips - 1) * 100 if expected_dry_trips else None
        ),
        "rain_vs_dry_tip_pct_change": _number(
            (rainy_tip_pct / dry_tip_pct - 1) * 100 if dry_tip_pct else None
        ),
        "tip_percentage_note": (
            "Tip percentages use credit-card trips only; cash tips are not reported."
        ),
    }


def export_marts(settings: Settings) -> ExportSummary:
    """Export all required dbt marts, derived confessions, and enforce the byte budget."""
    if not settings.duckdb_path.is_file():
        raise FileNotFoundError(f"DuckDB warehouse not found at {settings.duckdb_path}.")
    destination = settings.app_data_dir
    destination.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(
        str(settings.duckdb_path),
        read_only=True,
        config={
            "memory_limit": settings.duckdb_memory_limit,
            "threads": settings.duckdb_threads,
        },
    )
    try:
        confessions = _confessions(connection, settings.year)
        with tempfile.TemporaryDirectory(prefix=".ycc-export-", dir=destination) as temp_dir:
            staging_dir = Path(temp_dir)
            for mart in MARTS:
                target = staging_dir / f"{mart}.parquet"
                connection.execute(
                    f"COPY (SELECT * FROM marts.{mart}) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                    [str(target)],
                )
            confessions_path = staging_dir / "confessions.json"
            confessions_path.write_text(
                json.dumps(confessions, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )

            sizes = {path.name: path.stat().st_size for path in staging_dir.iterdir()}
            total_bytes = sum(sizes.values())
            budget_bytes = settings.export_size_budget_mb * 1024 * 1024
            if total_bytes > budget_bytes:
                raise ValueError(
                    f"App export is {total_bytes:,} bytes, exceeding the "
                    f"{settings.export_size_budget_mb} MiB budget ({budget_bytes:,} bytes)."
                )

            for name in sorted(sizes):
                os.replace(staging_dir / name, destination / name)
    finally:
        connection.close()

    logger.info(
        "marts.export.completed",
        extra={
            "file_count": len(MARTS) + 1,
            "total_bytes": total_bytes,
            "budget_bytes": budget_bytes,
            "files": sizes,
        },
    )
    return ExportSummary(files=sizes, total_bytes=total_bytes, confessions=confessions)
