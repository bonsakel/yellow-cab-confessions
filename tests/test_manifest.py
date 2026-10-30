"""Tests for the ingestion manifest schema and idempotent upserts."""

from pathlib import Path

from ycc.load.manifest import IngestionManifest, ManifestRecord


def test_manifest_records_extracted_files_and_resets_load_state(tmp_path: Path) -> None:
    manifest = IngestionManifest(tmp_path / "warehouse.duckdb")
    record = ManifestRecord(
        source_file="yellow_tripdata_2024-01.parquet",
        s3_key="raw/yellow/year=2024/month=01/yellow_tripdata_2024-01.parquet",
        bytes=123,
        sha256="abc123",
        source_etag="etag-one",
        row_count=None,
        status="EXTRACTED",
        loaded_at=None,
    )
    manifest.record_extracted(record)
    manifest.record_extracted(
        ManifestRecord(
            source_file=record.source_file,
            s3_key=record.s3_key,
            bytes=456,
            sha256="def456",
            source_etag="etag-two",
            row_count=10,
            status="LOADED",
            loaded_at=None,
        )
    )

    result = manifest.get(record.source_file)

    assert result is not None
    assert result.bytes == 456
    assert result.sha256 == "def456"
    assert result.source_etag == "etag-two"
    assert result.row_count is None
    assert result.status == "EXTRACTED"
    assert result.loaded_at is None
