"""Tests for scheduled and manually requested pipeline months."""

import pytest

from ycc.scheduling import resolve_months


def test_resolve_months_uses_the_scheduled_month_for_configured_year() -> None:
    assert resolve_months(None, "2024-07", 2024) == ["2024-07"]


def test_resolve_months_accepts_manual_months_without_a_schedule_interval() -> None:
    assert resolve_months(["2024-01"], None, 2024) == ["2024-01"]


def test_resolve_months_skips_schedules_outside_configured_year() -> None:
    assert resolve_months(None, "2025-01", 2024) is None


def test_resolve_months_deduplicates_and_validates_manual_backfills() -> None:
    assert resolve_months(["2024-02", "2024-01", "2024-02"], "2024-07", 2024) == [
        "2024-02",
        "2024-01",
    ]


@pytest.mark.parametrize(
    "requested",
    [
        "2024-01",
        ["2024-13"],
        ["2023-12"],
        [""],
    ],
)
def test_resolve_months_rejects_invalid_manual_backfills(requested: object) -> None:
    with pytest.raises(ValueError):
        resolve_months(requested, "2024-07", 2024)


def test_resolve_months_rejects_non_string_values() -> None:
    with pytest.raises(ValueError):
        resolve_months([2024], "2024-07", 2024)
