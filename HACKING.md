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
| DYNATRACE_ACCESS_KEY_SECRET_NAME | name of Google Secret Manager Secret containing Dynatrace Access Key | DYNATRACE_ACCESS_KEY |
| DYNATRACE_URL_SECRET_NAME | name of Google Secret Manager Secret containing Dynatrace URL | DYNATRACE_URL |
| GOOGLE_APPLICATION_CREDENTIALS | path to GCP service account key file | |