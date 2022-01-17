# Migration from 0.1.x to 1.0.x

Upgrading existing `dynatrace-gcp-function` installations (either K8S or Cloud Function deployment) from 0.1.x is not supported.
Existing old 0.1.x deployments need to be deleted and new 1.0.x installation needs to be deployed.
New wersion (1.0.x) of `dynatrace-gcp-function` is using [Extensions 2.0](https://www.dynatrace.com/support/help/extend-dynatrace/extensions20/) and requires Dynatrace version 1.230 or higher.
Required permissions for Dynatrace API token has changed in 1.0.x
If you want to reuse previous Dynatrace API token in new deployment modify its permissions (see [Dynatrace documentation](https://www.dynatrace.com/support/help/setup-and-configuration/setup-on-cloud-platforms/google-cloud-platform/set-up-integration-gcp/) for details).

## K8S deployment
Uninstall old helm release and install new version as described in [Dynatrace documentation](https://www.dynatrace.com/support/help/shortlink/deploy-k8#type)

## Cloud Function deployment
Run uninstall script:
```shell script
wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/scripts/uninstall.sh -O uninstall.sh ; chmod a+x uninstall.sh ; ./uninstall.sh
```
Remove old configuration file (actovation-config.yaml)
Install new `dynatrace-gcp-function` deployment following instructions in [Dynatrace documentation](https://www.dynatrace.com/support/help/setup-and-configuration/setup-on-cloud-platforms/google-cloud-platform/set-up-integration-gcp/deploy-as-gcp-function/) 

## Dynatrace environment cleanup
There might be some Dynatrace dashboards and/or alerts left from previous 0.1.x installations. They need to be deleted manually.
New installation o 1.0.x version will add new dashboards and alerts.

## List of incompatible changes
Following GCP metrics dimension names has changed in 1.0.x.

:warning:If you created own dashboards or alerts or Management Zones based on GCP metrics you need to update them.

| Old dimension name | New dimension name |
| ------------- |------------- |
| project_id  | gcp.project.id |
| region | gcp.region  |
| zone  | gcp.region |
| instance_id | gcp.instance.id |
| autoscaler_id | gcp.instance.id |
| model_id | gcp.instance.id |
| queue_id | gcp.instance.id |
| device_registry_id | gcp.instance.id |
| job_id | gcp.instance.id |
| version_id | gcp.instance.id |
| database_id | gcp.instance.id |
| volume_id | gcp.instance.id |
| router_id | gcp.instance.id |
| instance_group_id | gcp.instance.id |
| interconnect | gcp.instance.id |
| attachment | gcp.instance.id |
| volume_id | gcp.instance.id |
| snapshot_id | gcp.instance.id |
| subscription_id | gcp.instance.id |
| topic_id | gcp.instance.id |
| key_id | gcp.instance.id |
| worker_id | gcp.instance.id |
| agent_id | gcp.instance.id |
| gateway_id | gcp.instance.id |
| name | gcp.instance.name |
| autoscaler_name | gcp.instance.name |
| environment_name | gcp.instance.name |
| cluster_name gcp.instance.name | gcp.instance.name |
| function_name gcp.instance.name | gcp.instance.name |
| revision_name | gcp.instance.name |
| job_name | gcp.instance.name |
| instance_name | gcp.instance.name |
| domain_name | gcp.instance.name |
| table_name | gcp.instance.name |
| firewall_name | gcp.instance.name |
| bucket_name | gcp.instance.name |
| container_name | gcp.instance.name |
| url_map_name | gcp.instance.name |
| instance_group_name | gcp.instance.name |
| load_balancer_name | gcp.instance.name |
| canonical_service_name | gcp.instance.name |
| node_name | gcp.instance.name |
| pod_name | gcp.instance.name |
| broker_name | gcp.instance.name |
| revision_name | gcp.instance.name |
| trigger_name | gcp.instance.name |
| fqdn | gcp.instance.name |
| target_domain_name | gcp.instance.name |
| gateway_name | gcp.instance.name |
| policy_name | gcp.instance.name |
| proxy_name  | gcp.instance.name |
| load_balancer_name | gcp.instance.name |
| backend_target_name | gcp.instance.name |
| connector_name | gcp.instance.name |
| gateway_name | gcp.instance.name |
