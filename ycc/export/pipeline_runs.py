"""Publish successful Airflow run summaries for the Streamlit About page."""

import logging
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from ycc.config import Settings
from ycc.extract.tlc import validate_month

logger = logging.getLogger(__name__)

_RUN_COLUMNS = (
    "run_id",
    "dag_id",
    "year",
    "months",
    "started_at_utc",
    "completed_at_utc",
    "duration_seconds",
    "raw_rows",
    "clean_rows",
    "quarantined_rows",
    "quarantine_pct",
    "dbt_tests_passed",
    "dbt_tests_failed",
    "dbt_tests_warned",
    "dbt_tests_skipped",
    "dbt_tests_total",
    "status",
)


@dataclass(frozen=True)
class _RunCounts:
    """Reconciled source and model row counts for selected months."""

    raw_rows: int
    clean_rows: int
    quarantined_rows: int


def _validated_months(months: Sequence[str], year: int) -> list[str]:
    if not months:
        raise ValueError("A pipeline run summary requires at least one month.")
    normalized = list(dict.fromkeys(months))
    for month in normalized:
        month_year, _ = validate_month(month)
        if month_year != year:
            raise ValueError(f"Month {month} does not match configured year {year}.")
    return normalized


def _count_rows(settings: Settings, months: Sequence[str]) -> _RunCounts:
    source_files = [f"yellow_tripdata_{month}.parquet" for month in months]
    placeholders = ", ".join("?" for _ in months)
    connection = duckdb.connect(
        str(settings.duckdb_path),
        read_only=True,
        config={
            "memory_limit": settings.duckdb_memory_limit,
            "threads": settings.duckdb_threads,
        },
    )
    try:
        raw_rows = int(
            connection.execute(
                f"""
                SELECT count(*)
                FROM raw.yellow_trips_raw
                WHERE source_file IN ({placeholders})
                """,
                source_files,
            ).fetchone()[0]
        )
        clean_rows = int(
            connection.execute(
                f"""
                SELECT count(*)
                FROM core.fct_trips
                WHERE source_file IN ({placeholders})
                """,
                source_files,
            ).fetchone()[0]
        )
        quarantined_rows = int(
            connection.execute(
                f"""
                SELECT count(*)
                FROM quarantine.quarantine_trips
                WHERE source_month IN ({placeholders})
                """,
                months,
            ).fetchone()[0]
        )
    finally:
        connection.close()

    if raw_rows != clean_rows + quarantined_rows:
        raise ValueError(
            "Pipeline run reconciliation failed: "
            f"{raw_rows} raw != {clean_rows} clean + {quarantined_rows} quarantined."
        )
    return _RunCounts(raw_rows, clean_rows, quarantined_rows)


