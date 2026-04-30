# Architecture

## System Overview

Dynatrace GCP Monitor is a bridge between Google Cloud Platform's monitoring/logging infrastructure and Dynatrace's ingestion APIs. It runs as a long-lived container process that periodically fetches data from GCP and pushes it to Dynatrace.

```
┌─────────────────────┐         ┌──────────────────────┐         ┌───────────────────┐
│   GCP Monitoring    │         │  dynatrace-gcp-      │         │    Dynatrace      │
│   API (metrics)     │◄────────│  monitor             │────────►│  Metrics API v2   │
│                     │  poll   │                      │  push   │  (MINT ingest)    │
├─────────────────────┤         │  ┌────────────────┐  │         ├───────────────────┤
│   GCP Pub/Sub       │◄────────│  │  Metrics mode  │  │────────►│  Log Ingest API   │
│   (log entries)     │  pull   │  │  Logs mode     │  │  push   │                   │
├─────────────────────┤         │  └────────────────┘  │         ├───────────────────┤
│   GCP Secret Mgr    │◄────────│                      │         │  Extensions API   │
│   (credentials)     │  fetch  │  Health: /health     │────────►│  (config fetch)   │
├─────────────────────┤         └──────────────────────┘         └───────────────────┘
│   GCP Resource Mgr  │
│   (project listing) │
│   GCP Service Usage │
│   (API enablement)  │
└─────────────────────┘
```

## Operation Modes

### Metrics Mode

The default mode. Runs an infinite polling loop:

1. **Pre-launch check** — `ExtensionsFetcher` calls the Dynatrace Extensions API to discover which GCP services have active extensions. This determines the set of `GCPService` objects (with their `Metric` definitions) to monitor.

2. **Polling cycle** (every `QUERY_INTERVAL_MIN` minutes, default 3):
   - **Token & context setup** — acquires a GCP OAuth access token, retrieves Dynatrace API key/URL (from env vars or GCP Secret Manager), constructs a `MetricsContext`.
   - **Project discovery** — lists all accessible GCP projects via Cloud Resource Manager, applies include/exclude filters.
   - **Topology fetch** — for each project, retrieves GCP resource instances (VMs, databases, etc.) to build an entity ID map for dimension enrichment.
   - **Metric fetch** — for each project × service × metric, calls `monitoring.googleapis.com/v3` `timeSeries.list`. Calls are issued concurrently via `asyncio.gather()`.
   - **Transform** — converts GCP time series data into `IngestLine` objects (Dynatrace MINT format), enriches with topology-derived entity IDs and dimensions.
   - **Push** — batches `IngestLine` objects (default batch size: 3000) and POSTs to the Dynatrace Metrics API v2. Supports concurrent pushes with exponential backoff on 429/5xx.

3. **Self-monitoring** — if enabled, pushes diagnostic metrics (request counts, error rates, execution times) back to GCP Cloud Monitoring.

4. **Execution time snapping** — `_snap_execution_time()` in `main.py` aligns polling cycles to the configured interval, with drift compensation and catch-up logic to avoid gaps or overlaps in queried time windows.

### Logs Mode

Runs multiple parallel processes:

1. **Fast check** — validates Dynatrace connectivity and GCP Pub/Sub subscription access.
2. **Worker processes** — `PARALLEL_PROCESSES` OS-level processes (default 1), each running concurrent coroutines that:
   - Pull messages from the GCP Pub/Sub subscription.
   - Parse log entries using per-service extraction rules from `src/config_logs/`.
   - Apply the metadata engine for attribute enrichment.
   - Batch log events respecting size/count limits.
   - Push batches to the Dynatrace Log Ingest API.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Async runtime | `asyncio` |
| HTTP client | `aiohttp` (two separate `ClientSession` pools — GCP and Dynatrace) |
| DNS | `aiodns` (async DNS resolution) |
| YAML parsing | `PyYAML` |
| JWT / Crypto | `PyJWT`, `cryptography` (for GCP service account auth) |
| Hashing | `mmh3` (MurmurHash3, for entity ID generation) |
| Log date parsing | `ciso8601`, `python-dateutil`, `pytz` |
| Log query language | `jmespath` (for extraction rules) |
| Linting | `flake8`, `pycodestyle` |
| Testing | `pytest`, `pytest-asyncio`, `pytest-mock`, `wiremock` (Java-based, for integration tests) |
| Container | Docker (Python 3.12-slim base) |
| Orchestration | Kubernetes via Helm chart |
| CI | Travis CI |

