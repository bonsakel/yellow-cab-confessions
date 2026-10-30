# Build progress

## Phase 1: Scaffold

**Status:** Complete. Acceptance checks passed; no work from Phase 2 began before this phase passed.

### Delivered

- Read the complete build specification in [CLAUDE.md](./CLAUDE.md).
- Added the initial Python package and project metadata, `.gitignore`,
  `.dockerignore`, `.env.example`, Makefile skeleton, MIT license, and data
  attribution notice.
- Added Docker Compose services for MinIO, Postgres, Airflow API server,
  scheduler, and DAG processor. Persistent Airflow JWT material is generated
  at runtime in an ignored Docker volume, not committed to the repository.
- Added the Airflow image with the `ycc` package and dbt tools installed, plus
  a hello-world DAG.
- Checked the latest stable package releases through PyPI: Apache Airflow 3.3.2,
  dbt-core 1.12.6, dbt-duckdb 1.11.1, DuckDB 2.0.0, Streamlit 1.66.1, and
  pydeck 0.9.3. Python.org currently lists Python 3.15.2 as stable.
- Chose the Airflow 3.3.2 image with Python 3.14 because Airflow's published
  metadata excludes Python 3.15. dbt-duckdb 1.11.1 accepts DuckDB 2.0.0. The
  pinned dbt packages were installed into an isolated virtual environment
  alongside Airflow, and `pip check` reported no broken requirements.
- Confirmed HTTP 200 responses for the January 2024 TLC trip parquet, taxi-zone
  lookup CSV, and taxi-zone shapefile archive.

### Verification

- `docker compose config --quiet`: passed.
- `docker compose up --build -d`: MinIO, Postgres, Airflow API server,
  scheduler, and DAG processor all reported healthy.
- Airflow health API returned healthy metadata DB, scheduler, and DAG processor;
  Airflow UI returned HTTP 200.
- Manually triggered `hello_world`; its DAG run and `say_hello` task both
  completed successfully.
- Airflow image reports dbt-core 1.12.6 and dbt-duckdb 1.11.1; importing the
  installed `ycc` package returned version 0.1.0.
- `ruff check .`, `ruff format --check .`, Python compilation, and Compose
  configuration validation passed.
- TLC trip parquet URL: HTTP 200.
- TLC taxi-zone lookup CSV URL: HTTP 200.
- TLC taxi-zone shapes ZIP URL: HTTP 200.

### Deviations

- The latest MinIO Docker Hub image was unavailable (HTTP 404), and the MinIO
  binary download endpoint returned HTTP 410. The Compose service therefore
  builds the latest published upstream source release,
  `RELEASE.2025-10-15T17-29-55Z`.
- The latest dbt dependencies conflict with pins in Airflow's global
  constraints (`pathspec` and `more-itertools`). dbt is isolated in its own
  Python virtual environment to keep Airflow's dependencies intact.
- A local Colima runtime was installed to perform the requested container
  acceptance checks because Docker was not initially available.

## Phase 2: Extract and load

**Status:** Complete. Acceptance checks passed before Phase 3 began.

### Delivered

- Added environment-driven settings, structured JSON logging, and the
  `python -m ycc extract|load --months YYYY-MM[,YYYY-MM]` CLI.
- Added streaming TLC downloads with bounded tenacity retries, SHA-256 and
  byte counts, S3-compatible uploads, and the canonical
  `raw/yellow/year=YYYY/month=MM/` object key.
- Added a DuckDB `raw.ingestion_manifest` with extraction/load state and
  checksums. Unchanged loaded files are skipped after comparing the TLC ETag
  and stored S3 checksum metadata.
- Added a transactional delete-then-insert loader for `raw.yellow_trips_raw`.
  TLC column-name and type drift is handled with `union_by_name`, normalized
  names, and explicit `TRY_CAST` projections.
- Added tiny January/February parquet schema-drift fixtures and tests for
  retry behavior, manifest updates, replacement loads, and schema evolution.
