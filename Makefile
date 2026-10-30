.PHONY: setup demo demo-lite full dbt-build export app test lint clean

setup:
	test -f .env || cp .env.example .env
	test -x .venv/bin/python || python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"
	.venv/bin/python -m pip install -r app/requirements.txt

demo:
	docker compose up --build -d
	@printf "Airflow UI: http://localhost:8080\n"
	@printf "Streamlit app: http://localhost:8501\n"

demo-lite:
	@echo "The local pipeline is added in a later build phase."

dbt-build:
	docker compose exec -T airflow-scheduler /usr/local/bin/dbt build --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt

export: dbt-build
	docker compose exec -T airflow-scheduler python -m ycc export

app:
	.venv/bin/streamlit run app/Home.py

full:
	@set -eu; \
	docker compose up -d --wait minio airflow-api-server airflow-scheduler airflow-dag-processor; \
	docker compose exec -T airflow-scheduler airflow dags unpause yellow_cab_confessions --yes; \
	run_id="manual__ycc_full_$$(date -u +%Y%m%dT%H%M%S)"; \
	conf="$$(docker compose exec -T airflow-scheduler python -c 'import json, os; year = int(os.environ["YCC_YEAR"]); print(json.dumps({"months": [f"{year}-{month:02d}" for month in range(1, 13)]}))')"; \
	docker compose exec -T airflow-scheduler airflow dags trigger yellow_cab_confessions --run-id "$$run_id" --conf "$$conf"; \
	printf "Triggered full-year run %s; waiting for completion...\n" "$$run_id"; \
	while :; do \
		state_output="$$(docker compose exec -T airflow-scheduler airflow dags state yellow_cab_confessions "$$run_id")"; \
		state="$$(printf '%s\n' "$$state_output" | awk -F, '$$1 == "queued" || $$1 == "running" || $$1 == "success" || $$1 == "failed" { print $$1; exit }')"; \
		case "$$state" in \
			success) break ;; \
			failed) printf "Full-year DAG run %s failed. See Airflow task logs at http://localhost:8080.\n" "$$run_id"; exit 1 ;; \
			queued|running) sleep 15 ;; \
			*) printf "Could not read the state of full-year DAG run %s.\n" "$$run_id"; exit 1 ;; \
		esac; \
	done; \
	printf "Full-year DAG run %s completed successfully.\n" "$$run_id"; \
	printf "Airflow UI: http://localhost:8080\n"; \
	printf "Streamlit app: http://localhost:8501\n"

test:
	.venv/bin/python -m pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

clean:
	rm -rf .pytest_cache .ruff_cache .coverage
	rm -f warehouse/ycc.duckdb warehouse/ycc.duckdb.wal
