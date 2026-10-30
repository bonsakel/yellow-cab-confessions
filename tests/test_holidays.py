"""Tests for generated US and New York holiday seeds."""

import csv
from pathlib import Path

from ycc.config import Settings
from ycc.extract.holidays import generate_holiday_seed


def test_generates_new_york_holidays_for_configured_year(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        year=2024,
        dbt_project_dir=tmp_path / "dbt",
        duckdb_path=tmp_path / "warehouse.duckdb",
        work_dir=tmp_path,
    )

    seed_path = generate_holiday_seed(settings)

    with seed_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert seed_path == tmp_path / "dbt" / "seeds" / "us_holidays.csv"
    assert any(row["date"] == "2024-07-04" for row in rows)
    assert all(row["holiday_name"] for row in rows)
