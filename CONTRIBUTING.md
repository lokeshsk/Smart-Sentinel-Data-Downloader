# Contributing to Smart Sentinel Downloader

Thank you for your interest in contributing! Whether you are reporting an issue, proposing a feature, or submitting code, your help is appreciated.

---

## 🛠️ Development Setup

We use [Astral `uv`](https://astral.sh/uv) for fast, reliable package and dependency management.

### 1. Prerequisites
- Python 3.8+
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `pip install uv`)

### 2. Clone and Install
```bash
git clone https://github.com/lokeshsk/Smart-Sentinel-Data-Downloader.git
cd Smart-Sentinel-Data-Downloader

# Create virtual environment and install dependencies in editable mode
uv venv
uv pip install -e ".[dev]"
```

---

## 🧪 Running Tests & Linting

Before opening a pull request, ensure all tests pass and code is cleanly formatted.

### Run Unit Tests
```bash
uv run pytest -v
```

### Run Linter
```bash
uv run ruff check .
```

### Auto-fix Linting Issues
```bash
uv run ruff check --fix .
```

---

## 📦 Building Distributions for PyPI

To build distribution wheels and source archives:
```bash
uv build
```
Built artifacts are stored in the `dist/` directory.

---

## 🚀 Pull Request Guidelines

1. **Branch Naming**: Use descriptive prefixes like `feat/new-sensor-support`, `fix/uuid-detection`, or `docs/update-examples`.
2. **Add Unit Tests**: Any new feature or bug fix must include corresponding tests under `tests/`.
3. **Keep Commits Clean**: Write concise, informative commit messages following conventional commits (`feat: ...`, `fix: ...`, `docs: ...`).
4. **CI Checks**: Ensure GitHub Actions workflow runs cleanly on your branch.

