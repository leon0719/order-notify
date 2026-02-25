.PHONY: all format lint lint-fix type-check check test coverage clean unused help
.PHONY: install up down logs build rebuild
.PHONY: migrate makemigrations shell createsuperuser
.PHONY: docker-clean logs-api logs-db logs-worker logs-flower

COMPOSE_DEV = docker compose -f docker/docker-compose.dev.yml

# ===================
# Help
# ===================

help:
	@echo "========================================"
	@echo "  Order Notify - Django Ninja + Celery"
	@echo "========================================"
	@echo ""
	@echo "Development (Docker):"
	@echo "  make up                - Start all dev containers (7 services)"
	@echo "  make down              - Stop all dev containers"
	@echo "  make build             - Build dev images only (no start)"
	@echo "  make rebuild           - Rebuild and start (after Dockerfile/pyproject.toml changes)"
	@echo "  make logs              - View all service logs"
	@echo "  make logs-api          - View API logs"
	@echo "  make logs-db           - View database logs"
	@echo "  make logs-worker       - View Celery worker logs"
	@echo "  make logs-flower       - View Celery Flower logs"
	@echo ""
	@echo "Django Commands (in dev container):"
	@echo "  make migrate           - Run database migrations"
	@echo "  make makemigrations    - Create new migration files"
	@echo "  make shell             - Open Django shell"
	@echo "  make createsuperuser   - Create admin user"
	@echo ""
	@echo "Code Quality:"
	@echo "  make all               - Run all checks (format + lint + type-check)"
	@echo "  make format            - Format code with ruff"
	@echo "  make lint              - Lint code with ruff"
	@echo "  make type-check        - Type check with mypy"
	@echo "  make unused            - Check for unused functions/classes/constants"
	@echo "  make test              - Run tests"
	@echo "  make coverage          - Run tests with coverage report"
	@echo ""
	@echo "Other:"
	@echo "  make install           - Install local deps (for IDE)"
	@echo "  make clean             - Clean cache files"
	@echo "  make docker-clean      - Remove Docker volumes"
	@echo ""
	@echo "URLs:"
	@echo "  API Docs:     http://localhost:80/api/docs"
	@echo "  RabbitMQ UI:  http://localhost:15672 (guest/guest)"
	@echo "  Flower:       http://localhost:5555"

# ===================
# Local Setup (for IDE)
# ===================

install:
	uv sync

# ===================
# Development (Docker)
# ===================

up:
	$(COMPOSE_DEV) up -d
	@echo ""
	@echo "All 7 services started!"
	@echo "  Nginx:       http://localhost:80"
	@echo "  API:         http://localhost:8000"
	@echo "  API Docs:    http://localhost:80/api/docs"
	@echo "  RabbitMQ UI: http://localhost:15672"
	@echo "  Flower:      http://localhost:5555"
	@echo ""
	@echo "First time? Run:"
	@echo "  make migrate"
	@echo "  make createsuperuser"

down:
	$(COMPOSE_DEV) down

build:
	$(COMPOSE_DEV) build

rebuild:
	$(COMPOSE_DEV) up -d --build

logs:
	$(COMPOSE_DEV) logs -f

logs-api:
	$(COMPOSE_DEV) logs -f api

logs-db:
	$(COMPOSE_DEV) logs -f db

logs-worker:
	$(COMPOSE_DEV) logs -f celery_worker

logs-flower:
	$(COMPOSE_DEV) logs -f celery_flower

docker-clean:
	$(COMPOSE_DEV) down -v
	@echo "Docker volumes removed"

# ===================
# Django Commands (in dev container)
# ===================

migrate:
	$(COMPOSE_DEV) exec api uv run python manage.py migrate

makemigrations:
	$(COMPOSE_DEV) exec api uv run python manage.py makemigrations

shell:
	$(COMPOSE_DEV) exec api uv run python manage.py shell

createsuperuser:
	$(COMPOSE_DEV) exec api uv run python manage.py createsuperuser

# ===================
# Code Quality
# ===================

all:
	@echo "Running all code quality checks..."
	@$(MAKE) format
	@echo ""
	@$(MAKE) lint
	@echo ""
	@$(MAKE) type-check
	@echo ""
	@$(MAKE) clean
	@echo "All checks completed!"

format:
	@echo "Formatting code with ruff..."
	@uv run ruff format .

lint:
	@echo "Linting code with ruff..."
	@uv run ruff check --fix .

type-check:
	@echo "Running type checks with mypy..."
	@uv run mypy .

unused:
	@echo "Checking for unused symbols..."
	@uv run python scripts/check_unused_functions.py

test:
	@echo "Running tests..."
	@$(COMPOSE_DEV) exec api uv run pytest $(TEST)

coverage:
	@echo "Running tests with coverage..."
	@$(COMPOSE_DEV) exec api uv run pytest --cov=apps --cov-report=term-missing --cov-report=html $(TEST)
	@echo "HTML report generated at htmlcov/"

# ===================
# Cleanup
# ===================

clean:
	@echo "Cleaning cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf htmlcov .coverage 2>/dev/null || true
	@echo "Cache cleaned!"
