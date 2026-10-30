"""Compare taxi zones and visualize their busiest connecting flows."""

import copy

import pydeck as pdk
import streamlit as st
from components.data import load_mart, load_zone_geojson
from components.ui import configure_page, footer, number

configure_page("Zone vs Zone")
zones = load_mart("zone_summary")
pairs = load_mart("zone_pairs")
zone_ids = [int(value) for value in zones["zone_id"].dropna().sort_values().unique()]
zone_names = zones.set_index("zone_id")["zone_name"].to_dict()

if not zone_ids:
    st.info("No zone summaries are available.")
    footer()
    st.stop()

if "zone_a_id" not in st.session_state or "zone_b_id" not in st.session_state:
    distinct_pairs = pairs.loc[pairs["pickup_zone_id"] != pairs["dropoff_zone_id"]]
    if not distinct_pairs.empty:
        default_pair = distinct_pairs.sort_values("trips", ascending=False).iloc[0]
        st.session_state.setdefault("zone_a_id", int(default_pair["pickup_zone_id"]))
        st.session_state.setdefault("zone_b_id", int(default_pair["dropoff_zone_id"]))
    else:
        st.session_state.setdefault("zone_a_id", zone_ids[0])
        st.session_state.setdefault("zone_b_id", zone_ids[min(1, len(zone_ids) - 1)])

if not pairs.empty and st.button("🎲 Surprise me with a fast flow"):
    surprise = pairs.sort_values(["avg_speed_mph", "trips"], ascending=False).iloc[0]
    st.session_state["zone_a_id"] = int(surprise["pickup_zone_id"])
    st.session_state["zone_b_id"] = int(surprise["dropoff_zone_id"])

zone_columns = st.columns(2)
with zone_columns[0]:
    pickup_id = st.selectbox(
        "First zone",
        zone_ids,
        format_func=lambda value: f"{zone_names[value]} ({value})",
        key="zone_a_id",
    )
with zone_columns[1]:
    dropoff_id = st.selectbox(
        "Second zone",
        zone_ids,
        format_func=lambda value: f"{zone_names[value]} ({value})",
        key="zone_b_id",
    )

stats = zones.set_index("zone_id")
for column, zone_id in zip(zone_columns, (pickup_id, dropoff_id), strict=True):
    row = stats.loc[zone_id]
    with column:
        st.subheader(f"{row['zone_name']} · {row['borough']}")
        metrics = st.columns(2)
        metrics[0].metric("Pickups", number(row["pickup_trips"]))
        metrics[1].metric("Drop-offs", number(row["dropoff_trips"]))
        metrics[0].metric("Average fare", f"${number(row['avg_fare'], 2)}")
        metrics[1].metric("Average speed", f"{number(row['avg_speed_mph'], 1)} mph")
        metrics[0].metric("Card tip %", f"{number(row['avg_tip_pct'], 1)}%")

pair = pairs.loc[(pairs["pickup_zone_id"] == pickup_id) & (pairs["dropoff_zone_id"] == dropoff_id)]
if pair.empty:
    st.info("Fewer than 30 clean trips connect these zones in this direction.")
else:
    row = pair.iloc[0]
    st.markdown(
        f"**{number(row['trips'])} rides** went from {row['pickup_zone']} to "
        f"{row['dropoff_zone']}; average fare **${number(row['avg_fare'], 2)}**, "
        f"duration **{number(row['avg_duration_min'], 1)} min**, "
        f"credit-card tip percentage **{number(row['avg_tip_pct'], 1)}%**."
    )

coordinates = zones[["zone_id", "centroid_lat", "centroid_lon"]].dropna().copy()
pickup_coordinates = coordinates.rename(
    columns={
        "zone_id": "pickup_zone_id",
        "centroid_lat": "pickup_lat",
        "centroid_lon": "pickup_lon",
    }
)
dropoff_coordinates = coordinates.rename(
    columns={
        "zone_id": "dropoff_zone_id",
        "centroid_lat": "dropoff_lat",
        "centroid_lon": "dropoff_lon",
    }
)
flows = (
    pairs.loc[
        pairs["pickup_zone_id"].isin([pickup_id, dropoff_id])
        | pairs["dropoff_zone_id"].isin([pickup_id, dropoff_id])
    ]
    .sort_values("trips", ascending=False)
    .head(80)
)
flows = flows.merge(pickup_coordinates, on="pickup_zone_id").merge(
    dropoff_coordinates, on="dropoff_zone_id"
)

geojson = copy.deepcopy(load_zone_geojson())
for feature in geojson["features"]:
    selected = int(feature["properties"]["LocationID"]) in {pickup_id, dropoff_id}
    feature["properties"]["fill_color"] = [245, 200, 66, 150] if selected else [68, 82, 92, 75]

layers = [
    pdk.Layer(
        "GeoJsonLayer",
        data=geojson,
        id="taxi-zones",
        stroked=True,
        filled=True,
        get_fill_color="properties.fill_color",
        get_line_color=[190, 200, 205, 100],
        line_width_min_pixels=0.5,
        pickable=True,
    )
]
if not flows.empty:
    layers.append(
        pdk.Layer(
            "ArcLayer",
            data=flows,
            id="zone-flows",
            get_source_position="[pickup_lon, pickup_lat]",
            get_target_position="[dropoff_lon, dropoff_lat]",
            get_source_color=[245, 200, 66, 160],
            get_target_color=[81, 194, 169, 180],
            get_width=3,
            pickable=True,
        )
    )
st.pydeck_chart(
    pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=40.73,
            longitude=-73.9,
            zoom=9,
            pitch=35,
        ),
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={"text": "{zone}\n{borough}"},
    ),
    width="stretch",
)
st.caption(
    "Zone centers are approximate centroids. Flows show the busiest qualifying "
    "zone pairs that touch either selected zone."
)
footer()
