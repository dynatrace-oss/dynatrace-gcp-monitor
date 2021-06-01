# Dynatrace integration for Google Cloud Platform monitoring

This is the home of `dynatrace-gcp-function` which provides the mechanism to pull all [Google Cloud metrics](https://cloud.google.com/monitoring/api/metrics_gcp) and  [Cloud logs](https://cloud.google.com/logging/docs)  into Dynatrace. 
  
To help with deployment you can use automation scripts available in this repo.

Maintaining its lifecycle places a burden on the operational team.


## Getting started
There are two deployment options available, you can:
- [Metrics and/or logs] [run it on Google Kubernetes Engine](https://www.dynatrace.com/support/help/shortlink/deploy-k8)  
- [Metrics] [deploy a Google Cloud Function](https://www.dynatrace.com/support/help/shortlink/deploy-gcp)


## Pricing
- Ingested metrics will consume DDUs. For more details [refer to documentation](https://www.dynatrace.com/support/help/reference/monitoring-consumption-calculation/#expand-gcp-service-monitoring-consumption-104)
- Ingested logs will consume DDUs. For more details [refer to documentation](https://www.dynatrace.com/support/help/reference/monitoring-consumption-calculation/log-monitoring-consumption/)

## Support
Before you create a ticket check [troubleshooting guides](https://www.dynatrace.com/support/help/shortlink/troubleshoot-gcp) specific to your deployment.  
If you didn't find a solution please [contact Dynatrace support](https://www.dynatrace.com/support/contact-support/). 


## Additional resources
- [Architecture overview of Kubernetes deployment](./docs/k8s.md)
- [Architecture overview of Google Cloud Function deployment](./docs/function.md)
- [Monitoring multiple projects](https://www.dynatrace.com/support/help/technology-support/cloud-platforms/google-cloud-platform/monitor-gcp-services-and-logs-with-dynatrace/monitor-multiple-projects/)
- [Expand monitoring in a Kubernetes container](https://www.dynatrace.com/support/help/shortlink/expand-k8s)
- [Self-monitoring in Google Cloud for metrics](https://www.dynatrace.com/support/help/shortlink/troubleshoot-gcp)
- [Self-monitoring for logs](docs/sfm_log.MD)



## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) for details on submitting changes.

## License

`dynatrace-gcp-function` is under Apache 2.0 license. See [LICENSE](LICENSE.md) for details.