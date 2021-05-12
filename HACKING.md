# Dynatrace Google Cloud Integration Hacking instructions

## Development environment setup

To run worker function locally you have to have Python dev environement installed: `Python 3.7` with `pip` tool.

to install all the dependencies run 
```shell script
pip install -r requirements.txt
```

To run metrics ingest worker function run `local_test.py` script file.

To run logs ingest worker function run `local_test.py` script file with `OPERATION_MODE` set to `Logs` 

## Environment variables

Worker function execution can be tweaked with environment variables. In Google Function you can input them when deploying/editing the function:

### Metric processing configuration variables

| Variable name | description   | default value |
| ----------------- | ------------- | ----------- |
| GCP_SERVICES     | comma separated list of services to monitor, if not specified will monitor all the services, e.g. `gce_instance,cloud_function` |  |
| PRINT_METRIC_INGEST_INPUT | boolean value, if true will print full MINT ingest input. Allowed values: `true`/`yes`, `false`/`no` | `false` |
| DYNATRACE_ACCESS_KEY_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace Access Key | DYNATRACE_ACCESS_KEY |
| DYNATRACE_URL_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace URL | DYNATRACE_URL |
| GOOGLE_APPLICATION_CREDENTIALS | path to GCP service account key file | |
| MAXIMUM_METRIC_DATA_POINTS_PER_MINUTE | Max number of MINT ingest lines processed in one minute interval | 100 000 |
| METRIC_INGEST_BATCH_SIZE | size of MINT ingest batch sent to Dynatrace cluster | 1000 |
| REQUIRE_VALID_CERTIFICATE | determines whether worker will verify SSL certificate of Dynatrace endpoint. Allowed values: `true`/`yes`, `false`/`no` | `true` |
| SERVICE_USAGE_BOOKING | `source` if API calls should use default billing mechanism, `destination` if they should be billed per project | `source` |
| USE_PROXY | Depending on value of this flag, function will use proxy settings for either Dynatrace, GCP API or both. Allowed values: `ALL`, `DT_ONLY`, `GCP_ONLY` |  |
| IMPORT_DASHBOARDS | Import predefined dashboards for selected services. Allowed values: `true`/`yes`, `false`/`no` | `true` |
| IMPORT_ALERTS | Import predefined alerting rules (inactive by default) for selected services. Allowed values: `true`/`yes`, `false`/`no` | `true` |
| MAX_DIMENSION_NAME_LENGTH | The maximum length of the dimension name sent to the MINT API. Longer names are truncated to the value indicated. Allowed values: positive integers. | 100 |
| MAX_DIMENSION_VALUE_LENGTH | The maximum length of the dimension value sent to the MINT API. Longer values are truncated to the value indicated. Allowed values: positive integers. | 250 |
| SELF_MONITORING_ENABLED | Send custom metrics to GCP to diagnose quickly if your dynatrace-gcp-function processes and sends metrics to Dynatrace properly. Allowed values: `true`/`yes`, `false`/`no` | `false` |

### Log processing configuration variables

| Variable name | description   | default value |
| ----------------- | ------------- | ----------- |
| DYNATRACE_ACCESS_KEY_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace Access Key | DYNATRACE_ACCESS_KEY |
| DYNATRACE_LOG_INGEST_URL_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace URL | DYNATRACE_LOG_INGEST_URL |
| GOOGLE_APPLICATION_CREDENTIALS | path to GCP service account key file | |
| REQUIRE_VALID_CERTIFICATE | determines whether worker will verify SSL certificate of Dynatrace endpoint. Allowed values: `true`/`yes`, `false`/`no` | `true` |
| DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH | determines max content length of log event. Should be the same or lower than on cluster | 8192 characters |
| DYNATRACE_LOG_INGEST_ATTRIBUTE_VALUE_MAX_LENGTH | Max length of log event attribute value. If it surpasses server limit, Content will be truncated | 250 |
| DYNATRACE_LOG_INGEST_REQUEST_MAX_EVENTS | Max number of log events in single payload to logs ingest endpoint. If it surpasses server limit, payload will be rejected with 413 code  | 5000 |
| DYNATRACE_LOG_INGEST_REQUEST_MAX_SIZE | Max size in bytes of single payload to logs ingest endpoint. If it surpasses server limit, payload will be rejected with 413 code | 1048576 (1 mb) |
| DYNATRACE_LOG_INGEST_EVENT_MAX_AGE_SECONDS | Determines max age of forwarded log event. Should be the same or lower than on cluster | 1 day |
| LOGS_SUBSCRIPTION_PROJECT | GCP project of log sink pubsub subscription | |
| LOGS_SUBSCRIPTION_ID | subscription id of log sink pubsub subscription | |
| DYNATRACE_LOG_INGEST_SENDING_WORKER_EXECUTION_PERIOD | Period of sending batched logs to Dynatrace | 60 seconds |
| DYNATRACE_TIMEOUT_SECONDS | Timeout of request to Dynatrace Log Ingest | 30 seconds |
| SELF_MONITORING_ENABLED | Send custom metrics to GCP to diagnose quickly if your gcp-log-forwarder processes and sends logs to Dynatrace properly. Allowed values: `true`/`yes`, `false`/`no` | `false` |
