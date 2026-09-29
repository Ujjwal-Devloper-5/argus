# Contributing to Argus

Thank you for your interest in contributing to Argus! This document walks you through everything you need to know — from setting up your development environment to getting your pull request merged.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Environment](#development-environment)
- [Project Architecture](#project-architecture)
- [Making Changes](#making-changes)
- [Commit Convention](#commit-convention)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Code Standards](#code-standards)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

---

## Code of Conduct

This project is a welcoming space for all contributors. We expect:

- Respectful and constructive communication
- Focusing on the technical merit of contributions
- Helping others learn and grow

---

## How Can I Contribute?

### Good First Issues

Look for issues tagged [`good first issue`](https://github.com/yourusername/argus/labels/good%20first%20issue). These are self-contained tasks that do not require deep knowledge of the whole codebase.

### Help Wanted

Issues tagged [`help wanted`](https://github.com/yourusername/argus/labels/help%20wanted) are areas where maintainers are actively looking for contributors.

### Other Ways to Help

- Improve documentation and tutorials
- Add RTSP camera profiles (test and document camera-specific stream URLs)
- Write tests to improve coverage
- Translate documentation
- Share Argus with others and report your experience

---

## Development Environment

### Requirements

- Python 3.11 or newer
- `git`
- `ffmpeg` (`sudo apt install ffmpeg` / `sudo pacman -S ffmpeg` / `brew install ffmpeg`)
- CUDA-capable GPU (recommended, not required — CPU mode is fully supported)

### Setup

```bash
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/argus.git
cd argus

# 2. Add the upstream remote
git remote add upstream https://github.com/yourusername/argus.git

# 3. Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
# .venv\Scripts\activate       # Windows

# 4. Install in editable mode with all dev dependencies
pip install -e ".[dev]"

# 5. Install pre-commit hooks
#    These run ruff and mypy automatically before every commit
pre-commit install

# 6. Copy config templates
cp .env.example .env
cp config/config.example.yaml config/config.yaml

# 7. Run database migrations
alembic upgrade head

# 8. Confirm everything works
make test
```

If `make test` passes, your environment is ready.

---

## Project Architecture

Before making changes, read the [architecture section in README.md](README.md#architecture) and familiarise yourself with the module responsibilities:

| Module | Responsibility |
|---|---|
| `argus/config/` | Pydantic-Settings typed config — single source of truth |
| `argus/core/` | Vision pipeline: stream → motion filter → YOLO → face recognition → recording |
| `argus/intelligence/` | AI layer: Laya 421M gate + vision LLM providers + AutoLearner |
| `argus/alerts/` | Alert engine: priority queue, rate limiter, Telegram, Discord |
| `argus/storage/` | Async upload manager: local disk, rclone cloud backends |
| `argus/database/` | SQLAlchemy ORM models + async repository pattern |
| `argus/pipeline/` | EventOrchestrator — wires all modules together |
| `argus/dashboard/` | Streamlit web UI |

---

## Making Changes

### 1. Create a branch

Always work on a branch, never directly on `master`.

```bash
# Sync with upstream first
git fetch upstream
git checkout master
git merge upstream/master

# Create your branch
git checkout -b feat/your-feature-name
# or
git checkout -b fix/issue-description
```

Branch naming convention:

| Prefix | When to use |
|---|---|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `test/` | Tests only |
| `refactor/` | Code restructure, no behaviour change |
| `perf/` | Performance improvement |
| `chore/` | Dependency updates, config changes |

### 2. Make your changes

- Write code following the [Code Standards](#code-standards) below.
- Write tests for any new behaviour (see [Testing Requirements](#testing-requirements)).
- Update docstrings for changed functions.
- If you changed configuration fields, update `config/config.example.yaml`.

### 3. Verify locally

```bash
make lint    # Must be clean (0 ruff errors, 0 mypy errors)
make test    # Must all pass, coverage must not drop below 80%
```

---

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/). Every commit message must follow this format:

```
<type>(<scope>): <short description>

[optional body — explain WHY, not WHAT]

[optional footer — BREAKING CHANGE: or Closes #123]
```

### Types

| Type | When to use |
|---|---|
| `feat` | New user-facing feature |
| `fix` | Bug fix |
| `docs` | Documentation changes only |
| `test` | Adding or fixing tests |
| `refactor` | Code change with no feature/fix |
| `perf` | Performance improvement |
| `chore` | Maintenance (deps, config, CI) |
| `ci` | CI/CD pipeline changes |

### Scopes

```
core | intelligence | alerts | storage | dashboard | database | config | pipeline | cli | docs
```

### Examples

```bash
git commit -m "feat(alerts): add ntfy.sh push notification channel"
git commit -m "fix(intelligence): handle Laya model load failure gracefully"
git commit -m "docs(readme): add ONVIF camera discovery section"
git commit -m "test(alerts): add adversarial tests for quiet hours gate"
git commit -m "perf(core): skip face recognition when motion score < threshold"
git commit -m "chore: bump python-telegram-bot to 21.1"
```

---

## Testing Requirements

### Rules

1. **All existing tests must pass.** No exceptions. A PR that breaks existing tests will not be merged.
2. **New behaviour must have tests.** If you add a feature, add tests for it.
3. **Coverage must not drop below 80%.** Check with `make test` — it prints the coverage percentage.
4. **All external API calls must be mocked.** Tests must run without real Telegram tokens, Discord tokens, or OpenAI keys.
5. **Tests must be deterministic.** No tests that are timing-dependent or randomly fail.

### Writing Tests

Tests live in `tests/` and mirror the package structure:

```
tests/
├── core/           # Tests for argus/core/
├── intelligence/   # Tests for argus/intelligence/
├── alerts/         # Tests for argus/alerts/
├── storage/        # Tests for argus/storage/
├── database/       # Tests for argus/database/
├── config/         # Tests for argus/config/
└── conftest.py     # Shared fixtures
```

#### Mocking External Services

```python
# Telegram API
from unittest.mock import AsyncMock, patch

async def test_telegram_send(info_alert):
    with patch("argus.alerts.telegram_client.Application") as MockApp:
        mock_app = MagicMock()
        mock_app.bot.send_message = AsyncMock()
        MockApp.builder.return_value.token.return_value.build.return_value = mock_app
        ...

# Discord API
with patch("argus.alerts.discord_client.discord") as mock_discord:
    ...

# OpenAI / httpx
with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
    ...
```

#### Test Naming Convention

```python
def test_<unit>_<scenario>():
    ...

# Examples
def test_rate_limiter_throttles_burst():
def test_quiet_hours_passes_critical_alert():
def test_telegram_returns_false_on_network_error():
def test_alert_manager_routes_to_discord_only():
```

### Running Tests

```bash
# Full suite with coverage
make test

# Specific module
.venv/bin/python -m pytest tests/alerts/ -v

# Single test
.venv/bin/python -m pytest tests/alerts/test_alert_engine.py::test_queue_priority_order -v

# Without coverage (faster)
.venv/bin/python -m pytest --no-cov tests/

# Generate HTML coverage report
.venv/bin/python -m pytest --cov=argus --cov-report=html
open htmlcov/index.html
```

---

## Pull Request Process

### Before Opening

- [ ] All tests pass (`make test`)
- [ ] Linting is clean (`make lint`)
- [ ] Commits follow Conventional Commits format
- [ ] New code has tests
- [ ] Coverage has not dropped below 80%
- [ ] `config.example.yaml` is updated if you added config fields

### PR Description Template

```markdown
## What does this PR do?
<!-- One sentence summary -->

## Why?
<!-- Context and motivation -->

## How was it tested?
<!-- Describe what you tested and how -->

## Checklist
- [ ] Tests pass
- [ ] Linting clean
- [ ] Coverage ≥ 80%
- [ ] External APIs are mocked in tests
- [ ] Config example updated (if applicable)
- [ ] Documentation updated (if applicable)

## Related Issues
Closes #<issue number>
```

### Review Process

1. A maintainer will review your PR within a few days.
2. Requested changes must be addressed before merge.
3. Respond to comments directly — do not force-push while a review is active.
4. Once approved, a maintainer will squash-merge your PR.

---

## Code Standards

These rules apply to every file without exception:

### Type Hints

```python
# ✅ Correct — fully annotated
async def detect(self, frame: np.ndarray) -> list[Detection]:
    ...

# ❌ Wrong — no annotations
async def detect(self, frame):
    ...
```

### Structured Logging

```python
# ✅ Correct — structured, contextual
logger.info("Face matched", profile_id=match.profile.id, similarity=match.similarity, camera=camera.name)

# ❌ Wrong — unstructured
print(f"Face matched: {match.profile.id}")
logger.info(f"Face matched {match.profile.id}")
```

### Error Handling

```python
# ✅ Correct — specific exception, log with context, safe fallback
try:
    result = await provider.analyze(frame)
except httpx.TimeoutException:
    logger.warning("LLM provider timeout", provider=self._provider, camera=camera.name)
    return SAFE_FALLBACK  # Never raises to caller

# ❌ Wrong — bare except, silent failure
try:
    result = await provider.analyze(frame)
except:
    pass
```

### Async Safety

```python
# ✅ Correct — CPU/GPU work off event loop
embedding = await asyncio.get_event_loop().run_in_executor(
    self._executor, self._model.get, frame_bgr
)

# ❌ Wrong — blocks the entire async event loop
embedding = self._model.get(frame_bgr)
```

### Dependency Injection

```python
# ✅ Correct — all dependencies injected, fully testable
class AlertManager:
    def __init__(self, settings: Settings, callback_handler: CallbackHandler | None = None):
        ...

# ❌ Wrong — global singleton, not testable
_manager = AlertManager()   # module-level
```

### Pydantic for Data

```python
# ✅ Correct — validated, typed, serialisable
class Detection(BaseModel):
    box: tuple[int, int, int, int]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    class_name: str

# ❌ Wrong — raw dict, no validation
{"box": [x1, y1, x2, y2], "conf": 0.9}
```

---

## Reporting Bugs

1. Search [existing issues](https://github.com/yourusername/argus/issues) first — it may already be reported.
2. If not found, open a [new issue](https://github.com/yourusername/argus/issues/new?template=bug_report.md) and include:
   - Your OS, Python version, and GPU (if applicable)
   - Argus version (`python -m argus --version`)
   - Clear steps to reproduce
   - Expected vs actual behaviour
   - Relevant log output — **redact any tokens, API keys, or RTSP URLs with credentials**

---

## Requesting Features

1. Search [existing issues](https://github.com/yourusername/argus/issues) — it may already be planned.
2. Open a [feature request](https://github.com/yourusername/argus/issues/new?template=feature_request.md) describing:
   - The problem you are trying to solve
   - Your proposed solution
   - Alternatives you considered

Large features benefit from discussion before implementation. Opening an issue first prevents you from doing work that goes in a different direction from the project's goals.

---

## Questions?

If you have a question that is not covered here, open a [Discussion](https://github.com/yourusername/argus/discussions) rather than an issue.

---

*Thank you for helping make Argus better.*
