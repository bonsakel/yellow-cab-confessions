"""DuckDB-backed ingestion manifest for idempotent pipeline runs."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class ManifestRecord:
    """One source object's extraction and load state."""

    source_file: str
    s3_key: str
    bytes: int
    sha256: str
    source_etag: str | None
    row_count: int | None
    status: str
    loaded_at: datetime | None


class IngestionManifest:
    """Create and query the raw ingestion manifest in a DuckDB database."""

    def __init__(self, database_path: Path) -> None:
        """Initialize the manifest database, creating the parent directory."""
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        """Open a configured DuckDB connection."""
        return duckdb.connect(str(self.database_path))

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("CREATE SCHEMA IF NOT EXISTS raw")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS raw.ingestion_manifest (
                    source_file VARCHAR PRIMARY KEY,
                    s3_key VARCHAR NOT NULL,
                    bytes BIGINT NOT NULL,
                    etag_or_sha256 VARCHAR NOT NULL,
                    source_etag VARCHAR,
                    row_count BIGINT,
                    status VARCHAR NOT NULL,
                    loaded_at TIMESTAMP
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info('raw.ingestion_manifest')"
                ).fetchall()
            }
            if "source_etag" not in columns:
                connection.execute(
                    "ALTER TABLE raw.ingestion_manifest ADD COLUMN source_etag VARCHAR"
                )

    def get(self, source_file: str) -> ManifestRecord | None:
        """Return the manifest record for a source filename, if present."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT source_file, s3_key, bytes, etag_or_sha256, source_etag,
                       row_count, status, loaded_at
                FROM raw.ingestion_manifest
                WHERE source_file = ?
                """,
                [source_file],
            ).fetchone()
        if row is None:
            return None
        return ManifestRecord(
            source_file=row[0],
            s3_key=row[1],
            bytes=row[2],
            sha256=row[3],
            source_etag=row[4],
            row_count=row[5],
            status=row[6],
            loaded_at=row[7],
        )

    def record_extracted(self, record: ManifestRecord) -> None:
        """Upsert extraction metadata and clear the previous load state."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO raw.ingestion_manifest (
                    source_file, s3_key, bytes, etag_or_sha256, source_etag,
                    row_count, status, loaded_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, 'EXTRACTED', NULL)
                ON CONFLICT (source_file) DO UPDATE SET
                    s3_key = excluded.s3_key,
                    bytes = excluded.bytes,
                    etag_or_sha256 = excluded.etag_or_sha256,
                    source_etag = excluded.source_etag,
                    row_count = NULL,
                    status = 'EXTRACTED',
                    loaded_at = NULL
                """,
                [
                    record.source_file,
                    record.s3_key,
                    record.bytes,
                    record.sha256,
                    record.source_etag,
                ],
            )

    @staticmethod
    def mark_loaded(
        connection: duckdb.DuckDBPyConnection,
        source_file: str,
        row_count: int,
    ) -> None:
        """Mark a source as loaded within the caller's transaction."""
        result = connection.execute(
            """
            UPDATE raw.ingestion_manifest
            SET row_count = ?, status = 'LOADED', loaded_at = current_localtimestamp()
            WHERE source_file = ?
            RETURNING source_file
            """,
            [row_count, source_file],
        ).fetchone()
        if result is None:
            raise ValueError(f"No ingestion manifest entry for {source_file}.")
