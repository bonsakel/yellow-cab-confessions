"""Command-line entry point for pipeline extraction and loading."""

import logging

import typer

from ycc.config import Settings
from ycc.export.marts_to_parquet import export_marts
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
from ycc.logging import configure_logging

logger = logging.getLogger(__name__)
app = typer.Typer(help="Extract and load Yellow Cab Confessions data.")


def _months_argument(value: str | None, default: str) -> list[str]:
    months = [month.strip() for month in (value or default).split(",") if month.strip()]
    if not months:
        raise typer.BadParameter("Provide at least one YYYY-MM month.")
    return list(dict.fromkeys(months))


@app.command()
def extract(
    months: str | None = typer.Option(
        None,
        "--months",
        help="Comma-separated YYYY-MM months; defaults to YCC_DEMO_MONTHS.",
    ),
) -> None:
    """Download and upload monthly TLC yellow taxi parquet files."""
    configure_logging()
    settings = Settings()
    manifest = IngestionManifest(settings.duckdb_path)
    storage = S3ObjectStore(settings)
    for month in _months_argument(months, settings.demo_months):
        result = extract_tlc_month(month, settings, manifest, storage)
        logger.info(
            "cli.extract.month",
            extra={
                "month": month,
                "source_file": result.source_file,
                "bytes": result.bytes,
                "skipped": result.skipped,
            },
        )


@app.command()
def load(
    months: str | None = typer.Option(
        None,
        "--months",
        help="Comma-separated YYYY-MM months; defaults to YCC_DEMO_MONTHS.",
    ),
) -> None:
    """Load extracted TLC parquet files into raw.yellow_trips_raw."""
    configure_logging()
    settings = Settings()
    manifest = IngestionManifest(settings.duckdb_path)
    for month in _months_argument(months, settings.demo_months):
        row_count = load_tlc_month(month, settings, manifest)
        logger.info(
            "cli.load.month",
            extra={"month": month, "row_count": row_count},
        )


@app.command("extract-zones")
def extract_zones() -> None:
    """Download and cache the public TLC taxi zone lookup CSV."""
    configure_logging()
    path = download_zone_lookup(Settings())
    logger.info(
        "cli.extract_zones.completed",
        extra={"path": str(path), "bytes": path.stat().st_size},
    )


@app.command("load-zones")
def load_zones() -> None:
    """Load the cached TLC taxi zone lookup into raw.taxi_zone_lookup."""
    configure_logging()
    row_count = load_zone_lookup(Settings())
    logger.info("cli.load_zones.completed", extra={"row_count": row_count})


@app.command("extract-weather")
def extract_weather() -> None:
    """Fetch, normalize, cache, and upload the configured year's hourly weather."""
    configure_logging()
    settings = Settings()
    json_path, parquet_path = extract_weather_year(settings, S3ObjectStore(settings))
    logger.info(
        "cli.extract_weather.completed",
        extra={"json_path": str(json_path), "parquet_path": str(parquet_path)},
    )


@app.command("load-weather")
def load_weather() -> None:
    """Load cached normalized weather into raw.weather_hourly."""
    configure_logging()
    row_count = load_weather_year(Settings())
    logger.info("cli.load_weather.completed", extra={"row_count": row_count})


@app.command("extract-holidays")
def extract_holidays() -> None:
    """Generate the configured year's US and New York holiday dbt seed."""
    configure_logging()
    path = generate_holiday_seed(Settings())
    logger.info(
        "cli.extract_holidays.completed",
        extra={"path": str(path), "bytes": path.stat().st_size},
    )


@app.command("extract-zone-shapes")
def extract_zone_shapes_command() -> None:
    """Download and export simplified WGS84 zone shapes and centroids."""
    configure_logging()
    settings = Settings()
    geojson_path, centroid_path = extract_zone_shapes(settings, S3ObjectStore(settings))
    logger.info(
        "cli.extract_zone_shapes.completed",
        extra={"geojson_path": str(geojson_path), "centroids_path": str(centroid_path)},
    )


@app.command("load-zone-shapes")
def load_zone_shapes() -> None:
    """Load zone centroid parquet into raw.zone_centroids."""
    configure_logging()
    row_count = load_zone_centroids(Settings())
    logger.info("cli.load_zone_shapes.completed", extra={"row_count": row_count})


@app.command("export")
def export() -> None:
    """Export dbt marts for the Streamlit app within the configured size budget."""
    configure_logging()
    result = export_marts(Settings())
    logger.info(
        "cli.export.completed",
        extra={
            "file_count": len(result.files),
            "total_bytes": result.total_bytes,
            "files": result.files,
        },
    )


def main() -> None:
    """Run the command-line application."""
    app()
