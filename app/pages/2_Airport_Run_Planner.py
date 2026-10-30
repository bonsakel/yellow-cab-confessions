"""Historical airport trip-duration and fare planner."""

import plotly.express as px
import streamlit as st
from components.data import load_mart
from components.ui import configure_page, footer, number

configure_page("Airport Run Planner")
data = load_mart("airport_runs")
filters = st.columns(3)
with filters[0]:
    airport = st.selectbox("Airport", ["JFK", "LGA", "EWR"])
with filters[1]:
    direction = st.selectbox("Direction", ["to_airport", "from_airport"])
with filters[2]:
    day_type = st.selectbox("Day type", ["weekday", "weekend", "holiday"])

matched = data.loc[
    (data["airport"] == airport) & (data["direction"] == direction) & (data["day_type"] == day_type)
]
boroughs = sorted(matched["other_end_borough"].dropna().unique())
if not boroughs:
    st.info("No trips match those airport and day-type filters.")
    footer()
    st.stop()
other_borough = st.selectbox("Other-end borough", boroughs)
matched = matched.loc[matched["other_end_borough"] == other_borough]
hour_counts = matched.groupby("hour_of_day")["trips"].sum()
default_hour = int(hour_counts.idxmax())
selected_hour = st.slider("Pickup hour", 0, 23, default_hour)

hour_row = matched.loc[matched["hour_of_day"] == selected_hour]
if hour_row.empty:
    st.info("No recorded trips in that hour for this historical slice.")
else:
    values = hour_row.iloc[0]
    metric_columns = st.columns(3)
    metric_columns[0].metric(
        "Typical duration (p50)", f"{number(values['duration_p50_min'], 1)} min"
    )
    metric_columns[1].metric(
        "Duration p10-p90",
        f"{number(values['duration_p10_min'], 1)}-{number(values['duration_p90_min'], 1)} min",
    )
    metric_columns[2].metric(
        "Fare p10-p90",
        f"${number(values['fare_p10'], 2)}-${number(values['fare_p90'], 2)}",
    )

hourly = matched.sort_values("hour_of_day")
if hourly.empty:
    st.info("No hourly profile is available for this selection.")
else:
    best = hourly.loc[hourly["duration_p50_min"].idxmin()]
    st.markdown(
        f"**Best observed time to leave:** around **{int(best['hour_of_day']):02d}:00** "
        f"for the lowest historical median of **{number(best['duration_p50_min'], 1)} minutes**."
    )
    st.plotly_chart(
        px.bar(
            hourly,
            x="hour_of_day",
            y="duration_p50_min",
            hover_data=["trips", "duration_p10_min", "duration_p90_min"],
            title="Historical median duration across the day",
            labels={"hour_of_day": "Pickup hour", "duration_p50_min": "Median minutes"},
        ),
        width="stretch",
    )

st.caption(
    "A historical estimate from the selected other-end borough and day type—not live traffic, "
    "a guaranteed travel time, or a fare quote."
)
footer()
