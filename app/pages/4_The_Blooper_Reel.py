"""Explore quarantined records and verify raw-to-clean reconciliation."""

import plotly.express as px
import streamlit as st
from components.data import load_confessions, load_mart
from components.ui import configure_page, footer, number

RULE_CAPTIONS = {
    "NEGATIVE_FARE": "The meter went below zero. Nobody's that generous.",
    "DROPOFF_BEFORE_PICKUP": "This cab dropped you off before it picked you up.",
    "ZERO_DURATION": "A long ride completed in no time. Sure, pal.",
    "ABSURD_DURATION": "Six hours in one cab. Hope the radio was good.",
    "ZERO_DISTANCE_PAID": "The cab didn't move, but the meter sure did.",
    "ABSURD_DISTANCE": "A hundred-mile city trip? That's one ambitious fare.",
    "TELEPORTING_CAB": "That average speed belongs in science fiction.",
    "OUT_OF_RANGE_DATE": "This ride wandered outside the month in its own file.",
    "BAD_PASSENGER_COUNT": "More than eight passengers squeezed into one cab.",
    "UNKNOWN_ZONE": "The pickup or drop-off zone isn't in the TLC lookup.",
    "DUPLICATE_TRIP": "A copycat ride; the first record keeps its seat.",
}

configure_page("The Blooper Reel")
confessions = load_confessions()
counts = load_mart("blooper_counts")
examples = load_mart("blooper_examples")
clean = int(confessions["clean_trips"])
quarantined = int(confessions["quarantined_trips"])
raw = clean + quarantined

st.subheader("The reconciliation guarantee")
funnel = st.columns(3)
funnel[0].metric("Raw rows", number(raw))
funnel[1].metric("Clean rows", number(clean))
funnel[2].metric("Quarantined rows", number(quarantined))
st.success(
    f"{number(raw)} raw = {number(clean)} clean + {number(quarantined)} quarantined. "
    "Nothing quietly disappeared."
)

chart = px.bar(
    counts,
    x="source_month",
    y="rejected_trips",
    color="reason_code",
    barmode="stack",
    title="Rejections by rule and source month",
    labels={"source_month": "Source month", "rejected_trips": "Trips", "reason_code": "Rule"},
)
st.plotly_chart(chart, width="stretch")

rules = sorted(examples["reason_code"].dropna().unique())
if not rules:
    st.info("No rejected examples are available for this run.")
else:
    selected_rule = st.selectbox("Browse the weirdest records", rules)
    st.markdown(
        f"**{selected_rule}:** "
        f"{RULE_CAPTIONS.get(selected_rule, 'This trip broke a data-quality rule.')}"
    )
    selected_examples = examples.loc[examples["reason_code"] == selected_rule].sort_values(
        "example_rank"
    )
    display_columns = [
        "example_rank",
        "source_month",
        "pickup_datetime",
        "dropoff_datetime",
        "pickup_location_id",
        "dropoff_location_id",
        "passenger_count",
        "trip_distance",
        "fare_amount",
        "total_amount",
        "weirdness_score",
        "reject_reasons",
    ]
    st.dataframe(
        selected_examples[display_columns],
        width="stretch",
        hide_index=True,
    )

footer()
