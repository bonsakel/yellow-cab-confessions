# Yellow Cab Confessions

> An end-to-end ELT pipeline plus an interactive web app that makes NYC taxi data confess its secrets.
> Anyone can open the live demo, or run one command and watch the whole pipeline work on their own laptop.

This file is the build spec. Read it fully before writing any code, then follow the phases in order.

---

## 0. How you (Claude Code) should work

1. **Work phase by phase** (Section 9). Do not start a phase until the previous phase's acceptance checks pass.
2. **Commit at the end of every phase** using Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`). Small, meaningful commits inside a phase are encouraged.
3. **Keep `PROGRESS.md` updated.** After each phase, log what was done, what was verified, and any deviation from this spec with the reason.
4. **Verify everything by running it.** Never claim something works without executing it. If a check fails, fix it before moving on.
5. **Check latest stable versions at build time** for Airflow, dbt-core, dbt-duckdb, DuckDB, Streamlit, pydeck, and Python. Pin them (`requirements*.txt` or `uv.lock`) after confirming they work together. Do not rely on memory for versions or API details; read current docs when unsure.
6. **No paid services, no API keys, no secrets in the repo.** Everything must run for free. Only ship an `.env.example`.
7. **Never commit raw data, the warehouse file, or anything over 25 MB.** The only data files committed are the small app exports (Section 7) and the tiny CI fixtures (Section 8).
8. **Ask the user only at these checkpoints:** (a) end of Phase 1 to confirm the repo name and GitHub remote, (b) when something requires a manual action only the user can do (recording GIFs, connecting Streamlit Cloud). Otherwise make the best decision, record it in `PROGRESS.md`, and continue.
9. **Code quality bar:** Python 3.11+, type hints, `ruff` (lint + format), `pytest`, structured logging (no bare `print`), retries with backoff via `tenacity`, config via environment variables only, small focused modules, docstrings on public functions.

---

## 1. Concept

**Name:** Yellow Cab Confessions
**Tagline:** *40 million rides. Every one has a story. Some of them are lies.*

A data pipeline ingests a full year of NYC yellow taxi trips (2024, about 40M rows), cleans and models them into a star schema, enriches them with hourly weather and US holidays, and serves the results through a playful Streamlit app. Bad data is not silently dropped. It is quarantined, explained, and shown off on its own page.

The tone of the app is a wise-cracking New York cabbie who has seen everything. Playful copy, dark theme with taxi-yellow accents, but the engineering underneath is serious and clean.

**Rule for all "confession" headlines in the app:** they must be computed from the data at export time, never hardcoded. Example: "Confession: when it rains hard, tips drop X% but demand jumps Y%". The numbers come from the marts.

---

## 2. Free data sources (no keys, no paid APIs)

| Data | Source | Notes |
|---|---|---|
| Yellow taxi trips | NYC TLC trip record parquet files. URL pattern: `https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_YYYY-MM.parquet` | Public CDN, about 40-60 MB per month. Default year is 2024, configurable via `YCC_YEAR`. Verify the URL pattern still works before building. |
| Zone lookup | `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv` | Columns: `LocationID, Borough, Zone, service_zone`. |
| Zone shapes | `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip` | Shapefile. Reproject to EPSG:4326, simplify geometry, export GeoJSON plus a centroids table. |
| Hourly weather | Open-Meteo Archive API: `https://archive-api.open-meteo.com/v1/archive` | No key. Use Central Park coordinates (lat 40.7794, lon -73.9692). Hourly vars: `temperature_2m, precipitation, rain, snowfall, wind_speed_10m, weather_code`. Fetch the whole year in one call. Add attribution and check their current terms of use for the README. |
| Holidays | Python `holidays` library (US, state NY) | Generate a seed CSV with a script. |

Add a `NOTICE.md` with data attributions (NYC TLC, Open-Meteo, `holidays` library) and a note that this is an independent portfolio project.

