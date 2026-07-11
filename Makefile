.PHONY: install lint format typecheck test run check

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