- Added isolated `.venv` setup and shared writable pipeline storage in Compose.

### Verification

- `make setup`: passed using the project `.venv`.
- `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
  `.venv/bin/python -m pytest -q`, and Python compilation: passed; **9 tests**.
- `docker compose config --quiet` and `docker compose up --build -d`: passed;
  MinIO, Postgres, Airflow API server, scheduler, and DAG processor reported
  healthy. The Airflow health API was healthy and the UI returned HTTP 200.
- `python -m ycc extract --months 2024-01` downloaded the real TLC file:
  **49,961,641 bytes**, SHA-256
  `c4d59da7bbc8abaeeeb1727947ee93d9891a71acb42854bd80db1571b2030510`.
  MinIO confirmed the uploaded object size and checksum metadata.
- `python -m ycc load --months 2024-01` loaded **2,964,624 rows**.
  Running it again skipped the already-loaded month; the raw table still held
  2,964,624 rows for exactly one source file, and the manifest reported
  `LOADED` with the same row count.
- Re-running extract for the unchanged month skipped the download based on the
  TLC ETag and S3 checksum metadata.
- Fixture tests verified schema drift across timestamp/string types, numeric
  types, and the addition of `Airport_Fee`.

### Deviations

- The manifest adds `source_etag` alongside the specified columns so it can
  cheaply detect unchanged TLC source objects without downloading them again.
- Compose now initializes ownership on its shared DuckDB/download volume; the
  first real container load exposed that a fresh named volume is root-owned.
- `make setup` installs into an ignored project virtual environment rather
  than changing the selected global Python environment.
- Pylance's workspace diagnostic reports only the Airflow import in the DAG
  as unresolved under the local `.venv`; Airflow is installed and the DAG
  runtime is verified inside the Airflow image.

## Phase 3: dbt staging, quarantine, and star schema

**Status:** Complete. The demo-month dbt build and reconciliation acceptance
checks passed before Phase 4 began.

### Delivered

- Added the dbt DuckDB project and profile, a schema-naming macro, raw source
  declarations, and configured quality thresholds in `dbt_project.yml`.
- Added typed TLC staging with local-time metrics, deterministic trip IDs,
  exact-duplicate ranks, and every applicable reject reason.
- Added lookup-backed zone validation. TLC IDs 264 and 265 remain clean but are
  flagged as unknown; other IDs absent from the loaded lookup are quarantined.
- Added the quarantine table, date/zone/weather/payment dimensions, clean trip
  fact table, dimension relationships, range checks, and per-source-file raw
  reconciliation test.
- Added and loaded the 265-row TLC taxi zone lookup. Its extraction/load CLI is
  narrowly scoped to supplying the zone dimension and validating zone IDs.
- Documented model and column meanings, including the quarantine rule
  conditions and naive local-hour uniqueness choice.
- Added a focused zone-loader unit test.

### Verification

- Airflow/MinIO/Postgres Compose services remained healthy; the dbt adapter
  successfully connected to the shared DuckDB warehouse.
- `dbt build --no-partial-parse`: **42/42 passed** (8 models and 34 data tests,
  with no warnings, errors, or skips).
- January 2024 raw rows: **2,964,624**; clean fact rows: **2,884,524**;
  quarantined trips: **80,100**. The reconciliation test passed exactly.
- The quarantine contains examples for **9 of 11** rules. Counts include
  37,984 `NEGATIVE_FARE`, 39,138 `ZERO_DISTANCE_PAID`, 1,772
  `ABSURD_DURATION`, and 18 `OUT_OF_RANGE_DATE` rows. No exact duplicate or
  non-lookup zone IDs occurred in this source month; the data does include
  **28,770** clean trips flagged with TLC unknown-zone IDs.
- The 2024 date dimension has **366** dates; the local-hour weather dimension
  has **8,784** unique rows, including one row per naive wall-clock hour.
  No non-credit-card fact row has a tip percentage.
- `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, and
  `.venv/bin/python -m pytest -q`: passed; **10 tests**.
