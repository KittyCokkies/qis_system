# QIS System - Makefile
# Common development and deployment commands

.PHONY: help install test lint format db-migrate db-upgrade db-downgrade clean

# Default target
help:
	@echo "QIS System - Available Commands"
	@echo "================================"
	@echo "  make install       - Install dependencies from requirements.txt"
	@echo "  make test          - Run test suite"
	@echo "  make test-cov      - Run tests with coverage report"
	@echo "  make lint          - Run code linting (ruff)"
	@echo "  make format        - Format code (black)"
	@echo "  make db-init       - Initialize database tables"
	@echo "  make db-migrate    - Create new migration (use MESSAGE='msg')"
	@echo "  make db-upgrade    - Apply database migrations"
	@echo "  make db-downgrade  - Rollback last migration"
	@echo "  make db-history    - Show migration history"
	@echo "  make sync-daily    - Run daily data sync"
	@echo "  make clean         - Remove cache files"
	@echo "  make run           - Start the application"

# Development setup
install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements.txt
	pip install -e .

# Testing
test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=. --cov-report=html --cov-report=term

# Code quality
lint:
	ruff check .

format:
	black . --line-length 100
	isort . --profile black

format-check:
	black . --line-length 100 --check
	isort . --profile black --check-only

# Database operations
db-init:
	python -c "from data.database import DatabaseManager; db = DatabaseManager(); db.create_tables()"

db-migrate:
	@if not defined MESSAGE (echo "Usage: make db-migrate MESSAGE='description'" && exit /b 1)
	alembic revision --autogenerate -m "$(MESSAGE)"

db-upgrade:
	alembic upgrade head

db-downgrade:
	alembic downgrade -1

db-history:
	alembic history --verbose

db-current:
	alembic current

# Data sync
sync-daily:
	python scripts/sync_daily.py

sync-config:
	python scripts/import_config.py

# Application
run:
	python main.py

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov 2>/dev/null || true

# Windows cleanup (for Git Bash)
clean-win:
	powershell -Command "Get-ChildItem -Recurse -Filter __pycache__ | Remove-Item -Recurse -Force"
	powershell -Command "Get-ChildItem -Recurse -Filter *.pyc | Remove-Item -Force"
