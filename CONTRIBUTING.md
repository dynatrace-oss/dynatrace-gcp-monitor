# Dynatrace Google Cloud Integration

## How to Contribute

You are welcome to contribute to `Dynatrace Google Cloud Integration`
Use issues for discussing proposals or to raise a question.
If you have improvements to `Dynatrace Google Cloud Integration`, please submit your pull request.
For those just getting started, consult this  [guide](https://help.github.com/articles/creating-a-pull-request-from-a-fork/).


### Before you start

1. [Fork](https://docs.github.com/en/github/getting-started-with-github/fork-a-repo) this repository 
2. Checkout the repository from GitHub:
```shell script
git clone git@github.com:{username}/dynatrace-gcp-extension.git
```  


## Ways to contribute

### Adding dashboards
To add a dashboard you have to 

1. Create a dashboard in Dynatrace and export it as Json.
2. Name the file as the configuration file from `./src/config` that has correspodning metrics
3. Put the file into `./src/dashboards` with `json` extension
4. Commit your changes
```shell script
git add .
git commit -m"Introducing dashboard for {service name}"
```
5. Open a [Pull Request](https://docs.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request)

### Adding support for Google Cloud Platform service or metric

To add support for GCP service, you have to add new configuration file:

1. Create configuration YAML file compliant with `./src/config/gcp_schema_v_1_0.json` schema
2. Put it into `./config` directory, with `yml` or `yaml` extension
3. Commit your changes
```shell script
git add .
git commit -m"Introducing {service name} service support"
```
4. Open a [Pull Request](https://docs.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request)