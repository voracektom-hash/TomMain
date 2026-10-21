PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

.PHONY: install dev stats test clean

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -e ".[dev]"

install: $(BIN)/python  ## Create .venv and install dependencies

dev: install  ## Run the watcher locally (Ctrl+C to stop)
	@test -f .env || cp .env.example .env
	$(BIN)/python -m hlidac.watcher

stats: install  ## Show collected data and medians
	$(BIN)/python -m hlidac.stats

test: install  ## Run automated tests
	$(BIN)/python -m pytest -q

clean:  ## Remove .venv (keeps your data/)
	rm -rf $(VENV) *.egg-info
