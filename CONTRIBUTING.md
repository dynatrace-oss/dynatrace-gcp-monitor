# Dynatrace Google Cloud Integration

## How to Contribute

You are welcome to contribute to `Dynatrace Google Cloud Integration`
Use issues for discussing proposals or to raise a question.
If you have improvements to `Dynatrace Google Cloud Integration`, please submit your pull request.
For those just getting started, consult this  [guide](https://help.github.com/articles/creating-a-pull-request-from-a-fork/).

## How to add support for Google Cloud Platform service

To add support for GCP service, you have to add new configuration file:

1. [Fork](https://docs.github.com/en/github/getting-started-with-github/fork-a-repo) this repository 
2. Checkout the repository from GitHub:
```shell script
git clone git@github.com:{username}/dynatrace-gcp-extension.git
```  
3. Create configuration YAML file compliant with `./config/gcp_schema_v_1_0.json` schema
4. Put it into `./config` directory, with `yml` or `yaml` extension
5. Commit git changes
```shell script
git add .
git commit -m"Introducing {service name} service support"
```
6. Open the [Pull Request](https://docs.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request)