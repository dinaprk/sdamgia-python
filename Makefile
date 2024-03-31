.POSIX:

PROJECT_DIR := .

lint:
	@poetry run ruff format --check --diff $(PROJECT_DIR)
	@poetry run ruff check $(PROJECT_DIR)
	@poetry run mypy $(PROJECT_DIR)

format:
	@poetry run ruff format $(PROJECT_DIR)
	@poetry run ruff check --fix $(PROJECT_DIR)

.PHONY: lint, format