- `git diff --check`: passed.

### Deviations and deferred work

- Phase 2 had not loaded the zone lookup, so a small TLC lookup extractor and
  loader were added here to implement lookup-backed validation and a useful
  `dim_zone`.
- The weather dimension is currently a complete local-hour scaffold with
  unknown weather values; weather and holiday staging/enrichment, zone-shape
  centroids, and holiday labels remain for Phase 4. The fallback DST hour is
  represented once at naive local-hour grain, as required for uniqueness.
- The January source month has no examples for `DUPLICATE_TRIP` or
  `UNKNOWN_ZONE`; those checks are present but those two rules cannot be
  demonstrated by this input. No fixture rows were added because Phase 3 is
  being validated against the loaded demo month; CI fixtures are specified in
  a later phase.

## Phase 4: Enrichment, tests, and freshness

**Status:** Complete. Enrichment, dbt test, source freshness, and docs
acceptance checks passed before Phase 5 began.

### Delivered

- Added retrying Open-Meteo archive extraction for the configured year, caching
  the original JSON and normalized compressed parquet in the work directory
  and MinIO. The DuckDB loader replaces `raw.weather_hourly` after validating
  its expected unique local-hour coverage.
- Converted UTC weather timestamps to naive `America/New_York` local time.
  The repeated fall-back hour is represented once: mean temperature and wind,
  maximum precipitation/rain/snowfall, and the first weather code. The
  nonexistent spring-forward wall hour is included with null weather values
  so the dimension retains exactly 24 rows per calendar day.
- Added weather staging and precipitation/snowfall buckets. Thresholds for
  dry, light rain, and moderate rain live in dbt vars.
- Added US/New York holiday seed generation using `holidays` and joined those
  labels to `dim_date`.
- Added the TLC zone-shape pipeline: reprojected source CRS to WGS84, simplified
  polygons to GeoJSON, generated centroid parquet, uploaded the archive and
  centroids, and loaded `raw.zone_centroids` for `dim_zone`.
- Added dbt source freshness for `raw.ingestion_manifest`, accepted-value
  checks, local-hour coverage and quarantine-code tests, and a dbt unit test
  exercising all 11 quarantine rule codes.
- Added mocked network retry/cache tests, DST aggregation tests, weather loader
  coverage tests, and holiday-seed tests. Updated Open-Meteo attribution and
  terms in `NOTICE.md`.

### Verification

- `python -m ycc extract-weather` fetched the actual 2024 archive once and
  produced **8,784** local-hour records; the raw JSON is **401,621 bytes** and
  the compressed parquet is **67,109 bytes**. `load-weather` loaded all 8,784
  hours into DuckDB.
- The weather buckets contain **7,474 dry**, **1,048 light-rain**,
  **116 moderate-rain**, **25 heavy-rain**, **120 snow**, and **1 unknown**
  hour. The unknown hour is the spring-forward wall-clock hour with no actual
  observation.
- `extract-zone-shapes` produced **263** valid GeoJSON features and centroids;
  verified polygon bounds are NYC WGS84 coordinates (longitude -74.256 to
  -73.700; latitude 40.496 to 40.916). The 2024 holiday seed contains **14**
  rows.
- `dbt build --no-partial-parse`: **56/56 passed** (10 models, one seed, 44
  data tests, and one unit test; no warnings or skips).
- `dbt test`: **45/45 passed**. `dbt source freshness`: manifest freshness
  passed. `dbt docs generate`: passed and wrote `target/catalog.json`; all 10
  models have descriptions and no model columns are undocumented.
- Raw-to-clean reconciliation remains **2,964,624 = 2,884,524 + 80,100**.
  The enriched dimensions contain 366 dates, 8,784 local weather hours, 266
  zones, and 27 payment/rate-code pairs.
