"""Extraction of the NYC TLC taxi zone lookup."""

import logging
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ycc.config import Settings

logger = logging.getLogger(__name__)

TLC_ZONE_LOOKUP_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"
_CHUNK_SIZE = 64 * 1024


def _is_retryable(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return 500 <= error.code < 600
    return isinstance(error, (OSError, TimeoutError, URLError))


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def download_zone_lookup(settings: Settings) -> Path:
    """Download and cache the small public TLC taxi zone CSV."""
    destination = settings.download_dir / "taxi_zone_lookup.csv"
    if destination.is_file() and destination.stat().st_size > 0:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination.with_suffix(".csv.part")
    request = Request(TLC_ZONE_LOOKUP_URL, headers={"User-Agent": "YellowCabConfessions/0.1"})
    try:
        with urlopen(request, timeout=30) as response, partial_path.open("wb") as target:
            if response.status < 200 or response.status >= 300:
                raise OSError(f"Unexpected HTTP status {response.status} for {TLC_ZONE_LOOKUP_URL}")
            while chunk := response.read(_CHUNK_SIZE):
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if partial_path.stat().st_size == 0:
            raise OSError("Downloaded an empty TLC taxi zone lookup.")
        os.replace(partial_path, destination)
    finally:
        partial_path.unlink(missing_ok=True)

    logger.info(
        "zones.extract.completed",
        extra={"source_file": destination.name, "bytes": destination.stat().st_size},
    )
    return destination
