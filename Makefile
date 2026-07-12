.PHONY: install lint format typecheck test run check eval

install:
	uv sync

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy

test:
	uv run pytest

# Lint + types + tests in one shot
check: lint typecheck test

run:
	uv run python examples/orchestrator_sim.py

# Result-quality baseline: run every eval scenario and print the metrics table
eval:
	uv run python tests/eval/report.py
