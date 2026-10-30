# Build progress

## Phase 1: Scaffold

**Status:** Complete. Acceptance checks passed; no work from Phase 2 has started.

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
