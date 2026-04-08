# CLAUDE.md

## Project overview

nwb-video-widgets is a Python library providing interactive Jupyter widgets for visualizing NWB (Neurodata Without Borders) video data and pose estimation overlays. Built with `anywidget` for cross-platform Jupyter compatibility (JupyterLab, Notebook, VS Code, Colab). Supports both local NWB files and remote streaming from the DANDI Archive.

## Architecture

Design decisions, package structure, intent, and logic are documented in `documentation/design/`. Read the relevant documents there before making architectural changes.

## Commands

```bash
# Install all dependencies (including dev and optional)
uv sync --all-extras

# Run tests
uv run pytest tests/ -v

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Run pre-commit hooks
uv run pre-commit run --all-files
```

## Test markers

- `@pytest.mark.slow` - Long-running tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.dandi` - Tests that require network access to DANDI Archive

## Code conventions

- Python 3.10+, line length 120 characters
- Ruff for linting and formatting (configured in pyproject.toml)
- Pre-commit hooks enforce ruff, trailing whitespace, end-of-file fixes
- Use `uv` for all Python execution (`uv run pytest`, `uv run python`, etc.)
- Relative imports within the package
- Any source code change requires an update to CHANGELOG.md (enforced in CI)

## CI

Tests run on Python 3.10 and 3.13 across Ubuntu, Windows, and macOS. Publishing to PyPI is triggered by GitHub Releases with tags starting with `v`.
