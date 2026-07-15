# Development Guide

## Prerequisites

- **Python 3.12** with `pip`
- **Java Runtime** (for WireMock in integration tests)
- **Docker** (for container builds)

## Environment Setup

```sh
# Clone the repository
git clone git@github.com:dynatrace-oss/dynatrace-gcp-monitor.git
cd dynatrace-gcp-monitor

# Install all dependencies
pip install -r src/requirements.txt
pip install -r tests/requirements.txt
pip install -r requirements-dev.txt

# Set PYTHONPATH (required for all test/run commands)
export PYTHONPATH="src:tests"
```

On Windows, the `cryptography` library may need special handling:
```sh
pip install --only-binary :all: cryptography
```

## Running Locally

### Quick single run (Metrics)

Edit `src/dev_local_run.py` and fill in the placeholder values:

| Variable | What to set |
|---|---|
| `GCP_PROJECT` | Your GCP project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to a GCP service account key JSON file |
| `DYNATRACE_URL` | Your Dynatrace environment URL (e.g., `https://abc12345.live.dynatrace.com`) |
| `DYNATRACE_ACCESS_KEY` | A Dynatrace API token with metrics ingest scope |
| `ACTIVATION_CONFIG` | JSON defining which services/featureSets to monitor |

Then run:
```sh
cd src
python dev_local_run.py
```

This starts `run_docker.main()` which runs the polling loop continuously. For a single execution that returns immediately, call `main.py`'s `async_dynatrace_gcp_extension()` directly.

### Logs mode

Set `OPERATION_MODE=Logs` in `dev_local_run.py` and additionally configure:
- `LOGS_SUBSCRIPTION_ID` — your Pub/Sub subscription ID
- `DYNATRACE_LOG_INGEST_URL` — Dynatrace Log Ingest endpoint URL

## Testing

### Unit tests

```sh
pytest tests/unit -v
```

Run a single test file:
```sh
pytest tests/unit/test_utilities.py -v
```

Run a single test function:
```sh
pytest tests/unit/test_utilities.py::test_safe_read_yaml_reads_file_successfully -v
```

Unit tests use plain `pytest` with `unittest.mock`. Async tests use `pytest-asyncio`.

### Integration tests

**Logs integration tests:**
```sh
pytest tests/integration/logs -v
```

**Metrics integration tests:**
```sh
cd tests/integration/metrics
pytest -v
```

> ⚠️ Metrics integration tests **must** be run from inside `tests/integration/metrics/`. WireMock loads stub mappings from relative `mappings/` and `__files/` directories in the current working directory. Running from the project root will fail.

Integration tests require a Java runtime for WireMock.

### Test structure

- `tests/unit/` — fast, isolated tests with mocked dependencies
- `tests/unit/lib/` — tests for `src/lib/` submodules (mirrors source structure)
- `tests/integration/logs/` — log pipeline integration tests
- `tests/integration/metrics/` — full metrics flow with WireMock stubs
- `tests/testresources/` — shared test data files and fixtures
- `tests/e2e/` — end-to-end Helm deployment tests (CI-only, require GCP credentials)

## Linting

```sh
flake8 src/
```

Configuration in `setup.cfg`:
- Max line length: **100 characters**
- Ignored rules: `F401` (unused imports), `F403` (wildcard imports)

Pylint configuration is also available in `.pylintrc` but flake8 is the primary linter used in CI.

## Docker

### Build

```sh
docker build -t dynatrace-gcp-monitor .
```

The Dockerfile uses a multi-stage build:
1. **Build stage** — installs build tools and compiles native dependencies from `src/requirements.txt`.
2. **Runtime stage** — `python:3.12-slim`, copies only compiled packages and `src/` contents. Runs as non-root user `gcp-monitor`.

### Run

```sh
docker run \
  -e GCP_PROJECT=your-project-id \
  -e DYNATRACE_URL=https://your-env.live.dynatrace.com \
  -e DYNATRACE_ACCESS_KEY=your-api-token \
  -e GOOGLE_APPLICATION_CREDENTIALS=/keys/sa-key.json \
  -e ACTIVATION_CONFIG='{"services":[{"service":"api","featureSets":["default_metrics"]}]}' \
  -v /path/to/sa-key.json:/keys/sa-key.json:ro \
  dynatrace-gcp-monitor
```

The container exposes a health check endpoint at `GET /health` on port 8080 (configurable via `HEALTH_CHECK_PORT`).

## Debugging

### Verbose metric output

Set `PRINT_METRIC_INGEST_INPUT=true` to log every MINT ingest line before it's sent to Dynatrace. Useful for verifying metric transformations.

### Self-monitoring

Set `SELF_MONITORING_ENABLED=true` to push diagnostic metrics to GCP Cloud Monitoring. These track request counts, error rates, and execution times. See [docs/sfm_log.MD](sfm_log.MD) for log-specific SFM metrics.

### Common issues

- **Tests fail with `ModuleNotFoundError`** — ensure `PYTHONPATH="src:tests"` is set.
- **Metrics integration tests fail with WireMock errors** — run from inside `tests/integration/metrics/`, not from the project root.
- **Windows async noise** — `aiohttp` may produce warnings on Windows at shutdown. This is a known upstream issue ([aiohttp#4324](https://github.com/aio-libs/aiohttp/issues/4324)).
- **Token errors locally** — verify `GOOGLE_APPLICATION_CREDENTIALS` points to a valid service account key with the required IAM roles (see `gcp_iam_roles/`).
