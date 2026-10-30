"""Cached loading of the app's committed, warehouse-independent data files."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

APP_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MART_FILES = {
    "airport_runs": "mart_airport_runs.parquet",
    "blooper_counts": "mart_blooper_counts.parquet",
    "blooper_examples": "mart_blooper_examples.parquet",
    "night_city": "mart_night_city.parquet",
    "rain_tax": "mart_rain_tax.parquet",
    "zone_pairs": "mart_zone_pairs.parquet",
    "zone_summary": "mart_zone_summary.parquet",
}


@st.cache_data(show_spinner=False)
def load_mart(name: str) -> pd.DataFrame:
    """Load one known app mart from the local data directory."""
    if name not in MART_FILES:
        raise ValueError(f"Unknown app mart: {name}")
    path = APP_DATA_DIR / MART_FILES[name]
    if not path.is_file():
        raise FileNotFoundError(f"App mart is missing: {path}")
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False)
def load_confessions() -> dict[str, Any]:
    """Load computed headline metrics exported from the warehouse."""
    path = APP_DATA_DIR / "confessions.json"
    if not path.is_file():
        raise FileNotFoundError(f"Confession metrics are missing: {path}")
    with path.open(encoding="utf-8") as file:
        return json.load(file)


@st.cache_data(show_spinner=False)
def load_zone_geojson() -> dict[str, Any]:
    """Load the simplified WGS84 zone polygons for the app maps."""
    path = APP_DATA_DIR / "zones.geojson"
    if not path.is_file():
        raise FileNotFoundError(f"Taxi-zone geometry is missing: {path}")
    with path.open(encoding="utf-8") as file:
        return json.load(file)


@st.cache_data(show_spinner=False)
def load_pipeline_runs() -> pd.DataFrame | None:
    """Load pipeline history when available, otherwise report no published runs."""
    path = APP_DATA_DIR / "pipeline_runs.parquet"
    if not path.is_file():
        return None
    return pd.read_parquet(path)
