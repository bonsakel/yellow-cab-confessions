"""Tests for streaming TLC extraction and retry behavior."""

import hashlib
import io
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

import pytest
from tenacity import wait_none

from ycc.config import Settings
from ycc.extract import tlc
from ycc.load.manifest import IngestionManifest
from ycc.load.s3 import ObjectStorage


class _Response(io.BytesIO):
    status = 200
    headers = {"ETag": '"source-etag"'}


def test_stream_download_retries_network_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    requests: list[tuple[str, int]] = []

    def fake_urlopen(request: Request, *, timeout: int) -> _Response:
        nonlocal calls
        calls += 1
        requests.append((request.full_url, timeout))
        if calls == 1:
            raise URLError("temporary network failure")
        return _Response(b"parquet-payload")

    monkeypatch.setattr(tlc, "urlopen", fake_urlopen)
    monkeypatch.setattr(tlc._stream_download.retry, "wait", wait_none())
    target = tmp_path / "download.parquet"

    size, checksum = tlc._stream_download("2024-01", target)

    assert calls == 2
    assert requests == [(requests[0][0], 60), (requests[0][0], 60)]
    assert target.read_bytes() == b"parquet-payload"
    assert size == len(b"parquet-payload")
    assert checksum == hashlib.sha256(b"parquet-payload").hexdigest()


@pytest.mark.parametrize("month", ["2024-00", "2024-13", "24-01", "2024-1"])
def test_month_validation_rejects_invalid_values(month: str) -> None:
    with pytest.raises(ValueError, match="YYYY-MM"):
        tlc.validate_month(month)


def test_extract_records_checksums_and_s3_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"small parquet fixture"
    uploaded: list[tuple[Path, str, str, str | None]] = []

    class FakeStorage:
        def upload_file(
            self,
            path: Path,
            key: str,
            *,
            sha256: str,
            source_etag: str | None,
        ) -> None:
            uploaded.append((path, key, sha256, source_etag))

        def object_matches(self, key: str, sha256: str) -> bool:
            return key.endswith("yellow_tripdata_2024-01.parquet") and len(sha256) == 64

    def fake_stream_download(month: str, path: Path) -> tuple[int, str]:
        assert month == "2024-01"
        assert path.name == "yellow_tripdata_2024-01.parquet"
        return _write_payload(path, payload)

    storage: ObjectStorage = FakeStorage()
    settings = Settings(
        _env_file=None,
        work_dir=tmp_path,
        duckdb_path=tmp_path / "warehouse.duckdb",
    )
    manifest = IngestionManifest(settings.duckdb_path)

    def fake_source_etag(month: str) -> str:
        assert month == "2024-01"
        return "source-etag"

    monkeypatch.setattr(tlc, "_source_etag", fake_source_etag)
    monkeypatch.setattr(tlc, "_stream_download", fake_stream_download)

    result = tlc.extract_tlc_month("2024-01", settings, manifest, storage)

    assert result.s3_key == "raw/yellow/year=2024/month=01/yellow_tripdata_2024-01.parquet"
    assert result.bytes == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.local_path is not None
    assert uploaded == [(result.local_path, result.s3_key, result.sha256, "source-etag")]
    record = manifest.get(result.source_file)
    assert record is not None
    assert record.status == "EXTRACTED"
    assert record.bytes == len(payload)


def _write_payload(path: Path, payload: bytes) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return len(payload), hashlib.sha256(payload).hexdigest()
