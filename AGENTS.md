# AGENTS.md — dynatrace-gcp-monitor

## Project Overview

Dynatrace GCP Monitor pulls metrics and logs from Google Cloud Platform and ingests them into Dynatrace. It runs as a Docker container on Kubernetes (deployed via Helm) with two operation modes set by the `OPERATION_MODE` env var:

- **Metrics** (default) — polls GCP Monitoring API per service/project, transforms results into MINT ingest lines, pushes to Dynatrace Metrics API v2.
- **Logs** — pulls from a GCP Pub/Sub subscription, processes and batches entries, forwards to Dynatrace Log Ingest API.

## Quick Reference

| Action | Command |
|---|---|
| Install deps | `pip install -r src/requirements.txt -r tests/requirements.txt -r requirements-dev.txt` |
| Set PYTHONPATH | `export PYTHONPATH="src:tests"` |
| Integration (metrics) | `cd tests/integration/metrics && pytest -v` |

**Python version**: 3.12
**Line length**: 100 (non-default, configured in `setup.cfg`)

> ⚠️ Metrics integration tests **must** run from `tests/integration/metrics/` — WireMock loads relative `mappings/` and `__files/` directories.

Full commands (unit tests, lint, Docker): [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

## Source Structure

### Entry points

| File | Role |
|---|---|
| `src/run_docker.py` | Production entry point — runs the metrics or logs loop forever. Docker CMD target. |
| `src/main.py` | Single-execution metrics polling function (`async_dynatrace_gcp_extension`). |
| `src/dev_local_run.py` | Local dev entry point — sets env vars, then calls `run_docker.main()`. |
| `src/operation_mode.py` | `OperationMode` enum (`Metrics`, `Logs`). |

### Core modules (`src/lib/`)

| Module | Responsibility |
|---|---|
| `configuration/config.py` | All config via `os.environ.get()`. Each setting is a standalone function. |
| `context.py` | Context hierarchy: `LoggingContext` → `ExecutionContext` → `MetricsContext` / `LogsContext`. |
| `metrics.py` | Data classes: `GCPService`, `Metric`, `IngestLine`, `DimensionValue`. |
| `metric_ingest.py` | Fetch GCP time series → transform to MINT lines → push to Dynatrace. |
| `credentials.py` | GCP OAuth tokens, DT API key/URL retrieval (env vars or GCP Secret Manager). |
| `dt_extensions/` | Fetch Dynatrace extension configs to determine monitored GCP services. |
| `autodiscovery/` | Optional metric autodiscovery beyond extension-defined metrics. |
| `entities/` | GCP resource entity model and extraction. |
| `topology/` | Fetch GCP resource instances for entity ID mapping. |
| `logs/` | Log forwarding: Pub/Sub pull → process → batch → DT Log Ingest API. |
| `sfm/` | Self-monitoring metric definitions and push logic. |
| `webserver/` | Health check HTTP server (daemon thread, port `HEALTH_CHECK_PORT`). |
| `clientsession_provider.py` | Creates `aiohttp.ClientSession` instances for GCP and Dynatrace APIs. |

### Other directories

| Path | Content |
|---|---|
| `src/config_logs/` | Per-GCP-service log processing rules (extraction rules, attribute mappings). |
| `src/dashboards/` | Exported Dynatrace dashboard JSON files. |
| `tests/unit/` | Unit tests — plain pytest + `unittest.mock`. |
| `tests/integration/` | Integration tests — WireMock stubs for GCP/DT APIs. |
| `tests/testresources/` | Shared test fixtures and data files. |
| `k8s/helm-chart/` | Helm chart for Kubernetes deployment. |
| `build/` | CI scripts: Docker deploy, Helm packaging, versioning. |
| `gcp-simulator/` | Local GCP API simulator for development. |
| `gcp_iam_roles/` | IAM role definitions for GCP setup. |

## Key Environment Variables (Local Dev)

Edit `src/dev_local_run.py` or export these before running:

| Variable | Purpose |
|---|---|
| `GCP_PROJECT` | GCP project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account key file |
| `DYNATRACE_URL` | Dynatrace environment URL |
| `DYNATRACE_ACCESS_KEY` | Dynatrace API token |
| `OPERATION_MODE` | `Metrics` (default) or `Logs` |
| `ACTIVATION_CONFIG` | JSON string defining services/featureSets to monitor |
| `PRINT_METRIC_INGEST_INPUT` | `true` to log full MINT ingest payloads (debugging) |

Full environment variable reference: [HACKING.md](HACKING.md)

## Workflow Rules for AI Agents

1. Always set `PYTHONPATH="src:tests"` before running tests.
2. Run `flake8 src/` after code changes to catch lint issues.
3. When modifying metric ingestion logic, run unit tests first (`pytest tests/unit -v`), then integration tests.
4. Configuration is **only** via environment variables — never introduce config file parsing.
5. Thread `MetricsContext` or `LogsContext` through function calls — don't read `config.*` directly in deep functions.
6. Integration tests for metrics **must** be run from inside `tests/integration/metrics/`.
7. Log processing rules live in `src/config_logs/<service-name>/` — one directory per GCP service.
8. Self-monitoring metrics: define in `sfm/for_metrics/metrics_definitions.py`, register in `MetricsContext.__init__`.

## Documentation

| Document | Description |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture, tech stack, design decisions |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Setup, local run, testing, debugging |
| [docs/HOT_RELOAD.md](docs/HOT_RELOAD.md) | Hot-reload configuration — what can change without a pod restart |
| [docs/INDEX.md](docs/INDEX.md) | Full documentation index |
| [HACKING.md](HACKING.md) | Environment variables reference, local run modes, experimental features |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to add dashboards and GCP service support |
| [README.md](README.md) | Project overview, deployment links, support |
