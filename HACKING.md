# Dynatrace Google Cloud Integration Hacking instructions

## Development environment setup

To run worker function locally you have to have Python dev environement installed: `Python 3.7` with `pip` tool.

to install all the dependencies run 
```shell script
pip install -r requirements.txt
```

To run worker function run `local_test.py` script file. 

## Environment variables

Worker function execution can be tweaked with environment variables. In Google Function you can input them when deploying/editing the function:

| Variable name | description   | default value |
| ----------------- | ------------- | ----------- |
| GCP_SERVICES     | comma separated list of services to monitor, if not specified will monitor all the services, e.g. `gce_instance,cloud_function` |  |
| PRINT_METRIC_INGEST_INPUT | boolean value, if true will print full MINT ingest input | false |
| DYNATRACE_ACCESS_KEY_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace Access Key | DYNATRACE_ACCESS_KEY |
| DYNATRACE_URL_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace URL | DYNATRACE_URL |
| GOOGLE_APPLICATION_CREDENTIALS | path to GCP service account key file | |
| MAXIMUM_METRIC_DATA_POINTS_PER_MINUTE | Max number of MINT ingest lines processed in one minute interval | 100 000 |
| METRIC_INGEST_BATCH_SIZE | size of MINT ingest batch sent to Dynatrace cluster | 1000 |
| REQUIRE_VALID_CERTIFICATE | determines whether worker will verify SSL certificate of Dynatrace endpoint | True |
| SERVICE_USAGE_BOOKING | `source` if API calls should use default billing mechanism, `destination` if they should be billed per project | `source` |
| USE_PROXY | Depending on value of this flag, function will use proxy settings for either Dynatrace, GCP API or both. Allowed values: `ALL`, `DT_ONLY`, `GCP_ONLY` |  |
| IMPORT_DASHBOARDS | Import predefined dashboards for selected services. Allowed values: `yes`, `no` | `yes` |
| IMPORT_ALERTS | Import predefined alerting rules (inactive by default) for selected services Allowed values: `yes`, `no`| `yes` |abled by default