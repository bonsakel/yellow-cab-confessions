"""Idempotent loading of monthly TLC parquet files into DuckDB."""

import hashlib
import logging
from pathlib import Path

import duckdb

from ycc.config import Settings
from ycc.extract.tlc import ExtractedTlcFile, tlc_source_file, validate_month
from ycc.load.manifest import IngestionManifest

logger = logging.getLogger(__name__)

_COLUMN_TYPES = (
    ("vendor_id", "INTEGER", ("vendorid", "vendor_id")),
    ("pickup_datetime", "TIMESTAMP", ("tpep_pickup_datetime", "pickup_datetime")),
    ("dropoff_datetime", "TIMESTAMP", ("tpep_dropoff_datetime", "dropoff_datetime")),
    ("passenger_count", "INTEGER", ("passenger_count",)),
    ("trip_distance", "DOUBLE", ("trip_distance",)),
    ("rate_code_id", "INTEGER", ("ratecodeid", "rate_code_id")),
    ("store_and_fwd_flag", "VARCHAR", ("store_and_fwd_flag",)),
    ("pickup_location_id", "INTEGER", ("pulocationid", "pickup_location_id")),
    ("dropoff_location_id", "INTEGER", ("dolocationid", "dropoff_location_id")),
    ("payment_type", "INTEGER", ("payment_type",)),
    ("fare_amount", "DOUBLE", ("fare_amount",)),
    ("extra", "DOUBLE", ("extra",)),
    ("mta_tax", "DOUBLE", ("mta_tax",)),
    ("tip_amount", "DOUBLE", ("tip_amount",)),
    ("tolls_amount", "DOUBLE", ("tolls_amount",)),
    ("improvement_surcharge", "DOUBLE", ("improvement_surcharge",)),
    ("total_amount", "DOUBLE", ("total_amount",)),
    ("congestion_surcharge", "DOUBLE", ("congestion_surcharge",)),
    ("airport_fee", "DOUBLE", ("airport_fee",)),
    ("cbd_congestion_fee", "DOUBLE", ("cbd_congestion_fee",)),
)


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_trip_table(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("CREATE SCHEMA IF NOT EXISTS raw")
    columns = ",\n".join(f"{name} {data_type}" for name, data_type, _ in _COLUMN_TYPES)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS raw.yellow_trips_raw (
            {columns},
            source_file VARCHAR NOT NULL
        )
        """
    )


def _parquet_columns(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
) -> dict[str, str]:
    rows = connection.execute(
        "DESCRIBE SELECT * FROM read_parquet(?, union_by_name = true)",
        [str(path)],
    ).fetchall()
    return {str(row[0]).casefold(): str(row[0]) for row in rows}


def _projection(source_columns: dict[str, str]) -> str:
    expressions: list[str] = []
    for target, data_type, aliases in _COLUMN_TYPES:
        source = next((source_columns[name] for name in aliases if name in source_columns), None)
        if source is None:
            expressions.append(f"CAST(NULL AS {data_type}) AS {_quote_identifier(target)}")
        else:
            expressions.append(
                f"TRY_CAST({_quote_identifier(source)} AS {data_type}) "
                f"AS {_quote_identifier(target)}"
            )
    return ",\n".join(expressions)


def load_tlc_month(
    month: str,
    settings: Settings,
    manifest: IngestionManifest,
    extracted: ExtractedTlcFile | None = None,
) -> int:
    """Load one extracted month transactionally, replacing any prior copy."""
    year, month_number = validate_month(month)
    source_file = tlc_source_file(month)
    record = manifest.get(source_file)
    if record is None:
        raise ValueError(f"No ingestion manifest entry for {source_file}; run extract first.")
    if extracted is not None and extracted.sha256 != record.sha256:
        raise ValueError(f"Extracted checksum for {source_file} differs from its manifest.")
    if record.status == "LOADED" and record.row_count is not None:
        logger.info(
            "tlc.load.skipped",
            extra={"source_file": source_file, "row_count": record.row_count},
        )
        return record.row_count

    path = extracted.local_path if extracted is not None else settings.download_dir / source_file
    if path is None or not path.is_file():
        raise FileNotFoundError(
            f"Local parquet file for {source_file} is missing; run extract first."
        )
    checksum = _sha256_file(path)
    if checksum != record.sha256:
        raise ValueError(
            f"Checksum mismatch for {source_file}: manifest {record.sha256}, file {checksum}."
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
        source_columns = _parquet_columns(connection, path)
        selected_columns = _projection(source_columns)
        with connection:
            _ensure_trip_table(connection)
            row_count = int(
                connection.execute(
                    "SELECT count(*) FROM read_parquet(?, union_by_name = true)",
                    [str(path)],
                ).fetchone()[0]
            )
            connection.execute(
                "DELETE FROM raw.yellow_trips_raw WHERE source_file = ?",
                [source_file],
            )
            connection.execute(
                f"""
                INSERT INTO raw.yellow_trips_raw
                SELECT {selected_columns}, ? AS source_file
                FROM read_parquet(?, union_by_name = true)
                """,
                [source_file, str(path)],
            )
            manifest.mark_loaded(connection, source_file, row_count)
    finally:
        connection.close()

    logger.info(
        "tlc.load.completed",
        extra={
            "source_file": source_file,
            "row_count": row_count,
            "month": f"{year}-{month_number:02d}",
        },
    )
    return row_count
