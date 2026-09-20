.PHONY: install dev test lint demo clean

install:
	pip install -e .

dev:
	pip install -e ".[dev,llm]"

test:
	pytest -q

lint:
	ruff check src tests

demo:
	robotops fusion --demo
	robotops diagnostics --demo
	robotops latency --demo
	robotops rca --demo
	robotops maintenance --demo

clean:
	rm -rf .pytest_cache .ruff_cache out build dist *.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} +
