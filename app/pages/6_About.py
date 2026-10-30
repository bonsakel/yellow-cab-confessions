"""Project architecture, data quality, and pipeline history."""

import streamlit as st
from components.data import load_confessions, load_pipeline_runs
from components.ui import REPOSITORY_URL, configure_page, footer, number

configure_page("About / Under the Hood")
st.subheader("A pipeline with a paper trail")
st.code(
    """\
NYC TLC ─┐
Weather ─┼─> Airflow ─> S3-compatible raw files ─> DuckDB
Holidays ┘                                     │
                                               v
                               dbt staging -> quarantine -> star schema -> marts
                                                                        │
                                                                        v
                                                  compressed app/data exports -> Streamlit
""",
    language="text",
)

st.subheader("Run history")
runs = load_pipeline_runs()
if runs is None or runs.empty:
    st.info(
        "No pipeline-run history has been published yet. "
        "The full Airflow workflow will add it to app/data/pipeline_runs.parquet."
    )
else:
    st.dataframe(runs, width="stretch", hide_index=True)

confessions = load_confessions()
clean = int(confessions["clean_trips"])
quarantined = int(confessions["quarantined_trips"])
st.subheader("Data-quality snapshot")
quality = st.columns(3)
quality[0].metric("Raw rows reconciled", number(clean + quarantined))
quality[1].metric("Clean facts", number(clean))
quality[2].metric("Quarantined", number(quarantined))
st.success(f"{number(clean + quarantined)} = {number(clean)} + {number(quarantined)}")

st.subheader("The stack")
st.write(
    "Python keeps business logic testable; Airflow orchestrates it. MinIO provides "
    "local S3-compatible storage, DuckDB is the supported warehouse, dbt owns the "
    "transforms and tests, and Streamlit reads only the small exported files."
)
st.write(
    "Trip timestamps are naive NYC local time. Weather timestamps are converted to "
    "the same wall-clock hour; the duplicated daylight-saving fall-back hour is "
    "aggregated to keep the weather dimension unique."
)
st.write(
    "Tip percentages use credit-card trips only. Cash tips are not reported by TLC. "
    "Weather comes from one Central Park station and is not a citywide measurement."
)
st.write(
    "DuckDB is the supported warehouse target. The optional Snowflake profile is a "
    "demonstration and is not required for this app."
)
st.markdown(
    f"[Repository]({REPOSITORY_URL}) · "
    "[Data attributions](https://github.com/bonsakel/yellow-cab-confessions/blob/main/NOTICE.md) · "
    "[dbt documentation](https://docs.getdbt.com/docs/build/documentation) · "
    "[Deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud)"
)
st.caption(
    "Historical airport estimates are not live traffic or fare quotes. "
    "Rain comparisons are descriptive and do not establish causation."
)
footer()
