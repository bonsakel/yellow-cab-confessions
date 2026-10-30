"""Tests for compressed mart exports and the app-data size budget."""

import json
from pathlib import Path

import duckdb
import pytest

from ycc.config import Settings
from ycc.export.marts_to_parquet import MARTS, export_marts


def _warehouse(path: Path, clean_rows: int = 3) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute("CREATE SCHEMA core")
        connection.execute("CREATE SCHEMA quarantine")
        connection.execute("CREATE SCHEMA marts")
        connection.execute(
            """
            CREATE TABLE core.fct_trips (
                trip_distance DOUBLE,
                tip_amount DOUBLE,
                payment_type INTEGER,
                is_unknown_zone BOOLEAN
            )
            """
        )
        connection.executemany(
            "INSERT INTO core.fct_trips VALUES (?, ?, ?, ?)",
            [(2.5, 1.0, 1, False)] * clean_rows,
        )
        connection.execute("CREATE TABLE quarantine.quarantine_trips (trip_id INTEGER)")
        connection.execute("INSERT INTO quarantine.quarantine_trips VALUES (1), (2)")
        connection.execute(
            """
            CREATE TABLE marts.mart_rain_tax (
                weather_bucket VARCHAR,
                trips INTEGER,
                observed_days INTEGER,
                avg_tip_pct DOUBLE,
                credit_card_trips INTEGER,
                credit_card_tip_trips INTEGER,
                speed_trips INTEGER,
                dry_avg_trips_per_day DOUBLE
            )
            """
        )
        connection.execute(
            """
            INSERT INTO marts.mart_rain_tax VALUES
                ('dry', 40, 10, 10.0, 20, 20, 40, 4.0),
                ('heavy_rain', 12, 2, 8.0, 4, 4, 12, 4.0)
            """
        )
        for mart in MARTS:
            if mart == "mart_rain_tax":
                continue
            connection.execute(f"CREATE TABLE marts.{mart} (value INTEGER)")
            connection.execute(f"INSERT INTO marts.{mart} VALUES (1)")
    finally:
        connection.close()
    (path.parent / "zones.geojson").write_text(
        '{"type":"FeatureCollection","features":[]}\n',
        encoding="utf-8",
    )


def test_exports_each_mart_and_data_derived_confessions(tmp_path: Path) -> None:
    warehouse = tmp_path / "warehouse.duckdb"
    output = tmp_path / "app" / "data"
    _warehouse(warehouse)
    settings = Settings(
        _env_file=None,
        year=2024,
        duckdb_path=warehouse,
        app_data_dir=output,
        work_dir=tmp_path,
    )

    result = export_marts(settings)

    assert set(result.files) == {
        *[f"{mart}.parquet" for mart in MARTS],
        "confessions.json",
        "zones.geojson",
    }
    assert result.total_bytes == sum(result.files.values())
    assert result.total_bytes < 50 * 1024 * 1024
    assert all((output / name).is_file() for name in result.files)
    confessions = json.loads((output / "confessions.json").read_text(encoding="utf-8"))
    assert confessions["clean_trips"] == 3
    assert confessions["quarantined_trips"] == 2
    assert confessions["total_miles"] == 7.5
    assert confessions["rain_vs_dry_demand_pct"] == 50
    assert confessions["rain_vs_dry_tip_pct_change"] == pytest.approx(-20)
    assert (output / "zones.geojson").read_text(encoding="utf-8").startswith("{")
    parquet = duckdb.connect()
    try:
        for mart in MARTS:
            rows = parquet.execute(
                "SELECT count(*) FROM read_parquet(?)",
                [str(output / f"{mart}.parquet")],
            ).fetchone()[0]
            assert rows >= 1
    finally:
        parquet.close()


def test_export_fails_over_budget_without_replacing_existing_exports(tmp_path: Path) -> None:
    warehouse = tmp_path / "warehouse.duckdb"
    output = tmp_path / "app" / "data"
    _warehouse(warehouse)
    output.mkdir(parents=True)
    existing = output / "confessions.json"
    existing.write_text('{"existing":true}\n', encoding="utf-8")
    connection = duckdb.connect(str(warehouse))
    try:
        connection.execute("DROP TABLE marts.mart_zone_pairs")
        connection.execute(
            """
            CREATE TABLE marts.mart_zone_pairs AS
            SELECT repeat(md5(cast(i AS varchar)), 4) AS value
            FROM range(100000) AS generated(i)
            """
        )
    finally:
        connection.close()
    settings = Settings(
        _env_file=None,
        duckdb_path=warehouse,
        app_data_dir=output,
        export_size_budget_mb=1,
        work_dir=tmp_path,
    )

    with pytest.raises(ValueError, match="exceeding the 1 MiB budget"):
        export_marts(settings)

    assert existing.read_text(encoding="utf-8") == '{"existing":true}\n'
    assert sorted(path.name for path in output.iterdir()) == ["confessions.json"]


def test_export_replaces_existing_geojson_before_checking_budget(tmp_path: Path) -> None:
    warehouse = tmp_path / "warehouse.duckdb"
    output = tmp_path / "app" / "data"
    _warehouse(warehouse)
    output.mkdir(parents=True)
    asset = output / "zones.geojson"
    asset.write_bytes(b"x" * (1024 * 1024))
    settings = Settings(
        _env_file=None,
        duckdb_path=warehouse,
        app_data_dir=output,
        export_size_budget_mb=1,
        work_dir=tmp_path,
    )

    result = export_marts(settings)

    assert result.total_bytes == sum(result.files.values())
    assert asset.read_text(encoding="utf-8") == (tmp_path / "zones.geojson").read_text(
        encoding="utf-8"
    )


def test_export_budget_counts_retained_app_files(tmp_path: Path) -> None:
    warehouse = tmp_path / "warehouse.duckdb"
    output = tmp_path / "app" / "data"
    _warehouse(warehouse)
    output.mkdir(parents=True)
    retained = output / "other_asset.bin"
    retained.write_bytes(b"x" * (1024 * 1024))
    settings = Settings(
        _env_file=None,
        duckdb_path=warehouse,
        app_data_dir=output,
        export_size_budget_mb=1,
        work_dir=tmp_path,
    )

    with pytest.raises(ValueError, match="exceeding the 1 MiB budget"):
        export_marts(settings)

    assert retained.stat().st_size == 1024 * 1024
    assert sorted(path.name for path in output.iterdir()) == ["other_asset.bin"]
