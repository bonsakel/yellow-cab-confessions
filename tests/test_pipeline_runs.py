"""Tests for app-facing Airflow pipeline summaries."""

from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from ycc.config import Settings
from ycc.export.pipeline_runs import publish_pipeline_run

_DBT_TESTS = {"passed": 12, "failed": 0, "warned": 0, "skipped": 1, "total": 13}


def _warehouse(path) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute("CREATE SCHEMA raw")
        connection.execute("CREATE TABLE raw.yellow_trips_raw (source_file VARCHAR)")
        connection.execute(
            "INSERT INTO raw.yellow_trips_raw VALUES "
            "('yellow_tripdata_2024-01.parquet'), "
            "('yellow_tripdata_2024-01.parquet'), "
            "('yellow_tripdata_2024-02.parquet')"
        )
        connection.execute("CREATE SCHEMA core")
        connection.execute("CREATE TABLE core.fct_trips (source_file VARCHAR)")
        connection.execute("INSERT INTO core.fct_trips VALUES ('yellow_tripdata_2024-01.parquet')")
        connection.execute("CREATE SCHEMA quarantine")
        connection.execute("CREATE TABLE quarantine.quarantine_trips (source_month VARCHAR)")
        connection.execute("INSERT INTO quarantine.quarantine_trips VALUES ('2024-01')")
    finally:
        connection.close()


def _publish(settings: Settings, run_id: str = "run-1") -> dict[str, object]:
    started_at = datetime(2024, 2, 1, tzinfo=UTC)
    return publish_pipeline_run(
        settings,
        run_id=run_id,
        dag_id="yellow_cab_confessions",
        year=2024,
        months=["2024-01"],
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=90),
        dbt_tests=_DBT_TESTS,
    )


def test_pipeline_summary_reconciles_and_writes_parquet(tmp_path) -> None:
    warehouse = tmp_path / "warehouse.duckdb"
    _warehouse(warehouse)
    settings = Settings(
        duckdb_path=warehouse,
        app_data_dir=tmp_path / "app-data",
        export_size_budget_mb=1,
    )

    result = _publish(settings)
    connection = duckdb.connect()
    try:
        rows = connection.execute(
            "SELECT * FROM read_parquet(?)",
            [str(settings.app_data_dir / "pipeline_runs.parquet")],
        ).fetchall()
    finally:
        connection.close()

    assert result == {
        "run_id": "run-1",
        "raw_rows": 2,
        "clean_rows": 1,
        "quarantined_rows": 1,
        "dbt_tests_total": 13,
    }
    assert len(rows) == 1
    assert rows[0][9] == 1
    assert rows[0][10] == 50.0
    assert rows[0][11:16] == (12, 0, 0, 1, 13)


def test_pipeline_summary_upserts_run_id_on_retry(tmp_path) -> None:
    warehouse = tmp_path / "warehouse.duckdb"
    _warehouse(warehouse)
    settings = Settings(
        duckdb_path=warehouse,
        app_data_dir=tmp_path / "app-data",
        export_size_budget_mb=1,
    )

    _publish(settings)
    _publish(settings)

    connection = duckdb.connect()
    try:
        count = connection.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [str(settings.app_data_dir / "pipeline_runs.parquet")],
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 1


def test_pipeline_summary_enforces_reconciliation(tmp_path) -> None:
    warehouse = tmp_path / "warehouse.duckdb"
    _warehouse(warehouse)
    connection = duckdb.connect(str(warehouse))
    try:
        connection.execute(
            "INSERT INTO raw.yellow_trips_raw VALUES ('yellow_tripdata_2024-01.parquet')"
        )
    finally:
        connection.close()
    settings = Settings(
        duckdb_path=warehouse,
        app_data_dir=tmp_path / "app-data",
    )

    with pytest.raises(ValueError, match="reconciliation failed"):
        _publish(settings)
