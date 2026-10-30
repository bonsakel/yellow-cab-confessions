"""Extraction and local-time normalization for Open-Meteo archive weather."""

import hashlib
import json
import logging
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import duckdb
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ycc.config import Settings
from ycc.load.s3 import ObjectStorage

logger = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
NYC_TIMEZONE = ZoneInfo("America/New_York")
HOURLY_VARIABLES = (
    "temperature_2m",
    "precipitation",
    "rain",
    "snowfall",
    "wind_speed_10m",
    "weather_code",
)
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
def _download_weather_json(year: int, destination: Path) -> None:
    """Fetch one UTC-bounded archive response and atomically cache its JSON."""
    query = urlencode(
        {
            "latitude": 40.7794,
            "longitude": -73.9692,
            "start_date": f"{year}-01-01",
            "end_date": f"{year + 1}-01-02",
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": "UTC",
            "wind_speed_unit": "kmh",
        }
    )
    request = Request(
        f"{OPEN_METEO_ARCHIVE_URL}?{query}",
        headers={"User-Agent": "YellowCabConfessions/0.1"},
    )
    partial_path = destination.with_suffix(".json.part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=60) as response, partial_path.open("wb") as target:
            if response.status < 200 or response.status >= 300:
                raise OSError(
                    f"Unexpected HTTP status {response.status} for {OPEN_METEO_ARCHIVE_URL}"
                )
            while chunk := response.read(_CHUNK_SIZE):
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        os.replace(partial_path, destination)
    finally:
        partial_path.unlink(missing_ok=True)


def _hourly_rows(payload: dict[str, object], year: int) -> list[dict[str, object]]:
    """Convert UTC response timestamps to unique naive NYC local-hour records."""
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise ValueError("Open-Meteo response is missing its hourly time series.")
    times = hourly["time"]
    if not isinstance(times, list):
        raise ValueError("Open-Meteo hourly time values must be a list.")
    missing = [name for name in HOURLY_VARIABLES if name not in hourly]
    if missing:
        raise ValueError(f"Open-Meteo response is missing hourly variables: {missing}.")
    series: dict[str, list[object]] = {}
    for name in HOURLY_VARIABLES:
        values = hourly[name]
        if not isinstance(values, list) or len(values) != len(times):
            raise ValueError(f"Open-Meteo variable {name!r} does not align with hourly times.")
        series[name] = values

    grouped: dict[datetime, list[dict[str, object]]] = defaultdict(list)
    for index, timestamp in enumerate(times):
        utc_hour = datetime.fromisoformat(str(timestamp)).replace(tzinfo=UTC)
        local_hour = utc_hour.astimezone(NYC_TIMEZONE).replace(tzinfo=None)
        if local_hour.year != year:
            continue
        grouped[local_hour].append({name: series[name][index] for name in HOURLY_VARIABLES})

    year_start = datetime(year, 1, 1)
    year_hours = 24 * 366 if _is_leap_year(year) else 24 * 365
    expected_hours = {year_start + timedelta(hours=offset) for offset in range(year_hours)}
    nonexistent_hours = {
        local_hour
        for local_hour in expected_hours
        if local_hour.replace(tzinfo=NYC_TIMEZONE)
        .astimezone(UTC)
        .astimezone(NYC_TIMEZONE)
        .replace(tzinfo=None)
        != local_hour
    }
    missing = expected_hours - set(grouped)
    extra = set(grouped) - expected_hours
    if missing != nonexistent_hours or extra:
        raise ValueError(
            f"Open-Meteo local-hour coverage is incomplete for {year}: "
            f"{len(missing)} missing, {len(extra)} unexpected."
        )
    for local_hour in nonexistent_hours:
        grouped[local_hour] = []

    rows: list[dict[str, object]] = []
    for local_hour in sorted(grouped):
        observations = grouped[local_hour]
        row: dict[str, object] = {"local_hour": local_hour}
        for field in ("temperature_2m", "wind_speed_10m"):
            values = [float(item[field]) for item in observations if item[field] is not None]
            row[field] = sum(values) / len(values) if values else None
        for field in ("precipitation", "rain", "snowfall"):
            values = [float(item[field]) for item in observations if item[field] is not None]
            row[field] = max(values) if values else None
        codes = [
            int(item["weather_code"]) for item in observations if item["weather_code"] is not None
        ]
        row["weather_code"] = codes[0] if codes else None
        rows.append(row)
    return rows


def _is_leap_year(year: int) -> bool:
    """Return whether a Gregorian calendar year contains February 29."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def extract_weather_year(
    settings: Settings,
    storage: ObjectStorage,
    year: int | None = None,
) -> tuple[Path, Path]:
    """Cache Open-Meteo JSON and a deduplicated local-hour parquet in object storage."""
    selected_year = year if year is not None else settings.year
    if not 1 <= selected_year <= 9998:
        raise ValueError(f"Weather year must be between 1 and 9998: {selected_year}.")

    json_path = settings.download_dir / f"open_meteo_{selected_year}.json"
    parquet_path = settings.download_dir / f"weather_hourly_{selected_year}.parquet"
    if not json_path.is_file() or not parquet_path.is_file():
        _download_weather_json(selected_year, json_path)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Open-Meteo response must be a JSON object.")
        rows = _hourly_rows(payload, selected_year)
        connection = duckdb.connect()
        try:
            connection.execute(
                """
                CREATE TABLE weather_hourly (
                    local_hour TIMESTAMP,
                    temperature_2m DOUBLE,
                    precipitation DOUBLE,
                    rain DOUBLE,
                    snowfall DOUBLE,
                    wind_speed_10m DOUBLE,
                    weather_code INTEGER
                )
                """
            )
            connection.executemany(
                "INSERT INTO weather_hourly VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        row["local_hour"],
                        row["temperature_2m"],
                        row["precipitation"],
                        row["rain"],
                        row["snowfall"],
                        row["wind_speed_10m"],
                        row["weather_code"],
                    )
                    for row in rows
                ],
            )
            connection.execute(
                "COPY weather_hourly TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                [str(parquet_path)],
            )
        finally:
            connection.close()

    for path, key, content_type in (
        (
            json_path,
            f"raw/weather/year={selected_year}/open_meteo_{selected_year}.json",
            "application/json",
        ),
        (
            parquet_path,
            f"raw/weather/year={selected_year}/weather_hourly_{selected_year}.parquet",
            "application/vnd.apache.parquet",
        ),
    ):
        checksum = _sha256_file(path)
        if not storage.object_matches(key, checksum):
            storage.upload_file(
                path,
                key,
                sha256=checksum,
                source_etag=None,
                content_type=content_type,
            )

    logger.info(
        "weather.extract.completed",
        extra={
            "year": selected_year,
            "hourly_rows": _parquet_row_count(parquet_path),
            "json_bytes": json_path.stat().st_size,
            "parquet_bytes": parquet_path.stat().st_size,
        },
    )
    return json_path, parquet_path


def _parquet_row_count(path: Path) -> int:
    """Return the record count stored in a parquet file."""
    connection = duckdb.connect()
    try:
        return int(
            connection.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
        )
    finally:
        connection.close()
