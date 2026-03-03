set dotenv-load

# Start the full stack in Docker (postgres → migrations → mcp-server)
up *args:
    docker compose up -d --build {{args}}

# Stop all services
down *args:
    docker compose down {{args}}

# Rebuild and restart all services
rebuild *args:
    docker compose up -d --build --force-recreate {{args}}

# Show logs (all services, or pass a service name)
logs *args:
    docker compose logs -f {{args}}

# Show service status
ps:
    docker compose ps

# Start MCP server locally without Docker (for rapid dev)
dev:
    uv run python -m sovereign_brain.mcp

# Install Python dependencies
install:
    uv sync

# Run tests
test *args:
    uv run pytest {{args}}

# Lint
lint:
    uv run ruff check sovereign_brain/ tests/
    uv run ruff format --check sovereign_brain/ tests/

# Fix lint issues
lint-fix:
    uv run ruff check --fix sovereign_brain/ tests/
    uv run ruff format sovereign_brain/ tests/

# Create a new migration file (local golang-migrate)
migrate-create name:
    migrate create -ext sql -dir migrations -seq -digits 14 {{name}}

# Apply migrations locally (requires DATABASE_URL in .env)
migrate-up:
    migrate -path migrations -database "${DATABASE_URL}?sslmode=disable" up

# Roll back one migration locally
migrate-down:
    migrate -path migrations -database "${DATABASE_URL}?sslmode=disable" down 1