## Context Hierarchy

Contexts are the primary mechanism for threading state through async call chains. They form an inheritance hierarchy:

```
LoggingContext                    # Timestamped print-based logging with throttling
  └── ExecutionContext            # + project_id, DT credentials, SSL settings
        ├── LogsContext           # + sfm_queue, log self-monitoring
        │     └── LogsProcessingContext   # + message_publish_time
        ├── SfmContext            # + GCP token, SFM metric map, GCP session
        │     ├── MetricsContext  # + DT session, execution_time, ingest config, SFM metrics dict
        │     └── LogsSfmContext  # + subscription_id, container metadata
        └── SfmDashboardsContext  # + GCP token, operation_mode (separate hierarchy branch)
```

`MetricsContext` is the most commonly used — it carries everything needed for a complete metrics polling cycle. New functionality should accept the appropriate context type as a parameter.

## Extension-Driven Configuration

The monitor does **not** hardcode which GCP services or metrics to collect. Instead:

1. At startup, `ExtensionsFetcher` queries the Dynatrace Extensions API v2 for all installed Google Cloud extensions.
2. Each extension defines services, feature sets, and their metrics (names, sample periods, dimensions).
3. This produces a list of `GCPService` objects, each containing `Metric` definitions.
4. Optionally, **metric autodiscovery** (`METRIC_AUTODISCOVERY=true`) queries GCP for additional metric descriptors beyond what extensions define.
5. The `ACTIVATION_CONFIG` env var (JSON) can filter services, feature sets, and dimensions.

The extension config is refreshed each polling cycle when `KEEP_REFRESHING_EXTENSIONS_CONFIG=true` (default). See [HOT_RELOAD.md](HOT_RELOAD.md) for the full list of hot-reloadable values and how the dynamic ConfigMap works.

## Self-Monitoring (SFM)

When `SELF_MONITORING_ENABLED=true`, the monitor pushes diagnostic metrics to GCP Cloud Monitoring under the `custom.googleapis.com/dynatrace/` prefix. Metrics are defined as classes inheriting from base SFM types:

- **Metrics mode SFM**: defined in `sfm/for_metrics/metrics_definitions.py`, registered in the `MetricsContext.sfm` dict.
- **Logs mode SFM**: defined in `sfm/for_logs/`, pushed via an async queue.

SFM dashboards can be auto-imported into GCP Monitoring at startup.

## Deployment Model

- **Docker image**: Multi-stage build (`Dockerfile`). Build stage compiles native deps; runtime stage is `python:3.12-slim`. The working directory is `/code` with `src/` contents copied in.
- **Kubernetes**: Deployed via Helm chart (`k8s/helm-chart/dynatrace-gcp-monitor/`). The chart manages ConfigMaps (for `ACTIVATION_CONFIG`), Secrets (DT credentials), and the deployment itself.
- **Health check**: An `aiohttp` web server runs on a daemon thread (default port 8080), serving `GET /health`.
- **CI pipeline** (Travis CI): shellcheck → unit/integration tests → Docker build & push to Artifact Registry → e2e Helm deployment tests on a GKE cluster.

## Key Design Decisions

**No configuration framework** — All config is via `os.environ.get()` in `config.py`. Each setting is a standalone function. This keeps the dependency tree minimal and avoids framework lock-in.

**Print-based logging** — The codebase uses a custom `LoggingContext` that calls `print()` rather than Python's `logging` module. Log messages are formatted with UTC timestamps and bracketed context identifiers. Throttling prevents log flooding from repeated errors.

**Dual HTTP sessions** — Separate `aiohttp.ClientSession` instances for GCP and Dynatrace APIs, created via `init_gcp_client_session()` and `init_dt_client_session()`. This allows independent connection pool tuning and proxy configuration (`USE_PROXY` supports `ALL`, `DT_ONLY`, `GCP_ONLY`).

**Asyncio throughout** — All I/O-bound operations (GCP API calls, Dynatrace pushes) are async. Metrics for multiple services are fetched concurrently via `asyncio.gather()`. The polling loop itself is async with configurable timeouts.

**Execution time snapping** — Rather than using wall-clock time directly, `_snap_execution_time()` aligns polling cycles to prevent drift from causing gaps or overlaps in queried time windows. Includes catch-up logic for delayed executions (up to 30 minutes) and hard-reset for large drifts.
