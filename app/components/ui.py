"""Shared page framing and display helpers."""

import streamlit as st

REPOSITORY_URL = "https://github.com/bonsakel/yellow-cab-confessions"


def configure_page(title: str) -> None:
    """Apply the shared page configuration, header, and title."""
    st.set_page_config(page_title=f"{title} | Yellow Cab Confessions", layout="wide")
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1440px;}
        [data-testid="stMetricValue"] {color: #F5C842;}
        a {color: #F5C842 !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### 🚕 Yellow Cab Confessions")
    st.caption("40 million rides. Every one has a story. Some of them are lies.")
    st.header(title)


def footer() -> None:
    """Render the project repository and required source attributions."""
    st.divider()
    st.caption(
        f"[Project repository]({REPOSITORY_URL}) · "
        "[NYC TLC trip data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) · "
        "[Open-Meteo](https://open-meteo.com/en/terms) · "
        "Holiday dates from the Python `holidays` library."
    )


def number(value: object, decimals: int = 0) -> str:
    """Format a finite numeric value for display."""
    if value is None:
        return "—"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "—"
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        return "—"
    return f"{numeric:,.{decimals}f}"


def signed_percent(value: object) -> str:
    """Format a percentage change with its sign."""
    if value is None:
        return "unavailable"
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "unavailable"
