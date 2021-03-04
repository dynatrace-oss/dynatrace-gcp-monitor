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



