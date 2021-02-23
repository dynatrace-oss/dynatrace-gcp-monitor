## Quick start with Google Cloud Shell
### Overview
`dynatrace-gcp-function` is a [Cloud Function](https://cloud.google.com/functions) written in Python that pulls metrics for configured services from [Cloud Monitoring API](https://cloud.google.com/monitoring/api/v3). Function execution is triggered by [Pub/Sub](https://cloud.google.com/pubsub) upon 1 minute schedule defined in [Cloud Scheduler](https://cloud.google.com/scheduler). Authentication token to query for metrics is retrieved for the scope of [Service account](https://cloud.google.com/iam/docs/service-accounts) that is created during installation process. Once the time series are collected, the values are pushed to [Dynatrace Metrics API v2](https://www.dynatrace.com/support/help/dynatrace-api/environment-api/metric-v2/) using Dynatrace API token and URL to Dynatrace tenant environment stored in [Secret Manager](https://cloud.google.com/secret-manager).


In addition to metrics `dynatrace-gcp-function` is calling Service specific API's (for example Pub/Sub API). The purpose is to get properties of the instances that are not available in Monitoring API.  Particularly the function try to retrieve endpoint addresses (FQDN's, IP addresses).

*Architecture with Google Cloud Function deployment*
![Google Cloud Function Architecture](../../img/architecture-function.svg)

### Requirements
Make sure the following dependencies are installed:
* yq [mikefarah/yq GitHub project](https://github.com/mikefarah/yq)

For example, You can use:
```
sudo wget https://github.com/mikefarah/yq/releases/download/3.4.0/yq_linux_amd64 -O /usr/bin/yq && sudo chmod +x /usr/bin/yq
```

`dynatrace-gcp-function` uses Cloud Scheduler that requires App Engine to be created. If you don't have App Engine enabled yet, installer script will prompt you to Create it and select region, where it will run. Reference: [Cloud Scheduler documentation](https://cloud.google.com/scheduler/docs)

### Installation

Download & run the `dynatrace-gcp-function` installation script
```
wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/scripts/setup.sh -O setup.sh ; chmod a+x setup.sh ; ./setup.sh
```

Installation script will prompt for following parameters:
| Parameter   | Description                                   |
| ----------- | --------------------------------------------- |
| GCP project | Google Cloud project, where `dynatrace-gcp-function` should be deployed to. By default, current project set for gcloud CLI. |
| Function size | Amount of memory that should be assigned to the function. Possible options</br> **[s]** - small, up to 500 instances, 256 MB memory allocated to function</br> **[m]** - medium, up to 1000 instances, 512 MB memory allocated to function </br>**[l]** - large, up to 5000 instances, 2048 MB memory allocated to function</br>Please note that You will be able to adjust amount of memory after installation. |
| Dynatrace tenant URI | The URL to Your Dynatrace SaaS or Managed environment |
| Dynatrace API token | Dynatrace API token. You can learn how to generate token [Dynatrace API - Tokens and authentication](https://www.dynatrace.com/support/help/dynatrace-api/basics/dynatrace-api-authentication) manual. Integration requires `API v2 Ingest metrics`, `API v1 Read configuration` and `WriteConfig` Token permission.

## Quick start with Bash
### Requirements
Make sure the following dependencies are installed:
* jq
* yq [mikefarah/yq GitHub project](https://github.com/mikefarah/yq)
* Google Cloud SDK [Google Cloud SDK installer](https://cloud.google.com/sdk/docs/downloads-interactive#linux)

For example, on Ubuntu You can use:
```
sudo wget https://github.com/mikefarah/yq/releases/download/3.4.0/yq_linux_amd64 -O /usr/bin/yq && sudo chmod +x /usr/bin/yq
sudo apt-get install jq
curl https://sdk.cloud.google.com | bash
```

Restart the console and initialize Cloud SDK ([Initializing Cloud SDK](https://cloud.google.com/sdk/docs/initializing)):
```
gcloud init
```

### Install `dynatrace-gcp-function`

Run the `dynatrace-gcp-function` installation script:
```
wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/scripts/setup.sh -O setup.sh ; chmod a+x setup.sh ; ./setup.sh
```

Installation script will prompt for following parameters:
| Parameter   | Description                                   |
| ----------- | --------------------------------------------- |
| GCP project | Google Cloud project, where `dynatrace-gcp-function` should be deployed to. By default, current project set for gcloud CLI. |
| Function size | Amount of memory that should be assigned to the function. Possible options</br> **[s]** - small, up to 500 instances, 256 MB memory allocated to function</br> **[m]** - medium, up to 1000 instances, 512 MB memory allocated to function </br>**[l]** - large, up to 5000 instances, 2048 MB memory allocated to function</br>Please note that You will be able to adjust amount of memory after installation. |
| Dynatrace tenant URI | The URL to Your Dynatrace SaaS or Managed environment |
| Dynatrace API token | Dynatrace API token. You can learn how to generate token [Dynatrace API - Tokens and authentication](https://www.dynatrace.com/support/help/dynatrace-api/basics/dynatrace-api-authentication) manual. Integration requires `Ingest metrics using API V2` Token permission.

**Please note** `dynatrace-gcp-function` uses Cloud Scheduler that requires App Engine to be created. If you don't have App Engine enabled yet, installer script will prompt you to Create it and select region, where it will run. Reference: [Cloud Scheduler documentation](https://cloud.google.com/scheduler/docs)



### Extend monitoring scope
...



### Troubleshoot and support
#### I can not see metrics in Dynatrace...
If you are having issues running `Cloud Function`
...