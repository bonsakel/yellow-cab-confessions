"""Tests for transactional, schema-tolerant raw TLC loading."""

import hashlib
from datetime import datetime
from pathlib import Path

import duckdb

from ycc.config import Settings
from ycc.extract.tlc import ExtractedTlcFile
from ycc.load.duckdb_loader import load_tlc_month
from ycc.load.manifest import IngestionManifest, ManifestRecord


def _write_parquet(path: Path, sql: str) -> str:
    connection = duckdb.connect()
    try:
        connection.execute(
            f"COPY ({sql}) TO ? (FORMAT PARQUET)",
            [str(path)],
        )
    finally:
        connection.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_record(month: str, path: Path, checksum: str) -> ManifestRecord:
    filename = f"yellow_tripdata_{month}.parquet"
    return ManifestRecord(
        source_file=filename,
        s3_key=f"raw/yellow/year={month[:4]}/month={month[-2:]}/{filename}",
        bytes=path.stat().st_size,
        sha256=checksum,
        source_etag="fixture-etag",
        row_count=None,
        status="EXTRACTED",
        loaded_at=None,
    )


def test_loads_schema_drift_and_preserves_month_rows(tmp_path: Path) -> None:
    fixtures_dir = Path(__file__).parent / "fixtures"
    old_schema = fixtures_dir / "tlc_schema_2024_01.parquet"
    new_schema = fixtures_dir / "tlc_schema_2024_02.parquet"
    old_checksum = hashlib.sha256(old_schema.read_bytes()).hexdigest()
    new_checksum = hashlib.sha256(new_schema.read_bytes()).hexdigest()
    settings = Settings(
        _env_file=None,
        duckdb_path=tmp_path / "warehouse.duckdb",
        work_dir=tmp_path,
    )
    manifest = IngestionManifest(settings.duckdb_path)
    for month, path, checksum in (
        ("2024-01", old_schema, old_checksum),
        ("2024-02", new_schema, new_checksum),
    ):
        record = _manifest_record(month, path, checksum)
        manifest.record_extracted(record)
        extracted = ExtractedTlcFile(
            month=month,
            source_file=record.source_file,
            s3_key=record.s3_key,
            local_path=path,
            bytes=record.bytes,
            sha256=checksum,
            source_etag=record.source_etag,
            skipped=False,
        )

        assert load_tlc_month(month, settings, manifest, extracted) == 1
        if month == "2024-01":
            assert load_tlc_month(month, settings, manifest, extracted) == 1

    connection = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        rows = connection.execute(
            """
            SELECT source_file, vendor_id, pickup_datetime, airport_fee
            FROM raw.yellow_trips_raw
            ORDER BY source_file
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        ("yellow_tripdata_2024-01.parquet", 1, datetime(2024, 1, 3, 8), None),
        ("yellow_tripdata_2024-02.parquet", 2, datetime(2024, 2, 4, 9), 1.25),
    ]
    january_record = manifest.get("yellow_tripdata_2024-01.parquet")
    february_record = manifest.get("yellow_tripdata_2024-02.parquet")
    assert january_record is not None
    assert february_record is not None
    assert january_record.status == "LOADED"
    assert february_record.status == "LOADED"


def test_reloading_a_month_replaces_its_rows(tmp_path: Path) -> None:
    path = tmp_path / "yellow_tripdata_2024-01.parquet"
    settings = Settings(
        _env_file=None,
        duckdb_path=tmp_path / "warehouse.duckdb",
        work_dir=tmp_path,
    )
    manifest = IngestionManifest(settings.duckdb_path)

    for vendor_id in (1, 2):
        checksum = _write_parquet(
            path,
            f"""
            SELECT {vendor_id}::INTEGER AS VendorID,
                   TIMESTAMP '2024-01-03 08:00:00' AS tpep_pickup_datetime,
                   TIMESTAMP '2024-01-03 08:12:00' AS tpep_dropoff_datetime,
                   1.5::DOUBLE AS trip_distance,
                   12.0::DOUBLE AS fare_amount,
                   15.0::DOUBLE AS total_amount
            """,
        )
        record = _manifest_record("2024-01", path, checksum)
        manifest.record_extracted(record)
        extracted = ExtractedTlcFile(
            month="2024-01",
            source_file=record.source_file,
            s3_key=record.s3_key,
            local_path=path,
            bytes=record.bytes,
            sha256=checksum,
            source_etag=record.source_etag,
            skipped=False,
        )
        assert load_tlc_month("2024-01", settings, manifest, extracted) == 1

    connection = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        rows = connection.execute(
            "SELECT vendor_id, source_file FROM raw.yellow_trips_raw"
        ).fetchall()
    finally:
        connection.close()

    assert rows == [(2, "yellow_tripdata_2024-01.parquet")]
    record = manifest.get("yellow_tripdata_2024-01.parquet")
    assert record is not None
    assert record.row_count == 1