def _summary_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE new_run (
            run_id VARCHAR,
            dag_id VARCHAR,
            year INTEGER,
            months VARCHAR,
            started_at_utc TIMESTAMP,
            completed_at_utc TIMESTAMP,
            duration_seconds DOUBLE,
            raw_rows BIGINT,
            clean_rows BIGINT,
            quarantined_rows BIGINT,
            quarantine_pct DOUBLE,
            dbt_tests_passed BIGINT,
            dbt_tests_failed BIGINT,
            dbt_tests_warned BIGINT,
            dbt_tests_skipped BIGINT,
            dbt_tests_total BIGINT,
            status VARCHAR
        )
        """
    )


def _write_summary(
    settings: Settings,
    *,
    run_id: str,
    dag_id: str,
    year: int,
    months: Sequence[str],
    started_at: datetime,
    completed_at: datetime,
    counts: _RunCounts,
    dbt_tests: Mapping[str, int],
) -> int:
    if started_at.utcoffset() is None or completed_at.utcoffset() is None:
        raise ValueError("Pipeline run timestamps must include a timezone.")
    started_at_utc = started_at.astimezone(UTC)
    completed_at_utc = completed_at.astimezone(UTC)
    if completed_at_utc < started_at_utc:
        raise ValueError("Pipeline completion time cannot precede its start time.")
    test_counts = {
        name: int(dbt_tests[name]) for name in ("passed", "failed", "warned", "skipped", "total")
    }
    if any(value < 0 for value in test_counts.values()):
        raise ValueError("dbt test counts cannot be negative.")
    if (
        sum(test_counts[name] for name in ("passed", "failed", "warned", "skipped"))
        != (test_counts["total"])
    ):
        raise ValueError("dbt test status counts do not match the reported total.")

    app_data_dir = settings.app_data_dir
    app_data_dir.mkdir(parents=True, exist_ok=True)
    destination = app_data_dir / "pipeline_runs.parquet"
    duration_seconds = (completed_at_utc - started_at_utc).total_seconds()
    quarantine_pct = counts.quarantined_rows / counts.raw_rows * 100 if counts.raw_rows else None
    values = [
        run_id,
        dag_id,
        year,
        ",".join(months),
        started_at_utc.replace(tzinfo=None),
        completed_at_utc.replace(tzinfo=None),
        duration_seconds,
        counts.raw_rows,
        counts.clean_rows,
        counts.quarantined_rows,
        quarantine_pct,
        test_counts["passed"],
        test_counts["failed"],
        test_counts["warned"],
        test_counts["skipped"],
        test_counts["total"],
        "success",
    ]

    with tempfile.TemporaryDirectory(prefix=".ycc-pipeline-", dir=app_data_dir) as temp_dir:
        staged = Path(temp_dir) / "pipeline_runs.parquet"
        connection = duckdb.connect()
        try:
            _summary_schema(connection)
            connection.execute(
                f"INSERT INTO new_run ({', '.join(_RUN_COLUMNS)}) VALUES "
                f"({', '.join('?' for _ in _RUN_COLUMNS)})",
                values,
            )
            if destination.is_file():
                previous_columns = tuple(
                    row[0]
                    for row in connection.execute(
                        "DESCRIBE SELECT * FROM read_parquet(?)",
                        [str(destination)],
                    ).fetchall()
                )
                if previous_columns != _RUN_COLUMNS:
                    raise ValueError(
                        f"Unexpected pipeline summary schema in {destination}: {previous_columns}."
                    )
                connection.execute(
                    """
                    CREATE TABLE previous_runs AS
                    SELECT * FROM read_parquet(?)
                    """,
                    [str(destination)],
                )
                connection.execute(
                    """
                    COPY (
                        SELECT * FROM previous_runs WHERE run_id != ?
                        UNION ALL
                        SELECT * FROM new_run
                        ORDER BY completed_at_utc
                    ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
                    """,
                    [run_id, str(staged)],
                )
            else:
                connection.execute(
                    "COPY new_run TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                    [str(staged)],
                )
        finally:
            connection.close()

        retained_bytes = sum(
            path.stat().st_size
            for path in app_data_dir.rglob("*")
            if path.is_file() and Path(temp_dir) not in path.parents and path != destination
        )
        total_bytes = staged.stat().st_size + retained_bytes
        budget_bytes = settings.export_size_budget_mb * 1024 * 1024
        if total_bytes > budget_bytes:
            raise ValueError(
                f"Pipeline summary would make app data {total_bytes:,} bytes, "
                f"exceeding the {settings.export_size_budget_mb} MiB budget."
            )
        os.replace(staged, destination)

    logger.info(
        "pipeline.summary.published",
        extra={
            "run_id": run_id,
            "months": list(months),
            "raw_rows": counts.raw_rows,
            "clean_rows": counts.clean_rows,
            "quarantined_rows": counts.quarantined_rows,
            "dbt_tests": test_counts,
            "duration_seconds": duration_seconds,
            "bytes": destination.stat().st_size,
        },
    )
    return {
        "run_id": run_id,
        "raw_rows": counts.raw_rows,
        "clean_rows": counts.clean_rows,
        "quarantined_rows": counts.quarantined_rows,
        "dbt_tests_total": test_counts["total"],
    }


def publish_pipeline_run(
    settings: Settings,
    *,
    run_id: str,
    dag_id: str,
    year: int,
    months: Sequence[str],
    started_at: datetime,
    completed_at: datetime,
    dbt_tests: Mapping[str, int],
) -> dict[str, object]:
    """Write one idempotent, reconciled, size-bounded app-facing run summary."""
    normalized_months = _validated_months(months, year)
    counts = _count_rows(settings, normalized_months)
    return _write_summary(
        settings,
        run_id=run_id,
        dag_id=dag_id,
        year=year,
        months=normalized_months,
        started_at=started_at,
        completed_at=completed_at,
        counts=counts,
        dbt_tests=dbt_tests,
    )
