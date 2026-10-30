"""Generation of the United States and New York holiday dbt seed."""

import csv
import logging
from pathlib import Path

import holidays

from ycc.config import Settings

logger = logging.getLogger(__name__)


def generate_holiday_seed(settings: Settings, year: int | None = None) -> Path:
    """Write observed US and New York state holidays for the configured year."""
    selected_year = year if year is not None else settings.year
    if not 1 <= selected_year <= 9998:
        raise ValueError(f"Holiday year must be between 1 and 9998: {selected_year}.")

    destination = settings.dbt_project_dir / "seeds" / "us_holidays.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    calendar = holidays.country_holidays("US", subdiv="NY", years=selected_year)
    with destination.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("date", "holiday_name"))
        writer.writerows(
            (holiday_date.isoformat(), name) for holiday_date, name in sorted(calendar.items())
        )

    logger.info(
        "holidays.seed.generated",
        extra={"year": selected_year, "holiday_rows": len(calendar), "path": str(destination)},
    )
    return destination