- `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, and
  `.venv/bin/python -m pytest -q`: passed; **14 tests**.
- `docker compose config --quiet` passed; Airflow API, scheduler, DAG
  processor, MinIO, and Postgres report healthy.
- Reviewed Open-Meteo's current terms and licence: free API use is limited to
  non-commercial purposes and the data is CC BY 4.0 with required attribution.

### Deviations

- PyArrow was initially considered for parquet writes, but the Airflow Python
  3.14 constraints pin a PyArrow release without a compatible wheel. The
  pipeline instead writes the small normalized weather and centroid parquet
  files with the already-pinned DuckDB engine, avoiding an Airflow dependency
  conflict.
- The UTC Open-Meteo request includes two adjacent UTC calendar days to ensure
  the full local NYC year is covered at both year boundaries; local-hour
  conversion filters back to the configured year.

## Phase 5: Marts and export

**Status:** Complete. The mart build, tests, export, size budget, and sanity
checks passed before Phase 6 began.

### Delivered

- Added the rain-tax, airport-run, zone-pair, zone-summary, blooper-count,
  blooper-example, and featured-night flow marts, with model and column
  descriptions plus singular tests for percentile ordering, airport duration,
  minimum zone-pair volume, and per-rule example limits.
- Added the New Year's Eve, July 4th, and Halloween featured-night seed. The
  rainiest night is selected from the weather dimension at build time.
- Added a DuckDB-backed exporter that stages ZSTD-compressed parquet files and
  data-derived `confessions.json`, checks the configured byte budget before
  replacing existing files, and logs per-file sizes.
- Added `ycc export`, `make dbt-build`, and `make export`, with environment
  settings and Compose mounts for app output. Whitelisted the small app export
  files in `.gitignore` so they can be committed as the app's bundled data.
- Retained `source_month` in the quarantine model so the blooper counts can be
  grouped by source month.

### Verification

- `make export`: passed end to end using the real January 2024 TLC load and
  current DuckDB/dbt containers. The dbt build passed **93/93** items
  (13 table models, four views, two seeds, 73 data tests, and one unit test).
- Exported all seven mart parquet files plus `confessions.json`: **482,548
  bytes** total against the 52,428,800-byte (50 MiB) limit. Every file is below
  25 MiB, and the exports are small enough to commit.
- Data-based confessions from the January demo load report 2,884,524 clean
  trips, 80,100 quarantined trips, 9,437,923.06 miles, and 9,563,405.84 USD in
  credit-card tips. The weighted rain-vs-dry comparison is +3.57% demand and
  +5.02% average credit-card tip percentage; cash tips remain unobserved.
- The raw-to-clean reconciliation remains exact:
  **2,964,624 = 2,884,524 + 80,100**.
- Mart row counts: 553 rain-tax groups, 1,651 airport groups, 4,610 zone pairs,
  262 zones, nine rule/month blooper groups, 1,134 blooper examples, and
  21,499 featured-night flows. The configured July, Halloween, and New Year's
  Eve nights have no trip rows in the January-only demo; the dynamically
  selected rainiest night does.
- Airport duration p10 values are at least 1.05 minutes; the median across
  airport-group p50 values is about 30.1 minutes. The weather and airport
  aggregates are weighted by observed counts, and tip-percentage averages use
  credit-card trips with a calculable percentage.
- `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
  `.venv/bin/python -m pytest -q` (**16 passed**), `docker compose config
  --quiet`, and `git diff --check`: passed.

### Deviations

- Airport statistics exclude clean trips shorter than the configurable
  one-minute minimum. The initial marts had implausible zero-minute airport
  medians due to clean but non-travel-like TLC rows; the threshold is documented
  on the model, configured in `dbt_project.yml`, and covered by a singular
  test.
- Rain-vs-dry headline comparisons use observed-day and valid credit-card-tip
  weights instead of giving each weather category equal weight. This avoids
  category frequency and null tip ratios distorting the data-derived headline.
