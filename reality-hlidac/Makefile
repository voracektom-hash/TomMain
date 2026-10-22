PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

.PHONY: install dev stats test clean import-rules rules preview test-notify

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -e ".[dev]"

install: $(BIN)/python  ## Create .venv and install dependencies

dev: install  ## Run the watcher locally (Ctrl+C to stop)
	@test -f .env || cp .env.example .env
	$(BIN)/python -m hlidac.watcher

stats: install  ## Show collected data and medians
	$(BIN)/python -m hlidac.stats

import-rules: install  ## Load rules from pravidla.toml into the database
	@test -f pravidla.toml || (cp pravidla.example.toml pravidla.toml && echo "Vytvořen pravidla.toml ze vzoru – uprav ho a spusť znovu." && false)
	$(BIN)/python -m hlidac.rules_cli import pravidla.toml

rules: install  ## List rules
	$(BIN)/python -m hlidac.rules_cli list

preview: install  ## How many listings would each rule catch
	$(BIN)/python -m hlidac.rules_cli preview

test-notify: install  ## Send a test notification to all channels
	$(BIN)/python -m hlidac.rules_cli test-notify

test: install  ## Run automated tests
	$(BIN)/python -m pytest -q

clean:  ## Remove .venv (keeps your data/)
	rm -rf $(VENV) *.egg-info
