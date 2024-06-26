# Dynatrace integration for Google Cloud Platform monitoring

This is the home of `dynatrace-gcp-monitor` which provides the mechanism to pull all [Google Cloud metrics](https://cloud.google.com/monitoring/api/metrics_gcp) and  [Cloud logs](https://cloud.google.com/logging/docs)  into Dynatrace. 

This integration consists of K8s container and few auxiliary components. This setup will be running in your GCP project and will be pushing data to Dynatrace. We provide bash script that will deploy all necessary elements.

**To deploy this integration**, see the docs on how to [run it on Google Kubernetes Engine](https://www.dynatrace.com/support/help/shortlink/deploy-k8).

## (legacy info) Integration renamed from GCP Function to GCP Monitor, starting from version 1.1.0
The whole project was renamed, so all internal references and files are now named `dynatrace-gcp-monitor`. This includes created resources names and docker images.
Previous versions will still be available (but not updated), under the name `dynatrace-gcp-function`.

## (legacy info) Cloud Function deployment is deprecated
Up until version 1.1.8, there was an option to deploy GCP integration as a Cloud Function (instead of a K8s container). It is now deprecated and has no support. If you are using this kind of deployment, please refer to this [migration guide](https://www.dynatrace.com/support/help/shortlink/migrate-gcp-function-1-to-k8s-1).

## (legacy info) Migrating to 1.0.x from previous 0.1.x installations
If you already have a previous version of `dynatrace-gcp-monitor` deployed, please refer to this [migration guide](./MIGRATION-V1.md) before installing the latest version.

## Pricing
- Ingested metrics will consume DDUs. For more details [GCP service monitoring consumption](https://www.dynatrace.com/support/help/shortlink/metric-cost-calculation#which-built-in-metrics-consume-ddus)
- Ingested logs will consume DDUs. For more details [Log monitoring consumption](https://www.dynatrace.com/support/help/shortlink/calculate-log-consumption)

## Support
Before you create a ticket check [troubleshooting guides](https://www.dynatrace.com/support/help/shortlink/deploy-k8#troubleshoot) specific to your deployment.  
If you didn't find a solution please [contact Dynatrace support](https://www.dynatrace.com/support/contact-support/). 


## Additional resources
- [Architecture overview of Kubernetes deployment](./docs/k8s.md)
- [Monitoring multiple projects](https://www.dynatrace.com/support/help/shortlink/gcp-projects)
- [Expand monitoring in a Kubernetes container](https://www.dynatrace.com/support/help/shortlink/expand-k8s)
- [Self-monitoring in Google Cloud for metrics](https://www.dynatrace.com/support/help/shortlink/self-mon-gcp)
- [Self-monitoring for logs](docs/sfm_log.MD)
- [Dynatrace Azure Log Forwarder](https://github.com/dynatrace-oss/dynatrace-azure-log-forwarder)
- [Dynatrace AWS log forwarder](https://github.com/dynatrace-oss/dynatrace-aws-log-forwarder)

## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) for details on submitting changes.

## License

`dynatrace-gcp-monitor` is under Apache 2.0 license. See [LICENSE](LICENSE.md) for details.
