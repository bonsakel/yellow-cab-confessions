"""Streaming extraction of NYC TLC monthly yellow taxi parquet files."""

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from http.client import HTTPResponse
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ycc.config import Settings
from ycc.load.manifest import IngestionManifest, ManifestRecord
from ycc.load.s3 import ObjectStorage

logger = logging.getLogger(__name__)

TLC_TRIP_URL = (
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month}.parquet"
)
_MONTH_PATTERN = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")
_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ExtractedTlcFile:
    """Metadata for a downloaded and uploaded TLC month."""

    month: str
    source_file: str
    s3_key: str
    local_path: Path | None
    bytes: int
    sha256: str
    source_etag: str | None
    skipped: bool


def validate_month(month: str) -> tuple[int, int]:
    """Validate a YYYY-MM month and return its year and month number."""
    match = _MONTH_PATTERN.fullmatch(month)
    if match is None:
        raise ValueError(f"Month must use YYYY-MM format with a valid month: {month!r}")
    return int(match.group("year")), int(match.group("month"))


def tlc_source_file(month: str) -> str:
    """Return the TLC parquet filename for a validated month."""
    year, month_number = validate_month(month)
    return f"yellow_tripdata_{year}-{month_number:02d}.parquet"


def tlc_s3_key(month: str) -> str:
    """Return the canonical raw S3 key for a validated month."""
    year, month_number = validate_month(month)
    return f"raw/yellow/year={year}/month={month_number:02d}/{tlc_source_file(month)}"


def _is_retryable(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return 500 <= error.code < 600
    return isinstance(error, (OSError, TimeoutError, URLError))


def _open_url(request: Request) -> HTTPResponse:
    response = urlopen(request, timeout=60)
    if response.status < 200 or response.status >= 300:
        response.close()
        raise OSError(f"Unexpected HTTP status {response.status} for {request.full_url}")
    return response


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _source_etag(month: str) -> str | None:
    year, month_number = validate_month(month)
    url = TLC_TRIP_URL.format(year=year, month=f"{month_number:02d}")
    request = Request(url, method="HEAD")
    with _open_url(request) as response:
        etag = response.headers.get("ETag")
    return etag.strip('"') if etag else None


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _stream_download(month: str, destination: Path) -> tuple[int, str]:
    year, month_number = validate_month(month)
    url = TLC_TRIP_URL.format(year=year, month=f"{month_number:02d}")
    request = Request(url, headers={"User-Agent": "YellowCabConfessions/0.1"})
    partial_path = destination.with_suffix(destination.suffix + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with _open_url(request) as response, partial_path.open("wb") as target:
            digest = hashlib.sha256()
            size = 0
            while chunk := response.read(_CHUNK_SIZE):
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            target.flush()
            os.fsync(target.fileno())
            expected_size = response.headers.get("Content-Length")
            if expected_size is not None and size != int(expected_size):
                raise OSError(
                    f"Incomplete download for {month}: expected {expected_size} bytes, got {size}."
                )
            if size == 0:
                raise OSError(f"Downloaded an empty TLC parquet file for {month}.")
        os.replace(partial_path, destination)
    finally:
        partial_path.unlink(missing_ok=True)

    return size, digest.hexdigest()


def extract_tlc_month(
    month: str,
    settings: Settings,
    manifest: IngestionManifest,
    storage: ObjectStorage,
) -> ExtractedTlcFile:
    """Download a TLC month, upload it to S3, and record its checksum."""
    validate_month(month)
    source_file = tlc_source_file(month)
    key = tlc_s3_key(month)
    source_etag = _source_etag(month)
    previous = manifest.get(source_file)

    if (
        previous is not None
        and previous.status == "LOADED"
        and source_etag is not None
        and previous.source_etag == source_etag
        and storage.object_matches(key, previous.sha256)
    ):
        logger.info(
            "tlc.extract.skipped",
            extra={"source_file": source_file, "s3_key": key, "reason": "unchanged"},
        )
        return ExtractedTlcFile(
            month=month,
            source_file=source_file,
            s3_key=key,
            local_path=None,
            bytes=previous.bytes,
            sha256=previous.sha256,
            source_etag=source_etag,
            skipped=True,
        )

    local_path = settings.download_dir / source_file
    size, sha256 = _stream_download(month, local_path)
    storage.upload_file(local_path, key, sha256=sha256, source_etag=source_etag)
    manifest.record_extracted(
        ManifestRecord(
            source_file=source_file,
            s3_key=key,
            bytes=size,
            sha256=sha256,
            source_etag=source_etag,
            row_count=None,
            status="EXTRACTED",
            loaded_at=None,
        )
    )
    logger.info(
        "tlc.extract.completed",
        extra={
            "source_file": source_file,
            "s3_key": key,
            "bytes": size,
            "sha256": sha256,
        },
    )
    return ExtractedTlcFile(
        month=month,
        source_file=source_file,
        s3_key=key,
        local_path=local_path,
        bytes=size,
        sha256=sha256,
        source_etag=source_etag,
        skipped=False,
    )
