# Dynatrace integration for Google Cloud Platform monitoring

This is the home of `dynatrace-gcp-function` which provides the mechanism to pull all [Google Cloud metrics](https://cloud.google.com/monitoring/api/metrics_gcp) into Dynatrace. 
 
To help with deployment you can use automation scripts available in this repo.

Maintaining its lifecycle places a burden on the operational team.


## Getting started
There are two deployment options available, you can:
- [run it on Google Kubernetes Engine](https://www.dynatrace.com/support/help/shortlink/deploy-k8) or 
- [deploy a Google Cloud Function](https://www.dynatrace.com/support/help/shortlink/deploy-gcp)


## Pricing
Ingested metrics will consume DDUs. For more details [refer to documention](https://www.dynatrace.com/support/help/reference/monitoring-consumption-calculation/#expand-gcp-service-monitoring-consumption-104)


## Support
Before you create a ticket check [troubshooting guides](https://www.dynatrace.com/support/help/shortlink/troubleshoot-gcp) specific to your deployment.  
If you didn't find a solution please [contact Dynatrace support](https://www.dynatrace.com/support/contact-support/). 


## Additional resources
- [Architecture overview of Kubernetes deployment](./docs/k8s.md)
- [Architecture overview of Google Cloud Function deployment](./docs/function.md)
- [Monitoring multiple projects](https://www.dynatrace.com/support/help/shortlink/monitor-gcp#monitor-multiple-gcp-projects)
- [Self-monitoring in Google Cloud](https://www.dynatrace.com/support/help/shortlink/troubleshoot-gcp#self-monitoring-metrics)


## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) for details on submitting changes.

## License

`dynatrace-gcp-function` is under Apache 2.0 license. See [LICENSE](LICENSE.md) for details.