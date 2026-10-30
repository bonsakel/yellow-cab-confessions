"""Home page for Yellow Cab Confessions."""

import streamlit as st
from components.data import load_confessions
from components.ui import configure_page, footer, number, signed_percent

configure_page("The city has receipts")
confessions = load_confessions()

rain_demand = confessions.get("rain_vs_dry_demand_pct")
rain_tips = confessions.get("rain_vs_dry_tip_pct_change")
if rain_demand is None or rain_tips is None:
    st.info("The weather hasn't confessed yet. Run the pipeline to compute its story.")
else:
    st.markdown(
        "**The rain report:** compared with dry hours, rainy hours changed demand by "
        f"**{signed_percent(rain_demand)}** and credit-card tip percentage by "
        f"**{signed_percent(rain_tips)}**. That's what the January demo data says; "
        "the full-year run gets the final word."
    )

stats = st.columns(4)
stats[0].metric("Clean rides", number(confessions.get("clean_trips")))
stats[1].metric("Miles logged", number(confessions.get("total_miles")))
stats[2].metric("Credit-card tips", f"${number(confessions.get('credit_card_tips_usd'))}")
stats[3].metric("Trips quarantined", number(confessions.get("quarantined_trips")))

st.caption("The bundled sample is January 2024; a full-year export will replace these figures.")
st.caption(confessions.get("tip_percentage_note", "Tip percentages use credit-card trips only."))
st.subheader("Pick your ride")
pages = [
    (
        "The Rain Tax",
        "What the weather does to demand, fares, and card tips.",
        "pages/1_The_Rain_Tax.py",
    ),
    (
        "Airport Run Planner",
        "A historical trip window, never a live quote.",
        "pages/2_Airport_Run_Planner.py",
    ),
    (
        "Zone vs Zone",
        "Compare neighborhoods and follow their busiest flows.",
        "pages/3_Zone_vs_Zone.py",
    ),
    (
        "The Blooper Reel",
        "Bad rows, all their reasons, no quiet deletions.",
        "pages/4_The_Blooper_Reel.py",
    ),
    (
        "A Night in the City",
        "Follow rides through a featured NYC night.",
        "pages/5_A_Night_in_the_City.py",
    ),
    (
        "About / Under the Hood",
        "The serious plumbing behind the wisecracks.",
        "pages/6_About.py",
    ),
]
for row_start in range(0, len(pages), 3):
    cards = st.columns(3)
    for column, (title, description, page_path) in zip(
        cards, pages[row_start : row_start + 3], strict=False
    ):
        with column:
            st.markdown(f"#### {title}")
            st.write(description)
            st.page_link(page_path, label=f"Open {title}", icon="🚕")

footer()