**Important data facts to respect in the models:**
- TLC timestamps are naive **local NYC time**. Weather must be converted to the same naive local time before joining. Handle the daylight-saving fall-back hour (the duplicated hour in November) so that `dim_weather` stays unique on local hour. Document the choice.
- `tip_amount` is only recorded for credit-card payments (`payment_type = 1`). Cash tips are invisible. Compute tip percentages on credit-card trips only and say so in the app. This is itself a fun "confession".
- Airport zone IDs: JFK = 132, LaGuardia = 138, Newark = 1. Rate code 2 is the JFK flat fare, rate code 3 is Newark. Check against the lookup file.
- Zone IDs 264 and 265 mean "unknown". Keep those rows but flag them.
- Files contain stray timestamps outside their month (even other years). That is one of the quarantine rules.

---

## 3. Architecture

```
TLC CDN ─┐
Open-Meteo ─┼─► [Airflow DAG] ─► MinIO / S3 (raw parquet) ─► DuckDB raw schema
holidays ─┘                                                      │
                                                                 ▼
                                                    dbt (dbt-duckdb)
                                         staging ─► quarantine ─► star schema ─► marts
                                                                 │
                                                                 ▼
                                                  export small mart parquet files
                                                                 │
                                                                 ▼
                                                      Streamlit app (5 pages)
```

**Stack:**
- **Orchestration:** Apache Airflow in Docker (LocalExecutor, Postgres metadata DB).
- **Object storage:** MinIO locally (S3-compatible). Code must use S3 env vars so it swaps to AWS S3 or Cloudflare R2 with no code change.
- **Warehouse:** DuckDB (file-based) via `dbt-duckdb`. Free, fast on 40M rows, runs on a laptop.
- **Transform:** dbt Core with `dbt_utils` and `dbt_expectations` (or equivalent) packages.
- **Serving:** Streamlit, reading only the small exported parquet files so it deploys free on Streamlit Community Cloud.
- **CI:** GitHub Actions.
- **Optional:** a `snowflake` dbt target in `profiles.yml`, off by default (see Section 6.5).

**Design principle:** all business logic lives in a plain Python package `ycc/` with a CLI. Airflow DAG tasks are thin wrappers that call that package. This keeps the pipeline testable and lets it run without Airflow (`make demo-lite`).

---

## 4. Repository layout

```
yellow-cab-confessions/
├── CLAUDE.md                  # this spec
├── PROGRESS.md                # running build log (you maintain this)
├── README.md
├── NOTICE.md
├── LICENSE                    # MIT
├── Makefile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── pyproject.toml             # ruff, pytest, package metadata
├── ycc/                       # core Python package
│   ├── config.py              # env-driven settings (pydantic-settings)
│   ├── cli.py                 # `python -m ycc ...` (typer)
│   ├── extract/               # tlc.py, weather.py, zones.py, holidays.py
│   ├── load/                  # s3.py, duckdb_loader.py, manifest.py
│   ├── export/                # marts_to_parquet.py
│   └── logging.py
├── airflow/
│   ├── Dockerfile
│   └── dags/yellow_cab_confessions.py
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── packages.yml
│   ├── models/
│   │   ├── staging/
│   │   ├── quarantine/
│   │   ├── core/              # dims + fct_trips
│   │   └── marts/
│   ├── seeds/
│   ├── macros/
│   ├── tests/                 # singular tests
│   └── unit_tests/
├── app/                       # Streamlit app
│   ├── Home.py
│   ├── pages/
│   ├── components/
│   ├── data/                  # committed small parquet exports
│   ├── requirements.txt       # light deps only
│   └── .streamlit/config.toml # dark theme, yellow accent
├── tests/
│   ├── fixtures/              # tiny sample parquet + weather JSON (with deliberate bad rows)
│   └── test_*.py
├── docs/
│   ├── architecture.md        # Mermaid diagram
│   └── images/
└── .github/workflows/ci.yml
```

---

## 5. Configuration (`.env.example`)

Provide at least:

```
YCC_YEAR=2024
YCC_DEMO_MONTHS=2024-01
YCC_S3_ENDPOINT=http://minio:9000
YCC_S3_BUCKET=ycc-raw
YCC_S3_ACCESS_KEY=minioadmin
YCC_S3_SECRET_KEY=minioadmin
YCC_S3_REGION=us-east-1
YCC_DUCKDB_PATH=/data/warehouse/ycc.duckdb
YCC_DUCKDB_MEMORY_LIMIT=6GB
YCC_DUCKDB_THREADS=4
AIRFLOW_UID=50000
```

