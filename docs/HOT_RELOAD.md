# Hot-Reload Configuration Guide

Dynatrace GCP Monitor supports **hot-reloading** a subset of its configuration — meaning you can change certain Helm values and have the running pod pick them up **without a restart**.

## How It Works

The Helm chart splits configuration across two Kubernetes ConfigMaps:

| ConfigMap | Kind | What happens on change |
|---|---|---|
| `dynatrace-gcp-monitor-config` | **Static** | Pod restarts automatically (Deployment annotation `checksum/config` triggers a rollout). |
| `dynatrace-gcp-monitor-config-dynamic` | **Dynamic** | Pod stays running; new values are picked up on the next polling cycle. |

After `helm upgrade`:

- **Static ConfigMap changed** → the `checksum/config` annotation changes → pod rollout (restart).
- **Dynamic ConfigMap changed** → Kubernetes propagates new files to the volume mount (~60 s for kubelet sync) → the application re-reads YAML files from disk on the next polling/autodiscovery cycle → new configuration in effect.

The dynamic ConfigMap is mounted as a volume at `/code/config/activation/` inside the container. Kubernetes automatically updates mounted ConfigMap files when the ConfigMap changes — the application simply re-reads them from disk on each cycle.

### Where the re-read happens in code

| Value | Read function | Called from |
|---|---|---|
| `gcpServicesYaml` | `read_activation_yaml()` → `safe_read_yaml()` | `prepare_services_config_for_next_polling()` — runs every polling cycle when `KEEP_REFRESHING_EXTENSIONS_CONFIG=true` (default) |
| `excludedMetricsAndDimensions` | `read_filter_out_list_yaml()` → `safe_read_yaml()` | `async_dynatrace_gcp_extension()` — beginning of each polling cycle |
| `labelsGroupingByService` | `read_labels_grouping_by_service_yaml()` → `safe_read_yaml()` | `fetch_ingest_lines_task()` — beginning of each polling cycle |
| `autodiscoveryResourcesYaml` | `read_autodiscovery_config_yaml()` → `safe_read_yaml()` | `AutodiscoveryContext._load_yamls()` — beginning of each autodiscovery cycle |
| `autodiscoveryBlockListYaml` | `read_autodiscovery_block_list_yaml()` → `safe_read_yaml()` | `AutodiscoveryContext._load_yamls()` — beginning of each autodiscovery cycle |

All reads go through `safe_read_yaml()` in `src/lib/utilities.py`, which opens the file fresh from disk every time it is called.

## What Can Be Hot-Reloaded

| Helm value | File in container | Notes |
|---|---|---|
| `gcpServicesYaml` | `gcp_services.yaml` | Requires `keepRefreshingExtensionsConfig: "true"` (the default). |
| `excludedMetricsAndDimensions` | `metrics-filter-out.yaml` | Add/remove metric exclusions. |
| `labelsGroupingByService` | `labels-grouping-by-service.yaml` | Change label groupings for metrics. |
| `autodiscoveryResourcesYaml` | `autodiscovery-config.yaml` | Only present when `metricAutodiscovery: "true"`. |
| `autodiscoveryBlockListYaml` | `autodiscovery-block-list.yaml` | Only present when `metricAutodiscovery: "true"`. |

## What Cannot Be Hot-Reloaded

Everything else in `values.yaml` lives in the **static** ConfigMap and requires a pod restart. This includes:

- `gcpProjectId`, `dynatraceUrl`, `dynatraceAccessKey`
- `queryInterval`, `deploymentType`, `operationMode`
- Proxy settings (`httpProxy`, `httpsProxy`)
- `selfMonitoringEnabled`
- Project inclusion/exclusion lists
- All log-forwarding settings
- Resource limits, image references, service account

## When Will Changes Take Effect

After running `helm upgrade`:

1. **Kubernetes propagation**: kubelet syncs updated ConfigMap files to the volume mount — typically **30–60 seconds**.
2. **Application pick-up**: the monitor re-reads the files on the **next polling cycle** (default: every 1 minute, configured by `queryInterval`).

In practice, expect changes to be active within **1–2 polling cycles** after `helm upgrade`, i.e. roughly **60–120 seconds** with default settings.

For autodiscovery values, the cadence is controlled by `AUTODISCOVERY_QUERY_INTERVAL` (default: 60 seconds).

## Failure Handling

If a hot-reloaded file contains **invalid YAML**:

- The `safe_read_yaml()` function logs an error but **does not crash** the pod.
- It falls back to the corresponding environment variable (if set), or returns an empty config.
- The **previous valid configuration is effectively retained** because config loaded in the prior cycle is already in memory for the values that matter most (services list, autodiscovery resources).

This means a bad `helm upgrade` with broken YAML will **not** take down monitoring — it will simply be ignored until corrected.

## How to Use

### Typical workflow

```bash
# 1. Edit your values file
vim my-values.yaml   # change gcpServicesYaml, excludedMetricsAndDimensions, etc.

# 2. Upgrade the release
helm upgrade dynatrace-gcp-monitor ./k8s/helm-chart/dynatrace-gcp-monitor \
  -f my-values.yaml \
  --namespace dynatrace

# 3. Verify — no pod restart should occur
kubectl get pods -n dynatrace -w
# Pod age stays the same; no new pod is created.

# 4. Check logs for confirmation
kubectl logs -n dynatrace -l app=dynatrace-gcp-monitor --tail=50
# Look for "Refreshing services config" or autodiscovery log lines.
```

### Upgrading from a single-ConfigMap chart

The first `helm upgrade` from an older chart version that used a single ConfigMap **will** trigger a one-time pod restart (the static ConfigMap content changes, which changes its checksum annotation). Subsequent upgrades that only modify hot-reloadable values will not cause a restart.

## Key Environment Variable

| Variable | Default | Purpose |
|---|---|---|
| `KEEP_REFRESHING_EXTENSIONS_CONFIG` | `true` | Must be `true` for `gcpServicesYaml` hot-reload to work. When `false`, the services list is loaded once at startup and never refreshed. |
