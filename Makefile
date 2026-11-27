SHELL := /bin/bash
PY := backend/.venv/bin/python
HOST := 127.0.0.1

.PHONY: setup hooks dev run build seed demo import test lint clean

setup: hooks ## Install backend + frontend dependencies
	cd backend && python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt
	cd frontend && npm install --no-fund --no-audit

hooks: ## Enable the privacy pre-commit hook
	@git rev-parse --git-dir >/dev/null 2>&1 && git config core.hooksPath .githooks && echo "pre-commit hook enabled" || echo "not a git repo yet: run 'git init' then 'make hooks'"

dev: ## Backend (auto-reload) + Vite dev server → http://127.0.0.1:5173
	trap 'kill 0' EXIT; \
	(cd backend && .venv/bin/uvicorn app.main:app --reload --host $(HOST) --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

build: ## Build the frontend into frontend/dist
	cd frontend && npm run build

run: build ## Single process for daily use → http://127.0.0.1:8000
	cd backend && .venv/bin/uvicorn app.main:app --host $(HOST) --port 8000

seed: ## Generate fictional demo data into data/demo.db
	cd backend && .venv/bin/python -m app.seed

demo: seed build ## Run the app against the fictional demo data
	cd backend && APPLYTRAIL_DEMO=1 .venv/bin/uvicorn app.main:app --host $(HOST) --port 8000

import: ## Import a tracker workbook's "Applied" sheet: make import XLSX=path/to/file.xlsx [DRY=1]
	@test -n "$(XLSX)" || { echo 'usage: make import XLSX=path/to/file.xlsx [DRY=1]'; exit 2; }
	@f="$(XLSX)"; f="$$(cd "$$(dirname "$$f")" && pwd)/$$(basename "$$f")"; \
	cd backend && .venv/bin/python -m app.import_xlsx "$$f" $(if $(DRY),--dry-run,)

test: ## Backend tests + frontend type-check
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm run typecheck

lint:
	cd backend && .venv/bin/ruff check app tests

clean:
	rm -rf frontend/dist backend/.pytest_cache
