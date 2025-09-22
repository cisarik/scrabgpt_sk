# Repository Guidelines

## Project Structure & Module Organization
`scrabgpt/` holds all runtime code: `core/` for board math and rules, `ai/` for GPT prompts/parsers, `ui/` for PySide6 widgets, and `assets/` for board metadata. `config.py` centralizes environment flags; `logging_setup.py` wires Rich logging. Tests live in `tests/`, mirroring domain areas; add fixtures beside the scenarios they support. Utility scripts such as `tools/clear.sh` stay in `tools/`, and docs (`README.md`, `PRD.md`) should track product behavior.

## Build, Test, and Development Commands
`poetry install` provisions dependencies and the virtualenv. Run the desktop app via `poetry run python -m scrabgpt.ui.app` or the CLI shim `poetry run scrabgpt`. Execute automated checks with `poetry run pytest`, optionally `-k keyword` for a subset. Enforce style through `poetry run ruff check` (add `--fix` when safe) and typing with `poetry run mypy`. Run commands from the repo root so relative paths resolve.

## Coding Style & Naming Conventions
Code targets Python ≥3.10, 4-space indentation, and a 100-character limit enforced by Ruff. Type hints are mandatory because `mypy` runs in strict mode. Modules remain snake_case; Qt classes and QObject descendants use CamelCase. Pydantic models or dataclasses should back structured exchanges with OpenAI, and avoid heavy logic at import time—prefer pure functions plus explicit wiring in entry points.

## Testing Guidelines
Tests follow the `tests/test_<feature>.py` pattern and use pytest. Name functions `test_<behavior>_<condition>` to clarify intent. Reuse fixtures that craft boards, racks, and ENABLE lists; place new fixtures in the same module when feature-specific. When modifying AI move evaluation, cover both online and offline judge paths before merging. Always run `poetry run pytest` locally, and do not rely on real OpenAI traffic.

## Commit & Pull Request Guidelines
History is empty, so default to concise, imperative commit subjects (e.g., `Add offline judge cache`) with optional short bodies for context or follow-ups. PRs should brief the functional change, cite manual/automated checks, and link related issues. Attach screenshots or clips for UI updates and list any `.env` keys, migrations, or assets reviewers must prepare.

## Configuration & Secrets
Copy `.env.example` to `.env` and supply OpenAI credentials prior to launch. ENABLE word lists download to `~/.scrabgpt/wordlists/`; never commit generated files. Use `OFFLINE_JUDGE_URL` overrides only in controlled tests, mocking outbound calls instead of hitting live mirrors.
