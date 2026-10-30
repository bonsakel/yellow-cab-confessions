"""Tests for weather fetching, local-hour normalization, and object caching."""

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

import pytest
from tenacity import wait_none

from ycc.config import Settings
from ycc.extract import weather
from ycc.load.weather import load_weather_year


def _archive_payload(year: int) -> dict[str, object]:
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 3, tzinfo=UTC)
    times = []
    current = start
    while current < end:
        times.append(current.isoformat(timespec="minutes"))
        current += timedelta(hours=1)
    fields = {
        "temperature_2m": [10.0] * len(times),
        "precipitation": [0.0] * len(times),
        "rain": [0.0] * len(times),
        "snowfall": [0.0] * len(times),
        "wind_speed_10m": [5.0] * len(times),
        "weather_code": [0] * len(times),
    }
    fallback_hours = [
        index
        for index, timestamp in enumerate(times)
        if timestamp.startswith(f"{year}-11-03T05:") or timestamp.startswith(f"{year}-11-03T06:")
    ]
    assert len(fallback_hours) == 2
    fields["temperature_2m"][fallback_hours[0]] = 10.0
    fields["temperature_2m"][fallback_hours[1]] = 14.0
    fields["precipitation"][fallback_hours[0]] = 1.0
    fields["precipitation"][fallback_hours[1]] = 3.0
    fields["rain"][fallback_hours[0]] = 1.0
    fields["rain"][fallback_hours[1]] = 3.0
    return {"hourly": {"time": times, **fields}}


class _MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, str] = {}
        self.uploads: list[tuple[str, str]] = []

    def object_matches(self, key: str, sha256: str) -> bool:
        return self.objects.get(key) == sha256

    def upload_file(
        self,
        path: Path,
        key: str,
        *,
        sha256: str,
        source_etag: str | None,
        content_type: str = "application/vnd.apache.parquet",
    ) -> None:
        self.objects[key] = sha256
        assert path.is_file()
        self.uploads.append((key, content_type))


def test_weather_local_hours_aggregate_fall_back_hour() -> None:
    rows = weather._hourly_rows(_archive_payload(2024), 2024)

    assert len(rows) == 8784
    fallback = next(row for row in rows if row["local_hour"] == datetime(2024, 11, 3, 1))
    assert fallback["temperature_2m"] == 12
    assert fallback["precipitation"] == 3
    assert fallback["rain"] == 3


def test_weather_extraction_retries_and_caches_uploaded_objects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def fake_download(year: int, destination: Path) -> None:
        nonlocal calls
        calls += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(_archive_payload(year)), encoding="utf-8")

    settings = Settings(
        _env_file=None,
        year=2024,
        duckdb_path=tmp_path / "warehouse.duckdb",
        work_dir=tmp_path,
    )
    storage = _MemoryStorage()
    monkeypatch.setattr(weather, "_download_weather_json", fake_download)

    json_path, parquet_path = weather.extract_weather_year(settings, storage)
    first_uploads = len(storage.uploads)
    weather.extract_weather_year(settings, storage)

    assert json_path.is_file()
    assert parquet_path.is_file()
    assert calls == 1
    assert first_uploads == 2
    assert len(storage.uploads) == first_uploads
    assert load_weather_year(settings) == 8784
    assert load_weather_year(settings) == 8784


def test_weather_http_download_retries_network_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0
    requests: list[Request] = []

    class _Response(io.BytesIO):
        status = 200

    def fake_urlopen(request: Request, *, timeout: int) -> _Response:
        nonlocal calls
        calls += 1
        requests.append(request)
        assert timeout == 60
        if calls == 1:
            raise URLError("temporary network failure")
        return _Response(b'{"hourly":{}}')

    monkeypatch.setattr(weather, "urlopen", fake_urlopen)
    monkeypatch.setattr(weather._download_weather_json.retry, "wait", wait_none())
    target = tmp_path / "open_meteo.json"

    weather._download_weather_json(2024, target)

    assert calls == 2
    assert requests[0].full_url == requests[1].full_url
    assert "timezone=UTC" in requests[0].full_url
    assert target.read_bytes() == b'{"hourly":{}}'
