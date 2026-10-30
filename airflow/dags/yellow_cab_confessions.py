"""Monthly, retry-safe orchestration for the Yellow Cab Confessions pipeline."""

import json
import logging
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param, TaskGroup
from airflow.sdk.exceptions import AirflowSkipException

from ycc.config import Settings
from ycc.export.marts_to_parquet import export_marts
from ycc.export.pipeline_runs import publish_pipeline_run
from ycc.extract.holidays import generate_holiday_seed
from ycc.extract.tlc import extract_tlc_month
from ycc.extract.weather import extract_weather_year
from ycc.extract.zone_shapes import extract_zone_shapes
from ycc.extract.zones import download_zone_lookup
from ycc.load.duckdb_loader import load_tlc_month
from ycc.load.manifest import IngestionManifest
from ycc.load.s3 import S3ObjectStore
from ycc.load.weather import load_weather_year
from ycc.load.zone_shapes import load_zone_centroids
from ycc.load.zones import load_zone_lookup
from ycc.scheduling import resolve_months

logger = logging.getLogger(__name__)
settings = Settings()


def _resolve_month_specs(**context: Any) -> list[dict[str, str]]:
    """Resolve explicit backfill months or the month in the schedule interval."""
    dag_run = context["dag_run"]
    run_conf = dag_run.conf or {}
    requested = run_conf.get("months", context["params"].get("months"))
    interval_start = context.get("data_interval_start") or dag_run.data_interval_start
    scheduled_month = interval_start.strftime("%Y-%m") if interval_start else None
    months = resolve_months(requested, scheduled_month, settings.year)
    if months is None:
        raise AirflowSkipException(
            f"Scheduled month {scheduled_month} is outside configured year {settings.year}."
        )
    return [{"month": month} for month in months]


def _extract_month(month: str) -> dict[str, object]:
    """Extract one TLC month and return only JSON-serializable metadata."""
    result = extract_tlc_month(
        month,
        settings,
        IngestionManifest(settings.duckdb_path),
        S3ObjectStore(settings),
    )
    return {
        "month": month,
        "source_file": result.source_file,
        "bytes": result.bytes,
        "sha256": result.sha256,
        "skipped": result.skipped,
    }


def _extract_zones() -> None:
    """Download and cache the TLC zone lookup."""
    download_zone_lookup(settings)


def _extract_shapes() -> None:
    """Download and cache simplified WGS84 zone polygons and centroids."""
    extract_zone_shapes(settings, S3ObjectStore(settings))


def _extract_weather() -> None:
    """Fetch and cache the configured year's hourly weather."""
    extract_weather_year(settings, S3ObjectStore(settings))


def _extract_holidays() -> None:
    """Generate the configured year's holiday seed."""
    generate_holiday_seed(settings)


def _load_month(month: str) -> int:
    """Load or verify one TLC month in the raw warehouse."""
    return load_tlc_month(month, settings, IngestionManifest(settings.duckdb_path))


def _load_zones() -> None:
    """Load the TLC zone lookup into the raw warehouse."""
    load_zone_lookup(settings)


def _load_weather() -> None:
    """Load cached weather observations into the raw warehouse."""
    load_weather_year(settings)


def _load_centroids() -> None:
    """Load cached zone centroids into the raw warehouse."""
    load_zone_centroids(settings)


def _run_dbt(command: str) -> None:
    """Run one dbt command and stream its output into the Airflow task log."""
    project_dir = settings.dbt_project_dir
    subprocess.run(
        [
            "dbt",
            command,
            "--project-dir",
            str(project_dir),
            "--profiles-dir",
            str(project_dir),
        ],
        cwd=project_dir,
        check=True,
    )


def _dbt_test() -> dict[str, int]:
    """Run dbt tests and summarize the resulting test artifact."""
    _run_dbt("test")
    result_path = settings.dbt_project_dir / "target" / "run_results.json"
    if not result_path.is_file():
        raise FileNotFoundError(f"dbt test results not found at {result_path}.")
    results = json.loads(result_path.read_text(encoding="utf-8"))["results"]
    counts = {
        status: sum(result["status"] == status for result in results)
        for status in ("pass", "fail", "error", "warn", "skipped")
    }
    unsupported = [result["status"] for result in results if result["status"] not in counts]
    if unsupported:
        raise ValueError(f"Unsupported dbt test statuses: {sorted(set(unsupported))}.")
    summary = {
        "passed": counts["pass"],
        "failed": counts["fail"] + counts["error"],
        "warned": counts["warn"],
        "skipped": counts["skipped"],
        "total": len(results),
    }
    if summary["failed"] or summary["warned"]:
        raise RuntimeError(f"dbt tests did not pass cleanly: {summary}.")
    return summary


