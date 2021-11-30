#!/usr/bin/env bash
#     Copyright 2021 Dynatrace LLC
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

mkdir -p release
cp activation-config.yaml "./release/activation-config.yaml"

cd release/ || exit

wget -q "https://github.com/dynatrace-oss/dynatrace-gcp-function/releases/download/${TRAVIS_TAG}/function-deployment-package.zip" -O function-deployment-package.zip; unzip function-deployment-package.zip; chmod a+x *.sh;

cat <<EOF > activation.config.release.yaml
googleCloud:
  common:
    dynatraceUrlSecretName: "${DYNATRACE_URL_SECRET_NAME}"
    dynatraceAccessKeySecretName: "${DYNATRACE_ACCESS_KEY_SECRET_NAME}"
    serviceAccount: "${IAM_SERVICE_ACCOUNT}"
    iamRole: "${IAM_ROLE_METRCICS}"
    requireValidCertificate: false
  metrics:
    pubSubTopic: "${PUBSUB_TOPIC}"
    function: "${METRIC_FORWARDING_FUNCTION}"
    scheduler: "${CLOUD_SCHEDULER}"
activation:
  metrics:
    services:
    # Google Cloud APIs
    #- api/default_metrics
    # Google Apigee Environment
    #- apigee_googleapis_com_Environment/default_metrics
    # Google Apigee Proxy
    #- apigee_googleapis_com_Proxy/default_metrics
    # Google Apigee Proxy (v2)
    #- apigee_googleapis_com_ProxyV2/default_metrics
    # Google Assistant Action Project
    #- assistant_action_project/default_metrics
    # Google Autoscaler
    - autoscaler/default_metrics
    # Google Cloud BigQuery BI Engine Model
    #- bigquery_biengine_model/default_metrics
    # Google Cloud BigQuery Project
    #- bigquery_project/default_metrics
    # Google Cloud Bigtable Cluster
    #- bigtable_cluster/default_metrics
    # Google Cloud Bigtable Table
    #- bigtable_table/default_metrics
    # Google Cloud IoT Registry
    #- cloudiot_device_registry/default_metrics
    # Google Cloud ML Job
    #- cloudml_job/default_metrics
    # Google Cloud ML Model Version
    #- cloudml_model_version/default_metrics
    #Cloud SQL Database
    - cloudsql_database/default_metrics
    # Google Cloud Trace
    #- cloudtrace_googleapis_com_CloudtraceProject/default_metrics
    # Google NetApp CVS-SO
    #- cloudvolumesgcp_api_netapp_com_NetAppCloudVolumeSO/default_metrics
    # Google Cloud Composer Environment
    #- cloud_composer_environment/default_metrics
    # Google Cloud Dataproc Cluster
    #- cloud_dataproc_cluster/default_metrics
    # Google Cloud Data Loss Prevention Project
    #- cloud_dlp_project/default_metrics
    # Google Cloud Function
    - cloud_function/default_metrics
    # Google Cloud Run Revision
    - cloud_run_revision/default_metrics
    #Amazon EC2 Instance (via GCP)
    - cloud_tasks_queue/default_metrics
    # Google Consumer Quota
    #- consumer_quota/default_metrics
    # Google Dataflow Job
    #- dataflow_job/default_metrics
    # Google Cloud Datastore
    - datastore_request/default_metrics
    # Google Cloud DNS Query
    - dns_query/default_metrics
    # Google Filestore Instance
    - filestore_instance/default_metrics
    # Google Firebase Hosting Site Domain
    #- firebase_domain/default_metrics
    # Google Firebase Realtime Database
    #- firebase_namespace/default_metrics
    # Google Firestore Instance
    #- firestore_instance/default_metrics
    # Google App Engine Application
    - gae_app/default_metrics
    # Google App Engine Application - Uptime Checks
    #- gae_app_uptime_check/default_metrics
    # Google App Engine Instance
    - gae_instance/default_metrics
    # Google VM Instance
    - gce_instance/default_metrics
    # Google VM Instance Agent
    - gce_instance/agent
    # Google VM Instance Firewall Insights
    - gce_instance/firewallinsights
    # Google VM Instance Istio
    - gce_instance/istio
    # Google VM Instance Uptime Checks
    - gce_instance/uptime_check
    # Google VM Instance VM Flow
    - gce_instance_vm_flow/default_metrics
    # Google Cloud Router
    #- gce_router/default_metrics
    # Google Zone Network Health
    - gce_zone_network_health/default_metrics
    # Google Cloud Storage bucket
    - gcs_bucket/default_metrics
    # Google Cloud HTTP/S Load Balancing Rule
    - https_lb_rule/default_metrics
    # Google Instance Group
    - instance_group/default_metrics
    # Google Interconnect
    #- interconnect/default_metrics
    # Google Internal HTTP/S Load Balancing Rule
    - internal_http_lb_rule/default_metrics
    # Google Internal Network Load Balancer
    - internal_network_lb_rule/default_metrics
    # Google Network Load Balancer
    - network_lb_rule/default_metrics
    # Google Kubernetes Cluster
    - k8s/default_metrics
    # Google Kubernetes Container
    - k8s_container/default_metrics
    # Google Kubernetes Container Agent
    - k8s_container/agent
    # Google Kubernetes Container Apigee
    - k8s_container/apigee
    # Google Kubernetes Container Istio
    - k8s_container/istio
    # Google Kubernetes Container Nginx
    - k8s_container/nginx
    # Google Kubernetes Pod
    - k8s_pod/istio
    # Google Cloud Logging export sink
    #- logging_sink/default_metrics
    # Google Cloud Microsoft Active Directory Domain
    #- microsoft_ad_domain/default_metrics
    # Google Cloud NAT Gateway
    - nat_gateway/default_metrics
    # Google NetApp Cloud Volume
    #- netapp_cloud_volume/default_metrics
    # Google Network Security Policy
    #- network_security_policy/default_metrics
    # Google Producer Quota
    #- producer_quota/default_metrics
    # Google Pub/Sub Lite Topic Partition
    - pubsublite_topic_partition/default_metrics
    # Google Cloud Pub/Sub Snapshot
    - pubsub_snapshot/default_metrics
    # Google Cloud Pub/Sub Subscription
    - pubsub_subscription/default_metrics
    # Google Cloud Pub/Sub Topic
    - pubsub_topic/default_metrics
    # Google reCAPTCHA Key
    #- recaptchaenterprise_googleapis_com_Key/default_metrics
    # Google Cloud Memorystore
    - redis_instance/default_metrics
    # Google Cloud Spanner Instance
    - spanner_instance/default_metrics
    # Google Cloud TCP/SSL Proxy Rule
    - tcp_ssl_proxy_rule/default_metrics
    # Google Cloud TPU Worker
    - tpu_worker/default_metrics
    # Google Transfer Service Agent
    #- transfer_service_agent/default_metrics
    # Google Uptime Check URL
    #- uptime_url/default_metrics
    # Google VPC Access Connector
    #- vpc_access_connector/default_metrics
    # Google Cloud VPN Tunnel
    #- vpn_gateway/default_metrics
EOF
yq eval-all --inplace 'select(fileIndex == 0) * select(fileIndex == 1)' activation-config.yaml activation.config.release.yaml

echo "Deploying gcp cloud function"
echo -e "$GCP_PROJECT_ID\ns\n$DYNATRACE_URL\n$DYNATRACE_ACCESS_KEY" | ./setup.sh --auto-default
