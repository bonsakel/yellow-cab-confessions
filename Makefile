.PHONY: setup demo demo-lite full test lint clean

setup:
	test -f .env || cp .env.example .env
	python3 -m pip install -e ".[dev]"

demo:
	docker compose up --build

demo-lite:
	@echo "The local pipeline is added in a later build phase."

full:
	@echo "Full-year processing is added in a later build phase."

test:
	python3 -m pytest

lint:
	ruff check .
	ruff format --check .

clean:
	rm -rf .pytest_cache .ruff_cache .coverage
	rm -f warehouse/ycc.duckdb warehouse/ycc.duckdb.wal
