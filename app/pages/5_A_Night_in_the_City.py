"""Explore pickup flows in ten-minute windows through featured NYC nights."""

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st
from components.data import load_mart
from components.ui import configure_page, footer, number

configure_page("A Night in the City")
data = load_mart("night_city")
if data.empty:
    st.info("No featured-night trips are present in this export.")
    footer()
    st.stop()

night_names = sorted(data["night_name"].dropna().unique())
night_name = st.selectbox("Featured night", night_names)
night = data.loc[data["night_name"] == night_name].copy()
night["time_bin"] = pd.to_datetime(night["time_bin"])
time_bins = sorted(pd.Timestamp(value) for value in night["time_bin"].dropna().unique())
if not time_bins:
    st.info("There are no ten-minute flow bins for this night.")
    footer()
    st.stop()

if st.session_state.get("selected_night") != night_name:
    st.session_state["selected_night"] = night_name
    st.session_state["night_time_index"] = 0
st.session_state["night_time_index"] = min(
    int(st.session_state.get("night_time_index", 0)),
    len(time_bins) - 1,
)
st.session_state.setdefault("night_playing", False)
playback_label = "⏸ Pause playback" if st.session_state["night_playing"] else "▶ Play night"


def toggle_playback() -> None:
    st.session_state["night_playing"] = not st.session_state["night_playing"]


st.button(playback_label, on_click=toggle_playback)


@st.fragment(run_every=1 if st.session_state["night_playing"] else None)
def render_time_bin() -> None:
    if st.session_state["night_playing"] and len(time_bins) > 1:
        st.session_state["night_time_index"] = (st.session_state["night_time_index"] + 1) % len(
            time_bins
        )
    if len(time_bins) == 1:
        selected_index = 0
        st.caption("Only one time bin is available for this night.")
    else:
        selected_index = st.slider(
            "Time bin",
            min_value=0,
            max_value=len(time_bins) - 1,
            key="night_time_index",
            format="%d",
        )
    selected_bin = time_bins[selected_index]
    current = night.loc[night["time_bin"] == selected_bin]
    ride_count = int(current["trips"].sum())
    st.metric("Rides starting in this 10-minute block", number(ride_count))
    st.caption(
        f"{night_name} · {selected_bin:%H:%M}-"
        f"{(selected_bin + pd.Timedelta(minutes=10)):%H:%M} local time"
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=[
                pdk.Layer(
                    "ArcLayer",
                    data=current,
                    id="night-flows",
                    get_source_position="[pickup_lon, pickup_lat]",
                    get_target_position="[dropoff_lon, dropoff_lat]",
                    get_source_color=[245, 200, 66, 180],
                    get_target_color=[81, 194, 169, 200],
                    get_width=4,
                    pickable=True,
                    auto_highlight=True,
                )
            ],
            initial_view_state=pdk.ViewState(
                latitude=40.73,
                longitude=-73.9,
                zoom=9,
                pitch=40,
            ),
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            tooltip={"text": "{pickup_zone} → {dropoff_zone}\n{trips} rides"},
        ),
        width="stretch",
    )
    if not current.empty:
        flow_chart = px.bar(
            current.nlargest(10, "trips"),
            x="trips",
            y="pickup_zone",
            color="dropoff_zone",
            orientation="h",
            title="Busiest flows in this block",
            labels={
                "trips": "Rides",
                "pickup_zone": "Pickup zone",
                "dropoff_zone": "Drop-off",
            },
        )
        st.plotly_chart(flow_chart, width="stretch")


render_time_bin()
st.caption(
    "The count is trips picked up during the selected historical ten-minute window, "
    "not live vehicles or a real-time count of active rides."
)
footer()
