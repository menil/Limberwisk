# Project Task Runner

# List available recipes
default:
    @just --list

# Format code
format:
    ruff format .
    ruff check --fix .

# Run linting checks (code style and formatting)
lint:
    ruff check .
    ruff format --check .

# Run the unit tests (pure Python; no device, Wispr Flow or macOS frameworks needed)
test:
    pytest

# Run all local checks (tests, format checks, lints)
validate: lint test
