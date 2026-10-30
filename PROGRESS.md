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
