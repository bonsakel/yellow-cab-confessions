.PHONY: setup demo demo-lite full test lint clean

setup:
	test -f .env || cp .env.example .env
	test -x .venv/bin/python || python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"

demo:
	docker compose up --build

demo-lite:
	@echo "The local pipeline is added in a later build phase."

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
