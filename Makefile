.POSIX:

project_dir := .

lint:
	@poetry run ruff format --check --diff $(project_dir)
	@poetry run ruff check $(project_dir)
	@poetry run mypy $(project_dir)

reformat:
	@poetry run ruff format $(project_dir)
	@poetry run ruff check --fix $(project_dir)

.PHONY: lint, reformat
