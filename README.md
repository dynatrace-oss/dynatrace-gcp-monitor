# Dynatrace integration for Google Cloud Platform monitoring

> [!IMPORTANT]
> This integration is in maintenance mode. A new GCP poller is under active development.

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/dynatrace-oss/dynatrace-gcp-monitor/badge)](https://scorecard.dev/viewer/?uri=github.com/dynatrace-oss/dynatrace-gcp-monitor)

`dynatrace-gcp-monitor` pulls [Google Cloud metrics](https://cloud.google.com/monitoring/api/metrics_gcp) and [Cloud Logging logs](https://cloud.google.com/logging/docs) into Dynatrace.

It runs as a container on Google Kubernetes Engine in your GCP project and pushes data to Dynatrace. Logs reach it through a Cloud Logging sink and a Pub/Sub subscription. See the [architecture overview](./docs/k8s.md) for details.

## Deployment

Each [release](https://github.com/dynatrace-oss/dynatrace-gcp-monitor/releases) ships `helm-deployment-package.tar`, which contains the Helm chart and the `deploy-helm.sh` script that sets up all required resources.

For step-by-step instructions, see [Deploy on Google Kubernetes Engine](https://www.dynatrace.com/support/help/shortlink/deploy-k8) in the Dynatrace documentation.

## Pricing

- Ingested metrics consume DDUs. For details, see [GCP service monitoring consumption](https://www.dynatrace.com/support/help/shortlink/metric-cost-calculation#which-built-in-metrics-consume-ddus).
- Ingested logs consume DDUs. For details, see [Log monitoring consumption](https://www.dynatrace.com/support/help/shortlink/calculate-log-consumption).

## Support

Before you create a ticket, check the [troubleshooting guides](https://www.dynatrace.com/support/help/shortlink/deploy-k8#troubleshoot) for your deployment.
If you don't find a solution, [contact Dynatrace support](https://www.dynatrace.com/support/contact-support/).

## Additional resources

- [Architecture overview of Kubernetes deployment](./docs/k8s.md)
- [Monitoring multiple projects](https://www.dynatrace.com/support/help/shortlink/gcp-projects)
- [Expand monitoring in a Kubernetes container](https://www.dynatrace.com/support/help/shortlink/expand-k8s)
- [Self-monitoring in Google Cloud for metrics](https://www.dynatrace.com/support/help/shortlink/self-mon-gcp)
- [Self-monitoring for logs](./docs/sfm_log.MD)
- [Dynatrace Azure Log Forwarder](https://github.com/dynatrace-oss/dynatrace-azure-log-forwarder)
- [Dynatrace AWS log forwarder](https://github.com/dynatrace-oss/dynatrace-aws-log-forwarder)

## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) for how to submit changes and [HACKING](HACKING.md) for local development setup.

## License

`dynatrace-gcp-monitor` is licensed under Apache 2.0. See [LICENSE](LICENSE.md) for details.

## Legacy notes

### Renamed from GCP Function to GCP Monitor in 1.1.0

The project was renamed, so all internal references, created resource names and Docker images now use `dynatrace-gcp-monitor`. Previous versions are still available under the name `dynatrace-gcp-function`, but are no longer updated.

### Cloud Function deployment deprecated

Up to version 1.1.8, the integration could be deployed as a Cloud Function instead of a Kubernetes container. That option is deprecated and no longer supported. If you still use it, follow the [migration guide](https://www.dynatrace.com/support/help/shortlink/migrate-gcp-function-1-to-k8s-1).

### Migrating from 0.1.x to 1.0.x

If you run a 0.1.x version, read the [migration guide](./MIGRATION-V1.md) before installing the latest version.