Local MinIO credentials are throwaway defaults. Add a comment saying to change them for any real deployment.

---

## 6. Data pipeline spec

### 6.1 Extract and load (idempotent)

- Download each monthly TLC file with streaming, retries (`tenacity`), and a size and checksum record. Upload to MinIO at `raw/yellow/year=YYYY/month=MM/yellow_tripdata_YYYY-MM.parquet`.
- **Manifest table** `raw.ingestion_manifest`: `source_file, s3_key, bytes, etag_or_sha256, row_count, status, loaded_at`. Skip files already loaded with an unchanged checksum, so re-running a month is safe and cheap.
- Load into `raw.yellow_trips_raw` with a `source_file` column. Re-loading a month does **delete-then-insert by `source_file`** inside a transaction.
- TLC schemas drift between months (column types, `Airport_fee` casing). Read with explicit casts and `union_by_name` so a schema change in one month does not break the load. Add a test for this using the fixtures.
- Weather: one API call for the full year, store raw JSON plus a parquet version in MinIO, load to `raw.weather_hourly`. Cache so repeat runs do not re-call the API.
- Zones: download the lookup CSV and shapefile once. Load `raw.taxi_zone_lookup`. Write `zones.geojson` (simplified) and `zone_centroids.parquet` for the app.
- Holidays: script generates `seeds/us_holidays.csv` for the configured year range.

### 6.2 dbt layers

Materialization: staging as views or tables as appropriate, core as tables, marts as tables. Keep the 40M-row `fct_trips` efficient: select only needed columns, avoid wide string columns, and add sensible types.

**staging**
- `stg_yellow_trips`: rename to snake_case, cast types, standardize, compute helper columns (`trip_duration_min`, `avg_speed_mph`, `pickup_local_hour`, `trip_date`), and compute a `reject_reasons` array from the rules below. Create a deterministic `trip_id` (surrogate key from vendor, timestamps, zones, amounts plus a row number within duplicates).
- `stg_taxi_zones`, `stg_weather_hourly`, `stg_holidays`.

**quarantine** (the data-quality showcase)
Each trip is evaluated against these rules. A trip with any failed rule goes to `quarantine_trips` (with all reasons), and only clean trips reach `fct_trips`.

| Rule code | Condition |
|---|---|
| `NEGATIVE_FARE` | `fare_amount < 0` or `total_amount <= 0` |
| `DROPOFF_BEFORE_PICKUP` | dropoff earlier than pickup |
| `ZERO_DURATION` | duration under 30 seconds with distance over 0.5 mi |
| `ABSURD_DURATION` | duration over 6 hours |
| `ZERO_DISTANCE_PAID` | distance <= 0 but fare over a threshold |
| `ABSURD_DISTANCE` | distance over 100 mi |
| `TELEPORTING_CAB` | average speed over 80 mph |
| `OUT_OF_RANGE_DATE` | pickup not within the file's month |
| `BAD_PASSENGER_COUNT` | passenger count over 8 |
| `UNKNOWN_ZONE` | pickup or dropoff zone not in the lookup (IDs 264 and 265 are flagged but allowed through as `is_unknown_zone`, not quarantined) |
| `DUPLICATE_TRIP` | exact duplicate beyond the first |

Put thresholds in `dbt_project.yml` vars, not hardcoded in SQL. Document each rule in the model YAML.

**core (star schema)**
- `fct_trips`: grain is one clean trip. Foreign keys to dims, measures (fare, tip, tolls, total, distance, duration, speed), `tip_pct` (credit-card only, otherwise null), `is_airport_trip`.
- `dim_zone` (zone, borough, service zone, centroid lat/lon), `dim_date` (generated calendar with weekday, weekend flag, holiday name), `dim_weather` (local hour grain, with `weather_bucket`), `dim_payment` (payment type and rate code labels).

**weather buckets** (by precipitation mm per hour and snowfall): `dry` (<0.1), `light_rain` (0.1 to 2.5), `moderate_rain` (2.5 to 7.6), `heavy_rain` (>7.6), `snow` (snowfall > 0). Put thresholds in vars.

