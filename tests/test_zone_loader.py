"""Tests for loading the TLC taxi zone lookup."""

from pathlib import Path

import duckdb

from ycc.config import Settings
from ycc.load.zones import load_zone_lookup


def test_loads_zone_lookup_with_normalized_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "taxi_zone_lookup.csv"
    csv_path.write_text(
        "LocationID,Borough,Zone,service_zone\n1,EWR,Newark Airport,EWR\n264,Unknown,Unknown,N/A\n",
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        duckdb_path=tmp_path / "warehouse.duckdb",
        work_dir=tmp_path,
    )

    assert load_zone_lookup(settings, csv_path) == 2

    connection = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        rows = connection.execute(
            """
            select location_id, borough, zone, service_zone
            from raw.taxi_zone_lookup
            order by location_id
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        (1, "EWR", "Newark Airport", "EWR"),
        (264, "Unknown", "Unknown", "N/A"),
    ]
