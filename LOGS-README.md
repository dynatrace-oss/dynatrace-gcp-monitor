# GCP Logs Ingest 

> ### ⚠ Dynatrace Log Monitoring and generic log ingest is coming soon. If you are part of the Preview program you can already use dynatrace-gcp-function to ingest GCP logs. If you are waiting for Logs Ingest General Availability please star this repository to get notified when Log Monitoring is ready.

## Overview
This project can be configured to stream GCP logs from GCP Pub/Sub into Dynatrace Logs. Logs ingest option is available only for `dynatrace-gcp-function` deployed in Google Kubernetes Engine (GKE). Deployment as Cloud Function does not support log ingest.  

## Architecture

![Architecture](./img/logs-architecture.svg)

Dynatrace integration for GCP Logs is using [Officially supported log export design pattern](https://cloud.google.com/logging/docs/export). All incoming log entries sent to GCP Cloud Logging API are passed through Logs Router Sink. Router is running inclusion and exclusion filters to determine if log entry should be passed to defined GCP Cloud Pub/Sub topic. Filters allow user to select which logs they would like to export to Dynatrace. Finally, Pub/Sub messages with log entries are polled by containerized `dynatrace-gcp-function`, processed, batched and sent to Dynatrace Log Ingest API. 

## Deployment in Google Kubernetes Engine (GKE)

### Prerequisites:
* completed prerequisities from [GCP Integration GKE setup documentation page](https://www.dynatrace.com/support/help/shortlink/deploy-k8)
* set up a [Pub/Sub topic](https://cloud.google.com/pubsub/docs/quickstart-console#create_a_topic) that will receive logs and [add a subscription](https://cloud.google.com/pubsub/docs/quickstart-console#add_a_subscription) to the topic.
    
    * If you want to create Pub/Sub Topic and Subscription on your own, please change default values for following properties with our recommendations:
        * Acknowledgement deadline: 120s
        * Message retention duration: 1 day
    
      These settings are the most optimal for Pub/Sub working with dynatrace-gcp-function - it won't keep too old logs (older than 1 day) and it will wait 2 min for message acknowledgement.   
    
    * You can run shell script in Google Cloud Shell to have Topic and subscription created automatically.
Note: Be sure to replace <TOPIC_NAME> and <SUBSCRIPTION_NAME> with your values and run script in the GCP project you've selected for deployment:
```shell script
wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/scripts/deploy-pubsub.sh
chmod +x deploy-pubsub.sh
./deploy-pubsub.sh --topic-name <TOPIC_NAME> --subscription-name <SUBSCRIPTION_NAME>
```

* configured [Logs Export](https://cloud.google.com/logging/docs/export/configure_export_v2) sending desired logs to GCP Pub/Sub topic created in previous step, make sure that Sink is allowed to publish to Pub/Sub topic
* Dynatrace [ActiveGate configured for Generic Logs Ingest](https://www.dynatrace.com/support/help/how-to-use-dynatrace/log-monitoring/log-monitoring-v2/log-data-ingestion/)

Recommended way of deployment is using GCP Cloud Shell as a terminal.

### Deployment in GKE cluster 

Execute all steps in Google Cloud Shell after connecting to selected GKE cluster.

1. Create a dynatrace namespace.
```shell script
kubectl create namespace dynatrace
```

2. Create an Identity and Access Management (IAM) service account.
```shell script
gcloud iam service-accounts create dynatrace-gcp-function-sa
```

3. Configure the IAM service account for Workload Identity. (Make sure Workload Identity is enabled first. See Prerequisites for details.)
Note: Be sure to replace <your-GCP-project-ID> with your own GCP project ID.
```shell script
gcloud iam service-accounts add-iam-policy-binding --role roles/iam.workloadIdentityUser --member "serviceAccount:<your-GCP-project-ID>.svc.id.goog[dynatrace/dynatrace-gcp-function-sa]" dynatrace-gcp-function-sa@<your-GCP-project-ID>.iam.gserviceaccount.com
```

4. Create `dynatrace-gcp-function` IAM role(s).
 Note: Be sure to replace <your-GCP-project-ID> with your own GCP project ID.

for log ingest:
```shell script
wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/gcp_iam_roles/dynatrace-gcp-function-logs-role.yaml
gcloud iam roles create dynatrace_function.logs --project=<your-GCP-project-ID> --file=dynatrace-gcp-function-logs-role.yaml
````

for metrics ingest:
```shell script
wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/gcp_iam_roles/dynatrace-gcp-function-metrics-role.yaml
gcloud iam roles create dynatrace_function.metrics --project=<your-GCP-project-ID> --file=dynatrace-gcp-function-metrics-role.yaml
```

5. Grant the required IAM policies to the service account.
Note: Be sure to replace <your-GCP-project-ID> with your own GCP project ID.

For logs ingest:
```shell script
gcloud projects add-iam-policy-binding <your-GCP-project-ID> --member="serviceAccount:dynatrace-gcp-function-sa@<your-GCP-project-ID>.iam.gserviceaccount.com" --role=projects/<your-GCP-project-ID>/roles/dynatrace_function.logs
```

For metrics ingest:
```shell script
gcloud projects add-iam-policy-binding <your-GCP-project-ID> --member="serviceAccount:dynatrace-gcp-function-sa@<your-GCP-project-ID>.iam.gserviceaccount.com" --role=projects/<your-GCP-project-ID>/roles/dynatrace_function.metrics
```

6. Enable the APIs required for monitoring.
```shell script
gcloud services enable cloudapis.googleapis.com monitoring.googleapis.com cloudresourcemanager.googleapis.com
```

7. Install dynatrace-gcp-funtion with helm chart.

Download helm chart package
```shell script
wget https://github.com/dynatrace-oss/dynatrace-gcp-function/releases/latest/download/dynatrace-gcp-function.tgz
```

Update values file with your configuration.
Values that needs to be filled for logs ingest: dynatraceAccessKey, dynatraceLogIngestUrl, logsSubscriptionProject, logsSubscriptionId.
Values that needs to be filled for metrics ingest: dynatraceAccessKey, dynatraceUrl.
See comments in [values.yaml](https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/k8s/helm-chart/dynatrace-gcp-function/values.yaml) for more details
```shell script
tar -zxvf dynatrace-gcp-function.tgz
vi dynatrace-gcp-function/values.yaml
```

Install helm chart
```shell script
helm install ./dynatrace-gcp-function --generate-name
```

8. Create an annotation for the service account.
Note: Be sure to replace <your-GCP-project-ID> with your own GCP project ID.
```shell script
kubectl annotate serviceaccount --namespace dynatrace dynatrace-gcp-function-sa iam.gke.io/gcp-service-account=dynatrace-gcp-function-sa@<your-GCP-project-ID>.iam.gserviceaccount.com
```

9. Check the installation status
```shell script
kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-logs
kubectl -n dynatrace logs -l app=dynatrace-gcp-function -c dynatrace-gcp-function-metrics
```

## Viewing GCP logs in Dynatrace UI
You can view and analyze GCP logs in Dynatrace UI: Analyze -> Logs. To narrow view to GCP logs only use query: `cloud.provider: gcp`

## Self-monitoring
Self monitoring allows to diagnose quickly if your function processes and sends logs to Dynatrace properly through GCP custom  metrics.
By default (if this option is not enabled) custom metrics won't be sent to GCP.

### Self-monitoring metrics

| Metric name                   | Description                               | Dimension | 
| ------------------------------|-------------------------------------------|:----------:|
| custom.googleapis.com/dynatrace/logs/too_old_records | Reported when logs received from Pub/Sub are too old | - |
| custom.googleapis.com/dynatrace/logs/too_long_content_size | Reported when content of log is too long. The content will be trimmed | - |
| custom.googleapis.com/dynatrace/logs/parsing_errors | Reported when any parsing errors occurred during log processing | - |
| custom.googleapis.com/dynatrace/logs/processing_time | Time needed to process all logs [s] | - |
| custom.googleapis.com/dynatrace/logs/sending_time | Time needed to send all requests [s] | - |
| custom.googleapis.com/dynatrace/logs/all_requests | All requests sent to Dynatrace | - |
| custom.googleapis.com/dynatrace/logs/connectivity_failures | Reported when any Dynatrace connectivity issues occurred | connectivity_status |
| custom.googleapis.com/dynatrace/logs/log_ingest_payload_size | Size of log payload sent to Dynatrace [kB] | - |
| custom.googleapis.com/dynatrace/logs/sent_logs_entries | Number of logs entries sent to Dynatrace | - |

### Self-monitoring dashboard
If self monitoring is enabled, the self monitoring dashboard can be added in GCP:
```shell script
wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/src/dashboards/dynatrace-gcp-function-log-self-monitoring
gcloud monitoring dashboards create --config-from-file=dynatrace-gcp-function-log-self-monitoring
```