**marts** (each one feeds exactly one app page and stays small)
- `mart_rain_tax`: by weather bucket × hour of day × pickup borough: trips, average fare, average tip % (credit card only), average speed, and demand versus the dry baseline for the same hour.
- `mart_airport_runs`: by airport × direction (to or from) × day type (weekday, weekend, holiday) × hour: trip count, p10/p50/p90 duration and fare, plus the other end's borough.
- `mart_zone_pairs`: top zone pairs with at least 30 trips: trips, average fare, average duration, average speed, average tip %. Also `mart_zone_summary` per zone.
- `mart_blooper_reel`: counts by rule code and month, plus the top N (about 200) weirdest examples per rule with the reasons.
- `mart_night_city`: for each configured featured night, trips binned every 10 minutes by pickup zone × dropoff zone. Configure featured nights in a seed `featured_nights.csv` (default: New Year's Eve 2024, July 4th 2024, Halloween 2024, plus the rainiest night of the year, selected by a query).

### 6.3 Quality and tests (30+ dbt tests, all passing)

Cover:
- `unique` and `not_null` on all primary keys and key columns
- `relationships` from `fct_trips` to every dim
- `accepted_values` for payment type, rate code, weather bucket, rule codes
- range checks (`dbt_expectations` or custom): fare, distance, duration, speed on `fct_trips` all within sane bounds
- `dim_weather` unique on local hour, with 24 × days-in-year coverage (allow for the DST edge case)
- **Reconciliation singular test:** `rows in raw = rows in fct_trips + rows in quarantine_trips` (per month and total). This is the headline integrity check.
- **dbt unit tests** (dbt 1.8+ `unit_tests`) for the quarantine rule logic: one input row per rule, asserting the right reason code.
- Source freshness on the ingestion manifest `loaded_at`.
- Documented descriptions on every model and column, so `dbt docs generate` produces a rich lineage graph.

Python tests (`pytest`): extractor retry behavior (mocked), manifest idempotency, loader delete-then-insert, schema-drift handling, export file sizes.

### 6.4 Airflow DAG

One DAG, `yellow_cab_confessions`, scheduled monthly with `catchup` enabled, plus support for manual backfill with params. Task groups: `extract` → `load` → `dbt_build` (run, then test) → `export` → `publish_summary`. Use dynamic task mapping over months so `make full` processes 12 months with parallelism that respects memory. Tasks must be idempotent and retry-safe. `publish_summary` writes a pipeline-run summary (row counts, quarantine %, test results, duration) to `app/data/pipeline_runs.parquet` for the app's About page.

On `docker compose up`, the demo months trigger automatically (a small init service unpauses and triggers the DAG), so a recruiter sees tasks turn green without clicking.

### 6.5 Optional Snowflake target

Add a `snowflake` target in `dbt/profiles.yml` that reads credentials from env vars and is **never** the default. Isolate DuckDB-specific functions (percentiles, array handling, `union_by_name` reads) behind a few adapter-dispatch macros so the SQL stays mostly portable. Document in the README that DuckDB is the supported path and Snowflake is a demonstrated option, because Snowflake trials expire. Keep this to a small amount of effort; it must not slow down or complicate the default path.

---

## 7. Streamlit app spec

Multipage app, dark theme with yellow accent (`.streamlit/config.toml`), playful NYC-cabbie copy, a consistent header, and a footer linking to the repo and data attributions. Mobile-friendly where practical. The app reads only from `app/data/*.parquet` (and `zones.geojson`), never from the warehouse, so it deploys free. Budget: total committed app data under 50 MB. Use caching (`st.cache_data`) for all loads and keep every page snappy.

Libraries: `streamlit`, `pandas`, `pyarrow`, `plotly`, `pydeck` (add `duckdb` only if it clearly helps). Keep `app/requirements.txt` light.

**Home:** the pitch, the headline confessions (computed from marts), big stat tiles (total trips analyzed, miles, tips, bad rows caught), and navigation cards to each page.

**1. The Rain Tax:** select borough and hour range. Charts compare dry versus rain versus snow: demand change, average fare, tip %, average speed. Headline confession is computed. Footnote the credit-card-only tip caveat.

**2. Airport Run Planner:** select airport (JFK, LGA, EWR), direction, day type, and hour. Show the typical duration with a p10-p90 range, the typical fare range, a "best time to leave" bar chart across the 24 hours, and a short plain-English verdict. State clearly that it is a historical estimate, not live traffic or a quote.

**3. Zone vs Zone:** select two zones. Side-by-side stats (trips, fare, speed, tip habits) and a pydeck map highlighting both zones and the top flows between them and elsewhere. Include a "surprise me" button that picks an interesting pair.

**4. The Blooper Reel:** the quarantine showcase. A funnel from raw rows to clean rows, a chart of rejections by rule and month, and a browsable gallery of the weirdest rejected trips, each with a funny one-line caption derived from its rule code (for example the teleporting cab). Show the reconciliation check (raw = clean + quarantined) prominently, since it demonstrates data trust.

**5. A Night in the City:** choose a featured night. A pydeck `ArcLayer` between zone centroids animated by time slider (10-minute bins) plus a play button, with a live count of rides in progress.

**About / Under the Hood:** architecture diagram, pipeline-run history from `pipeline_runs.parquet`, the data-quality summary, tech stack, and links to the dbt docs and repo.

**Export step** (`ycc/export`): after dbt, write each mart to compressed parquet in `app/data/`, enforce the size budget (fail the export if exceeded), and write a small `confessions.json` with the computed headline numbers.

---

## 8. CI/CD and quality gates

`.github/workflows/ci.yml`, triggered on push and PR:
1. `ruff check` and `ruff format --check`
2. `sqlfluff lint` on dbt models (DuckDB dialect, dbt templater or jinja)
3. `pytest`
4. `dbt deps && dbt build` against the **committed fixtures** in `tests/fixtures/` (a few thousand rows including at least one row for every quarantine rule, plus a small weather file). CI must not download the real TLC data. Use a dbt var to switch the source to the fixtures.
5. Build the app export from the fixture-based warehouse and run a headless smoke test of the Streamlit app (for example `streamlit.testing.v1.AppTest`) so no page throws.
6. Upload the dbt docs as a CI artifact.

Add status badges to the README. Add `pre-commit` config (ruff, trailing whitespace, large-file check).

---

## 9. Build phases and acceptance checks

### Phase 1: Scaffold
Repo structure, `pyproject.toml`, `.gitignore`, `.env.example`, `Makefile` skeleton, `docker-compose.yml` with MinIO, Postgres, and Airflow (with healthchecks), the Airflow Dockerfile with dbt-duckdb and the `ycc` package installed, `PROGRESS.md`, LICENSE, NOTICE.
**Accept:** `docker compose up` brings up MinIO and Airflow healthy; the Airflow UI loads; a hello-world DAG runs.
**Checkpoint:** ask the user for the repo name and GitHub remote.

### Phase 2: Extract and load
Implement `ycc.extract` and `ycc.load`, the manifest, and the CLI (`python -m ycc extract|load --months ...`).
**Accept:** loading `YCC_DEMO_MONTHS` populates `raw.yellow_trips_raw`; running it twice changes nothing (idempotent); manifest rows are correct; pytest for these pieces passes.

### Phase 3: dbt staging, quarantine, star schema
Staging models, quarantine logic, `fct_trips`, and the dims.
**Accept:** `dbt build` succeeds on the demo month; the reconciliation test passes; the quarantine table contains examples of most rules.

### Phase 4: Enrichment, tests, freshness
Weather and holiday enrichment, weather buckets, all 30+ tests, unit tests, source freshness, full YAML docs.
**Accept:** `dbt test` is fully green; `dbt docs generate` shows a complete lineage graph; DST uniqueness handled and documented.

### Phase 5: Marts and export
All marts, the export module, the size-budget check, and `confessions.json`.
**Accept:** `make export` writes all parquet files under 50 MB total; sanity-check the numbers by hand (for example, rain really does change demand in the data; airport p50 durations are plausible).

### Phase 6: Streamlit app
All pages, theme, copy, caching, and zone GeoJSON.
**Accept:** `make app` runs locally; every page loads in a few seconds; no console errors; `AppTest` smoke test passes; take screenshots of each page with Playwright into `docs/images/` (if Playwright is awkward, skip and note it).

### Phase 7: Full-year run and Airflow DAG polish
Finalize the DAG (dynamic mapping, auto-trigger on `docker compose up`, `publish_summary`), then run `make full` for all of 2024 and regenerate the exports from the full year.
**Accept:** all 12 months load and the full-year `dbt build` and tests pass; reconciliation holds for the full year; peak memory stays within `YCC_DUCKDB_MEMORY_LIMIT`; record timings in `PROGRESS.md`.

### Phase 8: CI, docs, README, deploy readiness
GitHub Actions, pre-commit, the README, `docs/architecture.md` (Mermaid), `dbt docs` link instructions, and deploy notes for Streamlit Community Cloud (entry point `app/Home.py`, requirements path `app/requirements.txt`).
**Accept:** CI is green on a pushed branch; a fresh clone follows only the README and reaches a working app.
**User tasks to list at the end:** connect the repo to Streamlit Community Cloud, record GIFs for the README (list exactly which flows to record), and paste the live URL into the README.

---

## 10. Makefile targets

| Target | Behavior |
|---|---|
| `make setup` | create `.env` from `.env.example`, install dev tools, `pre-commit install` |
| `make demo` | `docker compose up` with MinIO and Airflow; auto-runs the DAG for `YCC_DEMO_MONTHS`; ends by printing the Airflow and app URLs |
| `make demo-lite` | same pipeline without Airflow via the `ycc` CLI plus dbt, for low-memory machines (this is the fastest path to a working app) |
| `make full` | process every month of `YCC_YEAR` |
| `make dbt-build` / `make dbt-test` / `make dbt-docs` | run dbt steps directly (`dbt-docs` serves the lineage site) |
| `make export` | export marts to `app/data/` |
| `make app` | run Streamlit locally |
| `make test` / `make lint` | pytest / ruff + sqlfluff |
| `make clean` | remove local warehouse and caches (never touch committed app data without a flag) |

Document resource needs in the README: roughly 10 GB free disk and 8 GB RAM for `make full`; the demo path needs far less.

---

## 11. README requirements

The README is the recruiter's front door. Structure:
1. Title, tagline, badges (CI, license), and a **"Try it live"** button at the very top
2. A short GIF or screenshot strip of the app
3. **What is this?** in 3 to 4 sentences, then "Cool things it found" (computed headline confessions)
4. **Run it yourself in 3 commands** (`git clone`, `make setup`, `make demo-lite`) and the Airflow path (`make demo`)
5. Architecture diagram (Mermaid) and a short walkthrough of each layer
6. **Data quality** section: the quarantine rules table and the reconciliation guarantee
7. Data model: star schema diagram and mart-to-page mapping
8. Design decisions (why DuckDB, why S3-compatible storage, why Airflow wraps a plain Python package, DST handling, credit-card-only tips)
9. Testing and CI
10. Optional Snowflake target note
11. Limitations and honest caveats (historical estimates, single weather station for the whole city, tips exclude cash)
12. Data attributions and license

Tone: confident, clear, a bit playful. No fluff, no unverifiable claims. Every number in the README must come from an actual run.

---

## 12. Definition of done

- [ ] A fresh clone plus `make setup && make demo-lite` yields a working app in under about 15 minutes on a normal laptop
- [ ] `make demo` (Airflow) runs the DAG end to end automatically
- [ ] Full-year 2024 processed; reconciliation test passes
- [ ] 30+ dbt tests and the unit tests pass; pytest passes; CI is green
- [ ] All 5 app pages plus Home and About work, and every headline number is computed from data
- [ ] App data under 50 MB; no secrets or large files committed
- [ ] dbt docs lineage graph generates cleanly
- [ ] README complete, with real numbers
- [ ] `PROGRESS.md` documents decisions, deviations, and timings
- [ ] Remaining manual user tasks listed clearly (Streamlit Cloud connection, GIFs, live URL)

## 13. Non-goals

No paid services, no real-time or streaming ingestion, no user accounts, no ML models, no claims about live traffic or predictions. This is a polished batch-analytics showcase.
