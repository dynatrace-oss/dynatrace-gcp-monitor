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
cd release/ || exit

wget -q "https://github.com/dynatrace-oss/dynatrace-gcp-function/releases/download/${TRAVIS_TAG}/function-deployment-package.zip" -O function-deployment-package.zip; unzip function-deployment-package.zip; chmod a+x *.sh;

cat <<EOF > activation.config.release.yaml
googleCloud:
  required:
    gcpProjectId: "${GCP_PROJECT_ID}"
    dynatraceTenantUrl: "${DYNATRACE_URL}"
    dynatraceApiToken: "${DYNATRACE_ACCESS_KEY}"
    cloudFunctionSize: s
    cloudFunctionRegion: us-central1
    preferredAppEngineRegion: us-central
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
activation: |
  services:
    - service: autoscaler
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloudsql_database
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloud_function
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloud_run_revision
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: cloud_tasks_queue
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: datastore_request
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: dns_query
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: filestore_instance
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: gae_app
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: gae_instance
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: gce_instance
      featureSets:
        - default_metrics
        - agent
        - firewallinsights
        - istio
        - uptime_check
      vars:
        filter_conditions: ""
    - service: gce_instance_vm_flow
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: gce_zone_network_health
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: gcs_bucket
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: https_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: instance_group
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: internal_http_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: internal_tcp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: internal_udp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: tcp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: udp_lb_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_cluster
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_container
      featureSets:
        - default_metrics
        - agent
        - apigee
        - istio
        - nginx
      vars:
        filter_conditions: ""
    - service: k8s_node
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: k8s_pod
      featureSets:
        - default_metrics
        - istio
      vars:
        filter_conditions: ""
    - service: nat_gateway
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsublite_topic_partition
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsub_snapshot
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsub_subscription
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: pubsub_topic
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: redis_instance
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: spanner_instance
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: tcp_ssl_proxy_rule
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""
    - service: tpu_worker
      featureSets:
        - default_metrics
      vars:
        filter_conditions: ""

EOF
ext_tools/yq_linux_x64 eval-all --inplace 'select(fileIndex == 0) * select(fileIndex == 1)' activation-config.yaml activation.config.release.yaml

echo "Deploying gcp cloud function"
./setup.sh --auto-default