def _export_app_data() -> dict[str, int]:
    """Export all app-facing marts and enforce the configured bundle budget."""
    result = export_marts(settings)
    return {"file_count": len(result.files), "total_bytes": result.total_bytes}


def _publish_summary(**context: Any) -> dict[str, object]:
    """Publish reconciled row counts and dbt test results for the About page."""
    task_instance = context["ti"]
    month_specs = task_instance.xcom_pull(task_ids="resolve_months")
    test_results = task_instance.xcom_pull(task_ids="dbt_build.test")
    dag_run = context["dag_run"]
    if dag_run.start_date is None:
        raise ValueError(f"DAG run {dag_run.run_id} is missing its start time.")
    return publish_pipeline_run(
        settings,
        run_id=dag_run.run_id,
        dag_id=dag_run.dag_id,
        year=settings.year,
        months=[item["month"] for item in month_specs],
        started_at=dag_run.start_date,
        completed_at=datetime.now(UTC),
        dbt_tests=test_results,
    )


with DAG(
    dag_id="yellow_cab_confessions",
    description="Ingest, model, test, and export NYC yellow taxi data.",
    start_date=datetime.now(UTC).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    ),
    schedule="@monthly",
    catchup=True,
    max_active_runs=1,
    max_active_tasks=3,
    params={
        "months": Param(
            default=[],
            type="array",
            items={"type": "string", "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"},
            description="Optional YYYY-MM months for a manual run or backfill.",
        )
    },
    default_args={
        "owner": "ycc",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=20),
    },
    tags=["yellow-cab-confessions", "elt"],
) as dag:
    month_specs = PythonOperator(
        task_id="resolve_months",
        python_callable=_resolve_month_specs,
    )

    with TaskGroup(group_id="extract") as extract_group:
        extracted_months = PythonOperator.partial(
            task_id="tlc_month",
            python_callable=_extract_month,
            max_active_tis_per_dag=1,
        ).expand(op_kwargs=month_specs.output)
        zone_lookup = PythonOperator(
            task_id="zone_lookup",
            python_callable=_extract_zones,
        )
        zone_shapes = PythonOperator(
            task_id="zone_shapes",
            python_callable=_extract_shapes,
        )
        weather = PythonOperator(
            task_id="weather",
            python_callable=_extract_weather,
        )
        holidays = PythonOperator(
            task_id="holidays",
            python_callable=_extract_holidays,
        )
        zone_lookup >> zone_shapes

    with TaskGroup(group_id="load") as load_group:
        loaded_zones = PythonOperator(
            task_id="zone_lookup",
            python_callable=_load_zones,
        )
        loaded_weather = PythonOperator(
            task_id="weather",
            python_callable=_load_weather,
        )
        loaded_centroids = PythonOperator(
            task_id="zone_centroids",
            python_callable=_load_centroids,
        )
        loaded_months = PythonOperator.partial(
            task_id="tlc_month",
            python_callable=_load_month,
            max_active_tis_per_dag=1,
        ).expand(op_kwargs=month_specs.output)
        loaded_zones >> loaded_weather >> loaded_centroids >> loaded_months

    with TaskGroup(group_id="dbt_build") as dbt_group:
        seeded = PythonOperator(
            task_id="seed",
            python_callable=_run_dbt,
            op_args=["seed"],
        )
        modeled = PythonOperator(
            task_id="run",
            python_callable=_run_dbt,
            op_args=["run"],
        )
        tested = PythonOperator(
            task_id="test",
            python_callable=_dbt_test,
        )
        seeded >> modeled >> tested

    with TaskGroup(group_id="export") as export_group:
        exported = PythonOperator(
            task_id="app_data",
            python_callable=_export_app_data,
        )

    published = PythonOperator(
        task_id="publish_summary",
        python_callable=_publish_summary,
    )

    month_specs >> extract_group
    extract_group >> load_group >> dbt_group >> export_group >> published
