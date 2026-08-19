SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
VENV := $(BACKEND)/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help setup backend-setup frontend-setup api ui test clean

help:
	@echo "Garimpo.ai"
	@echo "  make setup      instala backend (venv) e frontend (npm)"
	@echo "  make api        sobe a API em http://localhost:8000"
	@echo "  make ui         sobe a interface em http://localhost:4200"
	@echo "  make test       roda os testes do backend"
	@echo ""
	@echo "Rode 'make api' e 'make ui' em dois terminais."

setup: backend-setup frontend-setup

backend-setup:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND)/requirements.txt

frontend-setup:
	cd $(FRONTEND) && npm install

api:
	cd $(BACKEND) && .venv/bin/python -m uvicorn garimpo.main:app --reload --port 8000

ui:
	cd $(FRONTEND) && npm start

test:
	cd $(BACKEND) && .venv/bin/python -m pytest tests -q

clean:
	rm -rf $(VENV) $(FRONTEND)/node_modules $(FRONTEND)/dist
