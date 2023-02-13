# Google Cloud Function deployment 

## Overview
`dynatrace-gcp-monitor` is a [Cloud Function](https://cloud.google.com/functions) written in Python that pulls metrics for configured services from [Cloud Monitoring API](https://cloud.google.com/monitoring/api/v3). Function execution is triggered by [Pub/Sub](https://cloud.google.com/pubsub) upon 1 minute schedule defined in [Cloud Scheduler](https://cloud.google.com/scheduler). Authentication token to query for metrics is retrieved for the scope of [Service account](https://cloud.google.com/iam/docs/service-accounts) that is created during installation process. Once the time series are collected, the values are pushed to [Dynatrace Metrics API v2](https://www.dynatrace.com/support/help/dynatrace-api/environment-api/metric-v2/) using Dynatrace API token and URL to Dynatrace tenant environment stored in [Secret Manager](https://cloud.google.com/secret-manager).

![Google Cloud Function Architecture](./../img/architecture-function.svg)

**Please note** `dynatrace-gcp-monitor` uses Cloud Scheduler that requires App Engine to be created. If you don't have App Engine enabled yet, installer script will prompt you to Create it and select region, where it will run. Reference: [Cloud Scheduler documentation](https://cloud.google.com/scheduler/docs)


## Getting started
For a quick start guide [refer to documentation](https://www.dynatrace.com/support/help/shortlink/deploy-gcp)


## Troubleshooting
For troubleshooting [refer to documentation](https://www.dynatrace.com/support/help/shortlink/troubleshoot-gcp)