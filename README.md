# Dynatrace integration for Google Cloud Platform monitoring

This is the home of `dynatrace-gcp-function` which provides the mechanism to pull all [Google Cloud metrics](https://cloud.google.com/monitoring/api/metrics_gcp) and  [Cloud logs](https://cloud.google.com/logging/docs)  into Dynatrace. 

This integration consists of K8s container and few auxiliary components. This setup will be running in your GCP project and will be pushing data to Dynatrace. We provide bash script that will deploy all necessary elements.

**To deploy this integration**, see the docs on how to [run it on Google Kubernetes Engine](https://www.dynatrace.com/support/help/shortlink/deploy-k8).

## (legacy info) Cloud Function deployment is deprecated

For earlier customers, there was also option to deploy integration as Cloud Function (instead of K8s container). This option is now deprecated and will only be supported until 31 December 2022. If you are using this kind of deployment, you should switch to K8s container soon.

We will provide migration guide shortly.
  
## (legacy info) Migrating to 1.0.x from previous 0.1.x installations
If you already have previous version of `dynatrace-gcp-function` deployed, please refer to [migration guide](./MIGRATION-V1.md) before installing latest version.

## Pricing
- Ingested metrics will consume DDUs. For more details [GCP service monitoring consumption](https://www.dynatrace.com/support/help/reference/monitoring-consumption-calculation/#expand-gcp-service-monitoring-consumption-104)
- Ingested logs will consume DDUs. For more details [Log monitoring consumption](https://www.dynatrace.com/support/help/reference/monitoring-consumption-calculation/log-monitoring-consumption/)

## Support
Before you create a ticket check [troubleshooting guides](https://www.dynatrace.com/support/help/shortlink/troubleshoot-gcp) specific to your deployment.  
If you didn't find a solution please [contact Dynatrace support](https://www.dynatrace.com/support/contact-support/). 


## Additional resources
- [Architecture overview of Kubernetes deployment](./docs/k8s.md)
- [Monitoring multiple projects](https://www.dynatrace.com/support/help/technology-support/cloud-platforms/google-cloud-platform/monitor-gcp-services-and-logs-with-dynatrace/monitor-multiple-projects/)
- [Expand monitoring in a Kubernetes container](https://www.dynatrace.com/support/help/shortlink/expand-k8s)
- [Self-monitoring in Google Cloud for metrics](https://www.dynatrace.com/support/help/shortlink/troubleshoot-gcp)
- [Self-monitoring for logs](docs/sfm_log.MD)
- [Dynatrace Azure Log Forwarder](https://github.com/dynatrace-oss/dynatrace-azure-log-forwarder)
- [Dynatrace AWS log forwarder](https://github.com/dynatrace-oss/dynatrace-aws-log-forwarder)

## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) for details on submitting changes.

## License

`dynatrace-gcp-function` is under Apache 2.0 license. See [LICENSE](LICENSE.md) for details.