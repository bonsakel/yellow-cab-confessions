"""Command-line entry point for pipeline extraction and loading."""

import logging

import typer

from ycc.config import Settings
from ycc.extract.tlc import extract_tlc_month
from ycc.load.duckdb_loader import load_tlc_month
from ycc.load.manifest import IngestionManifest
from ycc.load.s3 import S3ObjectStore
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


def main() -> None:
    """Run the command-line application."""
    app()
