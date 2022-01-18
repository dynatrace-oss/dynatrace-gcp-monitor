## Self-monitoring Logs Overview
Self monitoring allows diagnosing quickly if your function processes and sends logs to Dynatrace properly through GCP custom metrics.
By default (if this option is not enabled) custom metrics won't be sent to GCP.

### Self-monitoring metrics for logs

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

### Self-monitoring dashboard for logs
If self monitoring is enabled, the self monitoring dashboard can be added in GCP:
```shell script
wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/src/dashboards/dynatrace-gcp-function-log-self-monitoring
gcloud monitoring dashboards create --config-from-file=dynatrace-gcp-function-log-self-monitoring
```