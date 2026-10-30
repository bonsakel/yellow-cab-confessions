"""Weather effects on taxi demand, fares, and credit-card tip percentages."""

import pandas as pd
import plotly.express as px
import streamlit as st
from components.data import load_mart
from components.ui import configure_page, footer, number, signed_percent

configure_page("The Rain Tax")
data = load_mart("rain_tax")
borough_options = ["All boroughs", *sorted(data["pickup_borough"].dropna().unique())]
filters = st.columns(2)
with filters[0]:
    selected_borough = st.selectbox("Pickup borough", borough_options)
with filters[1]:
    hour_range = st.slider("Pickup hour (local NYC time)", 0, 23, (0, 23))

filtered = data.loc[data["hour_of_day"].between(hour_range[0], hour_range[1])]
if selected_borough != "All boroughs":
    filtered = filtered.loc[filtered["pickup_borough"] == selected_borough]

if filtered.empty:
    st.info("No clean trips match those filters. Try another borough or hour.")
    footer()
    st.stop()

summary_rows = []
for bucket, group in filtered.groupby("weather_bucket", dropna=False):
    trips = float(group["trips"].sum())
    observed_days = float(group["observed_days"].sum())
    expected_dry = float((group["dry_avg_trips_per_day"] * group["observed_days"]).fillna(0).sum())
    row: dict[str, float | str] = {
        "weather_bucket": str(bucket),
        "avg_trips_per_day": trips / observed_days if observed_days else 0.0,
        "demand_vs_dry_pct": (trips / expected_dry - 1) * 100 if expected_dry else 0.0,
    }
    for metric, weight in (
        ("avg_fare", "trips"),
        ("avg_tip_pct", "credit_card_tip_trips"),
        ("avg_speed_mph", "speed_trips"),
    ):
        valid = group.loc[group[metric].notna() & group[weight].gt(0)]
        total_weight = float(valid[weight].sum())
        row[metric] = (
            float((valid[metric] * valid[weight]).sum() / total_weight) if total_weight else 0.0
        )
    summary_rows.append(row)

summary = pd.DataFrame(summary_rows)
columns = st.columns(4)
for column, (bucket, label, metric_name, decimals, suffix) in zip(
    columns,
    (
        ("heavy_rain", "Heavy-rain demand change", "demand_vs_dry_pct", 1, "%"),
        ("heavy_rain", "Heavy-rain average fare", "avg_fare", 2, ""),
        ("heavy_rain", "Heavy-rain card tip %", "avg_tip_pct", 1, "%"),
        ("heavy_rain", "Heavy-rain average speed", "avg_speed_mph", 1, " mph"),
    ),
    strict=True,
):
    row = summary.loc[summary["weather_bucket"] == bucket]
    value = row[metric_name].iloc[0] if not row.empty else None
    formatted = (
        signed_percent(value)
        if metric_name == "demand_vs_dry_pct"
        else f"{number(value, decimals)}{suffix}"
    )
    column.metric(label, formatted)

st.subheader("Weather changes the meter")
chart_columns = st.columns(2)
with chart_columns[0]:
    st.plotly_chart(
        px.bar(
            summary,
            x="weather_bucket",
            y="demand_vs_dry_pct",
            color="weather_bucket",
            title="Demand vs. dry baseline",
            labels={"weather_bucket": "Weather", "demand_vs_dry_pct": "Change (%)"},
            color_discrete_map={
                "dry": "#A7B0B5",
                "light_rain": "#58A6D6",
                "moderate_rain": "#3478A6",
                "heavy_rain": "#24527A",
                "snow": "#B7DCEB",
            },
        ),
        width="stretch",
    )
with chart_columns[1]:
    st.plotly_chart(
        px.bar(
            summary,
            x="weather_bucket",
            y="avg_fare",
            color="weather_bucket",
            title="Average fare by weather",
            labels={"weather_bucket": "Weather", "avg_fare": "Fare (USD)"},
        ),
        width="stretch",
    )

metric_columns = st.columns(2)
with metric_columns[0]:
    st.plotly_chart(
        px.bar(
            summary,
            x="weather_bucket",
            y="avg_tip_pct",
            color="weather_bucket",
            title="Average credit-card tip percentage",
            labels={"weather_bucket": "Weather", "avg_tip_pct": "Tip (%)"},
        ),
        width="stretch",
    )
with metric_columns[1]:
    st.plotly_chart(
        px.bar(
            summary,
            x="weather_bucket",
            y="avg_speed_mph",
            color="weather_bucket",
            title="Average trip speed",
            labels={"weather_bucket": "Weather", "avg_speed_mph": "Speed (mph)"},
        ),
        width="stretch",
    )
st.caption(
    "Tip percentages use credit-card trips only; cash tips are not reported. "
    "Demand compares observed weather hours with the same-hour, same-borough dry baseline."
)
footer()
