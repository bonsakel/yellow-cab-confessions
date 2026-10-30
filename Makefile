.PHONY: setup demo demo-lite full dbt-build export test lint clean

setup:
	test -f .env || cp .env.example .env
	test -x .venv/bin/python || python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"

demo:
	docker compose up --build

demo-lite:
	@echo "The local pipeline is added in a later build phase."

dbt-build:
	docker compose exec -T airflow-scheduler /usr/local/bin/dbt build --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt

export: dbt-build
	docker compose exec -T airflow-scheduler python -m ycc export

full:
	@echo "Full-year processing is added in a later build phase."

test:
	.venv/bin/python -m pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

clean:
	rm -rf .pytest_cache .ruff_cache .coverage
	rm -f warehouse/ycc.duckdb warehouse/ycc.duckdb.wal
