PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

.PHONY: install dev watcher web stats test clean import-rules rules preview test-notify icons

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -e ".[dev]"

install: $(BIN)/python  ## Create .venv and install dependencies

dev: install  ## Run watcher + web app locally (Ctrl+C to stop)
	./scripts/dev.sh

watcher: install  ## Run only the watcher
	@test -f .env || cp .env.example .env
	$(BIN)/python -m hlidac.watcher

web: install  ## Run only the web app (http://localhost:8000)
	$(BIN)/python -m hlidac.web.app

icons:  ## Regenerate app icons
	python3 scripts/make_icons.py

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
