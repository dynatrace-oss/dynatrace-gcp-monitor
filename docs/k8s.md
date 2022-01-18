# Kubernetes deployment

## Overview
It's possible to run monitoring as Kubernetes Container. In this case all configurations and secretes are stored as K8S ConfigMap / Secretes objects. 

*Architecture with Google Cloud Function deployment*

###### Metrics:

>![GKE Container Architecture](./../img/architecture-k8s.svg)

###### Logs:
>![Architecture](./../img/logs-architecture.svg)

Dynatrace integration for GCP Logs is using [Officially supported log export design pattern](https://cloud.google.com/logging/docs/export). All incoming log entries sent to GCP Cloud Logging API are passed through Logs Router Sink. Router is running inclusion and exclusion filters to determine if log entry should be passed to defined GCP Cloud Pub/Sub topic. Filters allow user to select which logs they would like to export to Dynatrace. Finally, Pub/Sub messages with log entries are polled by containerized `dynatrace-gcp-function`, processed, batched and sent to Dynatrace Log Ingest API. 

## Getting started
For a quick start guide [refer to documentation](https://www.dynatrace.com/support/help/shortlink/deploy-k8)


## Troubleshooting
For troubleshooting [refer to documentation](https://www.dynatrace.com/support/help/shortlink/troubleshoot-gcp)
