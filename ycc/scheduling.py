"""Month selection for scheduled and manual pipeline runs."""

from collections.abc import Sequence

from ycc.extract.tlc import validate_month


def resolve_months(
    requested_months: object | None,
    scheduled_month: str | None,
    configured_year: int,
) -> list[str] | None:
    """Return validated months, or None when a schedule falls outside the data year."""
    if requested_months:
        if isinstance(requested_months, str) or not isinstance(
            requested_months,
            Sequence,
        ):
            raise ValueError("Months must be provided as a list of YYYY-MM values.")
        requested = list(requested_months)
        if not requested or any(not isinstance(month, str) for month in requested):
            raise ValueError("Provide at least one YYYY-MM month.")
        months = list(dict.fromkeys(requested))
        for month in months:
            year, _ = validate_month(month)
            if year != configured_year:
                raise ValueError(f"Month {month} does not match configured year {configured_year}.")
        return months

    if scheduled_month is None:
        raise ValueError("A scheduled run requires a month in its data interval.")
    year, _ = validate_month(scheduled_month)
    if year != configured_year:
        return None
    return [scheduled_month]
